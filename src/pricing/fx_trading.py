"""
FX Trading flow: Quote → (KYA Monitor) → Execute → Settlement
Bảo vệ bởi Anti-Bot + role-based final price + quote single-use.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from datetime import datetime
import uuid

from src.pricing.engine import pricing_engine, QuoteResult
from src.pricing.quote_store import quote_store
from src.simulation.settlement import settlement_engine


def create_fx_quote(
    currency: str,
    side: str,
    amount: float,
    role: str = "KH",
    cif: str | None = None,
    principal_id: str | None = None,
    agent_id: str | None = None,
    branch_margin: float | None = None,
    owner_key: str = "anonymous",
) -> Dict[str, Any]:
    """Tạo quote, lưu single-use, trả response theo role."""
    q = pricing_engine.create_quote(
        currency=currency,
        side=side,
        amount=amount,
        role=role,
        cif=cif,
        principal_id=principal_id,
        agent_id=agent_id,
        branch_margin=branch_margin,
    )
    # Lưu full internal để execute sau
    internal = {
        "quote_id": q.quote_id,
        "currency": q.currency,
        "side": q.side,
        "amount": q.amount,
        "price": q.price,
        "valid_until": q.valid_until,
        "agent_id": agent_id,
        "principal_id": principal_id,
        "cif": cif,
        "role": role,
        "_base_rate": q._base_rate,
        "_hq_spread": q._hq_spread,
        "_branch_margin": q._branch_margin,
    }
    quote_store.put(q.quote_id, internal, owner=owner_key)
    return pricing_engine.to_response(q, role)


def execute_fx_trade(
    quote_id: str,
    owner_key: str,
    monitor_decision: str | None = None,
) -> Dict[str, Any]:
    """
    Execute quote (single-use).
    monitor_decision: kết quả từ AI Agent Monitor (ALLOW/REVIEW/BLOCK).
    Nếu BLOCK → từ chối. REVIEW có thể cho qua hoặc giữ tùy policy.
    """
    if monitor_decision == "BLOCK":
        return {
            "status": "REJECTED",
            "reason": "AI Agent Monitor BLOCKED this action",
            "quote_id": quote_id,
        }

    payload = quote_store.claim(quote_id, owner_key)
    if payload is None:
        return {
            "status": "REJECTED",
            "reason": "Quote invalid, expired, already used, or wrong owner",
            "quote_id": quote_id,
        }

    trade_id = f"FX-{uuid.uuid4().hex[:10].upper()}"
    trade = {
        "trade_id": trade_id,
        "quote_id": quote_id,
        "currency": payload["currency"],
        "side": payload["side"],
        "amount": payload["amount"],
        "price": payload["price"],
        "notional_usd": payload["amount"],  # simplified
        "agent_id": payload.get("agent_id"),
        "principal_id": payload.get("principal_id"),
        "cif": payload.get("cif"),
        "status": "FILLED",
        "executed_at": datetime.utcnow().isoformat(),
        "monitor_decision": monitor_decision,
    }

    # Settlement giả lập
    settlement = settlement_engine.settle_trade({
        "id": trade_id,
        "agent_id": trade.get("agent_id"),
        "principal_id": trade.get("principal_id"),
        "action_type": "FOREX_TRADE",
        "pair": payload["currency"] + "VND" if payload["currency"] != "USD" else "USDVND",
        "notional_usd": payload["amount"],
    })

    return {
        "status": "FILLED",
        "trade": trade,
        "settlement": settlement,
    }
