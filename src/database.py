from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/agent_monitor.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class AgentRegistry(Base):
    __tablename__ = "agent_registry"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(64), unique=True, index=True, nullable=False)
    principal_id = Column(String(64), index=True)
    agent_type = Column(String(32), default="hybrid")
    
    max_notional_per_trade = Column(Float, default=500_000)
    max_notional_daily = Column(Float, default=2_000_000)
    max_leverage = Column(Float, default=20.0)
    max_trades_per_hour = Column(Integer, default=30)
    max_trades_per_day = Column(Integer, default=200)
    allowed_pairs = Column(JSON, default=list)
    allowed_action_types = Column(JSON, default=list)
    
    max_drawdown_pct = Column(Float, default=10.0)
    require_human_approval_above = Column(Float, default=300_000)
    
    is_active = Column(Boolean, default=True)
    risk_tier = Column(String(16), default="STANDARD")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    principal_id = Column(String(64), unique=True, index=True, nullable=False)
    
    avg_notional = Column(Float, default=0)
    std_notional = Column(Float, default=0)
    avg_leverage = Column(Float, default=0)
    preferred_pairs = Column(JSON, default=list)
    typical_hours = Column(JSON, default=list)
    avg_trades_per_day = Column(Float, default=0)
    max_historical_notional = Column(Float, default=0)
    
    aggressiveness_score = Column(Float, default=0.5)
    consistency_score = Column(Float, default=0.5)
    
    is_watchlist = Column(Boolean, default=False)
    suspicion_score = Column(Float, default=0.0)
    last_suspicious_at = Column(DateTime, nullable=True)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    agent_id = Column(String(64), index=True, nullable=False)
    principal_id = Column(String(64), index=True)
    action_type = Column(String(32), index=True)
    pair = Column(String(16), nullable=True)
    side = Column(String(8), nullable=True)
    notional_usd = Column(Float, nullable=False)
    leverage = Column(Float, nullable=True)
    hour = Column(Integer)
    
    anomaly_score = Column(Float)
    behavior_deviation_score = Column(Float)
    anti_bot_score = Column(Float)
    final_risk_score = Column(Float)
    
    risk_level = Column(String(16))
    decision = Column(String(16))
    reason = Column(Text)
    
    llm_risk_score = Column(Float, nullable=True)
    llm_explanation = Column(Text, nullable=True)
    llm_recommendation = Column(String(32), nullable=True)
    
    daily_notional_so_far = Column(Float, nullable=True)
    trades_last_hour = Column(Integer, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_agent_ts", "agent_id", "timestamp"),
        Index("ix_principal_ts", "principal_id", "timestamp"),
    )


def init_db():
    """Create tables. On SQLite, drop old tables if schema is outdated."""
    os.makedirs("data", exist_ok=True)
    
    if "sqlite" in DATABASE_URL:
        try:
            with engine.connect() as conn:
                # Check if old schema (missing new columns)
                result = conn.execute(text("PRAGMA table_info(agent_actions)"))
                columns = [row[1] for row in result]
                if columns and "behavior_deviation_score" not in columns:
                    print("Old schema detected → recreating tables...")
                    Base.metadata.drop_all(bind=engine)
        except Exception as e:
            print(f"Schema check: {e}")
    
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
