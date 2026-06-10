#!/bin/bash
# Obsidian Memory System — Install Script
# Usage: bash install.sh [VAULT_PATH]
#
# Prerequisites:
#   - Claude Code CLI installed
#   - Obsidian installed
#   - Python 3.11+
#   - claude-extract: pip install claude-conversation-extractor

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT="${1:-$HOME/obsidian-vault}"
SCRIPTS_DIR="$HOME/.claude/skills/obsidian-memory/scripts"

echo "=== Obsidian Memory System Installer ==="
echo ""

# 1. Create vault structure
echo "[1/5] Creating vault structure at $VAULT ..."
mkdir -p "$VAULT"/{inbox,sessions,permanent,fleeting,logs,references,templates,graphify,chats/code,chats/web}

# 2. Create CLAUDE.md
echo "[2/5] Writing vault CLAUDE.md ..."
cat > "$VAULT/CLAUDE.md" << 'EOF'
# Vault — Instructions for Claude Code

## What is this vault
Centralized knowledge base for all projects.
Persistent memory across sessions.

## Zettelkasten Rules
- Use wikilinks: [[note-name]]
- Mandatory YAML frontmatter on every note
- One idea per note (atomic)

## Folder Convention
- `permanent/` — consolidated knowledge
- `inbox/` — auto-synced memory files
- `sessions/` — AI-distilled session summaries
- `logs/` — sync logs
- `templates/` — note templates
- `graphify/` — codebase knowledge graphs

## Graph View Filters
| Filter | Shows |
|--------|-------|
| `path:permanent` | Only permanent notes |
| `path:graphify` | Only codebase nodes |
| `tag:chat-import` | Only imported chats |
| `-path:graphify -path:chats` | Only manual notes |
EOF

# 3. Copy scripts
echo "[3/5] Installing scripts ..."
mkdir -p "$SCRIPTS_DIR"
cp "$SCRIPT_DIR/scripts/obsidian-sync.py" "$SCRIPTS_DIR/obsidian-sync.py"

# 4. Install Python dependencies
echo "[4/5] Installing Python dependencies ..."
pip install claude-conversation-extractor 2>/dev/null || echo "  (skip: claude-extract already installed or pip unavailable)"

# 5. Configure Stop hook
echo "[5/5] Configuring Stop hook ..."
SETTINGS="$HOME/.claude/settings.json"
if [ ! -f "$SETTINGS" ]; then
    echo '{}' > "$SETTINGS"
fi

# Use Python to merge hooks (preserves existing settings)
python3 -c "
import json, sys

settings_path = sys.argv[1]
sync_script = sys.argv[2]

with open(settings_path, 'r', encoding='utf-8') as f:
    d = json.load(f)

hooks = d.setdefault('hooks', {})
stop_hooks = hooks.setdefault('Stop', [])

# Check if our hook already exists
already = any(
    'obsidian-sync' in h.get('hooks', [{}])[0].get('command', '')
    for h in stop_hooks
    if h.get('hooks')
)

if not already:
    stop_hooks.append({
        'matcher': '',
        'hooks': [{
            'type': 'command',
            'command': f'python \"{sync_script}\"',
            'timeout': 90000
        }]
    })

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print('  Hook configured' if not already else '  Hook already exists')
" "$SETTINGS" "$SCRIPTS_DIR/obsidian-sync.py"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Vault:       $VAULT"
echo "Scripts:     $SCRIPTS_DIR"
echo "Hook:        ~/.claude/settings.json → hooks.Stop"
echo ""
echo "Usage:"
echo "  1. Open Obsidian → Create/open vault at $VAULT"
echo "  2. Start using Claude Code normally"
echo "  3. Session summaries auto-appear in vault/sessions/"
echo "  4. MEMORY.md auto-updates with context for next session"
echo ""
echo "Manual sync: python $SCRIPTS_DIR/obsidian-sync.py"
