"""
Obsidian Memory Sync v3 — Read-Write Closed Loop
Syncs memory files, distills conversations, and compiles MEMORY.md for retrieval.

Four-layer approach:
  1. Memory files → vault/inbox/ (incremental sync)
  2. Raw conversation export (via claude-extract)
  3. AI distillation → vault/sessions/ (via claude -p with Haiku)
  4. Compile MEMORY.md = index + recent summaries + vault pointers

Usage:
    python obsidian-sync.py                    # full sync (Stop hook default)
    python obsidian-sync.py --memory-only      # sync memory files only
    python obsidian-sync.py --compile-only     # recompile MEMORY.md only

Config via env vars:
    OBSIDIAN_VAULT      vault path (default: ~/obsidian-vault)
    CLAUDE_PROJECTS_DIR ~/.claude/projects (default: auto-detect)
    CLAUDE_EXPORT_DIR   staging dir (default: ~/claude-exports/code)
    HAIKU_MODEL         model for distillation (default: claude-haiku-4-5)
    CLAUDE_CMD          path to claude CLI (default: auto-detect)
    MAX_SUMMARY_TOKENS  token budget for MEMORY.md (default: 2000)
"""

import os
import re
import sys
import json
import hashlib
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# ── Configuration ───────────────────────────────────────────────────

def _default_projects_dir() -> Path:
    home = Path.home()
    return home / ".claude" / "projects"


VAULT = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "obsidian-vault")))
MEMORY_DIR = Path(os.environ.get("CLAUDE_PROJECTS_DIR", str(_default_projects_dir())))
EXPORT_DIR = Path(os.environ.get("CLAUDE_EXPORT_DIR", str(Path.home() / "claude-exports" / "code")))
SESSIONS_DIR = VAULT / "sessions"
LOG_FILE = VAULT / "logs" / "sync.log"
MAX_SUMMARY_TOKENS = int(os.environ.get("MAX_SUMMARY_TOKENS", "2000"))


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


