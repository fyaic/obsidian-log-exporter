# Obsidian Log Exporter

`Obsidian Log Exporter` 不是一个只为 Sync history 服务的小插件。

它的真正定位更接近一层“本地元数据暴露器”：

- 把 Obsidian 内部已经存在、但默认不方便给外部系统消费的日志和元数据导出来
- 让本地部署的智能体、脚本、日报系统、知识运维工具可以稳定读取
- 优先解决“最近谁改了什么”“设备与用户映射是什么”“哪些文件有历史痕迹”这类问题

换句话说，它服务的不是某一个按钮，而是 **让 Obsidian 的编辑历史与元数据能够被外部 agent 理解**。

---

## 现在能导出的数据

插件当前会输出两类文件：

### 1. 轻量导出

`/.obsidian/obsidian_log_export.json`

适合外部脚本或 agent 直接消费，当前包含：

- `this_device`
- `usernames`
- `server_files`
- `sync_history`

其中最关键的是 `server_files`：

- 文件路径
- 修改时间
- 设备名
- 用户 ID
- 用户名

这一层已经足够支撑“最后编辑者归因”之类的场景。

### 2. 调试探针

`/.obsidian/obsidian_log_probe.json`

它更偏排查用途，会多带一些上下文，例如：

- frontmatter `author` 扫描结果
- File Recovery 统计
- 文件夹级别计数
- `getHistory()` 抽样错误

### 3. 运行状态文件

`/.obsidian/obsidian_log_exporter_status.json`

这是为了避免插件黑盒运行时“到底执行了没有”这种问题。  
插件加载、等待 Sync、开始导出、写完结果，都会把阶段写到这里。

---

## 为什么这个插件存在

最初的问题不是“怎么导出 Sync history”，而是：

> 如何让本地智能体知道，Obsidian 里每个文件最近是谁改的？

一开始直觉会去找完整的版本历史。

但在真实 vault 里，更实用的路径其实是：

- 先导出 `serverFiles`
- 再结合 `getUsernames()`
- 把用户 ID 映射成具体的人

这样能优先打通“可用归因”，而不是陷在“全量历史一定要完美还原”里。

所以这个插件的核心思想是：

**先把 Obsidian 内部的元数据稳定暴露出来，再让外部系统自由组合。**

---

## 典型用途

### 1. 日报 / 周报归因

例如：

- Rosetta 今天改了哪些笔记
- veil 最近一周活跃在哪些主题
- 哪些更新是路径规则猜的，哪些是 Sync 用户直接给出的

### 2. 本地 agent 读取编辑历史元数据

本地部署的智能体可以读取导出文件后做：

- 贡献者识别
- 编辑趋势分析
- 知识库活跃度判断
- “最近谁在改这个目录”之类的上下文补充

### 3. 调试 Obsidian Sync / Metadata 暴露链路

当你怀疑：

- 插件到底有没有加载
- 命令有没有执行
- Sync 用户映射有没有拿到
- 为什么历史记录是空

状态文件和 probe 文件会比弹窗可靠得多。

---

## 命令

插件会注册命令：

`Run Obsidian Log Export`

执行后会尝试：

1. 等待 Sync ready
2. 导出 Sync 用户与 server file 索引
3. 抽样读取少量 `getHistory()` 结果
4. 写出导出文件与状态文件

---

## 为什么没有全量遍历所有文件历史

因为真实大 vault 里，全量串行 `await getHistory(file.path)` 很容易卡死。

这不是理论问题，而是实战里真的会遇到的问题。

所以当前策略是：

- `server_files` 全量导出
- `getHistory()` 只做小样本抽查
- 每次调用都带超时保护

这是一个偏工程化的取舍：

先保证系统稳定、结果可用，再考虑历史链补强。

---

## 与旧文件名的兼容

为了不打断已经接好的外部项目，插件现在会同时写两套文件名：

### 新文件名

- `obsidian_log_export.json`
- `obsidian_log_probe.json`
- `obsidian_log_exporter_status.json`

### 兼容旧文件名

- `sync_history_export.json`
- `sync_history_probe.json`
- `sync_history_plugin_status.json`

这样旧脚本还能继续跑，新项目也可以逐步迁移。

---

## 未来可以继续扩展的方向

- 增加更多 MetadataCache 暴露项
- 把最近变更列表单独导出成 agent 更好消费的结构
- 增加目录级别、标签级别、活跃主题级别的摘要
- 暴露更多 File Recovery 统计指标
- 加入“文件最后编辑者 vs 文件原作者”的双轨信息

---

## 一句话总结

`Obsidian Log Exporter` 做的事情，不是“替你看版本历史”。

它做的是更基础、也更重要的一步：

**把 Obsidian 里对 agent 有价值的日志和元数据，可靠地暴露出来。**
