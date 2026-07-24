from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import requests

from app.config import get_settings


VIDEO_STYLE_LOCK = (
    "画质与风格锁定：高完成度 2D 手绘动画电影质感，温暖东方水彩插画，柔和自然光，"
    "清晰大色块和简洁轮廓，儿童友好。角色必须保持同一脸型、发型、服装、配饰、颜色和身体比例。"
    "镜头优先固定中景或中远景，只做一个简单缓慢动作。"
    "负面约束：不要 3D 渲染，不要塑料质感，不要角色变脸，不要服装变化，不要手部特写，"
    "不要快速转身，不要复杂奔跑跳跃，不要多人混乱互动，不要文字水印。"
)

_RENDER_TASKS: dict[str, dict[str, Any]] = {}


def submit_short_video_render(
    *,
    prompt: str,
    duration: int = 5,
    previous_tail_frame_url: str | None = None,
    character_reference_image_data_url: str | None = None,
    prototype_reference_frame_url: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.kling_api_key:
        return _submit_kling_render(
            prompt=prompt,
            duration=duration,
            previous_tail_frame_url=previous_tail_frame_url,
            character_reference_image_data_url=character_reference_image_data_url,
            prototype_reference_frame_url=prototype_reference_frame_url,
        )
    if settings.short_video_render_api_base_url:
        return _submit_proxy_render(
            prompt=prompt,
            duration=duration,
            previous_tail_frame_url=previous_tail_frame_url,
        )
    raise RuntimeError("未配置 KLING_API_KEY，无法调用可灵视频生成。请在 backend/.env 中配置可灵密钥。")


def fetch_short_video_render_status(task_id: str) -> dict[str, Any]:
    if get_settings().kling_api_key:
        return _fetch_kling_status(task_id)
    return _fetch_proxy_status(task_id)


def get_short_video_asset_path(kind: str, filename: str) -> Path:
    if kind not in {"video", "frames"}:
        raise RuntimeError("不支持的短视频资源类型。")
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise RuntimeError("非法短视频资源文件名。")

    target = (_output_dir() / kind / filename).resolve()
    root = (_output_dir() / kind).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise RuntimeError("非法短视频资源路径。")
    if not target.exists():
        raise RuntimeError("短视频资源不存在。")
    return target


def list_short_video_prototype_frames() -> list[dict[str, str]]:
    root = _prototype_review_dir()
    if not root.exists():
        return []
    frames = sorted(path for path in root.glob("frame_*.jpg") if path.is_file())
    return [
        {
            "name": path.name,
            "url": f"/api/short-video/prototype-frames/{path.name}",
        }
        for path in frames
    ]


def get_short_video_prototype_frame_path(filename: str) -> Path:
    if not re.fullmatch(r"frame_\d+\.(jpg|jpeg|png|webp)", filename or "", re.IGNORECASE):
        raise RuntimeError("非法原型帧文件名。")

    root = _prototype_review_dir().resolve()
    target = (root / filename).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise RuntimeError("非法原型帧路径。")
    if not target.exists() or not target.is_file():
        raise RuntimeError("原型帧不存在。")
    return target


def _submit_kling_render(
    *,
    prompt: str,
    duration: int,
    previous_tail_frame_url: str | None,
    character_reference_image_data_url: str | None,
    prototype_reference_frame_url: str | None,
) -> dict[str, Any]:
    try:
        import dashscope
    except ImportError as exc:
        raise RuntimeError("缺少 dashscope 依赖，请先安装：pip install dashscope") from exc

    settings = get_settings()
    dashscope.api_key = settings.kling_api_key
    final_prompt = f"{VIDEO_STYLE_LOCK}\n镜头内容：{prompt}"
    media = []
    character_reference_path = _save_character_reference_image(character_reference_image_data_url)
    character_reference_url = f"file://{character_reference_path}" if character_reference_path else ""
    prototype_reference_path = _resolve_prototype_frame_url(prototype_reference_frame_url)
    prototype_reference_url = f"file://{prototype_reference_path}" if prototype_reference_path else ""

    if prototype_reference_path:
        final_prompt = (
            "画面原型约束：随请求提供的原型帧是本次视频的画面构图、角色造型、画风、色彩和场景质感依据；"
            "在此基础上只做轻微、稳定、自然的动作延展，不要重绘成其他角色或其他画风。\n"
            f"{final_prompt}"
        )
        media.append({"type": "refer", "url": prototype_reference_url})

    if character_reference_path:
        final_prompt = (
            "角色参考图约束：随请求提供的人物参考图是唯一主角外观依据，必须保持同一脸型、发型、服装、配色、体型和关键配饰；"
            "只允许动作和镜头发生变化，不要改变角色身份、年龄、服装或物种。\n"
            f"{final_prompt}"
        )
        media.append({"type": "refer", "url": character_reference_url})

    previous_frame_path = _resolve_local_asset_url(previous_tail_frame_url)
    if previous_frame_path:
        final_prompt = (
            "接续镜头：以上一个镜头尾帧作为本镜头首帧，保持构图、人物状态、服装、光线和背景方向自然延展。\n"
            f"{final_prompt}"
        )
        media.append({"type": "refer", "url": f"file://{previous_frame_path}"})

    kwargs = {
        "model": settings.kling_model,
        "prompt": final_prompt,
        "mode": "std",
        "duration": max(3, min(5, int(duration or 5))),
        "aspect_ratio": "16:9",
    }
    if prototype_reference_url:
        kwargs["img_url"] = prototype_reference_url
        kwargs["first_frame_url"] = prototype_reference_url
    if character_reference_url:
        kwargs["reference_url"] = character_reference_url
    reference_urls = [url for url in (prototype_reference_url, character_reference_url) if url]
    if reference_urls:
        kwargs["reference_urls"] = reference_urls
    if media:
        kwargs["media"] = media

    task = dashscope.VideoSynthesis.async_call(**kwargs)
    if task.status_code != 200:
        raise RuntimeError(f"可灵任务提交失败 [{task.code}]: {task.message}")
    if not task.output or not task.output.task_id:
        raise RuntimeError("可灵未返回 task_id。")

    task_id = task.output.task_id
    _RENDER_TASKS[task_id] = {
        "task_id": task_id,
        "status": "processing",
        "progress": 0,
        "video_url": "",
        "tail_frame_url": "",
        "duration": kwargs["duration"],
        "last_status": "",
    }
    return {"task_id": task_id, "duration": kwargs["duration"], "status": "processing"}


def _fetch_kling_status(task_id: str) -> dict[str, Any]:
    try:
        import dashscope
    except ImportError as exc:
        raise RuntimeError("缺少 dashscope 依赖，请先安装：pip install dashscope") from exc

    settings = get_settings()
    dashscope.api_key = settings.kling_api_key
    task = _RENDER_TASKS.setdefault(
        task_id,
        {"task_id": task_id, "status": "processing", "progress": 0, "video_url": "", "tail_frame_url": ""},
    )
    if task.get("status") in {"success", "failed"}:
        return task

    result = dashscope.VideoSynthesis.fetch(task_id)
    if result.status_code != 200:
        task.update(status="failed", error=f"可灵状态查询失败：{result.message}")
        return task

    status = result.output.task_status
    if status == "SUCCEEDED":
        video_url = getattr(result.output, "video_url", "") or ""
        if not video_url:
            task.update(status="failed", error="可灵未返回视频 URL。")
            return task
        video_path, tail_frame_path = _download_and_prepare_video(video_url, task_id)
        task.update(
            status="success",
            progress=100,
            video_url=_asset_url("video", video_path.name),
            tail_frame_url=_asset_url("frames", tail_frame_path.name) if tail_frame_path else "",
        )
    elif status in {"FAILED", "CANCELLED"}:
        task.update(status="failed", error=getattr(result, "message", "") or "可灵任务失败。")
    else:
        task.update(status="processing", progress=min(int(task.get("progress") or 0) + 5, 95), last_status=status)
    return task


def _submit_proxy_render(
    *,
    prompt: str,
    duration: int = 5,
    previous_tail_frame_url: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    base_url = settings.short_video_render_api_base_url.rstrip("/")
    payload = {"prompt": prompt, "duration": str(max(3, min(5, int(duration or 5))))}
    if previous_tail_frame_url:
        payload["is_continuation"] = "true"
        payload["prev_frame_path"] = previous_tail_frame_url

    response = requests.post(
        f"{base_url}/api/video/submit",
        data=payload,
        timeout=settings.short_video_render_timeout_seconds,
    )
    _raise_for_render_error(response)
    data = response.json()
    if not data.get("task_id"):
        raise RuntimeError("视频渲染服务未返回 task_id。")
    return data


def _fetch_proxy_status(task_id: str) -> dict[str, Any]:
    settings = get_settings()
    base_url = settings.short_video_render_api_base_url.rstrip("/")
    if not base_url:
        raise RuntimeError("未配置视频渲染服务。")
    response = requests.get(
        f"{base_url}/api/video/status/{task_id}",
        timeout=settings.short_video_render_timeout_seconds,
    )
    _raise_for_render_error(response)
    data = response.json()
    for key in ("video_url", "tail_frame_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("/"):
            data[key] = f"{base_url}{value}"
    return data


def _download_and_prepare_video(video_url: str, task_id: str) -> tuple[Path, Path | None]:
    video_dir = _output_dir() / "video"
    frames_dir = _output_dir() / "frames"
    video_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    raw_path = video_dir / f"raw_{task_id}.mp4"
    video_path = video_dir / f"kling_{task_id}.mp4"
    urllib.request.urlretrieve(video_url, raw_path)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(video_path),
            ],
            capture_output=True,
            check=True,
        )
        raw_path.unlink(missing_ok=True)
    except Exception:
        shutil.move(str(raw_path), str(video_path))

    return video_path, _extract_last_frame(video_path)


def _extract_last_frame(video_path: Path) -> Path | None:
    frame_path = _output_dir() / "frames" / f"tail_{video_path.stem}.jpg"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-sseof",
                "-0.08",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            capture_output=True,
            check=True,
        )
    except Exception:
        return None
    return frame_path if frame_path.exists() else None


