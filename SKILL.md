---
name: obsidian-memory
description: Claude Code Obsidian memory system — AI-powered session distillation, automatic memory sync, and read-write closed loop via Stop hook.
triggers:
  - "记忆" / "memory" / "obsidian" / "vault" 相关话题
  - 查看同步状态 / 手动触发同步
---

# Obsidian Memory System

Claude Code 的 AI 记忆系统，通过 Obsidian vault 实现跨会话知识持久化。

## 架构

```
SessionEnd (Stop hook)
    ├── Layer 1: memory 文件同步 → vault/inbox/
    ├── Layer 2: claude-extract 导出对话
    ├── Layer 3: AI 提炼 → vault/sessions/ (claude -p Haiku)
    └── Layer 4: 编译 MEMORY.md (索引 + 最近摘要 + 路径)
        ↓
下次启动 → Claude Code 自动读 MEMORY.md → 携带上下文
```

## 用户命令

| 场景 | 操作 |
|------|------|
| 查看同步日志 | 读取 vault 下的 `logs/sync.log` |
| 手动触发同步 | `python <scripts-dir>/obsidian-sync.py` |
| 查看 vault 结构 | 浏览 Obsidian 中的 vault 目录 |
| 永久沉淀 | 将 inbox/ 中有价值的笔记移到 permanent/ |

## vault 目录结构

| 目录 | 用途 |
|------|------|
| `inbox/` | 自动同步的 memory 文件（来自 ~/.claude/projects/） |
| `sessions/` | AI 提炼的会话摘要（自动生成） |
| `permanent/` | 手动沉淀的长期知识 |
| `logs/` | 同步日志 |
| `templates/` | 笔记模板 |
| `graphify/` | 代码知识图谱（配合 graphify 插件使用） |

## 文件位置

- 同步脚本: `~/.claude/skills/obsidian-memory/scripts/obsidian-sync.py`
- 安装脚本: `~/.claude/skills/obsidian-memory/install.sh`
- Vault: 由安装时指定（默认 `~/obsidian-vault`）
- Hook 配置: `~/.claude/settings.json` → `hooks.Stop`

## 注意事项

- MEMORY.md 由脚本自动编译，不要手动编辑
- session 摘要使用 `claude -p` (Haiku)，需要 `claude` CLI 可用
- 提炼超时 60 秒，超长对话自动分段处理
- 去重使用 md5 hash，同一天相同内容不会重复写入
