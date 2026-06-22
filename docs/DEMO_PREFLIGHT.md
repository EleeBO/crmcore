# Demo Pre-Flight Checklist — AI Sales Copilot

> Run this checklist 30 minutes before the demo. All items must be ✅ before starting.

## Environment

- [ ] Docker running: `docker compose up -d` → all 3 services healthy
- [ ] Backend health: `curl http://localhost:8000/api/v1/health` → `{"status":"ok",...}`
- [ ] Redis reachable: `docker compose exec redis redis-cli ping` → `PONG`
- [ ] ChromaDB reachable: `curl http://localhost:8001/api/v1/heartbeat` → response
- [ ] `.env` file has valid `OPENROUTER_API_KEY`

## Extension

- [ ] Chrome 120+ open
- [ ] Extension loaded: `chrome://extensions/` → "AI Sales Copilot" enabled, no errors
- [ ] Popup opens when clicking extension icon
- [ ] Mic permission granted (permissions page opened and accepted)
- [ ] Console shows no critical errors: `F12` → Console → no red errors

## Demo Content

- [ ] Demo KB files ready in `demo/` directory:
  - `tariffs.pdf` — тарифные планы
  - `competitors.xlsx` — сравнение конкурентов
  - `client_crm.docx` — данные клиента из CRM
- [ ] Files can be parsed: test upload before demo
- [ ] After upload: at least 50 chunks indexed
- [ ] Briefing generates correctly (test run)

## Network & Audio

- [ ] Local microphone working (test with system audio settings)
- [ ] Headphones connected (isolates mic from speaker for demo)
- [ ] OpenRouter API accessible: `curl https://openrouter.ai/api/v1/models` → HTTP 200
- [ ] No VPN that might block WebSocket connections

## Backup

- [ ] Pre-cached top-10 objection responses in Redis (run briefing on demo content)
- [ ] Demo laptop charged / plugged in
- [ ] Second browser tab with `docs/DEMO_SCRIPT.md` open for reference

## Final Check

- [ ] Rehearse full flow once (all 12 minutes)
- [ ] Widget appears on `about:blank` page
- [ ] Hint appears within 2s of final transcript in rehearsal
- [ ] Post-call summary generates correctly
