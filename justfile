# CodeRush2 - Unified Command Runner for AI Agents
# Usage: just <recipe>
# List all: just --list

# Load .env file if exists
set dotenv-load := true

# Variables
frontend_path := "frontend"
backend_path := "backend"
python_cmd := "uv run python"
js_manager := "npm"

# ============================================
# AI AGENT HELPERS (CRITICAL FOR TOKEN SAVINGS)
# ============================================

# Show project structure (excludes noise)
context:
    @echo "📁 Project Structure:"
    @find . -type f \
        -not -path "*/node_modules/*" \
        -not -path "*/.venv/*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/.git/*" \
        -not -path "*/dist/*" \
        -not -path "*/build/*" \
        -not -path "*/.next/*" \
        -not -name "*.lock" \
        -not -name "package-lock.json" \
        -not -name "uv.lock" \
        | head -100

# Search source code only (saves tokens vs grep)
search query:
    @echo "🔍 Searching for: {{query}}"
    @grep -rn "{{query}}" \
        --include="*.py" \
        --include="*.ts" \
        --include="*.tsx" \
        --include="*.js" \
        --include="*.jsx" \
        --include="*.md" \
        --exclude-dir=node_modules \
        --exclude-dir=.venv \
        --exclude-dir=__pycache__ \
        --exclude-dir=dist \
        --exclude-dir=.next \
        . 2>/dev/null || echo "No results found"

# Git history for a file (who touched it and why)
wtf file:
    @echo "📜 History for: {{file}}"
    @git log -p -n 3 --follow -- "{{file}}" 2>/dev/null || echo "No git history"

# Show all available commands (for AI discovery)
help:
    @just --list

# Show environment status
status:
    @echo "🔧 Environment Status:"
    @echo "Python: $(python3 --version 2>/dev/null || echo 'not found')"
    @echo "Node: $(node --version 2>/dev/null || echo 'not found')"
    @echo "uv: $(uv --version 2>/dev/null || echo 'not found')"
    @echo "Agent Browser: $(agent-browser --version 2>/dev/null || echo 'not found')"

# ============================================
# SETUP & INSTALLATION
# ============================================

# Full project setup (both frontend and backend)
setup:
    @echo "🚀 Setting up project..."
    just setup-backend
    just setup-frontend
    @echo "✅ Setup complete!"

# Setup Python backend
setup-backend:
    @echo "🐍 Setting up Python backend..."
    @uv sync

# Setup Node.js frontend
setup-frontend:
    @echo "⚛️  Setting up frontend..."
    @if [ -f "package.json" ]; then {{js_manager}} install; fi
    @if [ -d "{{frontend_path}}" ] && [ -f "{{frontend_path}}/package.json" ]; then \
        cd {{frontend_path}} && {{js_manager}} install; \
    fi

# Install development tools
setup-tools:
    @echo "🔧 Installing development tools..."
    ./scripts/install-tools.sh --auto

# ============================================
# DEVELOPMENT
# ============================================

# Run all services in development mode
dev:
    @echo "🏃 Starting development servers..."
    @if [ -d "{{frontend_path}}" ]; then \
        (cd {{frontend_path}} && {{js_manager}} run dev) & \
    fi
    @if [ -d "{{backend_path}}" ]; then \
        ({{python_cmd}} -m uvicorn backend.main:app --reload) & \
    fi
    @wait

# Run frontend only
dev-frontend:
    @if [ -d "{{frontend_path}}" ]; then \
        cd {{frontend_path}} && {{js_manager}} run dev; \
    elif [ -f "package.json" ]; then \
        {{js_manager}} run dev; \
    fi

# Run backend only
dev-backend:
    @if [ -d "{{backend_path}}" ]; then \
        {{python_cmd}} -m uvicorn backend.main:app --reload; \
    elif [ -f "main.py" ]; then \
        {{python_cmd}} -m uvicorn main:app --reload; \
    fi

# ============================================
# TESTING
# ============================================

# Run all tests
test:
    @echo "🧪 Running all tests..."
    just test-backend
    just test-frontend

# Run Python tests
test-backend:
    @echo "🐍 Running Python tests..."
    @if [ -d "tests" ] || [ -d "{{backend_path}}/tests" ]; then \
        uv run pytest -v; \
    else \
        echo "No Python tests found"; \
    fi

# Run frontend tests
test-frontend:
    @echo "⚛️  Running frontend tests..."
    @if [ -f "{{frontend_path}}/package.json" ]; then \
        cd {{frontend_path}} && {{js_manager}} test 2>/dev/null || echo "No test script"; \
    elif [ -f "package.json" ]; then \
        {{js_manager}} test 2>/dev/null || echo "No test script"; \
    fi

# Run tests with coverage
test-cov:
    @echo "📊 Running tests with coverage..."
    uv run pytest --cov=src --cov-report=term-missing

