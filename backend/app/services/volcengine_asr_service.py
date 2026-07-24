from __future__ import annotations

# gzip/json/uuid 用于按火山 ASR 协议压缩请求体、解析响应和生成请求 ID。
import gzip
import json
import uuid

from app.config import get_settings


PROTOCOL_VERSION = 0b0001
HEADER_SIZE = 0b0001

FULL_CLIENT_REQUEST = 0b0001
AUDIO_ONLY_REQUEST = 0b0010
FULL_SERVER_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

NO_SEQUENCE = 0b0000
NEGATIVE_SEQUENCE = 0b0010

NO_SERIALIZATION = 0b0000
JSON_SERIALIZATION = 0b0001
GZIP_COMPRESSION = 0b0001

CLIENT_HEADER = bytes(
    [
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (FULL_CLIENT_REQUEST << 4) | NO_SEQUENCE,
        (JSON_SERIALIZATION << 4) | GZIP_COMPRESSION,
        0,
    ]
)
AUDIO_HEADER = bytes(
    [
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (AUDIO_ONLY_REQUEST << 4) | NO_SEQUENCE,
        (NO_SERIALIZATION << 4) | GZIP_COMPRESSION,
        0,
    ]
)
LAST_AUDIO_HEADER = bytes(
    [
        (PROTOCOL_VERSION << 4) | HEADER_SIZE,
        (AUDIO_ONLY_REQUEST << 4) | NEGATIVE_SEQUENCE,
        (NO_SERIALIZATION << 4) | GZIP_COMPRESSION,
        0,
    ]
)


def has_volcengine_asr_config() -> bool:
    settings = get_settings()
    return bool(settings.volcengine_asr_app_id and settings.volcengine_asr_access_token)


def volcengine_asr_headers() -> dict[str, str]:
    settings = get_settings()
    if "/api/v2/asr" in settings.volcengine_asr_url:
        return {"Authorization": f"Bearer;{settings.volcengine_asr_access_token}"}

    return {
        "X-Api-App-Key": settings.volcengine_asr_app_id,
        "X-Api-Access-Key": settings.volcengine_asr_access_token,
        "X-Api-Resource-Id": settings.volcengine_asr_resource_id,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }


def build_volcengine_asr_request_frame() -> bytes:
    settings = get_settings()
    if "/api/v2/asr" in settings.volcengine_asr_url:
        payload = {
            "app": {
                "appid": settings.volcengine_asr_app_id,
                "token": settings.volcengine_asr_access_token,
                "cluster": settings.volcengine_asr_cluster,
            },
            "user": {
                "uid": "culture-video-agent",
            },
            "audio": {
                "format": settings.volcengine_asr_format,
                "codec": settings.volcengine_asr_codec,
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "language": "zh-CN",
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "workflow": settings.volcengine_asr_workflow,
                "result_type": "full",
                "show_utterances": True,
            },
        }
    else:
        payload = {
            "user": {
                "uid": "culture-video-agent",
            },
            "audio": {
                "format": settings.volcengine_asr_format,
                "codec": settings.volcengine_asr_codec,
                "rate": 16000,
                "bits": 16,
                "channel": 1,
            },
            "request": {
                "model_name": "bigmodel",
                "enable_punc": True,
                "enable_itn": True,
                "result_type": "full",
                "show_utterances": True,
            },
        }
    return _build_frame(CLIENT_HEADER, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def build_volcengine_audio_frame(audio: bytes, *, final: bool = False) -> bytes:
    return _build_frame(LAST_AUDIO_HEADER if final else AUDIO_HEADER, audio)


def parse_volcengine_asr_response(payload: bytes | str) -> tuple[int, str, int, int | None]:
    if isinstance(payload, str):
        data = json.loads(payload)
        code = int(data.get("code", data.get("status_code", 0)))
        return code, _extract_text(data) if code == 0 else str(data), 2, None

    if len(payload) < 4:
        return -1, "火山语音识别返回数据异常。", 2, None

    header_size = (payload[0] & 0x0F) * 4
    message_type = payload[1] >> 4
    flags = payload[1] & 0x0F
    compression = payload[2] & 0x0F
    body = payload[header_size:]
    sequence: int | None = None
    is_final = flags == NEGATIVE_SEQUENCE

    if message_type == SERVER_ERROR_RESPONSE:
        if len(body) < 8:
            return -1, "火山语音识别返回错误。", 2, None
        code = int.from_bytes(body[:4], "big", signed=False)
        size = int.from_bytes(body[4:8], "big", signed=False)
        error_body = body[8 : 8 + size]
        if compression == GZIP_COMPRESSION:
            error_body = gzip.decompress(error_body)
        return code or -1, error_body.decode("utf-8", errors="ignore"), 2, sequence

    if message_type == SERVER_ACK:
        if len(body) >= 4:
            sequence = int.from_bytes(body[:4], "big", signed=True)
            is_final = is_final or sequence < 0
        return 0, "", 2 if is_final else 1, sequence

    if message_type != FULL_SERVER_RESPONSE:
        return 0, "", 2 if is_final else 1, sequence

    data_body, sequence = _extract_server_payload(body, flags)
    if sequence is not None and sequence < 0:
        is_final = True

    if compression == GZIP_COMPRESSION and data_body:
        data_body = gzip.decompress(data_body)

    if not data_body:
        return 0, "", 2 if is_final else 1, sequence

    data = json.loads(data_body.decode("utf-8"))
    code = int(data.get("code", data.get("status_code", 0)))
    if code != 0:
        return code, data.get("message") or data.get("error") or str(data), 2, sequence
    return code, _extract_text(data), 2 if is_final else 1, sequence


def _build_frame(header: bytes, payload: bytes) -> bytes:
    compressed = gzip.compress(payload)
    return header + len(compressed).to_bytes(4, "big", signed=False) + compressed


def _extract_server_payload(body: bytes, flags: int) -> tuple[bytes, int | None]:
    if len(body) < 4:
        return b"", None

    if flags != NO_SEQUENCE and len(body) >= 8:
        sequence = int.from_bytes(body[:4], "big", signed=True)
        size = int.from_bytes(body[4:8], "big", signed=False)
        if 0 <= size <= len(body) - 8:
            return body[8 : 8 + size], sequence

    size = int.from_bytes(body[:4], "big", signed=False)
    if 0 <= size <= len(body) - 4:
        return body[4 : 4 + size], None

    return body, None


def _extract_text(data: dict) -> str:
    result = data.get("result")

    if isinstance(result, list):
        return "".join(str(item.get("text", "")) for item in result if isinstance(item, dict))

    if isinstance(result, dict):
        text = result.get("text")
        if text:
            return str(text)
        utterances = result.get("utterances")
        if isinstance(utterances, list):
            return "".join(str(item.get("text", "")) for item in utterances if isinstance(item, dict))

    if data.get("text"):
        return str(data["text"])

    utterances = data.get("utterances")
    if isinstance(utterances, list):
        return "".join(str(item.get("text", "")) for item in utterances if isinstance(item, dict))

    return ""
