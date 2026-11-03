import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any


def engineer_features(df: pd.DataFrame, customer_profiles: Dict[str, Dict] = None) -> Tuple[pd.DataFrame, List[str]]:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    
    df["notional_log"] = np.log1p(df["notional_usd"].fillna(0))
    df = df.sort_values(["agent_id", "timestamp"])
    
    df["rolling_notional_mean"] = df.groupby("agent_id")["notional_usd"].transform(
        lambda x: x.rolling(30, min_periods=2).mean()
    )
    df["rolling_notional_std"] = df.groupby("agent_id")["notional_usd"].transform(
        lambda x: x.rolling(30, min_periods=2).std()
    )
    df["notional_zscore"] = (df["notional_usd"] - df["rolling_notional_mean"]) / (df["rolling_notional_std"] + 1e-6)
    
    # Velocity (anti-bot)
    df["actions_last_5m"] = df.groupby("agent_id")["timestamp"].transform(
        lambda x: x.diff().dt.total_seconds().lt(300).rolling(20, min_periods=1).sum()
    )
    df["actions_last_1h"] = df.groupby("agent_id")["timestamp"].transform(
        lambda x: x.diff().dt.total_seconds().lt(3600).rolling(40, min_periods=1).sum()
    )
    
    df["hour"] = df["hour"].fillna(df["timestamp"].dt.hour).fillna(12).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["is_off_hour"] = df["hour"].isin([0, 1, 2, 3, 4, 5, 22, 23]).astype(int)
    
    df["is_forex"] = (df["action_type"] == "FOREX_TRADE").astype(int)
    df["is_payment"] = (df["action_type"] == "PAYMENT").astype(int)
    
    df["leverage_filled"] = df["leverage"].fillna(0.0)
    df["high_leverage_flag"] = (df["leverage_filled"] > 25).astype(int)
    df["extreme_leverage_flag"] = (df["leverage_filled"] > 50).astype(int)
    df["large_notional_flag"] = (df["notional_usd"] > 400_000).astype(int)
    df["very_large_notional_flag"] = (df["notional_usd"] > 1_500_000).astype(int)
    
    df["behavior_deviation"] = 0.0
    df["notional_vs_customer_avg"] = 0.0
    df["leverage_vs_customer_avg"] = 0.0
    
    if customer_profiles:
        for idx, row in df.iterrows():
            pid = row.get("principal_id")
            if pid and pid in customer_profiles:
                prof = customer_profiles[pid]
                avg_n = prof.get("avg_notional") or 1
                avg_l = prof.get("avg_leverage") or 1
                df.at[idx, "notional_vs_customer_avg"] = row["notional_usd"] / (avg_n + 1e-6)
                df.at[idx, "leverage_vs_customer_avg"] = (row.get("leverage") or 0) / (avg_l + 1e-6)
                
                dev = 0.0
                if row["notional_usd"] > avg_n * 3:
                    dev += 0.4
                if (row.get("leverage") or 0) > avg_l * 2.5:
                    dev += 0.3
                typical = prof.get("typical_hours") or list(range(24))
                if row["hour"] not in typical:
                    dev += 0.2
                df.at[idx, "behavior_deviation"] = min(dev, 1.0)
    
    feature_cols = [
        "notional_log", "notional_zscore",
        "actions_last_5m", "actions_last_1h",
        "hour_sin", "hour_cos", "is_off_hour",
        "is_forex", "is_payment",
        "leverage_filled", "high_leverage_flag", "extreme_leverage_flag",
        "large_notional_flag", "very_large_notional_flag",
        "behavior_deviation", "notional_vs_customer_avg", "leverage_vs_customer_avg"
    ]
    
    df[feature_cols] = df[feature_cols].fillna(0)
    return df, feature_cols


def compute_anti_bot_score(action: Dict[str, Any], recent_actions_count: int, trades_last_hour: int) -> float:
    score = 0.0
    notional = action.get("notional_usd", 0)
    leverage = action.get("leverage") or 0
    hour = action.get("hour", 12)
    
    if trades_last_hour >= 25:
        score += 0.45
    elif trades_last_hour >= 15:
        score += 0.25
    
    if notional > 1_000_000 and trades_last_hour >= 8:
        score += 0.30
    
    if hour in [0, 1, 2, 3, 4, 5] and notional > 300_000:
        score += 0.25
    
    if leverage > 60:
        score += 0.35
    elif leverage > 40:
        score += 0.20
    
    return min(score, 1.0)
