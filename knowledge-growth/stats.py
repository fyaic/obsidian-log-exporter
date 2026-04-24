"""Statistics and keyword extraction for daily reports."""

import re
from collections import Counter
from typing import List, Dict


def extract_keywords(text: str, top_n: int = 10) -> List[tuple]:
    """Extract Chinese and English keywords from text."""
    # Chinese words (2-8 chars)
    chinese_words = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
    # English words (3+ chars)
    english_words = re.findall(r'[a-zA-Z]{3,}', text)

    # Filter out common stop words
    stop_words = {
        "md", "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "had", "her", "was", "one", "our", "out", "day", "get", "has", "him",
        "his", "how", "its", "may", "new", "now", "old", "see", "two", "who",
        "boy", "did", "she", "use", "her", "way", "many", "oil", "sit", "set",
        "run", "eat", "far", "sea", "eye", "ago", "off", "too", "any", "say",
        "man", "try", "ask", "end", "why", "let", "put", "say", "she", "try",
        "way", "own", "say", "too", "old", "tell", "very", "when", "much", "would",
        "there", "their", "what", "said", "each", "which", "will", "about", "could",
        "other", "after", "first", "never", "these", "think", "where", "being",
        "every", "great", "might", "shall", "still", "those", "while", "this",
        "that", "with", "have", "from", "they", "know", "want", "been", "good",
        "much", "some", "time", "come", "than", "only", "them", "well", "were",
        "here", "look", "more", "also", "back", "work", "life", "even", "over",
        "such", "take", "year", "most", "long", "last", "find", "give", "does",
        "made", "part", "call", "came", "need", "feel", "seem", "turn", "hand",
        "high", "sure", "upon", "head", "help", "home", "side", "move", "both",
        "five", "once", "same", "must", "name", "left", "each", "done", "open",
        "case", "show", "live", "play", "went", "told", "seen", "hear", "talk",
        "soon", "read", "stop", "face", "fact", "land", "line", "kind", "next",
        "word", "came", "went", "told", "seen", "hear", "talk", "soon", "read",
        "stop", "face", "fact", "land", "line", "kind", "next", "word", "came",
        "没有", "可以", "就是", "这样", "我们", "他们", "一个", "什么", "这个",
        "那个", "不是", "但是", "如果", "因为", "所以", "然后", "现在", "今天",
        "需要", "进行", "通过", "使用", "已经", "作为", "自己", "如何", "一下",
        "开始", "完成", "查看", "设置", "相关", "问题", "注意", "以下", "以上",
        "文件", "内容", "笔记", "知识", "文档", "链接", "标题", "段落", "日期",
        "时间", "项目", "任务", "计划", "进度", "结果", "数据", "信息", "记录",
    }

    all_words = []
    for w in chinese_words:
        if w not in stop_words:
            all_words.append(w)
    for w in english_words:
        w_lower = w.lower()
        if w_lower not in stop_words:
            all_words.append(w_lower)

    counter = Counter(all_words)
    return counter.most_common(top_n)


def build_stats_panel(results_by_contributor: Dict[str, List[Dict]]) -> str:
    """Build a markdown statistics panel for the daily report."""
    lines = ["## 今日概览", ""]

    total_tracked = sum(len(v) for v in results_by_contributor.values())
    total_new = sum(
        sum(1 for f in files if f.get("is_new"))
        for files in results_by_contributor.values()
    )
    total_mod = total_tracked - total_new

    lines.append(f"- **贡献者**：{len(results_by_contributor)} 人")
    lines.append(f"- **文件数**：{total_tracked}（新增 {total_new}，修改 {total_mod}）")
    lines.append("")

    # Per-contributor breakdown
    for contributor in sorted(results_by_contributor.keys()):
        files = results_by_contributor[contributor]
        new_count = sum(1 for f in files if f.get("is_new"))
        mod_count = len(files) - new_count

        # Top folders
        folder_counts = {}
        for f in files:
            top = f["rel_path"].split("/")[0]
            folder_counts[top] = folder_counts.get(top, 0) + 1
        top_folders = sorted(folder_counts.items(), key=lambda x: -x[1])[:3]
        top_folders_str = ", ".join([f"{name}({cnt})" for name, cnt in top_folders])

        lines.append(f"- **{contributor}**：{len(files)} 份（新增 {new_count} / 修改 {mod_count}）— 主要活跃于：{top_folders_str}")

    lines.append("")

    # Keywords across all tracked files
    all_text = " ".join([f["title_hint"] + " " + f["content"][:500] for files in results_by_contributor.values() for f in files])
    keywords = extract_keywords(all_text, top_n=8)
    if keywords:
        lines.append(f"- **今日热词**：{', '.join([kw for kw, cnt in keywords])}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)
