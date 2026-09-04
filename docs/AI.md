# 可选 AI 层

AI 是 **可拔插增强层**，不是 Creator Intelligence Hub Core 的运行依赖。YouTube 同步、SQLite、博主发现、监控、工作流、二次指标、导出、备份与维护在 AI 关闭、没有 API Key 或远端模型不可达时都应继续工作。

## AI 搜索 Agent

AI Search 的职责是把用户输入的主题与要求转换成：

1. 受 Query Budget 限制的最终可执行 YouTube Query；
2. 结构化 `fit_criteria`；
3. 可审计的 Planner Strategy / Notes。

默认 Planner 是**行业中立**的。它不会假设用户搜索的是某类娱乐内容、某类软件、某个客户或某个商业模式。只有用户输入或当前 Workspace 明确提供相应语义时，Planner 才应使用这些约束。

Query Expansion 使用 `config/query_packs.json` 中的通用 Pack：教程与讲解、评测与比较、场景与实践、更新与趋势、社区与观点、自定义。

Language 同时表示搜索 Query 语言，并可作为 Creator 主要内容语言目标。实际搜索、Creator 去重、Profile 抽样、硬约束过滤、评分和持久化仍由本地 Core 执行。

## 主要功能

- **Ask Hub**：自然语言 → allowlist Creator 查询计划 → 本地 SQLite 返回事实结果。
- **Creator Brief**：基于本地证据生成定位、表现、Workspace 关系、机会、风险和下一步建议。
- **Creator 对比**：比较 2–5 个本地 Creator。
- **AI 搜索 Agent**：规划 Query 并调用现有 YouTube Discovery 流程。
- **七日 Creator Intelligence Brief**。
- **AI 调用记录 / 缓存 / Evidence / Feedback**。

## 配置

Dashboard 中进入【AI 助手 → AI 状态与配置】，配置：

- 接口协议；
- API Base URL；
- API Key；
- 模型 ID；
- 本地每日软限额。

支持 Responses API、OpenAI-compatible Chat Completions、Anthropic Messages、Gemini generateContent 与 Mock。模型 ID 和 Base URL 可直接填写，不依赖固定供应商目录。

本机密钥槽：

```text
CREATOR_HUB_AI_API_KEY
```

API Key 不写入 SQLite、HTML、JS 或浏览器 LocalStorage。

## Mock

Mock 用于离线验证安装、页面、缓存、AI 数据表和调用流程。Mock 输出不是实际模型质量，也不能作为业务判断。

## Result Set

Ask Hub 与 AI Search 均可生成持久 `Result Set`：

- `ai_result_sets` 保存运行元数据；
- `ai_result_items` 保存 Creator 结果快照；
- `ai_runs` 保存协议、模型、Prompt Version、状态与 Token 元数据；
- `ai_evidence` 保存可追溯证据；
- `ai_feedback` 保存人工反馈；
- `ai_cache` 保存结构化缓存。

历史 Result Set 是当次快照，不应被后续数据库更新静默改写。

## 安全边界

1. AI 不能执行任意 SQL。
2. AI 不获得任意数据库写权限；动作必须复用受控服务。
3. 人工复核高于 AI 判断。
4. 确定性系统评分与 AI 判断分开保存。
5. AI Finding / Evidence 与 Creator / Video Fact Layer 分离。
6. Dashboard 只允许本机 loopback 修改 AI Key。
7. AI 达到本地软限额时不得影响非 AI 功能。
8. Planner 必须遵守当前 Workspace 和用户明确要求，不得引入隐藏行业假设。
