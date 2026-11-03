"""
Web UI routes for AI Agent Monitor
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional
import os

from src.database import get_db, AgentAction, AgentRegistry
from src.monitor_service import AgentMonitorService

router = APIRouter()
templates = Jinja2Templates(directory="templates")
monitor_service = AgentMonitorService()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    total = db.query(func.count(AgentAction.id)).scalar() or 0
    by_decision = dict(db.query(AgentAction.decision, func.count(AgentAction.id)).group_by(AgentAction.decision).all())
    by_risk = dict(db.query(AgentAction.risk_level, func.count(AgentAction.id)).group_by(AgentAction.risk_level).all())
    high_risk = db.query(func.count(AgentAction.id)).filter(AgentAction.risk_level == "HIGH").scalar() or 0

    stats = {
        "total_actions": total,
        "by_decision": by_decision,
        "by_risk_level": by_risk,
        "high_risk_count": high_risk,
    }

    recent = db.query(AgentAction).order_by(AgentAction.timestamp.desc()).limit(10).all()
    recent_data = [{
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "agent_id": r.agent_id,
        "action_type": r.action_type,
        "notional_usd": r.notional_usd,
        "anomaly_score": r.anomaly_score,
        "decision": r.decision,
        "risk_level": r.risk_level,
    } for r in recent]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "recent": recent_data,
    })


@router.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
    return templates.TemplateResponse("submit.html", {"request": request, "result": None})


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
    result = monitor_service.score_action(payload, db, use_llm=bool(use_llm))
    return templates.TemplateResponse("submit.html", {"request": request, "result": result})


@router.get("/actions", response_class=HTMLResponse)
def actions_page(request: Request, db: Session = Depends(get_db)):
    records = db.query(AgentAction).order_by(AgentAction.timestamp.desc()).limit(100).all()
    actions = [{
        "timestamp": r.timestamp.isoformat() if r.timestamp else None,
        "agent_id": r.agent_id,
        "action_type": r.action_type,
        "pair": r.pair,
        "notional_usd": r.notional_usd,
        "anomaly_score": r.anomaly_score,
        "risk_level": r.risk_level,
        "decision": r.decision,
        "reason": r.reason,
    } for r in records]
    return templates.TemplateResponse("actions.html", {"request": request, "actions": actions})


@router.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request, db: Session = Depends(get_db)):
    agents = db.query(AgentRegistry).all()
    return templates.TemplateResponse("agents.html", {
        "request": request,
        "agents": agents,
        "message": None,
        "success": False,
    })


@router.post("/agents", response_class=HTMLResponse)
def register_agent_web(
    request: Request,
    agent_id: str = Form(...),
    principal_id: str = Form(...),
    max_notional_usd: float = Form(1000000),
    max_leverage: float = Form(20),
    db: Session = Depends(get_db),
):
    existing = db.query(AgentRegistry).filter(AgentRegistry.agent_id == agent_id).first()
    if existing:
        agents = db.query(AgentRegistry).all()
        return templates.TemplateResponse("agents.html", {
            "request": request,
            "agents": agents,
            "message": f"Agent {agent_id} đã tồn tại",
            "success": False,
        })

    # Try to create with flexible fields
    try:
        agent = AgentRegistry(
            agent_id=agent_id,
            principal_id=principal_id,
            max_leverage=max_leverage,
        )
        # Support both old and new schema field names
        if hasattr(AgentRegistry, "max_notional_usd"):
            agent.max_notional_usd = max_notional_usd
        if hasattr(AgentRegistry, "max_notional_per_trade"):
            agent.max_notional_per_trade = max_notional_usd
        if hasattr(AgentRegistry, "is_active"):
            agent.is_active = True

        db.add(agent)
        db.commit()
        message = f"Đăng ký thành công agent {agent_id}"
        success = True
    except Exception as e:
        message = f"Lỗi: {str(e)}"
        success = False

    agents = db.query(AgentRegistry).all()
    return templates.TemplateResponse("agents.html", {
        "request": request,
        "agents": agents,
        "message": message,
        "success": success,
    })
