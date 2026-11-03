"""
LLM Critic component.
Supports: mock | openai | groq
"""

from typing import Dict, Any
import os
import json
import httpx


class LLMCritic:
    def __init__(self, provider: str = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
        self.api_key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        
        if self.provider == "groq":
            self.base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
            self.model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        else:
            self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    def critique(self, action: Dict[str, Any], anomaly_score: float, decision: str) -> Dict[str, Any]:
        if self.provider == "mock" or not self.api_key:
            return self._mock_critique(action, anomaly_score, decision)
        return self._real_llm_critique(action, anomaly_score, decision)
    
    def _mock_critique(self, action: Dict, anomaly_score: float, decision: str) -> Dict:
        reasons = []
        risk = anomaly_score
        
        leverage = action.get("leverage") or 0
        notional = action.get("notional_usd", 0)
        hour = action.get("hour", 12)
        action_type = action.get("action_type", "")
        
        if leverage > 40:
            risk = max(risk, 0.85)
            reasons.append(f"Extremely high leverage ({leverage}x)")
        elif leverage > 25:
            risk = max(risk, 0.65)
            reasons.append(f"Elevated leverage ({leverage}x)")
        
        if notional > 5_000_000:
            risk = max(risk, 0.80)
            reasons.append(f"Very large notional (${notional:,.0f})")
        elif notional > 1_500_000:
            risk = max(risk, 0.55)
            reasons.append(f"Large notional (${notional:,.0f})")
        
        if hour in [0, 1, 2, 3, 4, 22, 23] and notional > 300_000:
            risk = max(risk, 0.70)
            reasons.append("Large activity during off-market hours")
        
        if action_type == "PAYMENT" and notional > 2_000_000:
            risk = max(risk, 0.75)
            reasons.append("High-value payment requires extra scrutiny")
        
        if not reasons:
            reasons.append("Activity appears within expected behavioral envelope")
        
        if risk >= 0.75:
            recommendation = "BLOCK"
        elif risk >= 0.45:
            recommendation = "REVIEW"
        else:
            recommendation = "ALLOW"
        
        explanation = (
            f"LLM Critic analysis for {action.get('agent_id')} ({action_type}): "
            + "; ".join(reasons)
            + f". Combined risk score: {risk:.2f}."
        )
        
        return {
            "llm_risk_score": round(risk, 4),
            "llm_explanation": explanation,
            "llm_recommendation": recommendation
        }
    
    def _real_llm_critique(self, action: Dict, anomaly_score: float, decision: str) -> Dict:
        prompt = f"""
You are a risk critic for AI agents operating in forex trading and payments.

Analyze this agent action and provide a risk assessment.

Action details:
{json.dumps(action, indent=2, default=str)}

ML Anomaly Score: {anomaly_score:.4f}
Initial Decision: {decision}

Respond ONLY with valid JSON in this exact format:
{{
  "llm_risk_score": <float 0 to 1>,
  "llm_explanation": "<concise explanation>",
  "llm_recommendation": "ALLOW" or "REVIEW" or "BLOCK"
}}
"""
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a precise financial risk critic. Output only valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                    }
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                content = content.strip().removeprefix("```json").removesuffix("```").strip()
                return json.loads(content)
        except Exception as e:
            result = self._mock_critique(action, anomaly_score, decision)
            result["llm_explanation"] += f" [LLM call failed: {str(e)[:80]}]"
            return result
