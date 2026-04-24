"""Generate daily report via LLM."""

import os
import sys
import datetime
from pathlib import Path
from typing import Dict, List

# Fix Windows PowerShell GBK encoding crash on emoji/special chars
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx

from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    REPORTS_DIR,
)
from stats import build_stats_panel


def build_prompt(contributor: str, files: List[Dict]) -> str:
    """Build LLM prompt for a single contributor's daily contribution."""
    file_blocks = []
    total_new = sum(1 for f in files if f.get("is_new"))
    total_mod = len(files) - total_new

    for f in files:
        # Truncate content to avoid token overload
        content_snippet = f["content"][:1200]
        if len(f["content"]) > 1200:
            content_snippet += "\n...（内容已截断）"
        action = "新增" if f.get("is_new") else "修改"
        file_blocks.append(
            f"【文件】{f['rel_path']} ({action})\n"
            f"【修改时间】{f['mtime_str']}\n"
            f"【内容摘要/开头】\n{content_snippet}\n"
        )

    files_text = "\n---\n".join(file_blocks)

    prompt = f"""你是一位知识库增量分析师。请根据以下 {contributor} 在 Obsidian 知识库中的更新内容，生成一段结构化的贡献日报。

统计：今日共 {len(files)} 份文件（新增 {total_new}，修改 {total_mod}）。

要求：
1. 用中文输出，总字数 250-400 字
2. 结构必须包含：
   - 【核心产出】用 1-2 句话概括今日最重要的贡献
   - 【内容梳理】按主题/项目分组，列出每份文件的价值点（不要简单复述标题，要提炼做了什么、解决了什么问题、产出了什么结论）
   - 【关联与延续】如有多个文件指向同一主题，请指出这是该主题的延续还是突破
3. 语气像一位了解项目的同事写的日报，简洁、有信息量、不寒暄
4. 不要编造文件中没有的信息

以下是原始文件内容：

{files_text}

请直接输出正文，不需要标题和问候语。"""

    return prompt


def heuristic_summary(contributor: str, files: List[Dict]) -> str:
    """Generate a naive heuristic summary when LLM is not available."""
    lines = [f"📌 **{contributor} 今日核心产出**：共更新 {len(files)} 份文件。"]
    lines.append("")

    # Group by top-level folder
    folders = {}
    for f in files:
        top = f["rel_path"].split("/")[0]
        folders.setdefault(top, []).append(f)

    lines.append("📝 **具体内容**：")
    for folder, folder_files in sorted(folders.items(), key=lambda x: -len(x[1])):
        lines.append(f"- **{folder}**（{len(folder_files)} 个）：")
        for f in folder_files:
            title = f["title_hint"]
            action = "新增" if f.get("is_new") else "修改"
            lines.append(f"  - {action} `{title}`")
    lines.append("")

    # Simple cross-file keyword matching for "关联发现"
    all_titles = [f["title_hint"] for f in files]
    common_words = set()
    for t in all_titles:
        words = t.replace("-", " ").replace("_", " ").split()
        for w in words:
            if len(w) >= 2 and w.lower() not in {"md", "the", "and", "or", "of", "to", "a", "in", "for", "on", "with", "by", "is", "at"}:
                common_words.add(w.lower())

    if len(files) > 1:
        lines.append("🔗 **关联发现**：")
        lines.append(f"- 今日 {len(files)} 份文件分布于 {len(folders)} 个文件夹下，建议检查是否有同一主题的连续迭代。")
        lines.append("")

    return "\n".join(lines)


def call_llm(prompt: str) -> str:
    """Call LLM API with the prompt."""
    if not OPENAI_API_KEY:
        return ""

    try:
        resp = httpx.post(
            f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "你是一位专业的知识库增量汇报生成助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.5,
                "max_tokens": 1500,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[LLM 调用失败: {e}]"


def generate_contributor_summary(contributor: str, files: List[Dict]) -> str:
    """Generate summary for a contributor, using LLM if available, fallback to heuristic."""
    if OPENAI_API_KEY:
        prompt = build_prompt(contributor, files)
        return call_llm(prompt)
    else:
        return heuristic_summary(contributor, files)


def generate_daily_report(results_by_contributor: Dict[str, List[Dict]]) -> str:
    """Generate full markdown daily report for all contributors."""
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    report_lines = [
        f"# 知识库增量日报 — {today_str}",
        "",
        "> 自动生成于 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "",
    ]

    # Stats panel
    report_lines.append(build_stats_panel(results_by_contributor))

    # Process each tracked contributor
    for contributor in sorted(results_by_contributor.keys()):
        files = results_by_contributor[contributor]
        report_lines.append(f"## {contributor}")
        report_lines.append(f"**今日文件数：** {len(files)}")
        report_lines.append("")

        # Generate summary (LLM or heuristic fallback)
        summary = generate_contributor_summary(contributor, files)
        report_lines.append(summary)
        report_lines.append("")

        # File list (collapsed for brevity)
        report_lines.append("<details>")
        report_lines.append("<summary>📁 原始文件清单（点击展开）</summary>")
        report_lines.append("")
        for f in files:
            report_lines.append(f"- `{f['rel_path']}` — *{f['mtime_str']}*")
        report_lines.append("</details>")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

    # Cross-reference hint
    all_files = []
    for files in results_by_contributor.values():
        all_files.extend(files)

    if len(results_by_contributor) > 1:
        report_lines.append("## 跨贡献者关联")
        report_lines.append("")
        report_lines.append(
            f"今日共有 **{len(all_files)}** 份文件更新，"
            f"涉及 **{len(results_by_contributor)}** 位贡献者。"
            "建议关注是否有主题交叉或可以联动的内容。"
        )
        report_lines.append("")

    return "\n".join(report_lines)


def save_report(report_md: str) -> Path:
    """Save report to disk and return path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"daily_report_{today_str}.md"
    path = REPORTS_DIR / filename
    path.write_text(report_md, encoding="utf-8")
    return path
