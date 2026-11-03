"""
Simulated AI Agents for testing KYA + limits + anti-bot.
"""
from typing import List, Dict, Any
import random

# Predefined test agents with different risk profiles
SIMULATED_AGENTS: List[Dict[str, Any]] = [
    {
        "agent_id": "agent_safe_001",
        "principal_id": "principal_retail_01",
        "agent_type": "trading",
        "name": "Safe Retail Bot",
        "max_notional_per_trade": 50_000,
        "max_notional_daily": 200_000,
        "max_leverage": 5.0,
        "max_trades_per_hour": 10,
        "allowed_pairs": ["EURUSD", "GBPUSD", "USDJPY"],
        "risk_tier": "CONSERVATIVE",
        "description": "Agent an toan - luon trong han muc",
        "behavior": "safe",
    },
    {
        "agent_id": "agent_normal_002",
        "principal_id": "principal_retail_02",
        "agent_type": "trading",
        "name": "Normal Active Bot",
        "max_notional_per_trade": 200_000,
        "max_notional_daily": 1_000_000,
        "max_leverage": 15.0,
        "max_trades_per_hour": 25,
        "allowed_pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"],
        "risk_tier": "STANDARD",
        "description": "Agent binh thuong - thinh thoang gan han muc",
        "behavior": "normal",
    },
    {
        "agent_id": "agent_aggressive_003",
        "principal_id": "principal_pro_01",
        "agent_type": "trading",
        "name": "Aggressive Pro Bot",
        "max_notional_per_trade": 500_000,
        "max_notional_daily": 3_000_000,
        "max_leverage": 30.0,
        "max_trades_per_hour": 40,
        "allowed_pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURGBP"],
        "risk_tier": "AGGRESSIVE",
        "description": "Agent manh - thuong vuot soft limit",
        "behavior": "aggressive",
    },
    {
        "agent_id": "agent_rogue_004",
        "principal_id": "principal_unknown_99",
        "agent_type": "hybrid",
        "name": "Rogue Test Bot",
        "max_notional_per_trade": 100_000,
        "max_notional_daily": 300_000,
        "max_leverage": 10.0,
        "max_trades_per_hour": 15,
        "allowed_pairs": ["EURUSD", "GBPUSD"],
        "risk_tier": "RESTRICTED",
        "description": "Agent de test BLOCK - co y vuot han muc",
        "behavior": "rogue",
    },
    {
        "agent_id": "agent_payment_005",
        "principal_id": "principal_corp_01",
        "agent_type": "payment",
        "name": "Corporate Payment Agent",
        "max_notional_per_trade": 1_000_000,
        "max_notional_daily": 5_000_000,
        "max_leverage": 1.0,
        "max_trades_per_hour": 20,
        "allowed_pairs": [],
        "risk_tier": "CORPORATE",
        "description": "Agent thanh toan doanh nghiep",
        "behavior": "payment",
    },
]


def get_agent(agent_id: str) -> Dict[str, Any] | None:
    for a in SIMULATED_AGENTS:
        if a["agent_id"] == agent_id:
            return a
    return None


def list_agents() -> List[Dict[str, Any]]:
    return SIMULATED_AGENTS


def generate_test_action(agent_id: str, force_over_limit: bool = False) -> Dict[str, Any]:
    """Generate a realistic test action for an agent (within or over limit)."""
    agent = get_agent(agent_id)
    if not agent:
        agent = SIMULATED_AGENTS[1]  # fallback normal

    behavior = agent.get("behavior", "normal")
    is_payment = agent["agent_type"] == "payment"

    if force_over_limit or behavior == "rogue":
        # Intentionally over limit
        notional = agent["max_notional_per_trade"] * random.uniform(1.5, 4.0)
        leverage = agent["max_leverage"] * random.uniform(1.3, 2.5) if not is_payment else None
        hour = random.choice([1, 2, 3, 4, 23])
    elif behavior == "safe":
        notional = agent["max_notional_per_trade"] * random.uniform(0.1, 0.5)
        leverage = agent["max_leverage"] * random.uniform(0.2, 0.6) if not is_payment else None
        hour = random.randint(9, 17)
    elif behavior == "aggressive":
        notional = agent["max_notional_per_trade"] * random.uniform(0.7, 1.15)
        leverage = agent["max_leverage"] * random.uniform(0.7, 1.1) if not is_payment else None
        hour = random.randint(7, 22)
    else:  # normal / payment
        notional = agent["max_notional_per_trade"] * random.uniform(0.3, 0.85)
        leverage = agent["max_leverage"] * random.uniform(0.3, 0.8) if not is_payment else None
        hour = random.randint(8, 20)

    pair = None
    side = None
    if not is_payment and agent["allowed_pairs"]:
        pair = random.choice(agent["allowed_pairs"])
        side = random.choice(["BUY", "SELL"])

    return {
        "agent_id": agent["agent_id"],
        "principal_id": agent["principal_id"],
        "action_type": "PAYMENT" if is_payment else "FOREX_TRADE",
        "pair": pair,
        "side": side,
        "notional_usd": round(notional, 2),
        "leverage": round(leverage, 2) if leverage else None,
        "hour": hour,
        "meta": {
            "simulated": True,
            "behavior": behavior,
            "force_over_limit": force_over_limit,
            "agent_name": agent["name"],
        },
    }
