# Feature Registry

| ID | Name | Status | Spec | Plans | Created |
|----|------|--------|------|-------|---------|
| FEAT-001 | Context Stuffing Pipeline | ACTIVE | [spec](FEAT-001-context-stuffing-pipeline.md) | [v1](../docs/plans/FEAT-001-context-stuffing-pipeline.md) | 2026-03-01 |
| FEAT-002 | Audio Pipeline Fix (End-to-End) | ACTIVE | [spec](FEAT-002-extension-redesign.md) | [v1](../docs/plans/FEAT-002-audio-pipeline-fix.md) | 2026-03-01 |
| FEAT-003 | Extension UI Redesign & Polish | ACTIVE | [spec](FEAT-003-extension-ui-redesign.md) | [v1](../docs/plans/FEAT-003-extension-ui-redesign.md) | 2026-03-01 |
| FEAT-004 | UX Polish — Settings, Stepper, VU Meters | ACTIVE | — | [v1](../docs/plans/FEAT-004-ux-polish-settings-progress-audio.md) | 2026-03-07 |
| FEAT-005 | Extension Critical Bug Fixes | ACTIVE | [spec](FEAT-005-extension-bugfixes.md) | — | 2026-03-07 |
| FEAT-006 | SaluteSpeech SSL Fix & Preflight Checks | ACTIVE | — | — | 2026-03-09 |
| FEAT-007 | Side Panel Migration | ACTIVE | [spec](FEAT-007-side-panel-migration.md) | [design](../docs/plans/2026-03-08-side-panel-migration-design.md), [v1](../docs/plans/FEAT-007-side-panel-migration.md) | 2026-03-08 |
| FEAT-008 | Backend Architecture Fixes | ACTIVE | [spec](FEAT-008-backend-arch-fixes.md) | [v1](../docs/plans/2026-03-14-backend-arch-fixes.md) | 2026-03-14 |
| FEAT-009 | Frontend Architecture Fixes — Sidepanel Split | DRAFT | [spec](FEAT-009-frontend-arch-fixes.md) | [v1](../docs/plans/2026-03-14-frontend-arch-fixes.md) | 2026-03-14 |
| FEAT-011 | Follow-Up Actions (Email + CRM Note) | ACTIVE | [design](../docs/superpowers/specs/2026-03-19-follow-up-actions-design.md) | [v1](../docs/superpowers/plans/2026-03-19-follow-up-actions.md) | 2026-03-19 |
| FEAT-012 | Brief Panel Redesign — Preact + SGR | ACTIVE | [spec](FEAT-012-brief-panel-redesign.md), [SGR contract](FEAT-012-sgr-contract.md) | [v1](../docs/superpowers/plans/2026-03-19-brief-panel-redesign.md) | 2026-03-19 |
| FEAT-013 | Live Call Panel Redesign | ACTIVE | [design](../docs/superpowers/specs/2026-03-19-live-call-redesign-design.md) | [v1](../docs/superpowers/plans/2026-03-19-live-call-redesign.md) | 2026-03-19 |

## Statuses
- DRAFT — specification in progress, not yet implemented
- ACTIVE — implemented and merged into main
- MODIFIED — has pending changes
- DEPRECATED — scheduled for removal
- ARCHIVED — moved to archive/

## Notes
- **FEAT-010 skipped** — this ID was never assigned; jump from FEAT-009 to FEAT-011 is intentional (FEAT-011 follow-up actions was sequenced after FEAT-009/010 planning stalled).
- **FEAT-003** spec file says DRAFT internally but commit `e956902` merged the full implementation into main — status corrected to ACTIVE.
- **FEAT-008** spec file says DRAFT internally but commits `29d0ada` and `789f91c` merged the full refactor into main — status corrected to ACTIVE.
- **FEAT-013** has no spec file under `specs/`; design doc and plan live in `docs/superpowers/`.

## Next ID: FEAT-014
