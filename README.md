# YouTube 博主数据中心 v3.10.3

> 当前源码快照：V3.10.3。完整源码仓库不包含任何业务数据库、API Key、导出文件或运行时缓存。

## 当前核心架构

- **三级 Field Taxonomy**：一级固定为「客观数据 / 博主标签 / 构建指标 / 比值指标」；二级为业务维度或用户自定义指标组；三级为具体稳定 Field ID。
- **统一条件构建器**：规则 / 标签构建器、二次指标应用结果、主博主库三处统一为“一条件一行”：逻辑关系 → 一级指标 → 二级指标 → 三级指标 → 运算符 → 值；三级指标搜索内嵌，不再出现旧式纵向堆叠和独立搜索按钮。
- **指标/规则列表**：已构建指标与规则列表固定 10 条/页，列表区域内部垂直滚动，并与左侧对应构建器保持配对等高。
- **Job Engine**：后台任务持久化、资源池并发限制、取消/重试/checkpoint 与安全恢复。
- **Migration Runner**：Schema 变更通过 `schema_migrations` 管理；当前 Schema 为 17。
- **API v1**：新增消费者优先使用 `/api/v1`；Legacy API 仅用于当前 Dashboard 兼容。
- **Run Specification**：AI Search / Ask Hub 保存冻结后的结构化运行条件，支持可重复执行。
- **Data Contract**：统一 fact / derived / ai / human / effective 语义，人工结果优先覆盖自动判断。
- **Creator Intelligence Engine**：确定性 SQL 生成 KPI 与事实上下文，LLM 只负责解释与行动建议。
- **GMV 口径**：固定为 UgPhone 后台 USD 累计快照，不进行自动汇率换算。
- **本地数据**：核心持久事实位于 `data/creator_hub.sqlite`；Dashboard 属于可重建输出，不是事实源。

## 安装与运行

1. Windows 上准备 Python 3.10+。
2. 首次部署运行 `setup.cmd`；已有环境升级运行 `upgrade.cmd`。
3. 日常使用运行 `start-dashboard.cmd`。
4. YouTube API Key 使用 `YOUTUBE_API_KEY` 用户环境变量；AI Key 使用独立的本机密钥配置，不写入源码仓库。
5. 本项目不需要 Node/npm。

## GitHub 源码与本地数据分离

- GitHub 只保存源码、配置模板、文档和启动脚本。
- `data/`、`output/`、`exports/` 仅保留 `.gitkeep`，业务数据库和生成结果由 `.gitignore` 排除。
- 不要把 SQLite、CSV/XLSX、API Key、备份目录、缓存或虚拟环境提交到仓库。
- 跨设备迁移业务数据时，在源设备停止 Dashboard 写入后复制一致性的 `data/creator_hub.sqlite`，放到目标设备相同位置，再运行 `upgrade.cmd`。


