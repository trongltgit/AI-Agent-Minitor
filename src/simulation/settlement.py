"""
Simulated Settlement engine (temporary mock).
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
import random
import uuid


class SettlementSimulator:
    def __init__(self):
        self.records: List[Dict[str, Any]] = []

    def settle_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate settlement for a single trade/action."""
        delay_hours = random.choice([0, 1, 2, 24, 48])
        status = random.choices(
            ["SETTLED", "PENDING", "FAILED"],
            weights=[0.75, 0.18, 0.07],
        )[0]

        record = {
            "settlement_id": f"SET-{uuid.uuid4().hex[:10].upper()}",
            "trade_ref": trade.get("id") or trade.get("trade_id") or "N/A",
            "agent_id": trade.get("agent_id"),
            "principal_id": trade.get("principal_id"),
            "action_type": trade.get("action_type"),
            "pair": trade.get("pair"),
            "notional_usd": trade.get("notional_usd"),
            "settlement_amount_usd": trade.get("notional_usd"),
            "status": status,
            "method": random.choice(["SWIFT", "INTERNAL", "BLOCKCHAIN_SIM"]),
            "created_at": datetime.utcnow().isoformat(),
            "settled_at": (datetime.utcnow() + timedelta(hours=delay_hours)).isoformat() if status == "SETTLED" else None,
            "note": "Simulated settlement",
        }
        self.records.append(record)
        return record

    def list_settlements(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self.records[-limit:]))

    def stats(self) -> Dict[str, Any]:
        total = len(self.records)
        by_status = {}
        for r in self.records:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        return {"total": total, "by_status": by_status}


# Global simulator instance
settlement_engine = SettlementSimulator()
