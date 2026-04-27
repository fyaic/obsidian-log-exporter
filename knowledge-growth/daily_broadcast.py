"""Daily Knowledge Growth Broadcast — analytical daily report for cron/AI agent."""

import sys
import datetime
import re
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from scanner import scan_daily_increments


# ──────────────────────────────
# Document classification
# ──────────────────────────────

# Contributors considered part of the team for cross-attention purposes
_TEAM_MEMBERS = {"Rosetta", "Veil"}


def _classify_doc(rel_path: str, title: str) -> tuple:
    path_lower = rel_path.lower()
    title_lower = title.lower()
    full = path_lower + " " + title_lower

    parts = rel_path.split("/")
    if len(parts) == 1:
        display_path = "(root)"
    elif len(parts) == 2:
        display_path = parts[0]
    else:
        display_path = " / ".join(parts[:2])

    # Default: not noteworthy unless it matches a meaningful category
    doc_type = "文档"
    impact = "知识库有更新"
    suggestion = ""
    is_noteworthy = False

    if any(k in full for k in ["prd", "产品需求", "需求文档", "m0", "m01", "m02", "m03", "m04"]):
        doc_type = "PRD"
        impact = "产品需求/验收标准可能有更新"
        suggestion = "对照自检，确认实现覆盖"
        is_noteworthy = True
    elif any(k in full for k in ["验收", "checklist", "验收清单"]):
        doc_type = "验收清单"
        impact = "验收标准变了"
        suggestion = "新增文档建议对照自检"
        is_noteworthy = True
    elif any(k in full for k in ["官网", "文案", "roadmap", "定位", "发布会", "宣传"]):
        doc_type = "官网文案"
        impact = "产品定位/对外口径可能变化"
        suggestion = "同步术语，统一对外表述"
        is_noteworthy = True
    elif any(k in full for k in ["技术方案", "架构", "探针", "side panel", "wecom", "企业微信", "gateway", "权限配置", "接入方案"]):
        doc_type = "技术方案"
        impact = "技术实现方案/接入限制有更新"
        suggestion = "确认是否影响现有 PRD 假设"
        is_noteworthy = True
    elif any(k in full for k in ["技术讨论", "问题排查", "故障", "bug", "fix", "启动命令错误", "权限丢失", "连接问题"]):
        doc_type = "技术讨论"
        impact = "技术问题/排障记录有更新"
        suggestion = "关注问题根因，确认是否有通用解决方案"
        is_noteworthy = True
    elif any(k in full for k in ["会议纪要", "会议记录", "会议精神"]):
        doc_type = "会议纪要"
        impact = "会议决策/结论已记录"
        suggestion = "关注决策项，确认执行分工"
        is_noteworthy = True
    elif any(k in full for k in ["openclaw", "cron", "自动化", "工程", "工具链", "plugin", "插件开发"]):
        doc_type = "工程"
        impact = "自动化/工具链有更新"
        suggestion = "关注工具变更对 workflow 的影响"
        is_noteworthy = True
    elif any(k in full for k in ["hermes", "dsearch", "技术调研", "开发现状", "机会研究"]):
        doc_type = "技术调研"
        impact = "技术调研/方案有更新"
        suggestion = "关注技术选型影响"
        is_noteworthy = True
    elif any(k in full for k in ["功能能力", "进展梳理", "能力梳理", "功能列表"]):
        doc_type = "产品梳理"
        impact = "产品功能/进展有更新"
        suggestion = "同步团队，确认 roadmap 一致性"
        is_noteworthy = True
    elif any(k in full for k in ["用户手册", "使用说明", "操作指南", "手册"]):
        doc_type = "用户文档"
        impact = "用户-facing 文档有更新"
        suggestion = "确认是否需要同步给客户/用户"
        is_noteworthy = True
    # Low-value categories — explicitly not noteworthy
    elif any(k in full for k in ["调研", "分析", "推荐算法", "交传", "录音", "plaud", "转写"]):
        doc_type = "调研"
        impact = "调研案例库在扩展"
        suggestion = "暂不需要响应，信息同步即可"
    elif any(k in full for k in ["聊天记录", "wx聊天记录", "聊天"]):
        doc_type = "聊天记录"
        impact = "群聊信息已归档"
        suggestion = "快速浏览，提取关键决策/行动项"
    elif any(k in full for k in ["日报", "观测日记", "跟踪记录", "周报"]):
        doc_type = "跟踪记录"
        impact = "日常跟踪/观测记录有更新"
        suggestion = "关注异常指标或趋势变化"
    elif any(k in full for k in ["报销", "行政", "注意事项", "部门报销"]):
        doc_type = "行政"
        impact = "行政/财务流程有更新"
        suggestion = "确认是否需要执行相关流程"
    elif any(k in full for k in ["资料收集", "web clippings", "clippings", "newsletter", "rss"]):
        doc_type = "资料收集"
        impact = "外部资料/参考信息已归档"
        suggestion = "快速浏览，提取与当前项目相关的洞察"

    return display_path, doc_type, impact, suggestion, is_noteworthy


