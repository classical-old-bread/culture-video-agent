from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, examples=["介绍一首地方民歌的文化背景"])
    conversation_context: str | None = Field(default=None, max_length=6000, examples=[None])
    calligraphy_source_text: str | None = Field(default=None, max_length=4000, examples=[None])
    calligraphy_style: str | None = Field(default=None, max_length=50, examples=[None])
    calligraphy_author: str | None = Field(default=None, max_length=50, examples=[None])

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "介绍一首地方民歌的文化背景"},
                {
                    "message": "把“春眠不觉晓，处处闻啼鸟”生成楷书书法作品",
                    "calligraphy_style": "楷书",
                    "calligraphy_author": "柳公权",
                },
                {"message": "上网搜索一首地方民歌的资料，并总结来源"},
            ]
        }
    }


class VideoItem(BaseModel):
    id: int
    video_name: str
    file_path: str
    category: str | None = None
    media_type: str = "audio/mpeg"
    media_kind: str | None = None

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    type: Literal["text", "text_with_video", "out_of_scope", "calligraphy", "agent"]
    answer: str
    videos: list[VideoItem] = []
    auto_play: bool = False
    calligraphy_image_url: str | None = None
    calligraphy_missing_chars: list[str] = []
    sources: list[dict] = []
    tool_calls: list[dict] = []


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
