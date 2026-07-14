---
description: Check environment and install missing dependencies
model: haiku
---
# SETUP MODE: Environment Configuration

Check and configure the development environment for this project.

## Step 1: Run Environment Check

```bash
python3 {{PROJECT_DIR}}/.claude/hooks/environment_checker.py --force
```

## Step 2: Analyze Results

Based on the check output:

### If all required tools are installed:
- Inform user: "Environment ready!"
- List optional tools that could be installed

### If required tools are missing:
- List each missing tool with install command
- Ask user: "Should I help install these tools?"

## Step 3: Install Missing Tools (with user permission)

### Python Tools (via uv)
```bash
# Install uv if missing
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python dev tools
uv tool install ruff
uv tool install mypy
uv tool install bandit
uv tool install pytest
```

### Node.js Tools
```bash
# Agent Browser
npm install -g agent-browser
agent-browser install
```

### Verify Installation
After installing, re-run the environment check:
```bash
python3 {{PROJECT_DIR}}/.claude/hooks/environment_checker.py --force
```

## Step 4: Project-Specific Setup

Check if project has:

1. **Python project (pyproject.toml exists)**:
   ```bash
   uv sync  # Install dependencies
   ```

2. **Node.js project (package.json exists)**:
   ```bash
   npm install  # or bun install
   ```

3. **Git repository**:
   ```bash
   git status  # Check git state
   ```

## Step 5: Summary

Report to user:
- What was installed
- What's ready to use
- Any manual steps needed

```
Environment Setup Complete!

✓ Python 3.12 with uv
✓ Ruff, Mypy for linting
✓ Agent Browser for E2E testing
✓ Project dependencies installed

Ready to use:
- /plan - Create implementation plans
- /implement - Execute with TDD
- /verify - Verify completed work
```
