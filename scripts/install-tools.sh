#!/bin/bash
# CodeRush2 - Development Environment Setup
# Usage: ./install-tools.sh [--check] [--auto]
#   --check  Only check, don't install
#   --auto   Install without prompts

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
INSTALLED=0
MISSING_REQUIRED=0
MISSING_OPTIONAL=0

# Parse arguments
CHECK_ONLY=false
AUTO_INSTALL=false
for arg in "$@"; do
    case $arg in
        --check) CHECK_ONLY=true ;;
        --auto) AUTO_INSTALL=true ;;
    esac
done

echo ""
echo -e "${CYAN}CodeRush2 Environment Setup${NC}"
echo "================================"
echo ""

# Check if command exists
check_command() {
    local name=$1
    local cmd=$2
    local required=$3
    local install_hint=$4

    if command -v "$cmd" &> /dev/null; then
        local version=$($cmd --version 2>/dev/null | head -n1 | cut -c1-40)
        echo -e "${GREEN}✓${NC} $name: $version"
        ((INSTALLED++))
        return 0
    else
        if [ "$required" = "required" ]; then
            echo -e "${RED}✗${NC} $name (required)"
            echo -e "  ${YELLOW}Install:${NC} $install_hint"
            ((MISSING_REQUIRED++))
        else
            echo -e "${YELLOW}○${NC} $name (optional)"
            echo -e "  ${YELLOW}Install:${NC} $install_hint"
            ((MISSING_OPTIONAL++))
        fi
        return 1
    fi
}

# Install function
install_tool() {
    local name=$1
    local install_cmd=$2

    if [ "$CHECK_ONLY" = true ]; then
        return 1
    fi

    if [ "$AUTO_INSTALL" = false ]; then
        echo ""
        read -p "Install $name? (y/n) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi

    echo -e "${CYAN}Installing $name...${NC}"
    eval "$install_cmd"
    return 0
}

echo "Checking required tools..."
echo ""

# Required tools
check_command "Python" "python3" "required" "https://python.org"
check_command "Node.js" "node" "required" "https://nodejs.org"
check_command "npm" "npm" "required" "Comes with Node.js"
check_command "Git" "git" "required" "https://git-scm.com"

echo ""
echo "Checking development tools..."
echo ""

# Python package manager
if ! check_command "uv" "uv" "optional" "curl -LsSf https://astral.sh/uv/install.sh | sh"; then
    install_tool "uv" "curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# Just command runner (IMPORTANT for AI agents)
if ! check_command "Just" "just" "optional" "brew install just (macOS) or cargo install just"; then
    if [ "$(uname)" = "Darwin" ] && command -v brew &> /dev/null; then
        install_tool "Just" "brew install just"
    fi
fi

# Python linters
check_command "Ruff" "ruff" "optional" "uv tool install ruff"
check_command "Mypy" "mypy" "optional" "uv tool install mypy"
check_command "Bandit" "bandit" "optional" "uv tool install bandit"

echo ""
echo "Checking testing tools..."
echo ""

# Agent Browser
if ! check_command "Agent Browser" "agent-browser" "optional" "npm install -g agent-browser && agent-browser install"; then
    if install_tool "Agent Browser" "npm install -g agent-browser && agent-browser install"; then
        echo -e "${GREEN}✓${NC} Agent Browser installed"
    fi
fi

# Playwright (for Python E2E)
check_command "Playwright" "playwright" "optional" "uv tool install playwright && playwright install"

echo ""
echo "================================"
echo -e "${CYAN}Summary${NC}"
echo "================================"
echo ""
echo -e "Installed: ${GREEN}$INSTALLED${NC}"
echo -e "Missing required: ${RED}$MISSING_REQUIRED${NC}"
echo -e "Missing optional: ${YELLOW}$MISSING_OPTIONAL${NC}"
echo ""

if [ $MISSING_REQUIRED -gt 0 ]; then
    echo -e "${RED}Please install required tools before proceeding.${NC}"
    exit 1
fi

if [ $MISSING_OPTIONAL -gt 0 ] && [ "$CHECK_ONLY" = false ]; then
    echo "To install optional tools, run:"
    echo ""
    echo "  # Python tools"
    echo "  uv tool install ruff mypy bandit"
    echo ""
    echo "  # Agent Browser"
    echo "  npm install -g agent-browser"
    echo "  agent-browser install"
    echo ""
fi

echo -e "${GREEN}Environment ready!${NC}"
echo ""
echo "Next steps:"
echo "  1. cd your-project"
echo "  2. cp -r path/to/CodeRush2/.claude ."
echo "  3. Run Claude Code"
echo ""
