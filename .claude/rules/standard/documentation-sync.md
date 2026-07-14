# Documentation Sync Rules

> **CRITICAL**: Documentation is updated **BEFORE commit**, not after.

## When to Update

| Change | Update Document |
|--------|-----------------|
| `src/**/*.py` or `src/**/*.ts` | Check if relevant `specs/FEAT-NNN-*.md` needs updating |
| `src/api/**` | `specs/` (Behavior section) |
| `src/models/**` | `specs/` (Components section) |
| New commands in `.claude/commands/` | `CLAUDE.md` (Workflow section) |
| New agents in `.claude/agents/` | `CLAUDE.md` (Agents table) |
| New hooks in `.claude/hooks/` | `CLAUDE.md` (Hooks section) |
| New rules in `.claude/rules/` | `CLAUDE.md` (Rules section) |
| New env variables | `.env.example` and project docs |
| Significant features | `specs/registry.md` |

## Checklist Before Commit

- [ ] Code changed → Spec updated (if spec exists for this feature)?
- [ ] New component → Added to spec's Components section?
- [ ] New endpoint/function → Added to spec's Behavior section?
- [ ] New command/agent/hook → CLAUDE.md updated?
- [ ] Registry reflects current feature statuses?

## Automatic Check

The `check_docs_update.py` hook runs before `git commit` and reminds about documentation updates.
