"""
Anti-Bot security layer adapted from anti-bot-pro for FastAPI.
HMAC signature + Nonce + Fingerprint + UA detection + Rate limit.
"""
import hmac
import hashlib
import time
import secrets
import re
from collections import OrderedDict
from threading import Lock
from typing import Optional, Tuple
from fastapi import Request, HTTPException, Header
import os

# Config
API_SIGNING_SECRET = os.getenv("API_SIGNING_SECRET", "dev-signing-secret-change-me")
NONCE_TTL = 120
NONCE_MAX_SIZE = 10000
MAX_TIMESTAMP_AGE = 60

_nonce_store: OrderedDict = OrderedDict()
_nonce_lock = Lock()

# Simple in-memory rate limit: key -> list of timestamps
_rate_store: dict = {}
_rate_lock = Lock()

BOT_UA_PATTERNS = [
    r"bot", r"crawl", r"spider", r"scrape", r"curl", r"wget",
    r"python-requests", r"httpx", r"aiohttp", r"java/", r"go-http",
    r"postman", r"insomnia", r"httpclient",
]


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def is_bot_user_agent(ua: str) -> bool:
    if not ua or len(ua) < 10:
        return True
    ua_lower = ua.lower()
    return any(re.search(p, ua_lower) for p in BOT_UA_PATTERNS)


def generate_fingerprint(request: Request) -> str:
    raw = f"{get_client_ip(request)}|{request.headers.get('user-agent', '')}|{request.headers.get('accept-language', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _check_nonce(nonce: str, ts: int) -> bool:
    if not nonce or len(nonce) < 8 or len(nonce) > 64:
        return False
    now = int(time.time())
    with _nonce_lock:
        # cleanup
        expired = [k for k, v in _nonce_store.items() if now - v > NONCE_TTL]
        for k in expired:
            _nonce_store.pop(k, None)
        if nonce in _nonce_store:
            return False
        _nonce_store[nonce] = ts
        while len(_nonce_store) > NONCE_MAX_SIZE:
            _nonce_store.popitem(last=False)
    return True


def generate_signature(
    timestamp: str,
    method: str,
    path: str,
    body: str = "",
    nonce: str = "",
    fingerprint: str = "",
) -> str:
    body_hash = hashlib.sha256(body.encode()).hexdigest() if body else ""
    message = f"{timestamp}:{method.upper()}:{path}:{body_hash}:{fingerprint}:{nonce}"
    return hmac.new(
        API_SIGNING_SECRET.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    timestamp: str,
    signature: str,
    method: str,
    path: str,
    body: str = "",
    nonce: str = "",
    fingerprint: str = "",
    max_age: int = MAX_TIMESTAMP_AGE,
) -> bool:
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return False
    now = int(time.time())
    if abs(now - ts) > max_age:
        return False
    if nonce and not _check_nonce(nonce, ts):
        return False
    expected = generate_signature(timestamp, method, path, body, nonce, fingerprint)
    return hmac.compare_digest(expected, signature)


def check_rate_limit(key: str, limit: int = 30, window: int = 60) -> Tuple[bool, int]:
    """Returns (allowed, remaining)."""
    now = time.time()
    with _rate_lock:
        timestamps = _rate_store.get(key, [])
        timestamps = [t for t in timestamps if now - t < window]
        if len(timestamps) >= limit:
            _rate_store[key] = timestamps
            return False, 0
        timestamps.append(now)
        _rate_store[key] = timestamps
        return True, limit - len(timestamps)


def anti_bot_check(
    request: Request,
    require_signature: bool = False,
    rate_limit: int = 60,
    rate_window: int = 60,
) -> dict:
    """
    Run anti-bot checks. Raises HTTPException on failure.
    Returns context dict (ip, fingerprint, ua...).
    """
    ua = request.headers.get("user-agent", "")
    ip = get_client_ip(request)
    fp = generate_fingerprint(request)

    # 1. Bot UA detection (soft for browser, hard for API if configured)
    if is_bot_user_agent(ua) and require_signature:
        raise HTTPException(status_code=403, detail="BOT_DETECTED: Suspicious User-Agent")

    # 2. Rate limit
    allowed, remaining = check_rate_limit(f"{ip}:{fp}", limit=rate_limit, window=rate_window)
    if not allowed:
        raise HTTPException(status_code=429, detail="RATE_LIMIT_EXCEEDED")

    # 3. Signature (optional, for sensitive endpoints)
    if require_signature:
        ts = request.headers.get("x-timestamp", "")
        sig = request.headers.get("x-signature", "")
        nonce = request.headers.get("x-nonce", "")
        body = ""
        # body reading is handled by caller if needed
        if not verify_signature(ts, sig, request.method, request.url.path, body, nonce, fp):
            raise HTTPException(status_code=401, detail="INVALID_SIGNATURE")

    return {
        "ip": ip,
        "fingerprint": fp,
        "user_agent": ua,
        "rate_remaining": remaining,
        "is_bot_ua": is_bot_user_agent(ua),
    }
