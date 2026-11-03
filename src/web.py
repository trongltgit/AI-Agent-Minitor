"""
Web UI routes for AI Agent Monitor
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional
import os

from src.database import get_db, AgentAction, AgentRegistry
from src.monitor_service import AgentMonitorService

router = APIRouter()

# Resolve templates path relative to project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

monitor_service = AgentMonitorService()


def _safe_stats(db: Session):
    try:
        total = db.query(func.count(AgentAction.id)).scalar() or 0
        by_decision = dict(db.query(AgentAction.decision, func.count(AgentAction.id)).group_by(AgentAction.decision).all())
        by_risk = dict(db.query(AgentAction.risk_level, func.count(AgentAction.id)).group_by(AgentAction.risk_level).all())
        high_risk = db.query(func.count(AgentAction.id)).filter(AgentAction.risk_level == "HIGH").scalar() or 0
        return {
            "total_actions": total,
            "by_decision": by_decision or {},
            "by_risk_level": by_risk or {},
            "high_risk_count": high_risk,
        }
    except Exception:
        return {
            "total_actions": 0,
            "by_decision": {},
            "by_risk_level": {},
            "high_risk_count": 0,
        }


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = _safe_stats(db)

    try:
        recent = db.query(AgentAction).order_by(AgentAction.timestamp.desc()).limit(10).all()
        recent_data = []
        for r in recent:
            recent_data.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "agent_id": r.agent_id,
                "action_type": r.action_type,
                "notional_usd": r.notional_usd or 0,
                "anomaly_score": r.anomaly_score or 0,
                "decision": r.decision or "N/A",
                "risk_level": r.risk_level or "N/A",
            })
    except Exception:
        recent_data = []

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": stats, "recent": recent_data},
    )


@router.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={"result": None},
    )


@router.post("/submit", response_class=HTMLResponse)
def submit_action(
    request: Request,
    agent_id: str = Form(...),
    principal_id: str = Form(""),
    action_type: str = Form(...),
    pair: str = Form(""),
    side: str = Form(""),
    notional_usd: float = Form(...),
    leverage: Optional[float] = Form(None),
    hour: int = Form(14),
    use_llm: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    payload = {
        "agent_id": agent_id,
        "principal_id": principal_id or None,
        "action_type": action_type,
        "pair": pair or None,
        "side": side or None,
        "notional_usd": notional_usd,
        "leverage": leverage,
        "hour": hour,
        "timestamp": datetime.utcnow().isoformat(),
    }
    try:
        result = monitor_service.score_action(payload, db, use_llm=bool(use_llm))
    except Exception as e:
        result = {
            "decision": "ERROR",
            "risk_level": "HIGH",
            "anomaly_score": 0,
            "reason": str(e),
            "llm_recommendation": None,
            "llm_explanation": None,
        }

    return templates.TemplateResponse(
        request=request,
        name="submit.html",
        context={"result": result},
    )


@router.get("/actions", response_class=HTMLResponse)
def actions_page(request: Request, db: Session = Depends(get_db)):
    try:
        records = db.query(AgentAction).order_by(AgentAction.timestamp.desc()).limit(100).all()
        actions = []
        for r in records:
            actions.append({
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "agent_id": r.agent_id,
                "action_type": r.action_type,
                "pair": r.pair,
                "notional_usd": r.notional_usd or 0,
                "anomaly_score": r.anomaly_score or 0,
                "risk_level": r.risk_level or "N/A",
                "decision": r.decision or "N/A",
                "reason": r.reason or "",
            })
    except Exception:
        actions = []

    return templates.TemplateResponse(
        request=request,
        name="actions.html",
        context={"actions": actions},
    )


@router.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request, db: Session = Depends(get_db)):
    try:
        agents = db.query(AgentRegistry).all()
    except Exception:
        agents = []

    return templates.TemplateResponse(
        request=request,
        name="agents.html",
        context={"agents": agents, "message": None, "success": False},
    )


@router.post("/agents", response_class=HTMLResponse)
def register_agent_web(
    request: Request,
    agent_id: str = Form(...),
    principal_id: str = Form(...),
    max_notional_usd: float = Form(1000000),
    max_leverage: float = Form(20),
    db: Session = Depends(get_db),
):
    message = None
    success = False

    try:
        existing = db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent_id).first()
        if existing:
            message = f"Agent {agent_id} đã tồn tại"
            success = False
        else:
            agent = AgentRegistry(
                agent_id=agent_id,
                principal_id=principal_id,
                max_leverage=max_leverage,
            )
            if hasattr(agent, "max_notional_per_trade"):
                agent.max_notional_per_trade = max_notional_usd
            if hasattr(agent, "max_notional_usd"):
                agent.max_notional_usd = max_notional_usd
            if hasattr(agent, "is_active"):
                agent.is_active = True

            db.add(agent)
            db.commit()
            message = f"Đăng ký thành công agent {agent_id}"
            success = True
    except Exception as e:
        message = f"Lỗi: {str(e)}"
        success = False

    try:
        agents = db.query(AgentRegistry).all()
    except Exception:
        agents = []

    return templates.TemplateResponse(
        request=request,
        name="agents.html",
        context={"agents": agents, "message": message, "success": success},
    )


# ========== SIMULATION & TEST ROUTES ==========

@router.get("/test-lab", response_class=HTMLResponse)
def test_lab_page(request: Request):
    from src.simulation.agents import list_agents
    agents = list_agents()
    return templates.TemplateResponse(
        request=request,
        name="test_lab.html",
        context={"agents": agents, "result": None, "batch_results": None},
    )


@router.post("/test-lab/run", response_class=HTMLResponse)
def test_lab_run(
    request: Request,
    agent_id: str = Form(...),
    force_over_limit: Optional[str] = Form(None),
    use_llm: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    from src.simulation.agents import list_agents, generate_test_action
    from src.simulation.settlement import settlement_engine

    action = generate_test_action(agent_id, force_over_limit=bool(force_over_limit))
    action["timestamp"] = datetime.utcnow().isoformat()

    try:
        result = monitor_service.score_action(action, db, use_llm=bool(use_llm))
        # Simulate settlement if ALLOW
        settlement = None
        if result.get("decision") == "ALLOW":
            settlement = settlement_engine.settle_trade({**action, **result})
        result["settlement"] = settlement
        result["test_action"] = action
    except Exception as e:
        result = {"decision": "ERROR", "reason": str(e), "test_action": action}

    agents = list_agents()
    return templates.TemplateResponse(
        request=request,
        name="test_lab.html",
        context={"agents": agents, "result": result, "batch_results": None},
    )


@router.post("/test-lab/batch", response_class=HTMLResponse)
def test_lab_batch(
    request: Request,
    n: int = Form(10),
    use_llm: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    from src.simulation.agents import list_agents, generate_test_action, SIMULATED_AGENTS
    from src.simulation.settlement import settlement_engine
    import random

    batch_results = []
    for _ in range(min(n, 30)):
        agent = random.choice(SIMULATED_AGENTS)
        force = agent["behavior"] == "rogue" or random.random() < 0.2
        action = generate_test_action(agent["agent_id"], force_over_limit=force)
        action["timestamp"] = datetime.utcnow().isoformat()
        try:
            res = monitor_service.score_action(action, db, use_llm=bool(use_llm))
            if res.get("decision") == "ALLOW":
                settlement_engine.settle_trade({**action, **res})
            batch_results.append({**res, "test_action": action})
        except Exception as e:
            batch_results.append({"decision": "ERROR", "reason": str(e), "test_action": action})

    agents = list_agents()
    return templates.TemplateResponse(
        request=request,
        name="test_lab.html",
        context={"agents": agents, "result": None, "batch_results": batch_results},
    )

@router.get("/fx", response_class=HTMLResponse)
def fx_page(request: Request):
    return templates.TemplateResponse(request=request, name="fx.html", context={})