# ── Helpers ─────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_haiku_model() -> str:
    return os.environ.get("HAIKU_MODEL", os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-5"))


def get_claude_cmd() -> str:
    env_cmd = os.environ.get("CLAUDE_CMD")
    if env_cmd and Path(env_cmd).exists():
        return env_cmd
    cmd = shutil.which("claude")
    if cmd:
        return cmd
    for candidate in [
        r"C:\npm-global\claude.cmd",
        r"C:\npm-global\claude",
        "/usr/local/bin/claude",
        str(Path.home() / ".npm-global" / "bin" / "claude"),
    ]:
        if Path(candidate).exists():
            return candidate
    return "claude"


def get_extract_cmd() -> str:
    cmd = shutil.which("claude-extract")
    if cmd:
        return cmd
    venv = Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "venv" / "Scripts" / "claude-extract.exe"
    if venv.exists():
        return str(venv)
    return "claude-extract"


def get_current_project_memory_dir() -> Path:
    candidates = []
    for d in MEMORY_DIR.iterdir():
        if d.is_dir() and (d / "memory").exists():
            candidates.append(d / "memory")
    if not candidates:
        default = MEMORY_DIR / "default" / "memory"
        default.mkdir(parents=True, exist_ok=True)
        return default
    cwd = os.getcwd().lower()
    for c in candidates:
        parent_name = c.parent.name.lower()
        if parent_name in cwd.replace("\\", "-").replace("/", "-").replace(":", "").lower():
            return c
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ── Layer 1: Memory file sync ──────────────────────────────────────

def sync_memory_files() -> int:
    copied = 0
    for project_dir in MEMORY_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.exists():
            continue

        project_name = project_dir.name.replace("--", "-").strip("-")[:30]

        for md_file in memory_dir.glob("*.md"):
            if md_file.name == "MEMORY.md":
                continue

            dest = VAULT / "inbox" / f"{project_name}_{md_file.name}"
            if dest.exists():
                if md_file.stat().st_mtime <= dest.stat().st_mtime:
                    continue

            content = md_file.read_text(encoding="utf-8")
            if not content.strip().startswith("---"):
                title = md_file.stem.replace("-", " ").replace("_", " ").title()
                content = f"""---
title: "{title}"
created: {today()}
updated: {today()}
tags: [memory, auto-sync]
type: note
source: claude-code-memory
project: {project_name}
---

""" + content

            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            copied += 1
    return copied


# ── Layer 2: Export raw conversation ────────────────────────────────

def export_latest_conversation() -> Path | None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    before = set(EXPORT_DIR.glob("*.md"))

    try:
        subprocess.run(
            [get_extract_cmd(), "--recent", "1", "--output", str(EXPORT_DIR), "--format", "markdown"],
            capture_output=True, text=True, timeout=25,
            encoding="utf-8", errors="replace"
        )
    except subprocess.TimeoutExpired:
        log("claude-extract timed out (25s)")
        return None
    except Exception as e:
        log(f"claude-extract failed: {e}")
        return None

    after = set(EXPORT_DIR.glob("*.md"))
    new_files = after - before
    if not new_files:
        return None
    return max(new_files, key=lambda f: f.stat().st_mtime)


# ── Layer 3: AI distillation ───────────────────────────────────────

DISTILL_PROMPT = """你是一个对话提炼专家。将以下 Claude Code 对话提炼为结构化的 Obsidian 笔记。

要求：
- 第一行是标题：# + 5-8个字的中文描述性标题
- 只保留有价值的信息，丢弃所有过程性内容
- 按以下结构输出（省略不适用的部分）：

## 目标
## 关键发现
## 决策记录
## 修改的文件
## 未解决的问题
## 可复用的经验

对话内容：
"""


def distill_conversation(raw_path: Path) -> str | None:
    content = raw_path.read_text(encoding="utf-8")

    if len(content) < 500:
        log("Conversation too short, skipping distillation")
        return None

    max_chars = 12000
    if len(content) <= max_chars:
        segments = [content]
    else:
        segments = []
        remaining = content
        while remaining and len(segments) < 3:
            if len(remaining) <= max_chars:
                segments.append(remaining)
                break
            cut = remaining.rfind("\n\n", 0, max_chars)
            if cut < max_chars // 2:
                cut = remaining.rfind("\n", 0, max_chars)
            if cut < max_chars // 4:
                cut = max_chars
            segments.append(remaining[:cut])
            remaining = remaining[cut:]

    all_summaries = []
    model = get_haiku_model()
    claude_cmd = get_claude_cmd()

    for i, segment in enumerate(segments):
        prompt = DISTILL_PROMPT + segment
        if len(segments) > 1:
            prompt = f"这是对话的第 {i+1}/{len(segments)} 部分：\n" + prompt

        try:
            result = subprocess.run(
                [claude_cmd, "-p", "--model", model],
                input=prompt,
                capture_output=True, text=True, timeout=60,
                encoding="utf-8", errors="replace"
            )
            if result.returncode == 0 and result.stdout.strip():
                all_summaries.append(result.stdout.strip())
        except subprocess.TimeoutExpired:
            log(f"claude -p timed out on segment {i+1}")
        except Exception as e:
            log(f"claude -p failed on segment {i+1}: {e}")

    if not all_summaries:
        return None

    if len(all_summaries) == 1:
        return all_summaries[0]

    merged = all_summaries[0]
    for extra in all_summaries[1:]:
        sections = re.findall(r'(## .+?)(?=## |\Z)', extra, re.DOTALL)
        for section in sections:
            heading = re.match(r'## (.+)', section)
            if heading and heading.group(1) not in merged:
                merged += "\n\n" + section.strip()
    return merged


def save_session_note(summary: str, raw_path: Path) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    first_line = summary.split("\n")[0].strip()
    title = re.sub(r'^#\s*', '', first_line)[:50]
    slug = re.sub(r'[^\w一-鿿]', '-', title).strip('-')[:30]

    h = content_hash(summary)
    filename = f"{today()}-{h}-{slug}.md"

    existing = list(SESSIONS_DIR.glob(f"{today()}-{h}-*.md"))
    if existing:
        log(f"Session note already exists: {existing[0].name}, skipping")
        return existing[0]

    note = f"""---
title: "{title}"
created: {today()}
tags: [session, auto-distilled]
type: log
source: claude-code
---

{summary}

---
> 原始对话：`{raw_path.name}`
"""

    dest = SESSIONS_DIR / filename
    dest.write_text(note, encoding="utf-8")
    log(f"Session note saved: {dest.name}")
    return dest


# ── Layer 4: Compile MEMORY.md ─────────────────────────────────────

SKIP_SECTIONS = {"---", "#", "name:", "description:", "metadata:", "type:", "tags:"}


def _extract_description(content: str) -> str:
    fm_match = re.search(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if fm_match:
        desc_match = re.search(r'^description:\s*(.+)', fm_match.group(1), re.MULTILINE)
        if desc_match:
            return desc_match.group(1).strip().rstrip("- ")[:80]
    for line in content.split("\n"):
        line = line.strip()
        if line and not any(line.startswith(s) for s in SKIP_SECTIONS):
            return line[:80]
    return ""


def compile_memory_md():
    memory_dir = get_current_project_memory_dir()
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_md = memory_dir / "MEMORY.md"

    entries = []
    for md_file in sorted(memory_dir.glob("*.md")):
        if md_file.name == "MEMORY.md":
            continue
        content = md_file.read_text(encoding="utf-8")
        desc = _extract_description(content)
        entries.append((md_file.stem, desc))

    recent_sessions = []
    if SESSIONS_DIR.exists():
        session_files = sorted(SESSIONS_DIR.glob("*.md"), reverse=True)
        seen_dates = set()
        total_chars = 0
        char_budget = MAX_SUMMARY_TOKENS * 2
        for sf in session_files:
            date_match = re.match(r'(\d{4}-\d{2}-\d{2})', sf.name)
            if not date_match:
                continue
            date_str = date_match.group(1)
            if date_str in seen_dates and len([s for s in recent_sessions if s[0] == date_str]) >= 2:
                continue
            if date_str not in seen_dates and len(seen_dates) >= 3:
                break
            seen_dates.add(date_str)
            content = sf.read_text(encoding="utf-8")
            title_match = re.search(r'title:\s*"(.+?)"', content)
            title = title_match.group(1) if title_match else sf.stem
            brief = ""
            goal_match = re.search(r'## 目标\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
            if goal_match:
                brief = goal_match.group(1).strip().split("\n")[0][:100]
            entry_chars = len(date_str) + len(title) + len(brief)
            if total_chars + entry_chars > char_budget:
                break
            total_chars += entry_chars
            recent_sessions.append((date_str, title, brief, sf.name))

    lines = ["# 记忆索引\n"]

    if recent_sessions:
        lines.append("## 最近会话摘要\n")
        for date, title, brief, fname in recent_sessions:
            line = f"- {date}: {title}"
            if brief:
                line += f" — {brief}"
            lines.append(line)
        lines.append(f"- 完整笔记: `{SESSIONS_DIR}`\n")

    if entries:
        lines.append("## 记忆文件\n")
        for stem, desc in entries:
            lines.append(f"- [{stem}]({stem}.md) — {desc}" if desc else f"- [{stem}]({stem}.md)")

    lines.append("\n## 知识库位置\n")
    lines.append(f"- Obsidian vault: `{VAULT}`")
    lines.append(f"- 会话摘要: `{SESSIONS_DIR}`")
    lines.append(f"- inbox: `{VAULT / 'inbox'}`")
    lines.append(f"- 永久笔记: `{VAULT / 'permanent'}`")

    content = "\n".join(lines) + "\n"
    memory_md.write_text(content, encoding="utf-8")
    log(f"MEMORY.md compiled ({len(entries)} entries, {len(recent_sessions)} sessions)")


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Obsidian Memory Sync for Claude Code")
    parser.add_argument("--memory-only", action="store_true", help="Only sync memory files")
    parser.add_argument("--compile-only", action="store_true", help="Only recompile MEMORY.md")
    args = parser.parse_args()

    log("=== Sync started (v3) ===")

    if args.compile_only:
        compile_memory_md()
        log("=== Sync done (compile-only) ===")
        return

    mem_count = sync_memory_files()
    log(f"Memory files synced: {mem_count}")

    if args.memory_only:
        compile_memory_md()
        log("=== Sync done (memory-only) ===")
        return

    raw_path = export_latest_conversation()
    if raw_path:
        log(f"Exported: {raw_path.name}")
        summary = distill_conversation(raw_path)
        if summary:
            save_session_note(summary, raw_path)
        else:
            log("Distillation skipped/failed, raw export kept")
    else:
        log("No new conversation to export")

    compile_memory_md()
    log("=== Sync done ===")


if __name__ == "__main__":
    main()
