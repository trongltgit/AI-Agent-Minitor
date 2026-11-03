"""
Generate fictional FX trading history and settlement records for testing.
"""
import random
import csv
import io
from datetime import datetime, timedelta
from typing import List, Dict, Any
from src.simulation.agents import SIMULATED_AGENTS

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURGBP"]
SIDES = ["BUY", "SELL"]


def generate_fx_history(
    n_trades: int = 200,
    days_back: int = 30,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    random.seed(seed)
    start = datetime.utcnow() - timedelta(days=days_back)
    rows = []

    for i in range(n_trades):
        agent = random.choice(SIMULATED_AGENTS)
        if agent["agent_type"] == "payment":
            continue

        ts = start + timedelta(
            minutes=random.randint(0, days_back * 24 * 60)
        )
        pair = random.choice(agent["allowed_pairs"] or PAIRS)
        side = random.choice(SIDES)
        notional = round(random.uniform(5000, 400000), 2)
        # clamp roughly to agent profile
        notional = min(notional, agent["max_notional_per_trade"] * 1.2)
        leverage = round(random.uniform(1, agent["max_leverage"]), 2)
        rate = round(random.uniform(0.85, 1.35) if "USD" in pair else random.uniform(100, 160), 5)
        pnl = round(random.gauss(0, notional * 0.002), 2)

        rows.append({
            "trade_id": f"FX{100000 + i}",
            "timestamp": ts.isoformat(),
            "agent_id": agent["agent_id"],
            "principal_id": agent["principal_id"],
            "pair": pair,
            "side": side,
            "notional_usd": notional,
            "leverage": leverage,
            "rate": rate,
            "pnl_usd": pnl,
            "status": random.choice(["FILLED", "FILLED", "FILLED", "PARTIAL", "CANCELLED"]),
        })

    rows.sort(key=lambda x: x["timestamp"])
    return rows


def generate_settlement_history(
    fx_rows: List[Dict[str, Any]],
    seed: int = 42,
) -> List[Dict[str, Any]]:
    random.seed(seed + 1)
    settlements = []
    for i, trade in enumerate(fx_rows):
        if trade["status"] not in ("FILLED", "PARTIAL"):
            continue
        settle_ts = datetime.fromisoformat(trade["timestamp"]) + timedelta(hours=random.randint(1, 48))
        settlements.append({
            "settlement_id": f"SET{200000 + i}",
            "trade_id": trade["trade_id"],
            "timestamp": settle_ts.isoformat(),
            "agent_id": trade["agent_id"],
            "principal_id": trade["principal_id"],
            "pair": trade["pair"],
            "notional_usd": trade["notional_usd"],
            "settlement_amount_usd": round(trade["notional_usd"] + trade.get("pnl_usd", 0), 2),
            "status": random.choice(["SETTLED", "SETTLED", "PENDING", "FAILED"]),
            "method": random.choice(["SWIFT", "INTERNAL", "BLOCKCHAIN_SIM"]),
        })
    return settlements


def to_csv_string(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def generate_sample_files(output_dir: str = "data/samples"):
    import os
    os.makedirs(output_dir, exist_ok=True)
    fx = generate_fx_history(250)
    stl = generate_settlement_history(fx)

    fx_path = os.path.join(output_dir, "fx_history_sample.csv")
    stl_path = os.path.join(output_dir, "settlement_history_sample.csv")

    with open(fx_path, "w", newline="", encoding="utf-8") as f:
        f.write(to_csv_string(fx))
    with open(stl_path, "w", newline="", encoding="utf-8") as f:
        f.write(to_csv_string(stl))

    return fx_path, stl_path, len(fx), len(stl)
