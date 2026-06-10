# Obsidian Memory System for Claude Code

AI 驱动的 Claude Code 记忆系统，通过 Obsidian vault 实现跨会话知识持久化。

## 效果

- 每次对话结束自动提炼摘要，存入 Obsidian vault
- 下次对话自动加载上次的上下文和记忆
- 结构化笔记：目标、关键发现、决策、修改文件、可复用经验
- Obsidian 图谱视图可视化知识关联

## 前提

- [Claude Code](https://claude.ai/code) CLI
- [Obsidian](https://obsidian.md)（免费）
- Python 3.11+
- `pip install claude-conversation-extractor`

## 安装

```bash
git clone <this-repo>
cd obsidian-memory
bash install.sh [vault-path]
```

不传路径默认用 `~/obsidian-vault`。

## 架构

```
SessionEnd (Stop hook)
    ├── Layer 1: memory 文件同步 → vault/inbox/
    ├── Layer 2: claude-extract 导出对话
    ├── Layer 3: AI 提炼 → vault/sessions/ (claude -p Haiku)
    └── Layer 4: 编译 MEMORY.md = 索引 + 最近摘要 + 路径
        ↓
下次启动 → Claude Code 自动读 MEMORY.md → 携带上下文
```

## 配置

通过环境变量自定义：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OBSIDIAN_VAULT` | `~/obsidian-vault` | Obsidian vault 路径 |
| `CLAUDE_PROJECTS_DIR` | `~/.claude/projects` | Claude Code 项目目录 |
| `CLAUDE_EXPORT_DIR` | `~/claude-exports/code` | 对话导出中转目录 |
| `HAIKU_MODEL` | `claude-haiku-4-5` | 提炼用的模型 |
| `CLAUDE_CMD` | 自动检测 | claude CLI 路径 |
| `MAX_SUMMARY_TOKENS` | `2000` | MEMORY.md token 预算 |

## 手动命令

```bash
# 完整同步（Stop hook 默认行为）
python obsidian-sync.py

# 只同步 memory 文件
python obsidian-sync.py --memory-only

# 只重新编译 MEMORY.md
python obsidian-sync.py --compile-only
```

## Vault 目录

| 目录 | 用途 |
|------|------|
| `inbox/` | 自动同步的 memory 文件 |
| `sessions/` | AI 提炼的会话摘要 |
| `permanent/` | 手动沉淀的长期知识 |
| `logs/` | 同步日志 |
| `templates/` | 笔记模板 |
| `graphify/` | 代码知识图谱 |

## License

MIT