def _normalize_title(title: str) -> str:
    t = re.sub(r'[\s_-]*[vV]\d+$', '', title)
    t = re.sub(r'^\d{4}-\d{2}-\d{2}[-_]', '', t)
    t = re.sub(r'^\d{2}-\d{2}[-_]', '', t)
    return t.strip()


def _extract_theme(rel_path: str, title: str = "") -> str:
    path_lower = rel_path.lower()
    title_lower = title.lower()
    full = path_lower + " " + title_lower

    path_segments = [p.lower() for p in rel_path.split("/")[:2]]
    if any("side panel" in p or "wecom" in p for p in path_segments):
        return "WeCom Side Panel 技术方案"
    if any(k in full for k in ["prd", "第二阶段", "验收清单", "m01 ", "m02 ", "m03 ", "m04 "]):
        return "第二阶段 PRD 迭代"
    if any(k in full for k in ["官网", "roadmap", "文案", "发布会", "产品定位"]):
        return "官网文案与产品定位"
    if "dsearch" in path_lower:
        return "技术调研"
    if any(k in full for k in ["录音", "plaud", "推荐算法", "交传"]):
        return "调研与信息归档"
    if any(k in full for k in ["会议纪要", "会议精神", "会议记录"]):
        return "会议决策跟进"
    if any(k in full for k in ["hermes", "gateway", "权限配置"]):
        return "Hermes 技术对接"
    if any(k in full for k in ["openclaw", "cron", "自动化", "工程"]):
        return "工程与工具链"
    if any(k in full for k in ["技术讨论", "问题排查", "故障"]):
        return "技术问题排查"
    if any(k in full for k in ["用户手册", "使用说明"]):
        return "用户文档"
    if any(k in full for k in ["报销", "行政", "admin"]):
        return "行政事务"
    if any(k in full for k in ["moltbot", "token", "观测"]):
        return "Moltbot 跟踪"
    if any(k in full for k in ["日报", "观测日记", "跟踪记录", "周报"]):
        return "跟踪记录"
    if any(k in full for k in ["聊天记录", "wx聊天"]):
        return "信息归档"

    parts = rel_path.split("/")
    for p in parts:
        if p.lower() not in ("t-b", "p-m", "录音", "dsearch") and not p.startswith("0-"):
            return p
    return parts[0] if parts else "其他"


# ──────────────────────────────
# Helpers
# ──────────────────────────────

_GENERIC_FILENAMES = {"final_delivery", "report", "raw", "result", "output", "summary", "index", "draft", "tmp"}

_DOC_TYPE_PRIORITY = {
    "PRD": 5, "验收清单": 5, "技术方案": 4, "官网文案": 4,
    "产品梳理": 3, "技术讨论": 3, "技术调研": 2, "工程": 2,
    "会议纪要": 1, "用户文档": 1, "文档": 0,
}


def _clean_files(files):
    return [f for f in files if f["filename"].replace(".md", "").lower() not in _GENERIC_FILENAMES]


def _detect_version_iteration(files):
    """Return list of (base_name, max_version, count) for version iterations."""
    by_folder = defaultdict(lambda: defaultdict(set))
    for f in files:
        parts = f["rel_path"].split("/")
        folder = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        name = f["filename"].replace(".md", "")
        m = re.search(r'^(.*?)[\s_-]*[vV](\d+)$', name)
        if m:
            base = m.group(1).strip()
            ver = int(m.group(2))
            by_folder[folder][base].add(ver)

    results = []
    for folder, base_map in by_folder.items():
        for base, versions in base_map.items():
            if len(versions) >= 2:
                results.append((base, max(versions), len(versions)))
    return results


def _detect_clusters(files):
    """Return list of (norm_title, count) for title clusters."""
    norm_counts = Counter(_normalize_title(f["title_hint"]) for f in files)
    return [(t, c) for t, c in norm_counts.most_common() if c >= 2]


# ──────────────────────────────
# Cross-attention module
# ──────────────────────────────

