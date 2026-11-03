import pandas as pd
import numpy as np
import joblib
import os
from sklearn.ensemble import IsolationForest
from src.features import engineer_features
from datetime import datetime, timedelta


def generate_training_data(n_agents=12, n_actions=10000):
    np.random.seed(42)
    agents = [f"agent_{i:03d}" for i in range(1, n_agents+1)]
    principals = [f"principal_{i%5 + 1}" for i in range(n_agents)]
    rows = []
    start = datetime(2026, 8, 1)
    
    for i in range(n_actions):
        agent_idx = np.random.randint(0, n_agents)
        is_anomaly = np.random.rand() < 0.08
        action_type = np.random.choice(["FOREX_TRADE", "PAYMENT"], p=[0.65, 0.35])
        
        if action_type == "FOREX_TRADE":
            pair = np.random.choice(["EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD"])
            notional = np.random.lognormal(11.0, 0.7) if not is_anomaly else np.random.lognormal(13.8, 1.1)
            leverage = np.random.uniform(1, 18) if not is_anomaly else np.random.uniform(35, 85)
            side = np.random.choice(["BUY","SELL"])
        else:
            pair = side = None
            notional = np.random.lognormal(8.5, 0.9) if not is_anomaly else np.random.lognormal(12.2, 1.2)
            leverage = None
        
        hour = np.random.randint(0, 24)
        if is_anomaly and np.random.rand() < 0.5:
            hour = np.random.choice([1,2,3,4,22,23])
        
        ts = start + timedelta(minutes=int(np.random.randint(0, 60*24*50)))
        rows.append({
            "timestamp": ts, "agent_id": agents[agent_idx], "principal_id": principals[agent_idx],
            "action_type": action_type, "pair": pair, "side": side,
            "notional_usd": round(float(notional), 2),
            "leverage": round(float(leverage), 2) if leverage else None,
            "hour": hour
        })
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def train_monitor(save_path="models/isolation_forest.joblib"):
    os.makedirs("models", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    print("Generating training data...")
    df = generate_training_data()
    df.to_csv("data/training_logs.csv", index=False)
    print("Engineering features...")
    df, feature_cols = engineer_features(df)
    X = df[feature_cols]
    print("Training Isolation Forest...")
    model = IsolationForest(n_estimators=300, contamination=0.08, random_state=42, n_jobs=-1, max_samples=0.8)
    model.fit(X)
    joblib.dump({"model": model, "features": feature_cols}, save_path)
    print(f"Model saved to {save_path}")
    return model, feature_cols


if __name__ == "__main__":
    train_monitor()
