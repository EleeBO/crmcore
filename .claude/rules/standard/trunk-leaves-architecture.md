# Trunk/Leaves Architecture

> Metaphor from Eric Schluntz (Anthropic): Trunk = critical code, Leaves = safe to change.

## TRUNK — Do Not Modify Without Permission

| Zone | Files |
|------|-------|
| Core Config | `src/core/config.py`, `src/core/database.py` |
| Domain Models | `src/domain/*.py` |
| Base Repository | `src/repositories/base.py` |
| DB Schema | `src/infrastructure/db_setup.py` |
| Bootstrap | `src/bootstrap.py`, `src/main.py` |
| Claude Config | `.claude/settings.local.json`, `CLAUDE.md` |

## LEAVES — Full Freedom

| Zone | Files |
|------|-------|
| Bot Handlers | `src/bot/handlers/*.py` |
| Services | `src/services/*.py` |
| Tests | `tests/**/*.py` |
| Commands | `.claude/commands/*.md` |
| Agents | `.claude/agents/*.md` |
| Rules | `.claude/rules/**/*.md` |
| Frontend | `src/app/**/*`, `src/components/**/*` |
| Landing | `landing/**/*` |

## Control Questions Before Modification

1. Is this a TRUNK zone? → STOP, ask the user for permission
2. Changing a method signature? → grep all callers first
3. Is this a domain model? → Check DB migrations
4. Documentation updated? → Check checklist in `documentation-sync.md`
5. Is this a test? → Freely change
