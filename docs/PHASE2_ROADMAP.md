# Phase 2 Roadmap — AI Sales Copilot

> One-page summary for Q&A during the SberCRM leadership demo.

---

## Phase 1 (MVP — Delivered Today)

- Real-time hints during SIP calls (Deepgram STT + Gemini 2.5 Flash)
- RAG over uploaded documents (PDF, Excel, DOCX)
- Pre-call briefing (buyer portrait + negotiation strategy)
- Post-call summary + email draft
- Shadow DOM overlay widget (6 states)
- Chrome MV3 extension (Vite + TypeScript)

---

## Phase 2 Features

### Multi-Tenancy & Authentication
- Auth: Yandex ID / SberID SSO (OpenID Connect)
- Role-based access: Admin, Manager, Supervisor
- Per-company knowledge bases with ACL
- Estimated effort: 3 weeks

### Call History & Analytics
- Persist conversations in PostgreSQL (with S3 audio archive)
- Dashboard: call stats, hint acceptance rate, conversion correlation
- Supervisor replay: annotated transcripts
- Estimated effort: 4 weeks

### GDPR / Russian PD Compliance (152-ФЗ)
- Audio stored encrypted, TTL 90 days, right-to-deletion
- Opt-in consent screen for call participants
- Data residency: Russian cloud (Yandex Cloud / SberCloud)
- Estimated effort: 2 weeks (with legal review)

### Wider Telephony Support
- SIP integration beyond Mizugate (Asterisk, FreeSWITCH, Avaya)
- Mobile softphone support (iOS/Android SDK wrapper)
- Estimated effort: 4 weeks per integration

### Script Compliance Check
- Upload sales script → AI flags deviations in real time
- Supervisor configures mandatory phrases and forbidden topics
- Report: compliance % per manager per day
- Estimated effort: 2 weeks

### Performance at Scale (50 Users)
| Component | Current | Phase 2 |
|-----------|---------|---------|
| Backend | Single container | 3× FastAPI replicas + nginx |
| Redis | Local | Redis Cluster |
| ChromaDB | Local volume | ChromaDB Cloud or pgvector |
| LLM | OpenRouter | Dedicated OpenRouter org plan |
| Estimated infra cost | ~5,000 ₽/mo | ~25,000–40,000 ₽/mo |

---

## Timeline

```
Month 1:  Auth + Multi-tenancy
Month 2:  Analytics dashboard + Call history
Month 3:  GDPR compliance + Script compliance
Month 4:  Scale testing + Second telephony integration
```

---

## Questions? Contact

- Architecture: [your-name@company.ru]
- Demo source code: available on request (monorepo)
