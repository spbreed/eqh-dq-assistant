"""FastAPI assistant service: chat (SSE streaming), asset pages, lineage graph, steward review queue.

Auth: Cognito hosted UI (OAuth2 code flow) -> signed session cookie with username + groups.
AUTH_MODE=dev (local only) accepts X-Dev-User / X-Dev-Groups headers instead.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from assistant.app import agent, review
from assistant.app import tools as T

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")
UI = Path(__file__).resolve().parents[1] / "ui"
templates = Jinja2Templates(directory=str(UI))
app = FastAPI(title="Data Quality Assistant (prototype)", docs_url=None, redoc_url=None)

AUTH_MODE = os.environ.get("AUTH_MODE", "cognito")
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "")          # https://<prefix>.auth.<region>.amazoncognito.com
CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
ORIGIN_SECRET = os.environ.get("ORIGIN_VERIFY_SECRET", "")      # header set by CloudFront; blocks direct ALB access
REGION = os.environ.get("AWS_REGION", "us-east-1")
SESSION_TTL = 8 * 3600
_signer = URLSafeTimedSerializer(os.environ.get("SESSION_SECRET") or secrets.token_hex(32), salt="eqh-dq-session")
_jwks = jwt.PyJWKClient(f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json") \
    if USER_POOL_ID else None


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    if ORIGIN_SECRET and request.url.path != "/health" and \
            request.headers.get("x-origin-verify") != ORIGIN_SECRET:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp


def user(request: Request) -> dict:
    if AUTH_MODE == "dev":
        return {"username": request.headers.get("x-dev-user", "dev"),
                "groups": [g for g in request.headers.get("x-dev-groups", "analyst").split(",") if g]}
    raw = request.cookies.get("eqh_session")
    if not raw:
        raise HTTPException(401, "login required")
    try:
        return _signer.loads(raw, max_age=SESSION_TTL)
    except BadSignature as e:
        raise HTTPException(401, "session expired") from e


@app.exception_handler(HTTPException)
async def http_err(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path in ("/", "/asset", "/review"):
        return RedirectResponse("/login")
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- auth (Cognito hosted UI)
@app.get("/login")
def login():
    if AUTH_MODE == "dev":
        return RedirectResponse("/")
    q = urlencode({"client_id": CLIENT_ID, "response_type": "code", "scope": "openid email profile",
                   "redirect_uri": f"{PUBLIC_URL}/auth/callback"})
    return RedirectResponse(f"{COGNITO_DOMAIN}/oauth2/authorize?{q}")


@app.get("/auth/callback")
def callback(code: str):
    r = httpx.post(f"{COGNITO_DOMAIN}/oauth2/token", timeout=15, data={
        "grant_type": "authorization_code", "client_id": CLIENT_ID, "code": code,
        "redirect_uri": f"{PUBLIC_URL}/auth/callback"})
    if r.status_code != 200:
        raise HTTPException(401, "login failed")
    tok = r.json()["id_token"]
    key = _jwks.get_signing_key_from_jwt(tok)
    claims = jwt.decode(tok, key.key, algorithms=["RS256"], audience=CLIENT_ID,
                        issuer=f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}")
    sess = {"username": claims.get("email") or claims["cognito:username"], "groups": claims.get("cognito:groups", [])}
    resp = RedirectResponse("/")
    resp.set_cookie("eqh_session", _signer.dumps(sess), httponly=True, secure=True, samesite="lax",
                    max_age=SESSION_TTL)
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(f"{COGNITO_DOMAIN}/logout?" + urlencode({"client_id": CLIENT_ID,
                                                                     "logout_uri": f"{PUBLIC_URL}/"})
                            if AUTH_MODE != "dev" else "/")
    resp.delete_cookie("eqh_session")
    return resp


# ---------------------------------------------------------------- pages
@app.get("/", response_class=HTMLResponse)
def chat_page(request: Request, u: dict = Depends(user)):
    return templates.TemplateResponse(request, "chat.html", {"user": u, "page": "chat"})


@app.get("/asset", response_class=HTMLResponse)
def asset_page(request: Request, key: str, u: dict = Depends(user)):
    return templates.TemplateResponse(request, "asset.html", {"user": u, "page": "asset", "asset_key": key})


@app.get("/review", response_class=HTMLResponse)
def review_page(request: Request, u: dict = Depends(user)):
    if "steward" not in u["groups"]:
        raise HTTPException(403, "steward group required")
    return templates.TemplateResponse(request, "review.html", {"user": u, "page": "review"})


# ---------------------------------------------------------------- APIs
@app.post("/api/chat")
async def chat(request: Request, u: dict = Depends(user)):
    body = await request.json()
    q = (body.get("question") or "").strip()[:4000]
    history = [h for h in body.get("history", [])[-6:] if h.get("role") in ("user", "assistant")]
    history = [{"role": h["role"], "content": str(h["content"])[:4000]} for h in history]
    if not q:
        raise HTTPException(400, "empty question")
    events: queue.Queue = queue.Queue()

    def work():
        try:
            agent.answer(q, u["groups"], history, on_event=events.put, user=u["username"])
        except Exception as e:  # noqa: BLE001
            log.exception("chat failed")
            events.put({"type": "error", "message": f"The assistant hit an error: {type(e).__name__}"})
        events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def gen():
        while True:
            ev = events.get()
            if ev is None:
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/asset")
def api_asset(key: str, u: dict = Depends(user)):
    ctx = T.Ctx(u["groups"])
    return {"asset": T.get_asset(ctx, key), "lineage": T.get_lineage(ctx, key, "both", 2),
            "issues": T.get_dq_issues(ctx, asset_key=key, status="all")["issues"][:20],
            "drift": T.get_schema_changes(ctx, asset_key=key)["changes"][:20]}


@app.get("/api/trend")
def api_trend(key: str, metric: str, column: str = "", segment: str = "", u: dict = Depends(user)):
    return T.get_dq_trend(T.Ctx(u["groups"]), key, metric, column or None, segment or None)


@app.get("/api/review")
def api_review_queue(u: dict = Depends(user)):
    if "steward" not in u["groups"]:
        raise HTTPException(403, "steward group required")
    return {"queue": review.queue(u["groups"])}


@app.post("/api/review")
async def api_review_action(request: Request, u: dict = Depends(user)):
    if "steward" not in u["groups"]:
        raise HTTPException(403, "steward group required")
    body = await request.json()
    action = body.get("action")
    if action not in ("approve", "edit_approve", "reject"):
        raise HTTPException(400, "bad action")
    return review.act(body["asset_key"], action, u["username"], body.get("text"), u["groups"])


@app.get("/api/me")
def me(u: dict = Depends(user)):
    return {**u, "time": time.time()}
