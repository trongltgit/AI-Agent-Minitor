from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
import os

from src.database import init_db, get_db, AgentRegistry, AgentAction, CustomerProfile
from src.monitor_service import AgentMonitorService

init_db()
monitor_service = AgentMonitorService()

app = FastAPI(
    title="AI Agent Monitor API v2 - KYA + Anti-Bot + Customer Behavior",
    description="Strict broker limits + Customer trading tendency + Anti-bot velocity detection",
    version="2.0.0"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Web UI
try:
    from src.web import router as web_router
    app.include_router(web_router)
except Exception as e:
    print(f"Web UI not loaded: {e}")



class ActionRequest(BaseModel):
    agent_id: str
    principal_id: Optional[str] = None
    action_type: str
    pair: Optional[str] = None
    side: Optional[str] = None
    notional_usd: float
    leverage: Optional[float] = None
    hour: Optional[int] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentCreate(BaseModel):
    agent_id: str
    principal_id: str
    agent_type: str = "hybrid"
    max_notional_per_trade: float = 500_000
    max_notional_daily: float = 2_000_000
    max_leverage: float = 20.0
    max_trades_per_hour: int = 30
    max_trades_per_day: int = 200
    allowed_pairs: List[str] = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    allowed_action_types: List[str] = ["FOREX_TRADE", "PAYMENT"]
    require_human_approval_above: float = 300_000
    risk_tier: str = "STANDARD"
    notes: Optional[str] = None


class CustomerProfileCreate(BaseModel):
    principal_id: str
    avg_notional: float = 50000
    avg_leverage: float = 5.0
    preferred_pairs: List[str] = ["EURUSD", "GBPUSD"]
    typical_hours: List[int] = list(range(8, 20))
    avg_trades_per_day: float = 8
    aggressiveness_score: float = 0.4


@app.get("/api")
def api_info():
    return {
        "service": "AI Agent Monitor v2",
        "features": ["Strict Broker Limits", "Customer Behavior Profiling", "Anti-Bot Velocity", "KYA", "LLM Critic"],
        "docs": "/docs",
        "web": "/"
    }


@app.post("/monitor/action")
def monitor_action(action: ActionRequest, use_llm: bool = True, db: Session = Depends(get_db)):
    payload = action.dict()
    if not payload.get("timestamp"):
        payload["timestamp"] = datetime.utcnow().isoformat()
    if payload.get("hour") is None:
        payload["hour"] = datetime.utcnow().hour
    return monitor_service.score_action(payload, db, use_llm=use_llm)


@app.get("/actions/recent")
def get_recent_actions(limit: int = 100, db: Session = Depends(get_db)):
    records = db.query(AgentAction).order_by(AgentAction.timestamp.desc()).limit(limit).all()
    return [{
        "id": r.id, "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "agent_id": r.agent_id, "principal_id": r.principal_id, "action_type": r.action_type,
        "pair": r.pair, "notional_usd": r.notional_usd, "leverage": r.leverage,
        "anomaly_score": r.anomaly_score, "behavior_deviation_score": r.behavior_deviation_score,
        "anti_bot_score": r.anti_bot_score, "final_risk_score": r.final_risk_score,
        "risk_level": r.risk_level, "decision": r.decision, "reason": r.reason,
        "trades_last_hour": r.trades_last_hour, "llm_recommendation": r.llm_recommendation,
    } for r in records]


@app.get("/actions/stats")
def get_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total = db.query(func.count(AgentAction.id)).scalar() or 0
    by_decision = dict(db.query(AgentAction.decision, func.count(AgentAction.id)).group_by(AgentAction.decision).all())
    by_risk = dict(db.query(AgentAction.risk_level, func.count(AgentAction.id)).group_by(AgentAction.risk_level).all())
    high_risk = db.query(func.count(AgentAction.id)).filter(AgentAction.risk_level == "HIGH").scalar() or 0
    return {"total_actions": total, "by_decision": by_decision, "by_risk_level": by_risk,
            "high_risk_count": high_risk, "block_rate": round(by_decision.get("BLOCK", 0) / total, 4) if total else 0}


@app.post("/agents/register")
def register_agent(agent: AgentCreate, db: Session = Depends(get_db)):
    if db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent.agent_id).first():
        raise HTTPException(status_code=400, detail="Agent already registered")
    record = AgentRegistry(**agent.dict())
    db.add(record)
    db.commit()
    return {"status": "registered", "agent_id": agent.agent_id}


@app.get("/agents")
def list_agents(db: Session = Depends(get_db)):
    return [{
        "agent_id": a.agent_id, "principal_id": a.principal_id, "agent_type": a.agent_type,
        "max_notional_per_trade": a.max_notional_per_trade, "max_notional_daily": a.max_notional_daily,
        "max_leverage": a.max_leverage, "max_trades_per_hour": a.max_trades_per_hour,
        "risk_tier": a.risk_tier, "is_active": a.is_active
    } for a in db.query(AgentRegistry).all()]


@app.post("/customers/profile")
def create_customer_profile(profile: CustomerProfileCreate, db: Session = Depends(get_db)):
    existing = db.query(CustomerProfile).filter(CustomerProfile.principal_id == profile.principal_id).first()
    if existing:
        for k, v in profile.dict().items():
            setattr(existing, k, v)
        db.commit()
        return {"status": "updated", "principal_id": profile.principal_id}
    db.add(CustomerProfile(**profile.dict()))
    db.commit()
    return {"status": "created", "principal_id": profile.principal_id}


@app.get("/customers")
def list_customers(db: Session = Depends(get_db)):
    return [{
        "principal_id": p.principal_id, "avg_notional": p.avg_notional, "avg_leverage": p.avg_leverage,
        "aggressiveness_score": p.aggressiveness_score, "suspicion_score": p.suspicion_score,
        "is_watchlist": p.is_watchlist
    } for p in db.query(CustomerProfile).all()]


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0", "timestamp": datetime.utcnow().isoformat()}
