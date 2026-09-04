# Installation and First Run / 安装与首次运行

本文档介绍 **YouTube Creator Intelligence Hub** 在 Windows 10 / Windows 11 下的完整安装流程。

项目采用 local-first 架构。Creator、Video、Snapshot、Workspace、指标、规则等业务数据主要保存在本机 SQLite 数据库中；公开 GitHub 仓库不应包含私人数据库、API Key、导出文件或业务数据。

> 如果你只是想快速查看项目，而不准备使用真实数据，请使用仓库中的 `setup-demo.cmd` + `start-demo.cmd`。  
> 如果你准备正常使用 Creator Discovery、监控、数据库写入、筛选、导出和 AI 功能，请按本文进行正式安装。

---

## 1. 系统要求

需要：

- Windows 10 或 Windows 11
- Python 3.10 或更高版本
- Internet 连接
- YouTube Data API v3 API Key（YouTube Discovery / Sync 等在线功能需要）
- Git（推荐，但不是必须）

不需要：

- Node.js
- npm
- 独立数据库服务器

运行时 Python 依赖由 `requirements.txt` 管理，目前核心运行依赖包括 FastAPI、Pydantic、Uvicorn 和 openpyxl。

### 推荐 Python 版本

建议使用：

- Python 3.11
- Python 3.12

安装 Python 时建议勾选：

```text
Add Python to PATH
```

安装完成后打开 PowerShell：

```powershell
python --version
```

如果显示：

```text
Python 3.10+
```

即可继续。

如果 `python` 命令不可用，但安装了 Windows Python Launcher：

```powershell
py -3 --version
```

项目的 `scripts\python-run.cmd` 会优先尝试 `python`，找不到时自动回退到 `py -3`。

---

## 2. 下载项目

### 方法 A：Git clone（推荐）

打开 PowerShell，进入希望保存项目的位置，例如：

```powershell
cd C:\
```

执行：

```powershell
git clone https://github.com/Nikolaustis/YouTube_Creator_Data_Hub.git
cd YouTube_Creator_Data_Hub
```

### 方法 B：Download ZIP

如果没有安装 Git：

1. 打开 GitHub 仓库：
   `https://github.com/Nikolaustis/YouTube_Creator_Data_Hub`
2. 点击 **Code**
3. 点击 **Download ZIP**
4. 解压到一个固定目录，例如：

```text
C:\YouTube_Creator_Data_Hub
```

后续所有命令均在项目根目录中执行。

---

## 3. 第一次安装

项目提供统一的首次安装入口：

```text
setup.cmd
```

可以直接双击运行，也可以在 PowerShell 中执行：

```powershell
.\setup.cmd
```

`setup.cmd` 会依次完成：

```text
检查 Python 版本
        ↓
安装 requirements.txt
        ↓
初始化 / 升级 SQLite Schema
        ↓
检查 YOUTUBE_API_KEY
        ↓
运行本地环境诊断
        ↓
构建初始 Dashboard Snapshot
```

因此正常安装时不需要手动执行 `pip install`，也不需要手动创建数据库。

`setup.cmd` 可以重复运行。已有 SQLite 数据库不会因为重新执行安装脚本而被主动删除。

---

## 4. 配置 YouTube Data API Key

YouTube Discovery、Creator / Video API enrichment、同步等在线 YouTube 功能需要：

```text
YouTube Data API v3
```

### 4.1 获取 API Key

在 Google Cloud Console 中：

1. 创建或选择一个 Google Cloud Project
2. 进入 **APIs & Services**
3. 在 **Library** 中搜索并启用 **YouTube Data API v3**
4. 进入 **Credentials**
5. 选择 **Create Credentials → API Key**

建议给 API Key 添加 API restriction，只允许访问 **YouTube Data API v3**。

不要把 API Key 写入 README、配置样例、Issue、Commit 或公开 GitHub 文件。

### 4.2 使用项目脚本保存 Key

第一次运行 `setup.cmd` 时，如果没有找到用户级 `YOUTUBE_API_KEY`，安装器会询问是否立即配置。

也可以之后单独运行：

```powershell
.\scripts\set-api-key.cmd
```

Key 会保存为当前 Windows 用户环境变量：

```text
YOUTUBE_API_KEY
```

输入过程中 Key 不会回显。

项目不要求把 Key 写入源码或普通配置文件。

新终端和 `start-dashboard.cmd` 会自动读取用户环境变量。

---

