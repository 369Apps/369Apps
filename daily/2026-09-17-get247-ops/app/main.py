"""FastAPI entrypoint for the Get247 ops control plane."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .catalog import CATALOG
from .lifecycle import decide_approval, process_intake
from .models import ChannelEnvelope, IntakeResponse
from .store import STORE

PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

app = FastAPI(
    title="Get247 Ops Control Plane",
    description=(
        "Bounded operations service: catalog request → policy + human → verified outcome. "
        "AI is the internal execution layer, not the product."
    ),
    version="0.1.0",
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class IntakeBody(BaseModel):
    channel: str = "whatsapp"
    channel_user_id: str = Field(
        ...,
        description="Stable channel identity, e.g. wa:+15551234567",
    )
    phone: str | None = None
    text: str
    event_id: str | None = None
    idempotency_key: str | None = None


class ApprovalBody(BaseModel):
    token: str
    decision: str = Field(..., pattern="^(approved|rejected)$")
    actor: str = "client"


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "get247-ops", "mode": "demo"}


@app.get("/catalog")
def catalog() -> dict:
    return {
        "positioning": "Managed operations service. Not a general-purpose AI assistant.",
        "ops": [op.model_dump() for op in CATALOG],
    }


@app.post("/intake", response_model=IntakeResponse)
def intake(body: IntakeBody) -> IntakeResponse:
    envelope = ChannelEnvelope(
        channel=body.channel,
        channel_user_id=body.channel_user_id,
        phone=body.phone,
        text=body.text,
        event_id=body.event_id or "",
        idempotency_key=body.idempotency_key,
    )
    if not envelope.event_id:
        from .models import new_id

        envelope.event_id = new_id("evt_")
    return process_intake(envelope, public_base=PUBLIC_BASE)


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.model_dump(mode="json")


@app.get("/jobs/{job_id}/audit")
def job_audit(job_id: str) -> dict:
    job = STORE.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    events = [e.model_dump(mode="json") for e in STORE.audit if e.trace_id == job.trace_id]
    return {"trace_id": job.trace_id, "events": events}


@app.get("/tenants/{client_id}")
def get_tenant(client_id: str) -> dict:
    tenant = STORE.get_tenant(client_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    return tenant.model_dump()


@app.post("/approve/{approval_id}", response_model=IntakeResponse)
def approve(approval_id: str, body: ApprovalBody) -> IntakeResponse:
    try:
        return decide_approval(approval_id, body.token, body.decision, body.actor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/approve/{approval_id}", response_class=HTMLResponse)
def approve_page(approval_id: str, token: str = Query(...)) -> str:
    record = STORE.get_approval(approval_id)
    if not record:
        raise HTTPException(404, "Unknown approval")
    job = STORE.get_job(record.job_id)
    status = "consumed" if record.consumed else "pending"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Approve action · Get247</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0c1210;--ink:#e8f0ea;--muted:#8aa193;--line:#243029;--ok:#3dba7a;--no:#e25b4c;--panel:#14201a}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#1a3328,transparent),var(--bg);color:var(--ink);font-family:"DM Sans",sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}}
.card{{width:min(520px,100%);background:var(--panel);border:1px solid var(--line);padding:28px 26px 24px}}
.brand{{font:500 12px/1 "IBM Plex Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--ok);margin-bottom:18px}}
h1{{font-size:1.55rem;letter-spacing:-.03em;margin:0 0 10px}}
p{{color:var(--muted);line-height:1.5;margin:0 0 14px}}
.meta{{font:500 12px/1.5 "IBM Plex Mono",monospace;color:var(--muted);border-top:1px solid var(--line);padding-top:14px;margin-top:8px}}
.row{{display:flex;gap:10px;margin-top:22px}}
button{{flex:1;border:0;padding:14px 12px;font:700 15px "DM Sans",sans-serif;cursor:pointer}}
.yes{{background:var(--ok);color:#062214}}.no{{background:transparent;color:var(--ink);border:1px solid var(--line)!important}}
#out{{margin-top:16px;font:500 13px/1.45 "IBM Plex Mono",monospace;color:var(--muted);white-space:pre-wrap}}
</style></head><body>
<div class="card">
  <div class="brand">Get247 · one-time approval</div>
  <h1>Authorize this exact action</h1>
  <p>{record.action_summary}</p>
  <div class="meta">
    approval: {approval_id}<br/>
    job: {record.job_id}<br/>
    status: {status}<br/>
    expires: {record.expires_at.isoformat()}<br/>
    trace: {job.trace_id if job else "—"}
  </div>
  <div class="row">
    <button class="yes" onclick="decide('approved')">Approve</button>
    <button class="no" onclick="decide('rejected')">Reject</button>
  </div>
  <div id="out"></div>
</div>
<script>
async function decide(decision){{
  const res = await fetch('/approve/{approval_id}', {{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{token: {token!r}, decision}})
  }});
  const data = await res.json();
  document.getElementById('out').textContent = res.ok
    ? (data.message + '\\nstate=' + data.state)
    : (data.detail || JSON.stringify(data));
}}
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    index = WEB_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    return HTMLResponse("<p>Get247 ops control plane. See /docs</p>")
