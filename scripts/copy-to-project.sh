#!/bin/bash
# Copy CodeRush2 configuration to another project
# Usage: ./copy-to-project.sh /path/to/target/project

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get script directory (where CodeRush2 is)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

# Target project
TARGET_DIR="$1"

if [ -z "$TARGET_DIR" ]; then
    echo -e "${RED}Usage: $0 /path/to/target/project${NC}"
    exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED}Target directory does not exist: $TARGET_DIR${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}CodeRush2 Configuration Copy${NC}"
echo "================================"
echo ""
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

# Check if .claude already exists
if [ -d "$TARGET_DIR/.claude" ]; then
    echo -e "${YELLOW}Warning: .claude directory already exists in target${NC}"
    read -p "Overwrite? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    rm -rf "$TARGET_DIR/.claude"
fi

# Copy .claude directory
echo -e "${CYAN}Copying .claude directory...${NC}"
cp -r "$SOURCE_DIR/.claude" "$TARGET_DIR/.claude"
echo -e "${GREEN}✓${NC} .claude copied"

# Copy CLAUDE.md if it doesn't exist
if [ ! -f "$TARGET_DIR/CLAUDE.md" ]; then
    cp "$SOURCE_DIR/CLAUDE.md" "$TARGET_DIR/CLAUDE.md"
    echo -e "${GREEN}✓${NC} CLAUDE.md copied"
else
    echo -e "${YELLOW}○${NC} CLAUDE.md already exists, skipped"
fi

# Copy scripts
if [ ! -d "$TARGET_DIR/scripts" ]; then
    mkdir -p "$TARGET_DIR/scripts"
fi
cp "$SOURCE_DIR/scripts/install-tools.sh" "$TARGET_DIR/scripts/"
chmod +x "$TARGET_DIR/scripts/install-tools.sh"
echo -e "${GREEN}✓${NC} scripts copied"

echo ""
echo "================================"
echo -e "${GREEN}Configuration copied successfully!${NC}"
echo ""
echo "Next steps:"
echo "  1. cd $TARGET_DIR"
echo "  2. ./scripts/install-tools.sh --check"
echo "  3. Run Claude Code"
echo ""

# Run environment check
echo -e "${CYAN}Running environment check...${NC}"
echo ""
"$TARGET_DIR/scripts/install-tools.sh" --check || true
