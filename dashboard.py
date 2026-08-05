"""
dashboard.py
------------
Simple web dashboard — browser se stats, recent logs, aur users ka breakdown
dekhne ke liye (sirf Telegram tak limited nahi). HTTP Basic-Auth se protected
(config.DASHBOARD_USERNAME / DASHBOARD_PASSWORD).

DASHBOARD_ENABLED=true karo .env me to ye main bot ke saath hi (same asyncio
event loop me) start ho jaata hai — koi alag process chalane ki zaroorat nahi.
"""

import html
import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

import config
import database as db
import logbuffer

logger = logging.getLogger(__name__)

app = FastAPI(title="ZipBot Dashboard", docs_url=None, redoc_url=None)
_security = HTTPBasic()


def _check_auth(credentials: HTTPBasicCredentials = Depends(_security)) -> bool:
    ok_user = secrets.compare_digest(credentials.username, config.DASHBOARD_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, config.DASHBOARD_PASSWORD)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return True


@app.get("/", response_class=HTMLResponse)
async def home(auth: bool = Depends(_check_auth)):
    a = await db.get_analytics_summary()
    tiers = await db.get_tier_counts()
    sent_pending_delete = await db.count_sent_messages()
    logs = html.escape("\n".join(logbuffer.recent(40)) or "No recent errors/warnings.")

    return f"""
    <html><head><meta charset="utf-8"><title>ZipBot Dashboard</title>
    <style>
      body {{font-family: -apple-system, Segoe UI, sans-serif; background:#0f1115; color:#e5e7eb; padding:2rem; max-width:1000px; margin:0 auto;}}
      .card {{background:#1a1d24; border-radius:14px; padding:1.4rem 1.6rem; margin-bottom:1.2rem; border:1px solid #262a33;}}
      h1 {{color:#7dd3fc; margin-bottom:0.2rem}} h2{{color:#a5b4fc; margin-top:0; font-size:1.05rem}}
      pre {{white-space: pre-wrap; word-break: break-word; background:#0b0d11; padding:1rem; border-radius:10px; max-height:420px; overflow:auto; font-size:0.82rem; color:#fca5a5;}}
      .stats {{display:flex; flex-wrap:wrap; gap:1.6rem;}}
      .stat b {{font-size:1.7rem; display:block; color:#4ade80}}
      .stat span {{opacity:0.7; font-size:0.85rem;}}
      .tiers span.badge {{display:inline-block; padding:0.3rem 0.8rem; border-radius:999px; margin-right:0.5rem; font-size:0.85rem;}}
      .free {{background:#374151;}} .vip {{background:#7c3aed;}} .premium {{background:#d97706;}}
      footer {{opacity:0.4; font-size:0.8rem; margin-top:1rem;}}
    </style></head><body>
    <h1>📦 ZipBot Dashboard</h1>
    <footer>Auto-refreshes every 15s</footer>

    <div class="card">
      <h2>Overview</h2>
      <div class="stats">
        <div class="stat"><b>{a['total_users']}</b><span>Total users</span></div>
        <div class="stat"><b>{a['banned_users']}</b><span>Banned</span></div>
        <div class="stat"><b>{a['total_extractions']}</b><span>Total extractions</span></div>
        <div class="stat"><b>{a['total_files_sent']}</b><span>Total files sent</span></div>
        <div class="stat"><b>{a['today_active']}</b><span>Active today</span></div>
        <div class="stat"><b>{a['week_active']}</b><span>Active (7d)</span></div>
        <div class="stat"><b>{sent_pending_delete}</b><span>Sent files (deletable)</span></div>
      </div>
    </div>

    <div class="card tiers">
      <h2>User tiers</h2>
      <span class="badge free">Free: {tiers.get('free', 0)}</span>
      <span class="badge vip">VIP: {tiers.get('vip', 0)}</span>
      <span class="badge premium">Premium: {tiers.get('premium', 0)}</span>
    </div>

    <div class="card">
      <h2>Recent logs (warnings/errors)</h2>
      <pre>{logs}</pre>
    </div>

    <script>setTimeout(()=>location.reload(), 15000)</script>
    </body></html>
    """


@app.get("/api/stats")
async def api_stats(auth: bool = Depends(_check_auth)):
    a = await db.get_analytics_summary()
    a["tiers"] = await db.get_tier_counts()
    return a


@app.get("/api/logs")
async def api_logs(auth: bool = Depends(_check_auth)):
    return {"logs": logbuffer.recent(100)}


async def run_dashboard():
    """post_init se asyncio task ke roop me start hota hai — alag process ki zaroorat nahi."""
    if not config.DASHBOARD_ENABLED:
        return
    try:
        import uvicorn
    except ImportError:
        logger.warning("DASHBOARD_ENABLED=true hai lekin uvicorn/fastapi installed nahi — 'pip install fastapi uvicorn' karo.")
        return

    cfg = uvicorn.Config(app, host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, log_level="warning")
    server = uvicorn.Server(cfg)
    logger.info("Web dashboard starting on http://%s:%s", config.DASHBOARD_HOST, config.DASHBOARD_PORT)
    await server.serve()