# ============================================
# LINTING & FORMATTING
# ============================================

# Run all linters
lint:
    @echo "🔍 Running linters..."
    just lint-python
    just lint-frontend

# Lint Python code
lint-python:
    @echo "🐍 Linting Python..."
    @ruff check . 2>/dev/null || echo "ruff not installed"
    @mypy . 2>/dev/null || echo "mypy not installed"

# Lint frontend code
lint-frontend:
    @echo "⚛️  Linting frontend..."
    @if [ -f "{{frontend_path}}/package.json" ]; then \
        cd {{frontend_path}} && {{js_manager}} run lint 2>/dev/null || true; \
    fi

# Format all code
format:
    @echo "✨ Formatting code..."
    @ruff format . 2>/dev/null || echo "ruff not installed"
    @if [ -f "package.json" ]; then \
        {{js_manager}} run format 2>/dev/null || true; \
    fi

# ============================================
# DATABASE
# ============================================

# Run database migrations
db-migrate msg="auto":
    @echo "🗄️  Running migrations..."
    @if [ -d "alembic" ] || [ -f "alembic.ini" ]; then \
        uv run alembic revision --autogenerate -m "{{msg}}" && \
        uv run alembic upgrade head; \
    elif [ -f "manage.py" ]; then \
        {{python_cmd}} manage.py makemigrations && \
        {{python_cmd}} manage.py migrate; \
    else \
        echo "No migration tool detected (Alembic/Django)"; \
    fi

# Reset database
db-reset:
    @echo "⚠️  Resetting database..."
    @if [ -d "alembic" ]; then \
        uv run alembic downgrade base && uv run alembic upgrade head; \
    fi

# ============================================
# E2E TESTING (Agent Browser)
# ============================================

# Run E2E tests with agent-browser
e2e url="http://localhost:3000":
    @echo "🌐 Running E2E tests on {{url}}..."
    agent-browser open {{url}}
    agent-browser snapshot -i -c

# Take screenshot
screenshot url name="screenshot.png":
    agent-browser open {{url}}
    agent-browser screenshot ./{{name}}
    @echo "📸 Screenshot saved to {{name}}"

# Run extension E2E tests
e2e-ext:
    @echo "Running extension E2E tests..."
    cd tests/e2e && npm install --silent 2>&1 | tail -1 && node extension.e2e.mjs

# ============================================
# BUILD & DEPLOY
# ============================================

# Build for production
build:
    @echo "📦 Building for production..."
    @if [ -f "{{frontend_path}}/package.json" ]; then \
        cd {{frontend_path}} && {{js_manager}} run build; \
    elif [ -f "package.json" ]; then \
        {{js_manager}} run build; \
    fi

# Clean build artifacts
clean:
    @echo "🧹 Cleaning build artifacts..."
    rm -rf dist build .next __pycache__ .pytest_cache .mypy_cache .ruff_cache
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true

# ============================================
# GREPTILE (AI Code Understanding)
# ============================================

# Query codebase with natural language (via Greptile MCP)
# Note: These wrap MCP tools for CLI convenience
# Use mcp__plugin_greptile_greptile__* tools directly in Claude for best results

# Index current repository for Greptile
greptile-index:
    @echo "📚 Indexing repository for Greptile..."
    @echo "Use MCP tool: mcp__plugin_greptile_greptile__index_repository"
    @echo "Or in Claude: 'Index this repository with Greptile'"

# Query codebase (natural language)
greptile-query query:
    @echo "🔍 Querying codebase: {{query}}"
    @echo "Use MCP tool: mcp__plugin_greptile_greptile__query_repository"
    @echo "Or ask Claude: '{{query}}' (Greptile will be used automatically)"

# Search code semantically
greptile-search term:
    @echo "🔎 Semantic search for: {{term}}"
    @echo "Use MCP tool: mcp__plugin_greptile_greptile__search_code"

# List PRs for code review
greptile-prs:
    @echo "📋 Listing pull requests..."
    @echo "Use MCP tool: mcp__plugin_greptile_greptile__list_pull_requests"

# Get Greptile code review for PR
greptile-review pr:
    @echo "👀 Getting Greptile review for PR #{{pr}}..."
    @echo "Use MCP tool: mcp__plugin_greptile_greptile__trigger_code_review"

# ============================================
# SECURITY
# ============================================

# Run security audit
security:
    @echo "🔒 Running security audit..."
    @bandit -r . -x ./node_modules,./.venv 2>/dev/null || echo "bandit not installed"
    @{{js_manager}} audit 2>/dev/null || true
    @uv pip audit 2>/dev/null || echo "pip-audit not installed"

# Check for secrets
secrets:
    @echo "🔑 Scanning for secrets..."
    @detect-secrets scan . 2>/dev/null || echo "detect-secrets not installed"
    @gitleaks detect --source . 2>/dev/null || echo "gitleaks not installed"
