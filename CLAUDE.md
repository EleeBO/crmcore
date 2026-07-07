# CodeRush2 - Claude Code Configuration

This project uses a multi-agent architecture for Claude Code.

## Worktrees

Worktree directory: `worktrees/` (project-local, visible). Do NOT use `.claude/worktrees/`.

## Quick Start

```bash
# Switch to an agent role
/orchestrator  # Project management, task coordination
/architect     # System design, ADRs
/backend       # Python API development
/frontend      # React/Next.js development
/tester        # QA, E2E testing with browser
/security      # Security audits
/designer      # UX/UI design
/infrastructure # Audit .claude/ consistency
```

## Workflow

1. **Setup**: `/setup` - Check environment, install dependencies
2. **Plan**: `/plan` - Create implementation plan
3. **Implement**: `/implement` - Execute plan with TDD
4. **Verify**: `/verify` - Verify completed work

## Tech Stack

### Backend
- Python 3.11+
- uv (package manager)
- FastAPI / Django
- SaluteSpeech (STT via gRPC, requires Russian Trusted Root CA)
- OpenRouter (LLM gateway)
- pytest, ruff, mypy

### Frontend
- Next.js 14+ (App Router)
- TypeScript (strict)
- Tailwind CSS
- Jest, Playwright

## Agents

### Core Agents

| Agent | Role | Use When |
|-------|------|----------|
| Orchestrator | Coordinator | Starting tasks, managing work |
| Architect | Designer | System design, tech decisions |
| Backend | Python Dev | APIs, business logic |
| Frontend | React Dev | UI components, pages |
| Tester | QA | Testing, E2E with browser |
| Security | Auditor | Security reviews |
| Designer | UX/UI | User flows, visual design |
| Infrastructure | .claude/ Manager | Audit hooks/skills/agents consistency |

### Specialized Agents (used by Task tool)

| Agent | Role | Use When |
|-------|------|----------|
| Test PM | QA Analyst | Extract acceptance criteria from specs |
| Test Writer | Test Author | Generate executable test files |
| Plan Reviewer — Architect | Arch Reviewer | Architecture review of plans |
| Plan Reviewer — Backend | Backend Reviewer | Backend review of plans |
| Plan Reviewer — Frontend | Frontend Reviewer | Frontend review of plans |

## Hooks

- **TDD Enforcer** (PreToolUse) - Warns if writing code without failing tests
- **Skill Enforcer** (PreToolUse) - Reminds to activate relevant skills before implementation
- **Python Checker** (PostToolUse) - Runs ruff/mypy after Python edits
- **Security Guard** (PostToolUse) - Checks for common security issues

## Skills

Skills provide specialized knowledge for agents.

| Skill | Description | Triggers |
|-------|-------------|----------|
| `backend-python` | Python/FastAPI/uv standards | "create API", "Python service" |
| `frontend-react` | React/Next.js/TypeScript | "create component", "add page" |
| `security-audit` | OWASP, vulnerability detection | "security audit", "check vulnerabilities" |
| `testing-patterns` | pytest/Jest patterns, TDD | "write test", "test coverage" |
| `react-best-practices` | 57 Vercel optimization rules | "optimize React", "review component" |
| `web-design-guidelines` | 100+ a11y/UX/performance rules | "check accessibility", "UX review" |
| `e2e-agent-browser` | Browser automation (Vercel) | "run e2e test", "browser test" |

## Just Commands (AI Agent Automation)

> **CRITICAL**: Always run `just --list` before using shell commands.

```bash
# AI Helpers (saves tokens)
just context              # Show project structure
just search <query>       # Search source code only
just wtf <file>          # Git history for file
just status              # Check environment

# Development
just setup               # Install all dependencies
just dev                 # Run dev servers
just test                # Run all tests
just lint                # Run linters

# E2E Testing
just e2e <url>           # Quick browser test
just screenshot <url>    # Capture screenshot

# Security
just security            # Full security audit
just secrets             # Scan for secrets
```

## Tools

### Just (Command Runner)
```bash
# Install
brew install just  # macOS
cargo install just # Others

# Usage - ALWAYS use just instead of raw commands
just --list        # See all commands
just test          # Instead of pytest
just search "foo"  # Instead of grep
```

### Agent Browser (E2E Testing)
```bash
# Install
npm install -g agent-browser
agent-browser install

# Usage (or use just e2e)
agent-browser open https://localhost:3000
agent-browser snapshot -i -c
```

### Exa (AI-Optimized Search)
For code examples and documentation research.
Enabled via MCP: `mcp__exa__*`

### Greptile (AI Code Understanding)
Semantic code search and AI-powered code review.
```bash
# Via Just
just greptile-query "how does authentication work?"
just greptile-prs     # List PRs
just greptile-review 123  # Review PR #123

# Via MCP (preferred)
mcp__plugin_greptile_greptile__search_code
mcp__plugin_greptile_greptile__query_repository
mcp__plugin_greptile_greptile__list_pull_requests
mcp__plugin_greptile_greptile__trigger_code_review
```

### Install All Tools
```bash
./scripts/install-tools.sh
```

## Directory Structure

```
.claude/
├── agents/      # Agent role definitions (13 agents)
├── commands/    # Slash commands (/plan, /implement, /verify, etc.)
├── hooks/       # Quality enforcement hooks (4 active + contract)
├── memory/      # Cross-session persistent learnings
├── rules/       # Coding standards (8 rule files)
└── skills/      # Reusable knowledge modules (23 skills)
```

## Rules

1. **TDD Required** - Write failing test before implementation
2. **Type Hints** - All functions must have type annotations
3. **No Hardcoded Secrets** - Use environment variables
4. **Task Tracking** - Update plan checkboxes after each task

## Copy to Another Project

```bash
# Option 1: Use the copy script
./scripts/copy-to-project.sh /path/to/your/project

# Option 2: Manual copy
cp -r .claude /path/to/your/project/
cp CLAUDE.md /path/to/your/project/
cp -r scripts /path/to/your/project/

# Then check environment
cd /path/to/your/project
./scripts/install-tools.sh --check
```

## Environment Check

```bash
# Check only (don't install)
./scripts/install-tools.sh --check

# Interactive install
./scripts/install-tools.sh

# Auto-install all
./scripts/install-tools.sh --auto
```

### Context7 (Up-to-date Documentation)
Fetches current library documentation directly into prompts.
```bash
# Add to Claude Code
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest

# Usage in prompts
# Just add "use context7" when you need library docs
```
Enabled via MCP: `mcp__context7__*`
