from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import asr, calligraphy, chat, media, short_video, speech


app = FastAPI(title="文化问答与本地媒体智能体")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(asr.router)
app.include_router(speech.router)
app.include_router(calligraphy.router)
app.include_router(media.router)
app.include_router(short_video.router)


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}