## 5. 验证安装

完成安装后执行：

```powershell
.\scripts\python-run.cmd hub.py doctor
```

也可以直接运行：

```powershell
python .\hub.py doctor
```

Doctor 会检查：

- Python >= 3.10
- pip
- 运行依赖
- SQLite / 数据库 Schema
- 数据与输出目录写权限
- `YOUTUBE_API_KEY` 是否存在
- 当前实际使用的 Python executable
- Interactive Dashboard 默认端口 `8765` 是否可用

### 在线验证 API Key

执行：

```powershell
python .\hub.py doctor --online
```

该命令会进行实际 API 验证。

如果 `python` 命令不可用：

```powershell
.\scripts\python-run.cmd hub.py doctor --online
```

---

## 6. 启动 Interactive Dashboard

正常日常使用时运行：

```powershell
.\start-dashboard.cmd
```

或直接双击：

```text
start-dashboard.cmd
```

启动器实际运行：

```text
hub.py serve --host 127.0.0.1 --port 8765
```

浏览器访问：

```text
http://127.0.0.1:8765/
```

数据路径为：

```text
Browser
   ↓
127.0.0.1:8765
   ↓
Local Python Service
   ↓
Local SQLite Database
```

Interactive Dashboard 是正常工作的推荐模式，可支持包括：

- YouTube Creator Discovery
- Query Expansion
- Creator / Video 写入 SQLite
- Server-side filtering / pagination
- Creator review / correction
- 联系方式相关处理
- 完整 XLSX 导出
- Monitoring / Jobs
- Workspace-specific metrics / rules
- 可选 AI Intelligence 功能

---

## 7. Static Dashboard

如果只需要查看已经生成的 Dashboard Snapshot：

```powershell
.\open-static-dashboard.cmd
```

Static Dashboard：

- 不启动 Python HTTP Service
- 适合离线查看
- 适合只读展示
- 不能替代需要服务端数据库操作的 Interactive Dashboard

如果页面可以打开，但搜索、写入、完整筛选或导出能力不可用，请确认自己是否误用了 Static Dashboard。

---

## 8. Public Demo 模式

公开仓库提供独立的 synthetic demo。

执行：

```powershell
.\setup-demo.cmd
.\start-demo.cmd
```

Demo 会创建确定性的 synthetic SQLite 数据库。

它不会读取或修改 production database，因此适合：

- GitHub reviewer
- 招聘方
- Portfolio 展示
- 无私人数据情况下的功能体验

如果需要重新生成 Demo Dataset：

```powershell
.\create-demo.cmd
```

---

## 9. FastAPI / OpenAPI

项目同时提供 typed FastAPI API：

```powershell
.\start-api.cmd
```

默认 OpenAPI / Swagger 页面：

```text
http://127.0.0.1:8766/docs
```

该接口主要用于新的集成与工程化 API Surface。

---

## 10. 可选：AI 配置

AI 不是核心运行依赖。

不配置任何 AI API 时，Creator 数据库、Discovery、Dashboard、监控、筛选、规则和导出等核心功能仍然可以正常工作。

启用 AI：

```powershell
.\setup-ai.cmd
```

配置向导支持的协议包括：

- OpenAI Responses API
- OpenAI-compatible Chat Completions
- Anthropic Messages
- Gemini `generateContent`
- Mock / Offline Test

配置内容包括：

- Protocol
- API Base URL
- API Key
- Model ID
- Daily AI Request Soft Limit

AI Provider / Model 并不固定绑定某一家供应商。

配置完成后，如果 Dashboard 正在运行，应关闭并重新启动：

```powershell
.\start-dashboard.cmd
```

---

## 11. 可选：自动监控

如果希望 Windows 定期执行 Creator Monitoring / Sync：

```powershell
.\scripts\install-sync-task.cmd
```

安装后会创建 Windows Scheduled Task。

任务会周期性唤醒，实际是否刷新某个 Creator 由其监控优先级和刷新周期决定，而不是每次重刷整个数据库。

当前监控周期设计包括：

- High: 6h
- Normal: 24h
- Low: 72h
- Archive: 168h

---

## 12. 数据安全与备份

这是 local-first 项目。

生产数据、API Key 和私人业务文件不应该上传到公开 GitHub 仓库。

尤其不要提交：

```text
production SQLite database
API keys
exports
backups
logs
cache
business CSV/XLSX
virtual environments
```

项目 `.gitignore` 已覆盖常见情况，但仍建议在 push 前检查：

