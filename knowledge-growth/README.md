# Knowledge Growth Daily Broadcast

基于 Obsidian Sync 日志的每日知识库增量**分析型播报**生成器。

> ⚠️ **非 standalone 项目**。本仓库刚需配合 `obsidian-log-exporter` Obsidian 插件使用，插件负责实时导出 Sync 元数据（`server_files`）。插件代码位于 Obsidian vault 的 `.obsidian/plugins/obsidian-log-exporter/` 目录下，**不包含在本仓库中**。

---

## 依赖

| 组件 | 位置 | 说明 |
|------|------|------|
| `obsidian-log-exporter` 插件 | `AIC-000/.obsidian/plugins/obsidian-log-exporter/` | 实时导出 Sync `server_files` 到 `.obsidian/obsidian_log_export.json` |
| Obsidian Sync | vault 内置 | 必须启用，插件等待 Sync ready 后导出 |
| Python 3.10+ | 本机 | `pip install -r requirements.txt` |

---

## 播报结构（三模块）

```
[YYYY-MM-DD 知识库增量播报]

【交叉关注】
【X 需要关注 Y】
• Y 在 <相对路径>/ 有 N 份更新
  → 影响：...
  → 建议：@Y ...

【个人工作摘要】
【X】
• 主攻方向：XXX / 今日横跨 XXX、YYY，多线程推进
• XXX 已迭代至 V3，定位趋于明确
• 「验收清单」集中更新 5 份，标准可能变化

【全局洞察】
• Rosetta 主攻 官网文案与产品定位，Veil 主攻 WeCom Side Panel 技术方案
• 今日无工作交叠，各自独立推进
• 「班底产品官网文案」迭代至 V3（共 2 个版本）
```

**设计原则**：
- 个人摘要 = **替这个人做汇报**，不写文档标题，只写结论和洞察
- 全局洞察 = **方向 + 交叠判断**，不写"活跃/有进展"这类废话
- 交叉关注 = **谁该关注谁**，基于路径和文档类型的关联分析

---

## 安装

```bash
cd C:\Hello-World\knowledge-growth
pip install -r requirements.txt
```

依赖：`python-dotenv`

---

## 配置

复制 `.env.example` 为 `.env`：

```env
# Obsidian Vault 路径（含 obsidian-log-exporter 插件的 vault）
VAULT_PATH=C:\Users\ryshi\Documents\AIC-000

# 报告输出目录
REPORTS_DIR=./reports

# 可选：将报告同时写回 vault 的相对路径
VAULT_REPORT_PATH=T-B AI工作搭子/日报

# 用户名标准化映射（JSON）
NAME_ALIAS={"Rosetta Guo":"Rosetta","veilchow":"Veil"}

# 设备名 fallback 映射（当 Sync username 为空时用）
DEVICE_MAP={"Rosetta":"Rosetta","fuyo-aicdeMac-mini.local":"Veil"}
```

---

## 使用方法

### 生成今日播报（cron 入口）

```bash
python daily_broadcast.py
```

输出到 stdout，同时写入 `reports/broadcast_YYYY-MM-DD.txt`。

### 手动回溯

```bash
python daily_broadcast.py --days 3
```

> ⚠️ 手动 `--days` **不会更新 `state.json`**，保护增量扫描基准。

---

## 项目结构

```
.
├── daily_broadcast.py   # 播报生成器入口（三模块结构）
├── scanner.py           # 扫描 + contributor 归因（读 Sync 导出）
├── reporter.py          # Markdown 报告生成（旧，保留兼容）
├── config.py            # 配置读取
├── main.py              # 旧 CLI 入口（保留兼容）
├── cron_example.json    # OpenClaw cron 配置参考
├── state.json           # 增量扫描状态
├── requirements.txt
└── .env.example
```

---

## OpenClaw 定时播报

已配置的 cron job：`knowledge-growth-daily-broadcast`

```bash
openclaw cron add --name "knowledge-growth-daily-broadcast" \
  --cron "0 16 * * *" --tz "Asia/Shanghai"
```

- **运行**：每天 16:00 执行 `python daily_broadcast.py`
- **输出**：stdout 即为播报正文
- **投递**：Slack `C0AE7L7J0EL`
- **跳过条件**：stdout 为空或含"今日无更新"

详见 `cron_example.json`。

---

## 注意事项

- **Windows PowerShell GBK 编码**：`daily_broadcast.py` 入口处已 `reconfigure(stdout, utf-8)`
- **Sync 未就绪时**：所有文件显示为 `unknown`，需检查 Obsidian 是否在线且插件已导出数据
- **插件更新后需重载**：Obsidian 中 disable/enable 插件或重启 Obsidian

---

## 架构说明

```
┌─────────────────┐     ┌─────────────────────────┐     ┌─────────────────┐
│  Obsidian Sync  │────▶│ obsidian-log-exporter   │────▶│ obsidian_log_   │
│  (server_files) │     │ 插件（实时导出）         │     │ export.json     │
└─────────────────┘     └─────────────────────────┘     └────────┬────────┘
                                                                  │
                                                                  ▼
┌─────────────────┐     ┌─────────────────────────┐     ┌─────────────────┐
│  Slack / WeCom  │◀────│  OpenClaw cron agent    │◀────│ daily_broadcast │
│  C0AE7L7J0EL    │     │ （捕获 stdout 投递）     │     │ .py             │
└─────────────────┘     └─────────────────────────┘     └─────────────────┘
```

本仓库只包含右侧 Python 部分。左侧 Obsidian 插件位于 vault 目录下，独立维护。