def _build_cross_attention(results_by_contributor: dict) -> list:
    # Only team members participate in cross-attention
    all_people = [c for c in results_by_contributor if c in _TEAM_MEMBERS]
    if len(all_people) < 2:
        return []

    all_noteworthy = []
    seen = set()

    for contributor, files in results_by_contributor.items():
        if contributor not in _TEAM_MEMBERS:
            continue
        for f in files:
            if f["filename"].replace(".md", "").lower() in _GENERIC_FILENAMES:
                continue
            dp, dt, imp, sug, nw = _classify_doc(f["rel_path"], f["title_hint"])
            if not nw:
                continue
            parts = f["rel_path"].split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
            norm_title = _normalize_title(f["title_hint"])
            dedup_key = (contributor, folder, norm_title)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            priority = _DOC_TYPE_PRIORITY.get(dt, 0)
            all_noteworthy.append((contributor, f, dp, dt, imp, sug, priority))

    if not all_noteworthy:
        return []

    blocks = []
    for observer in all_people:
        watch_items = []
        for contributor, f, dp, dt, imp, sug, priority in all_noteworthy:
            if contributor == observer:
                continue
            watch_items.append({
                "watch_who": contributor,
                "file": f,
                "path": dp,
                "impact": imp,
                "suggestion": sug,
                "priority": priority,
            })

        if not watch_items:
            continue

        # Sort by priority, then cap to avoid spam
        watch_items.sort(key=lambda x: (-x["priority"], x["watch_who"]))
        watch_items = watch_items[:5]

        primary_counter = Counter()
        for item in watch_items:
            primary_counter[item["watch_who"]] += item["priority"] + 1
        primary = primary_counter.most_common(1)[0][0]

        blocks.append((observer, primary, watch_items))

    return blocks


# ──────────────────────────────
# Personal summary — narrative, no doc titles
# ──────────────────────────────

def _theme_score(theme, tfiles):
    """Score a theme by count + noteworthy bonus."""
    count = len(tfiles)
    nw_bonus = sum(1 for f in tfiles if _classify_doc(f["rel_path"], f["title_hint"])[4])
    return count + nw_bonus * 3


def _summarize_person(contributor: str, files: list) -> list:
    """
    Return 2-4 narrative bullets summarizing this person's day.
    No document titles, no metadata — just conclusions and insights.
    """
    files = _clean_files(files)
    if not files:
        return []

    # Group by theme
    theme_files = defaultdict(list)
    for f in files:
        theme = _extract_theme(f["rel_path"], f["title_hint"])
        theme_files[theme].append(f)

    # Sort by score (not just count) so noteworthy themes rank higher
    themes = sorted(theme_files.items(), key=lambda x: -_theme_score(x[0], x[1]))
    bullets = []

    # 1. Overall direction
    main_themes = [(t, fs) for t, fs in themes if len(fs) >= 2]
    if len(main_themes) >= 2:
        names = [t for t, _ in main_themes[:2]]
        bullets.append(f"今日横跨{'、'.join(names)}，多线程推进")
    elif main_themes:
        bullets.append(f"主攻方向：{main_themes[0][0]}")
    else:
        single_themes = [t for t, _ in themes[:3]]
        bullets.append(f"今日涉及{'、'.join(single_themes)}")

    # 2. Per-theme insights (max 3 themes)
    for theme, tfiles in themes[:3]:
        count = len(tfiles)
        dp, dt, imp, sug, _ = _classify_doc(tfiles[0]["rel_path"], tfiles[0]["title_hint"])

        # Skip low-value tracking themes in summary
        if dt in ("跟踪记录", "聊天记录", "行政") and count <= 2:
            continue

        # Version iteration?
        versions = set()
        for f in tfiles:
            m = re.search(r'[vV](\d+)', f["filename"])
            if m:
                versions.add(int(m.group(1)))
        if len(versions) >= 2:
            max_v = max(versions)
            bullets.append(f"{theme}已迭代至 V{max_v}，定位趋于明确，建议团队同步")
            continue

        # Concentrated updates?
        clusters = _detect_clusters(tfiles)
        for norm_title, cnt in clusters:
            if cnt >= 3:
                if dt == "PRD":
                    bullets.append(f"「{norm_title}」集中更新 {cnt} 份，验收标准可能变化，建议相关方对照自检")
                elif dt == "官网文案":
                    bullets.append(f"「{norm_title}」集中更新 {cnt} 份，对外口径可能变化，建议团队同步")
                else:
                    bullets.append(f"「{norm_title}」集中更新 {cnt} 份")
                break
            elif cnt >= 2:
                bullets.append(f"「{norm_title}」连续更新 {cnt} 份")
                break
        else:
            # No cluster — type-based insight
            if dt == "技术方案" and count >= 2:
                bullets.append(f"{theme}持续深入，技术限制与架构判断已有初步结论，需确认是否影响下游 PRD")
            elif dt == "官网文案" and count >= 2:
                bullets.append(f"{theme}多份并行，对外口径可能变化，建议团队同步术语")
            elif dt == "PRD" and count >= 2:
                bullets.append(f"{theme}密集迭代，验收标准可能变化，建议开发侧对照自检")
            elif dt == "调研" and count >= 2:
                bullets.append(f"{theme}案例库持续扩展，暂不需要响应，信息同步即可")
            elif dt == "会议决策跟进":
                bullets.append(f"有 {count} 份会议相关记录，建议关注决策项与执行分工")
            elif dt == "技术讨论":
                bullets.append(f"有 {count} 份技术问题/排障记录，建议关注根因与通用解决方案")
            elif count >= 3:
                bullets.append(f"{theme}产出 {count} 份，较为活跃")
            elif count == 2:
                bullets.append(f"{theme}有 {count} 份更新")

    return bullets[:4]


