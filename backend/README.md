# 后端说明

## 项目介绍

后端基于 FastAPI 提供传统文化多 Agent 接口，通过 LangChain 的 OpenAI-compatible 方式接入 DeepSeek API。当前请求链路已经从早期的关键词意图识别升级为“总协调器 + 领域 Agent + 工具”的结构：

- `planner.py`：根据用户问题规划需要调用的工具。
- `coordinator.py`：总协调器，负责调用领域 Agent、汇总结果并生成最终回答。
- `agents/domain_registry.py`：维护文化问答、资料检索、媒体检索、书法生成、短视频创作等领域 Agent。
- `tool_registry.py`：统一执行文化问答、联网搜索、书法生成、本地媒体检索等底层工具。
- `/api/chat/stream`：通过 SSE 流式返回工具轨迹和回答正文。
- `/api/asr/stream`：通过 WebSocket 转发前端音频到火山 ASR。
- `/api/tts`：调用火山 TTS 合成语音。

## 目录结构

```text
backend
├── app
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── prompts
│   │   └── system_prompt.py
│   ├── agent
│   │   ├── coordinator.py
│   │   ├── agents
│   │   │   ├── __init__.py
│   │   │   └── domain_registry.py
│   │   ├── planner.py
│   │   ├── llm.py
│   │   ├── schemas.py
│   │   ├── tool_registry.py
│   │   └── tools
│   │       ├── calligraphy_tool.py
│   │       ├── culture_qa_tool.py
│   │       ├── knowledge_base_tool.py
│   │       ├── media_tool.py
│   │       └── web_search_tool.py
│   ├── services
│   │   ├── calligraphy_service.py
│   │   ├── text_cleaner.py
│   │   ├── tts_service.py
│   │   ├── video_service.py
│   │   └── volcengine_asr_service.py
├── database
│   └── schema.sql
├── generated
│   └── calligraphy
├── .env.example
├── requirements.txt
└── README.md
```

## 数据库创建方式

1. 使用 Navicat 连接 MySQL。
2. 新建查询。
3. 打开 `backend/database/schema.sql` 并执行。
4. 检查是否创建了 `culture_video_agent` 数据库、`media_resources` 表和 `calligraphy_glyphs` 表。
5. 当前本地媒体检索由 `app/services/video_service.py` 查询 `media_resources` 表；`videos` 表仅保留为早期演示兼容数据。

## 配置方式

复制环境变量文件：

```powershell
copy .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
AGENT_MODEL=deepseek-chat

WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=你的 Tavily API Key

VOLCENGINE_TTS_APP_ID=你的火山 TTS App ID
VOLCENGINE_TTS_ACCESS_TOKEN=你的火山 TTS Token
VOLCENGINE_TTS_VOICE_TYPE=你的火山 TTS 音色

VOLCENGINE_ASR_APP_ID=你的火山 ASR App ID
VOLCENGINE_ASR_ACCESS_TOKEN=你的火山 ASR Token

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的 MySQL 密码
MYSQL_DATABASE=culture_video_agent

CALLIGRAPHY_DATASET_DIR=/path/to/calligraphy_fonts
CALLIGRAPHY_OUTPUT_DIR=generated/calligraphy
```

不要把真实 API Key 提交到代码仓库。

## 启动方式

Windows PowerShell：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 接口

### POST /api/chat

请求：

```json
{
  "message": "我想了解一下兰花花和信天游"
}
```

响应：

```json
{
  "type": "text_with_video",
  "answer": "你提到的《兰花花》和信天游都与陕北民歌密切相关...",
  "videos": [
    {
      "id": 1,
      "video_name": "兰花花.mp4",
      "file_path": "/path/to/media/兰花花.mp4"
    }
  ]
}
```

### POST /api/chat/stream

流式聊天接口，返回 SSE 事件：

```text
meta   当前回答类型、媒体资源、书法图片、工具调用计划等结构化信息
tool   单个工具执行结果
delta  回答正文片段
done   本轮回答结束
error  错误信息
```

### POST /api/tts

根据文本返回语音音频。需要火山 TTS 配置；未配置或调用失败时前端会提示错误。

### WebSocket /api/asr/stream

接收前端麦克风音频流，转发到火山 ASR，并返回识别文本事件。

### GET /api/calligraphy/{filename}

返回 `CALLIGRAPHY_OUTPUT_DIR` 下生成的书法作品图片。

### GET /api/calligraphy-gallery

返回可展示的书法字形图库条目。

### GET /api/video/{video_id}

根据 `media_resources` 表中的媒体 ID 返回音频或视频文件。接口不接受任意路径参数，避免直接暴露本地文件系统。

## 测试问题

- 普通文化问题：`端午节有哪些习俗？`
- 陕北民歌问题：`我想了解一下兰花花和信天游`
- 非文化问题：`帮我写一个 Python 爬虫`

## 常见问题

- DeepSeek API Key 未配置：检查 `.env` 中 `DEEPSEEK_API_KEY`。
- 火山 TTS 不可用：检查 `.env` 中 `VOLCENGINE_TTS_APP_ID`、`VOLCENGINE_TTS_ACCESS_TOKEN` 和音色配置。
- 火山 ASR 不可用：检查 `.env` 中 `VOLCENGINE_ASR_APP_ID`、`VOLCENGINE_ASR_ACCESS_TOKEN`、`VOLCENGINE_ASR_RESOURCE_ID`。
- 联网搜索不可用：检查 `.env` 中 `TAVILY_API_KEY`。
- MySQL 连接失败：检查 MySQL 服务、账号、密码、端口和数据库名。
- 数据库查询失败：确认已执行 `database/schema.sql`。
- 媒体文件路径不存在：检查 `media_resources.file_path` 是否指向真实存在的本地音视频文件。
- 前端跨域失败：确认前端地址是 `http://127.0.0.1:5173` 或 `http://localhost:5173`。
- 端口被占用：修改 Uvicorn `--port` 或关闭占用进程。
