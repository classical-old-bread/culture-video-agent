# 传统文化多工具 Agent 工作台

本项目是一个面向传统文化场景的多工具智能体应用，支持文化问答、本地音视频资源检索、书法作品生成、短剧脚本与 AI 视频提示词生成、语音识别和语音朗读等能力。项目采用前后端分离架构，后端基于 FastAPI 构建 Agent 编排与工具调用链路，前端基于 Vue 3 + Vite 构建交互式工作台。

> 说明：本仓库主要用于展示项目结构、工程实现方式和核心业务设计。由于数据库、本地媒体资源、书法字形数据集和第三方 API Key 涉及权限与版权问题，无法随仓库公开提供。如需完整运行，请自行准备 MySQL 数据库、本地素材目录和相关 API 配置。

## 项目亮点

- 设计 `Planner -> Coordinator -> Domain Agents -> Tool Registry` 的多工具 Agent 架构，将文化问答、联网搜索、知识库检索、媒体检索、书法生成、短剧创作等能力统一编排。
- 基于 SSE 实现流式回答和工具调用轨迹展示，前端可实时展示 Agent 的计划、工具结果、正文输出和结构化资源。
- 支持火山引擎 ASR/TTS，实现语音输入、持续监听、播放中断和语音朗读。
- 实现基于本地书法字形库的书法图片生成，不依赖 AI 绘图，而是通过字形检索、竖排布局、背景纹理和印章叠加生成作品。
- 支持短剧创作工作台，可生成五镜头分镜、对白、AI 视频提示词，并预留视频渲染任务提交和状态轮询能力。
- 前端包含会话管理、工作区面板、媒体播放、书法选择、短剧分镜展示等完整交互。

## 技术栈

### 后端

- FastAPI
- SQLAlchemy + PyMySQL
- MySQL
- LangChain / OpenAI-compatible LLM 调用
- DeepSeek API
- Tavily Search API
- 火山引擎 ASR / TTS
- Pillow
- WebSocket / SSE

### 前端

- Vue 3
- Vite
- Axios
- Fetch Streaming API
- Web Speech / WebSocket 语音交互

## 目录结构

```text
.
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 FastAPI 应用入口
│  │  ├─ config.py               环境变量配置
│  │  ├─ database.py             数据库连接
│  │  ├─ models.py               ORM 模型
│  │  ├─ schemas.py              API 数据结构
│  │  ├─ routers/                HTTP / WebSocket 路由
│  │  ├─ agent/                  Agent 编排核心
│  │  │  ├─ planner.py           工具调用规划
│  │  │  ├─ coordinator.py       总协调器
│  │  │  ├─ tool_registry.py     工具注册表
│  │  │  ├─ agents/              领域 Agent
│  │  │  └─ tools/               Agent 工具适配层
│  │  ├─ services/               业务能力实现
│  │  └─ prompts/                系统提示词
│  ├─ database/schema.sql        数据库表结构
│  ├─ scripts/                   数据导入与知识库构建脚本
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ App.vue                 主界面
│  │  ├─ api/                    API 封装
│  │  ├─ components/             展示组件
│  │  └─ composables/            会话、语音、流式输出等逻辑
│  ├─ package.json
│  └─ vite.config.js
└─ .codex/skills/                项目维护用 Codex skills
```

## 核心链路

```text
用户输入
-> 前端发送 /api/chat/stream
-> 后端构造 AgentContext
-> Planner 生成工具调用计划
-> Coordinator 分发给领域 Agent
-> Tool Registry 执行具体工具
-> Services 调用数据库、本地文件或第三方 API
-> Coordinator 汇总工具结果并生成最终回答
-> SSE 推送 meta / tool / delta / done 事件
-> 前端展示回答、媒体、书法图片、短剧方案和工具轨迹
```

## 主要功能

- 传统文化问答：围绕民俗、诗词、书法、地方文化等问题生成回答。
- 联网资料检索：在需要实时资料或来源引用时调用搜索工具。
- 本地知识库检索：预留 RAG 检索链路，可基于本地文档构建知识库。
- 本地媒体检索：从数据库索引的音视频资源中匹配相关文化素材。
- 书法生成：根据文本、书体和作者，从本地字形库生成书法作品图片。
- 短剧创作：生成五镜头短剧方案、对白、分镜和 AI 视频提示词。
- 语音交互：支持语音识别、持续监听、TTS 朗读和播放中断。

## 数据库与资源说明

本项目运行依赖 MySQL 数据库和本地资源文件，但这些内容不会随仓库公开：

- `media_resources`：本地音视频资源索引，涉及本地文件路径和素材版权。
- `calligraphy_glyphs`：书法字形索引，依赖本地书法字形图片数据集。
- 本地音视频、书法图片、生成结果目录均需要使用者自行准备。
- DeepSeek、Tavily、火山引擎、Kling 等第三方服务的 API Key 需要使用者自行申请和配置。

仓库提供 `backend/database/schema.sql` 作为表结构参考。使用者如需运行，需要自行创建数据库、导入合法数据，并配置 `.env`。

## 本地运行方式

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux 可将激活命令替换为：

```bash
source .venv/bin/activate
cp .env.example .env
```

需要在 `backend/.env` 中配置数据库、模型 API、ASR/TTS、书法字库和输出目录等信息。

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

如果后端端口不是 `8000`，请在 `frontend/.env` 中配置：

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 环境变量示例

后端配置参考：

```text
DEEPSEEK_API_KEY=your_deepseek_api_key
TAVILY_API_KEY=your_tavily_api_key
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=culture_video_agent
CALLIGRAPHY_DATASET_DIR=/path/to/calligraphy_fonts
CALLIGRAPHY_OUTPUT_DIR=/path/to/generated/calligraphy
```

完整配置请参考 `backend/.env.example`。

## 当前限制

- 数据库和本地素材未公开，因此克隆仓库后不能直接获得完整演示效果。
- 书法生成依赖本地字形图片数据集，缺字时会返回 `missing_chars`。
- 音视频播放依赖数据库中的本地文件路径，运行者需要自行导入合法媒体资源。
- ASR、TTS、联网搜索和视频渲染依赖第三方服务配置。
