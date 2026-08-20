# 可选 AI 层（v3.9.0）

## v3.9.0 AI 搜索 Agent

AI 搜索要求会同时生成最终可执行 Query 与结构化 Fit Criteria。Planner v6 直接受 `Max Queries` 预算约束，本机只做去重/重复主题规范化。AI 请求遇到 read timeout、连接重置、429 或常见 5xx 时最多自动重试两次。Discovery 完成后先执行低成本预过滤，再将 Profile Budget 用于更有潜力的 Creator，抽样最近最多 50 条上传（不入库）。基础主题先在频道级上下文确认；确认后 AFK、Auto Farm、Overnight、Multi-account 等近期场景内容可直接计入连续性，不要求每条视频标题重复完整游戏名。Result Set 保存的是当次快照；旧 Result Set 不会被新规则自动改写。

“中小体量”等模糊规模要求在未给数字时默认解释为订阅数不高于 100,000，并显式写入 Planner Notes/Result Set/XLSX；需要其他范围时应在搜索要求中直接写数值。Prompt 出现“长期/持续/经常”等要求时，默认启用硬门槛：最近样本目标内容至少 5 条并覆盖至少 3 个月。因 Profile Budget 或请求异常尚未完成 Profile 的候选进入 `Pending Verification / 待验证`，不计作过滤失败，也不能进入正式高适配 Result Set。

Creator sourcing 默认排除云手机品牌官方/产品频道、游戏官方/开发者频道及明确官方预告来源，并排除以 Script/Hack/Cheat/Exploit/Executor/Keyless/Dupe 等脚本外挂内容为主的频道。结果分别输出内容适配、连续性、品牌安全、体量适配和 Query Coverage 五维评分，并在导出中保留过滤类别与原因。


AI 是 **可拔插增强层**，不是 Creator Data Hub Core 的运行依赖。YouTube 同步、SQLite、视频分类、人工复核、博主发现、监控、工作流、二次指标、XLSX、备份与维护在 AI 关闭、没有 AI API Key、AI 服务不可达时都应继续正常工作。

## 1. AI 默认关闭

`config/settings.json` 默认 `ai.enabled=false`。`doctor` 会把 AI 显示为可选能力，不会因为没有 AI Key 判定核心环境失败。

## 2. 最推荐的配置方式：Dashboard

启动交互 Dashboard：

```powershell
.\start-dashboard.cmd
```

进入【AI 助手 → AI 状态与配置】后只需要确定四项：

1. **接口协议**：选择你的 API 使用的 HTTP 协议，而不是从固定模型列表里挑供应商。
2. **API Base URL**：可使用默认值，也可填写代理、聚合网关或兼容服务自己的 Base URL。
3. **API Key**：直接在密码框输入。保存后 Key 只进入本机用户级密钥位置，不写 SQLite、不写浏览器 LocalStorage。
4. **模型 ID**：点击【读取可用模型】尝试从 API 获取；若服务不提供模型列表，可直接手工输入任意由该 API 支持的模型 ID。

当前支持的协议适配器：

| 接口协议 | 典型用途 | 默认 Base URL |
|---|---|---|
| Responses API | OpenAI Responses API 或兼容实现 | `https://api.openai.com/v1` |
| OpenAI-compatible Chat Completions | OpenAI Chat Completions 兼容网关/服务 | `https://api.openai.com/v1` |
| Anthropic Messages | Anthropic Messages 协议或兼容实现 | `https://api.anthropic.com/v1` |
| Gemini generateContent | Google Gemini generateContent 协议 | `https://generativelanguage.googleapis.com/v1beta` |
| Mock | 完全离线测试，不访问外部 AI | 无 |

> 这里固定的是少量**请求协议**，不是模型目录。模型 ID 和 Base URL 都可以自由输入，因此模型更新时不需要等待 Dashboard 更新。

保存后可点击【测试连接】。如果【读取可用模型】失败，但你的 API 文档给出了模型 ID，可以直接填入后测试连接。

## 3. 命令行配置

也可以运行：

```powershell
.\setup-ai.cmd
```

向导会询问协议、Base URL、API Key、模型 ID 和每日软限额；API 若支持模型列表，会先尝试读取并展示，仍允许手工输入模型。

只修改当前 AI Key：

```powershell
.\scripts\set-ai-key.cmd
```

v3.2.0 使用供应商中立的本机密钥槽：

```text
CREATOR_HUB_AI_API_KEY
```

为了兼容旧配置，程序也会只读回退到常见旧环境变量，例如 `OPENAI_API_KEY`、`OPENROUTER_API_KEY`、`ANTHROPIC_API_KEY`、`GEMINI_API_KEY` / `GOOGLE_API_KEY`。新配置不要求用户把 Key 写进源码、SQLite 或浏览器。

