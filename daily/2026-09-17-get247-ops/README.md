# get247-ops

Control plane for **[Get247.ai](https://get247.ai)**: a managed operations service clients reach by message. Scheduling, researched briefs, and approved follow-ups arrive in natural language. The **catalog** defines the product. AI is the internal execution layer, not what we sell.

> Catalog request → Policy + human → Verified outcome

This is the Day-3–8 core from the Get247 system blueprint (v1.1, September 2026), runnable in demo mode with zero infrastructure.

## Why this shape

WhatsApp policy and trust both punish "general-purpose AI on chat." Get247 ships a **bounded menu** of business tasks with deterministic gates:

| Class | Meaning | Gate |
|---|---|---|
| A | Read / draft / internal notes | Auto-run |
| B | Create/move appointments, routine comms | One-time approval link |
| C | Purchases, destructive, sensitive, ambiguous | Named human |

The model may propose a plan. Policy, approval, and budget services decide whether each step may run. Never the other way around.

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 for the product page, `/docs` for the API.

### Auto-run (class A)

```bash
curl -s localhost:8000/intake -H 'Content-Type: application/json' -d '{
  "channel": "whatsapp",
  "channel_user_id": "wa:+15551234567",
  "text": "Am I available Tuesday afternoon?"
}' | jq
```

### Approval path (class B)

```bash
curl -s localhost:8000/intake -H 'Content-Type: application/json' -d '{
  "channel": "whatsapp",
  "channel_user_id": "wa:+15551234567",
  "text": "Book a meeting tomorrow at 2pm titled Investor intro"
}' | jq
```

Open the returned `approval_url`, or POST `/approve/{id}` with the token.

### Out of catalog

```bash
curl -s localhost:8000/intake -H 'Content-Type: application/json' -d '{
  "channel": "whatsapp",
  "channel_user_id": "wa:+15551234567",
  "text": "Write me a poem about quantum foam"
}' | jq
```

## Layout

```
app/
  main.py        # FastAPI: /intake, /catalog, /approve, /jobs, /health
  catalog.py     # Bounded month-1 ops + matcher
  policy.py      # Consequence gates + budget kill-switch
  lifecycle.py   # Receive → match → reserve → approve → execute → close
  models.py      # Tenant, identity, job, approval, audit
  store.py       # In-memory demo store (swap for Postgres)
web/
  index.html     # Product positioning page
tests/
  test_lifecycle.py
```

## Month-1 catalog (ship)

- `calendar.check_availability`
- `calendar.create_event` / `move_event` / `cancel_event`
- `brief.research`
- `followup.prepare`
- `desk.escalate`

## Explicitly not in this MVP

Vector search, client-facing workflow builders, broad connector catalogs, autonomous purchasing, consumer Gmail automation, or marketing Get247 as an open-ended chatbot.

## Promote to its own GitHub repo

See [EXTRACT.md](./EXTRACT.md). This folder was built as the 2026-09-17 daily repo inside `369Apps/369Apps` because the Cloud Agent token can only write that repository today.

## Tests

```bash
pip install -r requirements.txt
pytest -q
```
