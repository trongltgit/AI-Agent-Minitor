import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import os
import sys

# Add parent to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="AI Agent Monitor Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

API_URL = os.getenv("API_URL", "http://localhost:8000")


# ---------- Helpers ----------
@st.cache_data(ttl=15)
def fetch_recent_actions(limit=200):
    try:
        r = requests.get(f"{API_URL}/actions/recent", params={"limit": limit}, timeout=5)
        r.raise_for_status()
        return pd.DataFrame(r.json())
    except Exception as e:
        st.warning(f"Cannot reach API ({e}). Showing empty state.")
        return pd.DataFrame()


@st.cache_data(ttl=30)
def fetch_stats():
    try:
        r = requests.get(f"{API_URL}/actions/stats", timeout=5)
        r.raise_for_status()
        return r.json()
    except:
        return {}


@st.cache_data(ttl=60)
def fetch_agents():
    try:
        r = requests.get(f"{API_URL}/agents", timeout=5)
        r.raise_for_status()
        return pd.DataFrame(r.json())
    except:
        return pd.DataFrame()


def color_decision(val):
    if val == "BLOCK":
        return "background-color: #ff4d4d; color: white"
    elif val == "REVIEW":
        return "background-color: #ffa500; color: black"
    elif val == "ALLOW":
        return "background-color: #28a745; color: white"
    return ""


# ---------- Sidebar ----------
st.sidebar.title("🛡️ AI Agent Monitor")
st.sidebar.markdown("**KYA Monitoring System**")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["Overview", "Live Actions", "Agent Registry", "Submit Test Action", "System Info"]
)

st.sidebar.markdown("---")
st.sidebar.caption(f"API: {API_URL}")
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()


# ---------- Pages ----------