def _save_character_reference_image(data_url: str | None) -> Path | None:
    if not data_url:
        return None

    match = re.fullmatch(r"data:image/(png|jpeg|jpg|webp);base64,(.+)", data_url, re.IGNORECASE | re.DOTALL)
    if not match:
        raise RuntimeError("人物参考图格式不支持，请上传 PNG、JPG 或 WebP 图片。")

    suffix = "jpg" if match.group(1).lower() == "jpeg" else match.group(1).lower()
    try:
        payload = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("人物参考图解析失败，请重新上传图片。") from exc

    if not payload:
        raise RuntimeError("人物参考图为空，请重新上传图片。")
    if len(payload) > 6 * 1024 * 1024:
        raise RuntimeError("人物参考图过大，请上传 6MB 以内的图片。")

    reference_dir = _output_dir() / "references"
    reference_dir.mkdir(parents=True, exist_ok=True)
    path = reference_dir / f"character_{uuid.uuid4().hex}.{suffix}"
    path.write_bytes(payload)
    return path


def _resolve_prototype_frame_url(value: str | None) -> Path | None:
    if not value:
        return None
    marker = "/api/short-video/prototype-frames/"
    normalized = value.replace("\\", "/")
    if marker not in normalized:
        return None
    filename = normalized.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
    return get_short_video_prototype_frame_path(filename)


def _resolve_local_asset_url(value: str | None) -> Path | None:
    if not value:
        return None
    marker = "/api/short-video/assets/"
    normalized = value.replace("\\", "/")
    if marker not in normalized:
        return None
    _, suffix = normalized.split(marker, 1)
    parts = suffix.split("/", 1)
    if len(parts) != 2:
        return None
    try:
        return get_short_video_asset_path(parts[0], parts[1])
    except RuntimeError:
        return None


def _asset_url(kind: str, filename: str) -> str:
    return f"/api/short-video/assets/{kind}/{filename}"


def _output_dir() -> Path:
    return Path(get_settings().short_video_output_dir).expanduser().resolve()


def _prototype_review_dir() -> Path:
    return Path(get_settings().short_video_prototype_frame_dir).expanduser().resolve()


def _raise_for_render_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        data = response.json()
        detail = data.get("detail") or data.get("message") or response.text
    except Exception:
        detail = response.text
    raise RuntimeError(f"视频渲染服务调用失败：{detail}")
