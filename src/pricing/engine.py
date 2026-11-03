"""
Pricing Engine – chỉ trả Final Price theo role.
Không bao giờ lộ base_rate / spread / margin / formula xuống client không đủ quyền.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import random
import hashlib
import time
import os

# Market rates giả lập (có thể thay bằng API thật)
_BASE_RATES = {
    "USD": 25450.0,
    "EUR": 27680.0,
    "GBP": 32200.0,
    "JPY": 168.5,
    "AUD": 16620.0,
}

# HQ policy giả lập theo tier khách hàng
_HQ_SPREAD = {
    "GOLD":   {"BUY": 15, "SELL": 20},
    "SILVER": {"BUY": 25, "SELL": 30},
    "BRONZE": {"BUY": 40, "SELL": 45},
    "DEFAULT": {"BUY": 50, "SELL": 55},
}

_BRANCH_MAX_MARGIN = {
    "GOLD": 25,
    "SILVER": 35,
    "BRONZE": 50,
    "DEFAULT": 60,
}


@dataclass
class QuoteResult:
    quote_id: str
    currency: str
    side: str
    amount: float
    price: float                 # FINAL PRICE ONLY for KH
    valid_until: int
    issued_at: str
    # Internal fields – chỉ trả theo role
    _base_rate: float = 0.0
    _hq_spread: float = 0.0
    _branch_margin: float = 0.0
    _tier: str = "DEFAULT"
    _agent_id: Optional[str] = None
    _principal_id: Optional[str] = None
    _cif: Optional[str] = None


class PricingEngine:
    def __init__(self):
        self._jitter = float(os.getenv("PRICE_JITTER", "3"))

    def _market_rate(self, currency: str) -> float:
        base = _BASE_RATES.get(currency.upper(), 25000.0)
        # small random walk
        return round(base + random.uniform(-self._jitter, self._jitter), 2)

    def _resolve_tier(self, cif: str | None, principal_id: str | None) -> str:
        # Giả lập: một số CIF/principal thuộc tier cao
        key = (cif or principal_id or "").upper()
        if "GOLD" in key or key.endswith("001"):
            return "GOLD"
        if "SILVER" in key or key.endswith("002"):
            return "SILVER"
        if "BRONZE" in key:
            return "BRONZE"
        return "DEFAULT"

    def create_quote(
        self,
        currency: str,
        side: str,
        amount: float,
        role: str = "KH",
        cif: str | None = None,
        principal_id: str | None = None,
        agent_id: str | None = None,
        branch_margin: float | None = None,
    ) -> QuoteResult:
        side = side.upper()
        currency = currency.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if amount <= 0:
            raise ValueError("amount must be positive")

        base = self._market_rate(currency)
        tier = self._resolve_tier(cif, principal_id)
        hq_spread = _HQ_SPREAD.get(tier, _HQ_SPREAD["DEFAULT"])[side]
        max_cn = _BRANCH_MAX_MARGIN.get(tier, _BRANCH_MAX_MARGIN["DEFAULT"])

        cn_margin = 0.0
        if branch_margin is not None:
            cn_margin = min(max(0.0, float(branch_margin)), max_cn)

        # Công thức giá (chỉ chạy server-side)
        if side == "SELL":  # NH bán cho KH → giá cao hơn
            final = base + hq_spread + cn_margin
        else:               # NH mua từ KH → giá thấp hơn
            final = base - hq_spread - cn_margin

        final = round(final, 2)
        now = int(time.time())
        quote_id = hashlib.sha256(
            f"{currency}{side}{amount}{final}{now}{random.random()}".encode()
        ).hexdigest()[:16].upper()

        return QuoteResult(
            quote_id=quote_id,
            currency=currency,
            side=side,
            amount=amount,
            price=final,
            valid_until=now + 30,  # 30s
            issued_at=datetime.utcnow().isoformat(),
            _base_rate=base,
            _hq_spread=hq_spread,
            _branch_margin=cn_margin,
            _tier=tier,
            _agent_id=agent_id,
            _principal_id=principal_id,
            _cif=cif,
        )

    def to_response(self, q: QuoteResult, role: str) -> Dict[str, Any]:
        """Chỉ trả field được phép theo role."""
        role = (role or "KH").upper()
        base = {
            "quote_id": q.quote_id,
            "currency": q.currency,
            "side": q.side,
            "amount": q.amount,
            "price": q.price,  # FINAL
            "valid_until": q.valid_until,
            "issued_at": q.issued_at,
            "valid_for_seconds": max(0, q.valid_until - int(time.time())),
        }
        if role in ("CN", "PNV", "STAFF", "ADMIN_CN"):
            # Chi nhánh được thấy margin của mình + trần
            base["branch_margin"] = q._branch_margin
            base["max_branch_margin"] = _BRANCH_MAX_MARGIN.get(q._tier, 60)
            base["tier"] = q._tier
        if role in ("HQ", "TSC", "ADMIN"):
            # Hội sở thấy đầy đủ nội bộ
            base["base_rate"] = q._base_rate
            base["hq_spread"] = q._hq_spread
            base["branch_margin"] = q._branch_margin
            base["tier"] = q._tier
            base["total_spread"] = q._hq_spread + q._branch_margin
        # KH / AI Agent mặc định: chỉ final price
        return base


pricing_engine = PricingEngine()