if page == "Overview":
    st.title("AI Agent Monitoring Dashboard")
    st.markdown("Real-time monitoring of AI agents in **Forex Trading** and **Payments** with KYA controls.")
    
    stats = fetch_stats()
    df = fetch_recent_actions(300)
    
    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    
    total = stats.get("total_actions", 0)
    high_risk = stats.get("high_risk_count", 0)
    by_decision = stats.get("by_decision", {})
    
    col1.metric("Total Actions Monitored", f"{total:,}")
    col2.metric("High Risk Actions", f"{high_risk:,}", delta=None)
    col3.metric("BLOCK decisions", by_decision.get("BLOCK", 0))
    col4.metric("REVIEW decisions", by_decision.get("REVIEW", 0))
    
    st.markdown("---")
    
    if not df.empty:
        # Decision distribution
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Decision Distribution")
            fig = px.pie(
                df, 
                names="decision", 
                title="ALLOW / REVIEW / BLOCK",
                color="decision",
                color_discrete_map={"ALLOW": "#28a745", "REVIEW": "#ffa500", "BLOCK": "#ff4d4d"}
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with c2:
            st.subheader("Risk Level Distribution")
            fig2 = px.pie(
                df,
                names="risk_level",
                title="Risk Levels",
                color="risk_level",
                color_discrete_map={"LOW": "#28a745", "MEDIUM": "#ffa500", "HIGH": "#ff4d4d"}
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        # Time series of anomaly scores
        st.subheader("Anomaly Score Over Time")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df_sorted = df.sort_values("timestamp")
            fig3 = px.scatter(
                df_sorted,
                x="timestamp",
                y="anomaly_score",
                color="decision",
                hover_data=["agent_id", "notional_usd", "action_type"],
                color_discrete_map={"ALLOW": "#28a745", "REVIEW": "#ffa500", "BLOCK": "#ff4d4d"},
                title="Anomaly Score Timeline"
            )
            st.plotly_chart(fig3, use_container_width=True)
        
        # Top risky agents
        st.subheader("Agents by High-Risk Actions")
        high_df = df[df["risk_level"] == "HIGH"]
        if not high_df.empty:
            agent_counts = high_df["agent_id"].value_counts().reset_index()
            agent_counts.columns = ["agent_id", "high_risk_count"]
            fig4 = px.bar(agent_counts.head(10), x="agent_id", y="high_risk_count", title="Top Agents with HIGH risk")
            st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No actions recorded yet. Submit some test actions or wait for live traffic.")


elif page == "Live Actions":
    st.title("Live Agent Actions")
    
    df = fetch_recent_actions(200)
    
    if df.empty:
        st.info("No actions yet.")
    else:
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            decision_filter = st.multiselect("Decision", options=["ALLOW", "REVIEW", "BLOCK"], default=["ALLOW", "REVIEW", "BLOCK"])
        with col2:
            risk_filter = st.multiselect("Risk Level", options=["LOW", "MEDIUM", "HIGH"], default=["LOW", "MEDIUM", "HIGH"])
        with col3:
            agent_filter = st.multiselect("Agent ID", options=sorted(df["agent_id"].unique().tolist()))
        
        filtered = df[
            df["decision"].isin(decision_filter) &
            df["risk_level"].isin(risk_filter)
        ]
        if agent_filter:
            filtered = filtered[filtered["agent_id"].isin(agent_filter)]
        
        st.dataframe(
            filtered[[
                "timestamp", "agent_id", "action_type", "pair", "notional_usd",
                "anomaly_score", "risk_level", "decision", "llm_recommendation", "reason"
            ]].style.applymap(color_decision, subset=["decision"]),
            use_container_width=True,
            height=500
        )


elif page == "Agent Registry":
    st.title("Agent Registry (KYA)")
    st.markdown("Registered agents with their mandates and hard limits.")
    
    agents_df = fetch_agents()
    
    if agents_df.empty:
        st.info("No agents registered yet. Use the API or the form below.")
    else:
        st.dataframe(agents_df, use_container_width=True)
    
    st.markdown("---")
    st.subheader("Register New Agent")
    
    with st.form("register_agent"):
        c1, c2 = st.columns(2)
        with c1:
            agent_id = st.text_input("Agent ID", value="agent_new_001")
            principal_id = st.text_input("Principal ID", value="principal_1")
            agent_type = st.selectbox("Agent Type", ["trading", "payment", "hybrid"])
        with c2:
            max_notional = st.number_input("Max Notional (USD)", value=500000.0, step=50000.0)
            max_leverage = st.number_input("Max Leverage", value=15.0, step=1.0)
        
        allowed_pairs = st.multiselect(
            "Allowed Pairs",
            ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURGBP", "NZDUSD"],
            default=["EURUSD", "GBPUSD", "USDJPY"]
        )
        notes = st.text_area("Notes", value="")
        
        submitted = st.form_submit_button("Register Agent")
        if submitted:
            payload = {
                "agent_id": agent_id,
                "principal_id": principal_id,
                "agent_type": agent_type,
                "max_notional_usd": max_notional,
                "max_leverage": max_leverage,
                "allowed_pairs": allowed_pairs,
                "allowed_action_types": ["FOREX_TRADE", "PAYMENT"],
                "notes": notes
            }
            try:
                r = requests.post(f"{API_URL}/agents/register", json=payload, timeout=5)
                if r.status_code == 200:
                    st.success(f"Agent {agent_id} registered successfully!")
                    st.cache_data.clear()
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"Failed to register: {e}")


elif page == "Submit Test Action":
    st.title("Submit Test Action")
    st.markdown("Simulate an agent action and see the monitoring decision in real time.")
    
    with st.form("test_action"):
        c1, c2 = st.columns(2)
        with c1:
            agent_id = st.text_input("Agent ID", value="agent_003")
            principal_id = st.text_input("Principal ID", value="principal_1")
            action_type = st.selectbox("Action Type", ["FOREX_TRADE", "PAYMENT"])
            pair = st.selectbox("Pair (Forex)", ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "None"])
            side = st.selectbox("Side", ["BUY", "SELL", "None"])
        with c2:
            notional = st.number_input("Notional USD", value=250000.0, step=10000.0)
            leverage = st.number_input("Leverage (Forex)", value=10.0, step=1.0)
            hour = st.slider("Hour of Day", 0, 23, 14)
            use_llm = st.checkbox("Use LLM Critic", value=True)
        
        submitted = st.form_submit_button("🚀 Submit for Monitoring")
        
        if submitted:
            payload = {
                "agent_id": agent_id,
                "principal_id": principal_id,
                "action_type": action_type,
                "pair": None if pair == "None" else pair,
                "side": None if side == "None" else side,
                "notional_usd": notional,
                "leverage": leverage if action_type == "FOREX_TRADE" else None,
                "hour": hour
            }
            try:
                r = requests.post(
                    f"{API_URL}/monitor/action",
                    params={"use_llm": use_llm},
                    json=payload,
                    timeout=15
                )
                if r.status_code == 200:
                    result = r.json()
                    st.success("Action processed!")
                    
                    # Result cards
                    rc1, rc2, rc3, rc4 = st.columns(4)
                    rc1.metric("Decision", result["decision"])
                    rc2.metric("Risk Level", result["risk_level"])
                    rc3.metric("Anomaly Score", f"{result['anomaly_score']:.3f}")
                    rc4.metric("LLM Recommendation", result.get("llm_recommendation") or "N/A")
                    
                    st.markdown("**Reason:**")
                    st.info(result.get("reason", ""))
                    
                    if result.get("llm_explanation"):
                        st.markdown("**LLM Critic Explanation:**")
                        st.write(result["llm_explanation"])
                    
                    st.json(result)
                    st.cache_data.clear()
                else:
                    st.error(f"API Error {r.status_code}: {r.text}")
            except Exception as e:
                st.error(f"Request failed: {e}")


elif page == "System Info":
    st.title("System Information")
    st.markdown("""
    ### Architecture
    - **API**: FastAPI (async-ready)
    - **Database**: SQLite (can switch to PostgreSQL via `DATABASE_URL`)
    - **ML Model**: Isolation Forest (unsupervised anomaly detection)
    - **LLM Critic**: Mock (or real OpenAI-compatible via env vars)
    - **Dashboard**: Streamlit + Plotly
    
    ### Key KYA Features
    - Agent Registry with hard limits (notional, leverage, allowed pairs)
    - Deterministic policy engine (cannot be overridden by ML)
    - Behavioral anomaly detection
    - LLM-based qualitative critique
    - Full audit trail in database
    
    ### Environment Variables
    - `DATABASE_URL` (default: sqlite:///./data/agent_monitor.db)
    - `LLM_PROVIDER` (mock | openai)
    - `OPENAI_API_KEY` or `LLM_API_KEY`
    - `LLM_BASE_URL`, `LLM_MODEL`
    - `API_URL` (for dashboard)
    
    ### Running
    ```bash
    # Terminal 1 - API
    uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
    
    # Terminal 2 - Dashboard
    streamlit run app/dashboard.py --server.port 8501
    ```
    """)
    
    st.markdown("---")
    st.subheader("Health Check")
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        st.success(f"API is healthy: {r.json()}")
    except Exception as e:
        st.error(f"API not reachable: {e}")