# ──────────────────────────────
# Global insights — direction + overlap, not volume
# ──────────────────────────────

def _build_global_insights(results_by_contributor: dict, all_files: list) -> list:
    insights = []
    clean = _clean_files(all_files)

    # Per-person main direction (use _theme_score, not raw count)
    person_themes = {}
    person_themes_full = {}
    for c, files in results_by_contributor.items():
        if c not in _TEAM_MEMBERS:
            continue
        cf = _clean_files(files)
        if not cf:
            continue
        theme_files = defaultdict(list)
        for f in cf:
            theme = _extract_theme(f["rel_path"], f["title_hint"])
            theme_files[theme].append(f)
        if theme_files:
            top_theme = max(theme_files.keys(), key=lambda t: _theme_score(t, theme_files[t]))
            person_themes[c] = top_theme
            person_themes_full[c] = set(theme_files.keys())

    # Direction summary
    if len(person_themes) >= 2:
        direction_parts = []
        for p in sorted(person_themes.keys()):
            direction_parts.append(f"{p} 主攻 {person_themes[p]}")
        insights.append("，".join(direction_parts))

        # Overlap detection
        all_theme_sets = list(person_themes_full.values())
        shared_themes = set.intersection(*all_theme_sets) if len(all_theme_sets) >= 2 else set()
        if shared_themes:
            for t in shared_themes:
                who = [p for p, ts in person_themes_full.items() if t in ts]
                insights.append(f"{'、'.join(sorted(who))} 今日工作交叠在「{t}」，建议对齐")
        else:
            insights.append("今日无工作交叠，各自独立推进")
    elif len(person_themes) == 1:
        p = list(person_themes.keys())[0]
        insights.append(f"今日仅 {p} 有更新，主攻 {person_themes[p]}")

    # Version iteration highlight
    versions = _detect_version_iteration(clean)
    for base, max_v, count in versions[:2]:
        insights.append(f"「{base}」迭代至 V{max_v}（共 {count} 个版本）")

    return insights[:4]


# ──────────────────────────────
# Main broadcast builder
# ──────────────────────────────

