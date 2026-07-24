# 前端说明

## 项目介绍

前端使用 Vue 3 + Vite 构建，提供聊天式传统文化 Agent 页面。用户输入问题后，前端优先调用后端 `POST /api/chat/stream`，以 SSE 方式展示工具调用轨迹、流式回答、书法图片和本地音视频卡片。

当前页面还包含：

- 本地会话保存。
- 按住说话和电台模式语音输入。
- 云端 ASR WebSocket 识别。
- TTS 分段朗读。
- 书法图库展示。

## 目录结构

```text
frontend
├── src
│   ├── api
│   │   └── chat.js
│   ├── components
│   │   ├── ChatMessage.vue
│   │   └── VideoCard.vue
│   ├── App.vue
│   ├── main.js
│   └── style.css
├── index.html
├── package.json
├── vite.config.js
└── README.md
```

## 配置方式

后端地址集中配置在：

```text
src/api/chat.js
```

默认：

```js
VITE_API_BASE_URL=http://127.0.0.1:8000
```

如果后端端口改变，请在 `frontend/.env` 中配置 `VITE_API_BASE_URL`。为空时表示前后端同源部署，由 Nginx 或同域代理转发 `/api`。

## 启动方式

```bash
cd frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

## 测试问题

- 普通文化问题：`端午节有哪些习俗？`
- 陕北民歌问题：`我想了解一下兰花花和信天游`
- 非文化问题：`帮我写一个 Python 爬虫`

## 常见问题

- 请求失败：确认后端已启动在 `http://127.0.0.1:8000`。
- 跨域失败：确认后端 CORS 允许 `http://127.0.0.1:5173`。
- 媒体无法播放：确认后端数据库 `media_resources.file_path` 指向真实存在的本地音视频文件。
- 语音识别失败：确认后端已配置火山 ASR，并且浏览器允许麦克风权限。
- 语音朗读失败：确认后端已配置火山 TTS。
- 端口被占用：关闭占用进程，或修改 `vite.config.js` 中端口。
