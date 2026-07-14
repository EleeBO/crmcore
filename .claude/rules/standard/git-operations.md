## Git Operations

**Rule:** Execute git operations freely when asked by the user. Stage, commit, push as needed.

### Allowed Operations

```bash
git status / git diff / git log   # Read state
git add <files>                   # Stage specific files
git commit -m "..."               # Commit with message
git push                          # Push to remote
git checkout / git switch         # Switch branches
git stash / git pull / git merge  # Standard workflows
```

### Safety Rules

- **Never force-push to main/master** without explicit user confirmation
- **Never commit .env or credential files** — always check gitignore first
- **Stage specific files** (not `git add -A`) to avoid accidentally including secrets
- **Conventional commits:** `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

### Before Committing

1. `git status --short` — verify what's staged
2. Confirm no secrets files (`.env`, `*.key`, `credentials*`) in staging
3. Commit with clear message
