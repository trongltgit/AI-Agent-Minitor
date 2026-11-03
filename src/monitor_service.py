import pandas as pd
import numpy as np
import joblib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.features import engineer_features, compute_anti_bot_score
from src.llm_critic import LLMCritic
from src.database import AgentAction, AgentRegistry, CustomerProfile
import os


class AgentMonitorService:
    def __init__(self, model_path: str = "models/isolation_forest.joblib"):
        self.model_path = model_path
        self.model = None
        self.feature_cols = None
        self.llm_critic = LLMCritic(provider=os.getenv("LLM_PROVIDER", "mock"))
        self._load_model()
    
    def _load_model(self):
        if os.path.exists(self.model_path):
            saved = joblib.load(self.model_path)
            self.model = saved["model"]
            self.feature_cols = saved["features"]
        else:
            from src.train import train_monitor
            self.model, self.feature_cols = train_monitor()
    
    def _get_customer_profile(self, principal_id: str, db: Session) -> Optional[Dict]:
        if not principal_id:
            return None
        prof = db.query(CustomerProfile).filter(CustomerProfile.principal_id == principal_id).first()
        if not prof:
            return None
        return {
            "avg_notional": prof.avg_notional,
            "std_notional": prof.std_notional,
            "avg_leverage": prof.avg_leverage,
            "preferred_pairs": prof.preferred_pairs or [],
            "typical_hours": prof.typical_hours or list(range(7, 22)),
            "avg_trades_per_day": prof.avg_trades_per_day,
            "max_historical_notional": prof.max_historical_notional,
            "aggressiveness_score": prof.aggressiveness_score,
            "is_watchlist": prof.is_watchlist,
            "suspicion_score": prof.suspicion_score,
        }
    
    def _get_recent_stats(self, agent_id: str, principal_id: str, db: Session) -> Dict:
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        trades_last_hour = db.query(func.count(AgentAction.id)).filter(
            AgentAction.agent_id == agent_id,
            AgentAction.timestamp >= one_hour_ago
        ).scalar() or 0
        
        daily_notional = db.query(func.coalesce(func.sum(AgentAction.notional_usd), 0)).filter(
            AgentAction.agent_id == agent_id,
            AgentAction.timestamp >= today_start,
            AgentAction.decision != "BLOCK"
        ).scalar() or 0
        
        daily_trades = db.query(func.count(AgentAction.id)).filter(
            AgentAction.agent_id == agent_id,
            AgentAction.timestamp >= today_start
        ).scalar() or 0
        
        return {
            "trades_last_hour": int(trades_last_hour),
            "daily_notional_so_far": float(daily_notional),
            "daily_trades": int(daily_trades)
        }
    
    def check_hard_policy(self, action: Dict, registry: Optional[AgentRegistry], stats: Dict) -> Optional[str]:
        if registry is None:
            return "Agent not registered in broker registry"
        if not registry.is_active:
            return "Agent is deactivated by broker"
        if registry.risk_tier == "RESTRICTED":
            return "Agent is in RESTRICTED risk tier"
        
        notional = action.get("notional_usd", 0)
        leverage = action.get("leverage") or 0
        
        if notional > registry.max_notional_per_trade:
            return f"Exceeds max notional per trade (${registry.max_notional_per_trade:,.0f})"
        if stats["daily_notional_so_far"] + notional > registry.max_notional_daily:
            return f"Would exceed daily notional limit (${registry.max_notional_daily:,.0f})"
        if leverage > registry.max_leverage:
            return f"Leverage {leverage}x exceeds broker limit {registry.max_leverage}x"
        if stats["trades_last_hour"] >= registry.max_trades_per_hour:
            return f"Exceeds max trades per hour ({registry.max_trades_per_hour})"
        if stats["daily_trades"] >= registry.max_trades_per_day:
            return f"Exceeds max trades per day ({registry.max_trades_per_day})"
        
        action_type = action.get("action_type")
        if registry.allowed_action_types and action_type not in registry.allowed_action_types:
            return f"Action type {action_type} not permitted"
        pair = action.get("pair")
        if pair and registry.allowed_pairs and pair not in registry.allowed_pairs:
            return f"Pair {pair} not in allowed list"
        return None
    
    def score_action(self, action: Dict[str, Any], db: Session, use_llm: bool = True) -> Dict[str, Any]:
        agent_id = action["agent_id"]
        principal_id = action.get("principal_id")
        
        registry = db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent_id).first()
        stats = self._get_recent_stats(agent_id, principal_id, db)
        customer_prof = self._get_customer_profile(principal_id, db)
        
        hard_reason = self.check_hard_policy(action, registry, stats)
        if hard_reason:
            result = {
                "timestamp": action.get("timestamp", datetime.utcnow().isoformat()),
                "agent_id": agent_id,
                "principal_id": principal_id,
                "action_type": action.get("action_type"),
                "notional_usd": action.get("notional_usd"),
                "anomaly_score": 1.0,
                "behavior_deviation_score": 0.0,
                "anti_bot_score": 0.0,
                "final_risk_score": 1.0,
                "risk_level": "HIGH",
                "decision": "BLOCK",
                "reason": f"HARD POLICY (Broker): {hard_reason}",
                "daily_notional_so_far": stats.get("daily_notional_so_far"),
                "trades_last_hour": stats.get("trades_last_hour"),
                "llm_risk_score": None,
                "llm_explanation": None,
                "llm_recommendation": "BLOCK"
            }
            self._persist(result, action, db)
            self._update_suspicion(principal_id, 0.3, db)
            return result
        
        profiles_dict = {principal_id: customer_prof} if customer_prof else {}
        df = pd.DataFrame([action])
        df, _ = engineer_features(df, profiles_dict)
        
        for col in self.feature_cols:
            if col not in df.columns:
                df[col] = 0.0
        X = df[self.feature_cols].fillna(0)
        
        pred = self.model.predict(X)[0]
        raw_score = -self.model.score_samples(X)[0]
        anomaly_score = float(np.clip(raw_score / 1.5, 0, 1.0))
        
        behavior_dev = float(df["behavior_deviation"].iloc[0]) if "behavior_deviation" in df.columns else 0.0
        anti_bot = compute_anti_bot_score(action, 0, stats["trades_last_hour"])
        
        final_risk = 0.40 * anomaly_score + 0.30 * behavior_dev + 0.30 * anti_bot
        if customer_prof and customer_prof.get("is_watchlist"):
            final_risk = min(final_risk + 0.15, 1.0)
        
        if final_risk >= 0.78 or (pred == -1 and final_risk > 0.55):
            decision, risk_level = "BLOCK", "HIGH"
        elif final_risk >= 0.48:
            decision, risk_level = "REVIEW", "MEDIUM"
        else:
            decision, risk_level = "ALLOW", "LOW"
        
        if registry and action.get("notional_usd", 0) >= registry.require_human_approval_above:
            if decision == "ALLOW":
                decision, risk_level = "REVIEW", "MEDIUM"
        
        reason_parts = []
        if anomaly_score > 0.45: reason_parts.append(f"anomaly={anomaly_score:.2f}")
        if behavior_dev > 0.3: reason_parts.append(f"behavior_dev={behavior_dev:.2f}")
        if anti_bot > 0.3: reason_parts.append(f"anti_bot={anti_bot:.2f}")
        if stats["trades_last_hour"] > 10: reason_parts.append(f"vel={stats['trades_last_hour']}/h")
        reason = "; ".join(reason_parts) if reason_parts else "within normal parameters"
        
        llm_result = {"llm_risk_score": None, "llm_explanation": None, "llm_recommendation": None}
        if use_llm:
            llm_result = self.llm_critic.critique(action, final_risk, decision)
            if llm_result.get("llm_recommendation") == "BLOCK" and decision != "BLOCK":
                decision = "REVIEW"
                risk_level = "HIGH"
                reason += " | LLM escalated"
        
        result = {
            "timestamp": action.get("timestamp", datetime.utcnow().isoformat()),
            "agent_id": agent_id,
            "principal_id": principal_id,
            "action_type": action.get("action_type"),
            "notional_usd": action.get("notional_usd"),
            "anomaly_score": round(anomaly_score, 4),
            "behavior_deviation_score": round(behavior_dev, 4),
            "anti_bot_score": round(anti_bot, 4),
            "final_risk_score": round(final_risk, 4),
            "risk_level": risk_level,
            "decision": decision,
            "reason": reason,
            "daily_notional_so_far": stats.get("daily_notional_so_far"),
            "trades_last_hour": stats.get("trades_last_hour"),
            **llm_result
        }
        
        self._persist(result, action, db)
        if decision in ["BLOCK", "REVIEW"]:
            self._update_suspicion(principal_id, 0.15 if decision == "REVIEW" else 0.35, db)
        return result
    
    def _persist(self, result: Dict, original_action: Dict, db: Session):
        ts = result["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", ""))
        record = AgentAction(
            timestamp=ts,
            agent_id=result["agent_id"],
            principal_id=result.get("principal_id"),
            action_type=result.get("action_type"),
            pair=original_action.get("pair"),
            side=original_action.get("side"),
            notional_usd=result.get("notional_usd") or 0,
            leverage=original_action.get("leverage"),
            hour=original_action.get("hour"),
            anomaly_score=result.get("anomaly_score"),
            behavior_deviation_score=result.get("behavior_deviation_score"),
            anti_bot_score=result.get("anti_bot_score"),
            final_risk_score=result.get("final_risk_score"),
            risk_level=result.get("risk_level"),
            decision=result.get("decision"),
            reason=result.get("reason"),
            llm_risk_score=result.get("llm_risk_score"),
            llm_explanation=result.get("llm_explanation"),
            llm_recommendation=result.get("llm_recommendation"),
            daily_notional_so_far=result.get("daily_notional_so_far"),
            trades_last_hour=result.get("trades_last_hour"),
            raw_payload=original_action
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        result["id"] = record.id
    
    def _update_suspicion(self, principal_id: str, delta: float, db: Session):
        if not principal_id:
            return
        prof = db.query(CustomerProfile).filter(CustomerProfile.principal_id == principal_id).first()
        if prof:
            prof.suspicion_score = min((prof.suspicion_score or 0) + delta, 1.0)
            prof.last_suspicious_at = datetime.utcnow()
            if prof.suspicion_score > 0.7:
                prof.is_watchlist = True
            db.commit()