```powershell
git status
```

数据库升级、备份和 Snapshot 维护可以通过 Interactive Dashboard 中的 **数据更新 / Data Update** 相关功能完成。

数据库 Schema 的升级由项目迁移逻辑处理。升级代码前应保留数据库备份。

---

## 13. 日常启动流程

完成第一次安装后，通常不再需要运行 `setup.cmd`。

正常使用：

```powershell
cd C:\YouTube_Creator_Data_Hub
.\start-dashboard.cmd
```

然后访问：

```text
http://127.0.0.1:8765/
```

---

## 14. 更新仓库

如果使用 Git clone 安装：

```powershell
cd C:\YouTube_Creator_Data_Hub
git pull
```

更新源码后，建议重新运行：

```powershell
.\setup.cmd
```

这样可以自动：

- 更新 Python dependencies
- 执行必要的 SQLite Schema migration
- 重新运行环境诊断
- 重建 Dashboard Snapshot

`setup.cmd` 的设计允许作为安装修复入口重复执行。

在更新生产数据库前，建议先备份本地 SQLite 数据。

---

## 15. 常见问题

### `python is not recognized`

安装 Python 3.10+ 并勾选：

```text
Add Python to PATH
```

如果系统已经安装 Windows Python Launcher：

```powershell
py -3 --version
```

项目启动器会自动尝试 `py -3`。

---

### Python 版本太低

检查：

```powershell
python --version
```

需要 Python 3.10 或更高版本。

---

### Python package 缺失

重新运行：

```powershell
.\setup.cmd
```

---

### YouTube API Key 没有配置

运行：

```powershell
.\scripts\set-api-key.cmd
```

---

### API Key 已配置，但 YouTube 功能报错

运行：

```powershell
python .\hub.py doctor --online
```

确认：

- Key 是否有效
- YouTube Data API v3 是否已启用
- Google Cloud Project 是否有正确的 API restriction
- 当前 Key 是否达到 quota / restriction 限制

---

### Dashboard 无法启动

运行：

```powershell
.\scripts\python-run.cmd hub.py doctor
```

重点检查：

```text
python_executable
interactive_port_available
```

---

### Port 8765 被占用

Interactive Dashboard 默认使用：

```text
127.0.0.1:8765
```

如果该端口已被其他程序占用，关闭冲突进程后重新运行：

```powershell
.\start-dashboard.cmd
```

---

### Dashboard 可以打开，但无法执行数据库操作

确认启动方式是不是：

```text
open-static-dashboard.cmd
```

需要完整交互能力时必须使用：

```text
start-dashboard.cmd
```

---

### AI 功能不能使用

运行：

```powershell
.\setup-ai.cmd
```

完成 Provider / Base URL / API Key / Model ID 配置后重新启动 Dashboard。

AI 配置失败不会阻止项目的非 AI 核心功能运行。

---

## 16. 最短安装流程

对于已经安装 Python 3.10+ 和 Git 的 Windows 用户：

```powershell
git clone https://github.com/Nikolaustis/YouTube_Creator_Data_Hub.git
cd YouTube_Creator_Data_Hub
.\setup.cmd
```

根据提示配置：

```text
YOUTUBE_API_KEY
```

然后：

```powershell
.\start-dashboard.cmd
```

访问：

```text
http://127.0.0.1:8765/
```

即可开始使用。

---

## 17. Reviewer 最短体验流程

如果只是查看公开项目能力，不使用真实业务数据：

```powershell
git clone https://github.com/Nikolaustis/YouTube_Creator_Data_Hub.git
cd YouTube_Creator_Data_Hub
.\setup-demo.cmd
.\start-demo.cmd
```

这样可以直接体验 synthetic demo，而无需 production database。

---

## Related documentation

- `README.md` — project overview and quick start
- `docs/ARCHITECTURE.md` — architecture
- `docs/API_FASTAPI.md` — typed API / FastAPI surface
- `docs/OPERATIONS.md` — operations and monitoring
- `docs/AI.md` — AI layer configuration and behavior
- `docs/PORTFOLIO.md` — portfolio/reviewer workflow
- `docs/BENCHMARKS.md` — benchmark policy
- `docs/AI_EVALUATION.md` — AI evaluation
- `docs/WORKSPACES.md` — Workspace model

---

## Current release

This installation guide is aligned with the public repository's **v4.2.0** surface.

Database Schema: **18**.
