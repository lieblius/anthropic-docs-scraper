#!/bin/bash
REPO_DIR=$(pwd)
DOCS_DIR="$REPO_DIR/docs/docs/claude-code"
PROJECT_COMMANDS_DIR="$REPO_DIR/.claude/commands"
USER_COMMANDS_DIR="$HOME/.claude/commands"

if [ ! -d "$DOCS_DIR" ]; then
    echo "Error: docs not found. Run 'just update' first"
    exit 1
fi

mkdir -p "$PROJECT_COMMANDS_DIR"
mkdir -p "$USER_COMMANDS_DIR"

cat > "$PROJECT_COMMANDS_DIR/load-claude-docs.md" << EOF
# Read All Claude Code Docs

Use Bash tool to concatenate all Claude Code documentation at once:

\`\`\`bash
cat $REPO_DIR/docs/docs/claude-code/*.md
\`\`\`

After reading all the documentation content, respond with:

"Read."
EOF

ln -sf "$PROJECT_COMMANDS_DIR/load-claude-docs.md" "$USER_COMMANDS_DIR/load-claude-docs.md"