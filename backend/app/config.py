import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

# python-dotenv 会读取 backend/.env，把环境变量加载到 os.getenv 可见的环境里。
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=True)


class Settings:
    backend_dir: Path = BACKEND_DIR

    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    agent_model: str = os.getenv("AGENT_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))

    web_search_provider: str = os.getenv("WEB_SEARCH_PROVIDER", "tavily")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
    tavily_search_url: str = os.getenv("TAVILY_SEARCH_URL", "https://api.tavily.com/search")
    web_search_max_results: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    web_search_timeout_seconds: int = int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "12"))

    volcengine_tts_app_id: str = os.getenv("VOLCENGINE_TTS_APP_ID", "")
    volcengine_tts_access_token: str = os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", "")
    volcengine_tts_cluster: str = os.getenv("VOLCENGINE_TTS_CLUSTER", "volcano_tts")
    volcengine_tts_voice_type: str = os.getenv("VOLCENGINE_TTS_VOICE_TYPE", "")
    volcengine_tts_url: str = os.getenv("VOLCENGINE_TTS_URL", "https://openspeech.bytedance.com/api/v1/tts")
    volcengine_tts_encoding: str = os.getenv("VOLCENGINE_TTS_ENCODING", "mp3")
    volcengine_tts_speed_ratio: float = float(os.getenv("VOLCENGINE_TTS_SPEED_RATIO", "1.0"))
    volcengine_tts_volume_ratio: float = float(os.getenv("VOLCENGINE_TTS_VOLUME_RATIO", "1.0"))
    volcengine_tts_pitch_ratio: float = float(os.getenv("VOLCENGINE_TTS_PITCH_RATIO", "1.0"))

    volcengine_asr_app_id: str = os.getenv("VOLCENGINE_ASR_APP_ID", os.getenv("VOLCENGINE_TTS_APP_ID", ""))
    volcengine_asr_access_token: str = os.getenv(
        "VOLCENGINE_ASR_ACCESS_TOKEN",
        os.getenv("VOLCENGINE_TTS_ACCESS_TOKEN", ""),
    )
    volcengine_asr_resource_id: str = os.getenv("VOLCENGINE_ASR_RESOURCE_ID", "volc.bigasr.sauc.duration")
    volcengine_asr_cluster: str = os.getenv("VOLCENGINE_ASR_CLUSTER", "volc.bigasr.sauc.duration")
    volcengine_asr_url: str = os.getenv("VOLCENGINE_ASR_URL", "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel")
    volcengine_asr_workflow: str = os.getenv("VOLCENGINE_ASR_WORKFLOW", "audio_in,resample,partition,vad,fe,decode")
    volcengine_asr_format: str = os.getenv("VOLCENGINE_ASR_FORMAT", "pcm")
    volcengine_asr_codec: str = os.getenv("VOLCENGINE_ASR_CODEC", "raw")

    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "culture_video_agent")

    backend_host: str = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))

    calligraphy_output_dir: str = os.getenv(
        "CALLIGRAPHY_OUTPUT_DIR",
        str(backend_dir / "generated" / "calligraphy"),
    )
    calligraphy_dataset_dir: str = os.getenv(
        "CALLIGRAPHY_DATASET_DIR",
        str(backend_dir / "data" / "calligraphy_fonts"),
    )
    media_library_dir: str = os.getenv(
        "MEDIA_LIBRARY_DIR",
        str(backend_dir / "data" / "media"),
    )

    knowledge_base_docs_dir: str = os.getenv(
        "KNOWLEDGE_BASE_DOCS_DIR",
        str(backend_dir / "knowledge_base" / "docs"),
    )
    knowledge_base_chroma_dir: str = os.getenv(
        "KNOWLEDGE_BASE_CHROMA_DIR",
        str(backend_dir / "knowledge_base" / "chroma"),
    )
    knowledge_base_collection: str = os.getenv("KNOWLEDGE_BASE_COLLECTION", "culture_knowledge")
    knowledge_base_embedding_model: str = os.getenv(
        "KNOWLEDGE_BASE_EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2",
    )
    knowledge_base_top_k: int = int(os.getenv("KNOWLEDGE_BASE_TOP_K", "4"))
    knowledge_base_chunk_size: int = int(os.getenv("KNOWLEDGE_BASE_CHUNK_SIZE", "800"))
    knowledge_base_chunk_overlap: int = int(os.getenv("KNOWLEDGE_BASE_CHUNK_OVERLAP", "120"))

    kling_api_key: str = os.getenv("KLING_API_KEY", "")
    kling_model: str = os.getenv("KLING_MODEL", "kling/kling-v3-omni-video-generation")
    short_video_output_dir: str = os.getenv(
        "SHORT_VIDEO_OUTPUT_DIR",
        str(backend_dir / "generated" / "short_video"),
    )
    short_video_prototype_frame_dir: str = os.getenv(
        "SHORT_VIDEO_PROTOTYPE_FRAME_DIR",
        str(backend_dir / "generated" / "short_video" / "prototype_frames"),
    )
    short_video_render_api_base_url: str = os.getenv("SHORT_VIDEO_RENDER_API_BASE_URL", "").rstrip("/")
    short_video_render_timeout_seconds: int = int(os.getenv("SHORT_VIDEO_RENDER_TIMEOUT_SECONDS", "30"))

    max_message_length: int = 1000

    @property
    def database_url(self) -> str:
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
