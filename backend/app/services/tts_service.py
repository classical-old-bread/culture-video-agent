from __future__ import annotations

import base64
import uuid

# requests 用于调用火山引擎 TTS 的 HTTP 接口。
import requests

from app.config import get_settings
from app.services.text_cleaner import clean_answer_text


def _ensure_volcengine_config() -> None:
    settings = get_settings()
    missing = []

    if not settings.volcengine_tts_app_id or settings.volcengine_tts_app_id.startswith("your_"):
        missing.append("VOLCENGINE_TTS_APP_ID")
    if not settings.volcengine_tts_access_token or settings.volcengine_tts_access_token.startswith("your_"):
        missing.append("VOLCENGINE_TTS_ACCESS_TOKEN")
    if not settings.volcengine_tts_voice_type or settings.volcengine_tts_voice_type.startswith("your_"):
        missing.append("VOLCENGINE_TTS_VOICE_TYPE")

    if missing:
        raise RuntimeError("火山引擎语音配置缺失，请在 backend/.env 中填写：" + "、".join(missing))


def synthesize_speech(text: str) -> bytes:
    _ensure_volcengine_config()
    settings = get_settings()

    cleaned_text = clean_answer_text(text).strip()
    if not cleaned_text:
        raise RuntimeError("语音合成文本不能为空。")

    payload = {
        "app": {
            "appid": settings.volcengine_tts_app_id,
            "token": settings.volcengine_tts_access_token,
            "cluster": settings.volcengine_tts_cluster,
        },
        "user": {
            "uid": "culture-video-agent",
        },
        "audio": {
            "voice_type": settings.volcengine_tts_voice_type,
            "encoding": settings.volcengine_tts_encoding,
            "speed_ratio": settings.volcengine_tts_speed_ratio,
            "volume_ratio": settings.volcengine_tts_volume_ratio,
            "pitch_ratio": settings.volcengine_tts_pitch_ratio,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": cleaned_text[:500],
            "operation": "query",
        },
    }

    try:
        response = requests.post(
            settings.volcengine_tts_url,
            headers={
                "Authorization": f"Bearer;{settings.volcengine_tts_access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=12,
        )
    except requests.RequestException as exc:
        raise RuntimeError("火山引擎语音合成请求失败，请检查网络或防火墙。") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"火山引擎语音合成返回异常：HTTP {response.status_code}") from exc

    if response.status_code != 200:
        raise RuntimeError(f"火山引擎语音合成失败：HTTP {response.status_code}，{data}")

    if data.get("code") not in (0, 3000, None):
        raise RuntimeError(f"火山引擎语音合成失败：{data}")

    audio_base64 = data.get("data")
    if not audio_base64:
        raise RuntimeError(f"火山引擎语音合成没有返回音频：{data}")

    try:
        return base64.b64decode(audio_base64)
    except Exception as exc:
        raise RuntimeError("火山引擎语音音频解码失败。") from exc