def build_broadcast(results_by_contributor: dict) -> str:
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    lines = [f"[{today} 知识库增量播报]", ""]

    if not results_by_contributor:
        lines.append("今日无更新。")
        return "\n".join(lines)

    results_by_contributor = {k: v for k, v in results_by_contributor.items() if v and k in _TEAM_MEMBERS}
    if not results_by_contributor:
        lines.append("今日无更新。")
        return "\n".join(lines)

    all_files = []
    for c, files in results_by_contributor.items():
        all_files.extend(files)

    # ========== Module 1: Cross Attention ==========
    cross_blocks = _build_cross_attention(results_by_contributor)
    if cross_blocks:
        lines.append("【交叉关注】")
        lines.append("")

        for observer, primary, watch_items in cross_blocks:
            if primary:
                lines.append(f"【{observer} 需要关注 {primary}】")
            else:
                lines.append(f"【{observer} 需要关注】")

            by_watch = defaultdict(list)
            for item in watch_items:
                by_watch[item["watch_who"]].append(item)

            for watch_who in sorted(by_watch.keys()):
                items = by_watch[watch_who]
                # Group items by folder for path-based display
                folder_items = defaultdict(list)
                for item in items:
                    parts = item["file"]["rel_path"].split("/")
                    folder = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
                    folder_items[folder].append(item)

                for folder, fitems in sorted(folder_items.items()):
                    if len(fitems) == 1:
                        rel = fitems[0]["file"]["rel_path"]
                        lines.append(f"• {watch_who} 在 {rel} 有更新")
                    else:
                        lines.append(f"• {watch_who} 在 {folder}/ 有 {len(fitems)} 份更新")
                    lines.append(f"  → 影响：{fitems[0]['impact']}")
                    if fitems[0].get("suggestion"):
                        lines.append(f"  → 建议：@{watch_who} {fitems[0]['suggestion']}")

            lines.append("")
            lines.append("───")
            lines.append("")

    # ========== Module 2: Personal Summary (narrative) ==========
    lines.append("【个人工作摘要】")
    lines.append("")

    for contributor in sorted(results_by_contributor.keys()):
        files = results_by_contributor[contributor]
        if not files:
            continue

        bullets = _summarize_person(contributor, files)
        if not bullets:
            continue

        lines.append(f"【{contributor}】")
        for b in bullets:
            lines.append(f"• {b}")
        lines.append("")

    # ========== Module 3: Global Insights ==========
    insights = _build_global_insights(results_by_contributor, all_files)
    if insights:
        lines.append("【全局洞察】")
        for ins in insights:
            lines.append(f"• {ins}")
        lines.append("")

    lines.append("---")
    lines.append(f"数据来源：Obsidian Sync 日志 | 生成时间：{datetime.datetime.now().strftime('%H:%M')}")
    return "\n".join(lines)


def build_dm_text(observer: str, results_by_contributor: dict) -> str:
    """
    Generate DM text for a specific observer.
    Content: other person's summary + cross-attention items about them.
    Returns empty string if no cross-attention for this observer.
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    results_by_contributor = {k: v for k, v in results_by_contributor.items() if v and k in _TEAM_MEMBERS}
    if observer not in results_by_contributor:
        return ""

    # Find cross-attention block for this observer
    cross_blocks = _build_cross_attention(results_by_contributor)
    observer_block = None
    for obs, primary, items in cross_blocks:
        if obs == observer:
            observer_block = (obs, primary, items)
            break

    if not observer_block:
        return ""

    _, primary, watch_items = observer_block
    # Keep only items from the primary watch person (not all others)
    primary_items = [it for it in watch_items if it["watch_who"] == primary]
    if not primary_items:
        return ""

    lines = [f"[{today} 今日关注提醒]", ""]

    # 1. Other person's work summary
    other_summary = _summarize_person(primary, results_by_contributor.get(primary, []))
    if other_summary:
        lines.append(f"【{primary} 今日工作】")
        for b in other_summary:
            lines.append(f"• {b}")
        lines.append("")
        lines.append("───")
        lines.append("")

    # 2. Cross-attention items from primary only, max 5
    lines.append(f"【{primary} 的更新需要你关注】")
    folder_items = defaultdict(list)
    for item in primary_items:
        parts = item["file"]["rel_path"].split("/")
        folder = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        folder_items[folder].append(item)

    shown = 0
    for folder, fitems in sorted(folder_items.items(), key=lambda x: -len(x[1])):
        if shown >= 5:
            remaining = sum(len(v) for v in folder_items.values()) - shown
            if remaining > 0:
                lines.append(f"• … 还有 {remaining} 份来自 {primary}")
            break
        if len(fitems) == 1:
            rel = fitems[0]["file"]["rel_path"]
            lines.append(f"• {primary} 在 {rel} 有更新")
        else:
            lines.append(f"• {primary} 在 {folder}/ 有 {len(fitems)} 份更新")
        lines.append(f"  → 影响：{fitems[0]['impact']}")
        if fitems[0].get("suggestion"):
            lines.append(f"  → 建议：@{primary} {fitems[0]['suggestion']}")
        shown += len(fitems)

    return "\n".join(lines)


def main():
    # Incremental scan: only files modified since last successful broadcast.
    # state.json tracks the checkpoint; on first run or after deletion it
    # defaults to last 24h to avoid blasting historical files.
    results = scan_daily_increments()
    results = {k: v for k, v in results.items() if v}
    broadcast = build_broadcast(results)
    print(broadcast)

    from config import REPORTS_DIR
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    broadcast_path = REPORTS_DIR / f"broadcast_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt"
    broadcast_path.write_text(broadcast, encoding="utf-8")

    return broadcast


if __name__ == "__main__":
    main()