## 4. Mock 输出是什么意思

如果运行：

```powershell
.\scripts\python-run.cmd hub.py ai-config --enable --provider mock --model mock-v1
```

看到：

```json
{
  "enabled": true,
  "available": true,
  "provider": "mock",
  "model": "mock-v1",
  "api_key_present": false,
  "daily_request_soft_limit": 100,
  "requests_today": 0
}
```

含义是：

- `enabled=true`：AI 增强层已打开。
- `available=true`：当前 Mock 适配器可以工作。
- `provider=mock` / `model=mock-v1`：正在使用离线模拟结果，不是真实大模型。
- `api_key_present=false`：**Mock 不需要 API Key，这是正常状态**。
- `requests_today=0`：`ai-config` 只是修改配置，本身不会调用模型。
- `store_remote=false`：支持该选项的远端接口不会由本系统主动要求保存响应。
- `send_contact_data=false`：公开联系方式默认不进入 AI 上下文。

Mock 的用途是验证安装、页面、缓存、AI 数据表和调用流程，不能作为真实业务判断。

## 5. AI 搜索 Agent：直接调用 YouTube API

v3.2.0 将原来的“Query Planner 只给建议”升级为：

```text
基础关键词
→ AI 规划多条搜索 Query
→ 本机校验/限制 Query 数量
→ 调用现有 YouTube Data API Discovery
→ 视频命中
→ Creator 去重与发现评分
→ 保存 discovery_runs / discovery_creator_results / discovery_hits
```

因此点击【AI 规划并搜索 YouTube】后，不需要再手工复制 Query 到【博主发现】。

这个动作会消耗 **YouTube API** 配额；AI 负责受预算约束的 Query 规划；实际搜索、去重、Creator Profile、硬约束过滤、多维评分和持久化仍由现有 Creator Data Hub Core 执行。搜索结果不会因为 AI 自行绕过现有业务规则而直接开启监控或批量修改 Creator。

## 6. 主要 AI 功能

- **Ask Hub**：自然语言 → allowlist Creator 查询计划 → 本地 SQLite 返回事实结果。
- **Creator Brief**：基于本地证据生成定位、表现、品牌关系、机会、风险和下一步建议。
- **Creator 对比**：比较 2–5 个本地 Creator。
- **AI 搜索 Agent**：AI 规划 Query 后直接调用现有 YouTube API Discovery。
- **七日 Creator Intelligence Brief**。
- **AI 调用记录 / 缓存 / Evidence**。

## 7. 安全与边界

1. AI 不能直接执行任意 SQL。
2. AI 不直接获得任意数据库写权限；需要动作时复用 Creator Data Hub Core 的受控服务。
3. 人工复核仍高于 AI；AI 不覆盖人工标签。
4. 确定性 Discovery Score 与 AI 判断分开保存。
5. AI Finding / Evidence 存储于独立 `ai_*` 表，核心 Creator / Video 事实层保持独立。
6. API Key 不写入 SQLite、HTML、JS 或浏览器 LocalStorage。
7. Dashboard 只允许来自本机 loopback 的请求修改 AI Key。
8. AI 调用使用本地软限额和缓存，达到 AI 限额不影响非 AI 功能。

## 8. 数据表

- `ai_runs`：协议/模型/Prompt版本/状态/Token 元数据。
- `ai_findings`：Creator Brief 等持久 AI Finding。
- `ai_evidence`：Finding 使用的本地证据快照。
- `ai_feedback`：运营人员对 AI 结果的反馈。
- `ai_cache`：结构化 AI 结果缓存。

v3.2.0 Schema 为 12。新增：

- `ai_result_sets`：一次 Ask Hub / AI 搜索 Agent 的可回看结果集元数据。
- `ai_result_items`：结果集中的 Creator 快照。
- `ai_runs.source_json / result_json / cache_hit`：每次 AI 操作的输入、输出和缓存命中状态。
- `discovery_runs.ai_run_id`：AI 搜索计划与实际 YouTube Discovery Run 的关联。


## v3.2.0 Result Set 与 Creator Picker

- Ask Hub 与 AI 搜索 Agent 每次执行都会生成 `ai_result_sets` + `ai_result_items` 快照。
- 结果集与 AI Run / Discovery Run 显式关联；历史查看不会被后续数据库更新改写。
- 所有 Creator 结果默认30条/页，支持搜索、字段筛选、排序、完整 XLSX 导出。
- Ask Hub 的 `result_limit` 仅在用户明确要求 Top N 时使用；UI分页不是查询上限。
- Creator Brief / Creator 对比使用本地 SQLite 自动完成候选，不调用 AI、不消耗 AI 配额。
