from __future__ import annotations

import re
from typing import Any

from app.agent.llm import invoke_agent_llm, parse_json_object


STABLE_VISUAL_STYLE = (
    "高完成度 2D 手绘动画电影质感，温暖水彩插画，柔和自然光，干净背景，亲和清爽。"
    "画面采用清晰大色块和简洁轮廓，避免过度写实细节。"
)

STABLE_PROMPT_RULES = (
    "稳定出片要求：固定机位或非常缓慢的推拉镜头；优先远景、中景或中远景；"
    "本镜头只表现一个核心动作；动作缓慢、幅度小；不要手部特写、脸部极近景、快速转身、奔跑跳跃、多人混乱互动；"
    "角色始终保持同一脸型、发型、服装、配饰、颜色和身体比例。"
)

STABLE_NEGATIVE_PROMPT = (
    "不要 3D 渲染，不要塑料质感，不要过度写实，不要恐怖血腥，不要角色变脸，"
    "不要服装变化，不要发型变化，不要身体比例变化，不要突然长高变矮，不要脸部融化，"
    "不要多余手指，不要手部特写，不要手指变形，不要身体扭曲，不要快速转身，"
    "不要复杂奔跑跳跃，不要多人混乱互动，不要镜头快速摇晃，不要文字水印。"
)


SHORT_VIDEO_SYSTEM_PROMPT = """你是通用短剧编剧、动画分镜导演和 AI 视频提示词设计师。

目标：把用户给出的任意主题，设计成可进入视频生成流程的 5 镜头短剧方案。题材可以是日常生活、校园、治愈、轻喜剧、奇幻、冒险、节日、传统文化或用户指定的其他方向。

硬性要求：
- 输出 JSON，不要输出 Markdown，不要添加解释。
- 中文输出。
- 当前只生成脚本、分镜和 AI 视频提示词，不要声称已经完成配音、渲染或视频合成。
- 不要强行把普通题材改写成传统文化或成语故事；只有用户明确要求传统文化、成语或典故时，才需要解释寓意。
- 5 个镜头必须形成清晰但简单的因果链：建立场景 -> 触发事件 -> 主角尝试行动 -> 情绪或关系变化 -> 温和收束。
- 剧情目标优先服务视频质量：宁可故事简单，也要让角色稳定、动作简单、构图清楚、镜头连续。
- 每个镜头台词控制在 10-18 个汉字，适合 3-5 秒配音。
- 每个镜头都要给出可直接用于文生视频/图生视频的 prompt。
- 镜头 2-5 必须写清楚如何承接上一镜头尾帧，保证角色、服装、道具、场景连续。
- 如果用户提供角色设定，必须把它作为唯一主角；main_character 和每个 video_prompt 都要保留角色外观、服装、关键配饰和一致性约束。
- 默认画风：高完成度 2D 手绘动画电影质感，温暖水彩插画，柔和自然光，干净背景，亲和、清爽、稳定。
- 必须采用“稳定出片优先”的分镜策略：每个镜头只做一个动作，动作幅度小，镜头运动少，角色尽量处于远景/中景/中远景。
- 避免高风险动作：不要复杂奔跑、跳跃、打斗、快速转身、多人互动、手部精细动作、脸部极近景、拿小物件特写。
- 允许剧情简单，但必须让镜头之间靠同一角色、同一服装、同一方向感和场景逻辑自然衔接。
- 禁止 3D 渲染、塑料质感、现代扁平矢量风、恐怖血腥、过度写实。

JSON 格式：
{
  "title": "短剧标题",
  "topic": "主题",
  "moral": "主题表达或情绪目标",
  "audience": "目标受众",
  "visual_style": "统一画风",
  "main_character": "主角设定",
  "negative_prompt": "全片通用负面提示词",
  "shots": [
    {
      "shot": 1,
      "duration": "3-5秒",
      "scene": "场景",
      "camera": "景别和镜头运动，必须是固定机位/缓慢推拉/缓慢横移之一",
      "action": "画面动作，只写一个核心动作",
      "dialogue": "台词或旁白",
      "continuity": "与上一镜头/下一镜头的衔接",
      "video_prompt": "可直接用于 AI 视频生成的中文提示词"
    }
  ]
}
"""


def generate_short_video_project(
    topic: str,
    *,
    user_message: str = "",
    character_profile: str | None = None,
) -> dict[str, Any]:
    # 模型先生成完整方案，随后仍会经过本地规整，保证前端拿到稳定的五镜头结构。
    cleaned_topic = _clean_topic(topic) or _clean_topic(user_message)
    if not cleaned_topic:
        raise RuntimeError("请提供要生成短剧的主题。")

    cleaned_character = _clean_character_profile(character_profile)
    prompt = (
        f"用户原始需求：{user_message or cleaned_topic}\n\n"
        f"短剧主题：{cleaned_topic}\n\n"
        f"角色设定：{cleaned_character or '用户未指定角色，请设计亲和、稳定、容易保持一致的原创动画主角。'}\n\n"
        "请生成 5 镜头短剧方案，并严格返回 JSON。"
        "优先保证角色不变形、动作可控、镜头连续自然，剧情可以简单但每镜头必须可稳定生成。"
    )
    raw = invoke_agent_llm(SHORT_VIDEO_SYSTEM_PROMPT, prompt, temperature=0.45)
    try:
        project = parse_json_object(raw)
    except Exception:
        project = _fallback_project(cleaned_topic, raw)

    return _normalize_project(project, cleaned_topic, cleaned_character)


def format_short_video_project(project: dict[str, Any]) -> str:
    lines = [
        f"【短剧主题】{project['title']}",
        "",
        f"【主题表达】{project['moral']}",
        "",
        f"【主角】{project['main_character']}",
        "",
        "【五镜头分镜】",
    ]
    for shot in project["shots"]:
        lines.extend(
            [
                f"- 镜头{shot['shot']}（{shot['duration']}）：{shot['scene']}",
                f"  画面：{shot['action']}",
                f"  台词：{shot['dialogue']}",
                f"  提示词：{shot['video_prompt']}",
            ]
        )
    return "\n".join(lines)


def _normalize_project(project: dict[str, Any], topic: str, character_profile: str = "") -> dict[str, Any]:
    # 外部模型可能漏字段、少镜头或输出不稳定描述；这里统一补齐前端需要的 project schema。
    shots = project.get("shots")
    if not isinstance(shots, list):
        shots = []

    normalized_shots = []
    for index, shot in enumerate(shots[:5], start=1):
        if not isinstance(shot, dict):
            continue
        normalized_shots.append(
            _stabilize_shot(
                {
                    "shot": _int_or_default(shot.get("shot"), index),
                    "duration": _safe_duration(shot.get("duration")),
                    "scene": str(shot.get("scene") or ""),
                    "camera": str(shot.get("camera") or ""),
                    "action": str(shot.get("action") or ""),
                    "dialogue": str(shot.get("dialogue") or ""),
                    "continuity": str(shot.get("continuity") or ""),
                    "video_prompt": str(shot.get("video_prompt") or ""),
                },
                topic,
                character_profile,
            )
        )

    while len(normalized_shots) < 5:
        number = len(normalized_shots) + 1
        normalized_shots.append(
            _stabilize_shot(
                {
                    "shot": number,
                    "duration": "3-5秒",
                    "scene": "简洁场景",
                    "camera": "固定中景，轻微推镜",
                    "action": "围绕主题推进一个简单动作。",
                    "dialogue": "我们要想清楚。",
                    "continuity": "承接上一镜头的角色方向和场景气氛。",
                    "video_prompt": f"围绕{topic}设计第{number}个镜头，主角完成一个简单动作。",
                },
                topic,
                character_profile,
            )
        )

    visual_style = str(project.get("visual_style") or "")
    return {
        "title": str(project.get("title") or f"{topic}短剧"),
        "topic": str(project.get("topic") or topic),
        "moral": str(project.get("moral") or "用轻松清晰的方式表达主题情绪，让观众容易理解。"),
        "audience": str(project.get("audience") or "通用动画短视频观众"),
        "visual_style": _ensure_sentence_contains(visual_style, STABLE_VISUAL_STYLE),
        "main_character": character_profile or str(project.get("main_character") or "亲和的原创动画主角，服装和道具在全片保持一致。"),
        "negative_prompt": _merge_negative_prompt(str(project.get("negative_prompt") or "")),
        "shots": normalized_shots,
    }


def _fallback_project(topic: str, raw: str) -> dict[str, Any]:
    return {
        "title": f"{topic}短剧",
        "topic": topic,
        "moral": "用轻松清晰的方式表达主题情绪，让观众容易理解。",
        "audience": "通用动画短视频观众",
        "visual_style": STABLE_VISUAL_STYLE,
        "main_character": "亲和的原创动画主角，服装和道具保持一致。",
        "negative_prompt": STABLE_NEGATIVE_PROMPT,
        "shots": [
            {
                "shot": 1,
                "duration": "3-5秒",
                "scene": "开场场景",
                "camera": "固定中景，轻微推镜",
                "action": raw[:80] or f"围绕{topic}展开一个简单动作。",
                "dialogue": "这个办法真的对吗？",
                "continuity": "为下一镜头的选择埋下伏笔。",
                "video_prompt": f"{STABLE_VISUAL_STYLE}。主题是{topic}，固定中景，主角完成一个简单缓慢动作。{STABLE_PROMPT_RULES}",
            }
        ],
    }


def _stabilize_shot(shot: dict[str, Any], topic: str, character_profile: str) -> dict[str, Any]:
    # 每个镜头都做一次“稳定出片”处理，避免高风险动作导致视频模型生成变形。
    shot_number = _int_or_default(shot.get("shot"), 1)
    scene = str(shot.get("scene") or "简洁场景").strip()
    camera = _stable_camera(str(shot.get("camera") or ""))
    action = _stable_action(str(shot.get("action") or ""), topic)
    continuity = str(shot.get("continuity") or "").strip() or "承接上一镜头的角色方向和场景气氛。"
    prompt = str(shot.get("video_prompt") or "").strip() or f"{scene}，{action}"

    return {
        "shot": shot_number,
        "duration": _safe_duration(shot.get("duration")),
        "scene": scene,
        "camera": camera,
        "action": action,
        "dialogue": _short_dialogue(str(shot.get("dialogue") or "")),
        "continuity": continuity,
        "video_prompt": _build_stable_video_prompt(
            prompt,
            topic=topic,
            scene=scene,
            camera=camera,
            action=action,
            continuity=continuity,
            character_profile=character_profile,
        ),
    }


def _build_stable_video_prompt(
    prompt: str,
    *,
    topic: str,
    scene: str,
    camera: str,
    action: str,
    continuity: str,
    character_profile: str,
) -> str:
    # video_prompt 必须自包含，因为单个镜头可能被独立提交给第三方视频生成服务。
    parts = [
        STABLE_VISUAL_STYLE,
        f"主题：{topic}。",
        f"场景：{scene}。",
        f"镜头：{camera}。",
        f"动作：{action}。",
        f"衔接：{continuity}。",
        prompt,
        STABLE_PROMPT_RULES,
    ]
    cleaned = "。".join(_trim_sentence(part) for part in parts if _trim_sentence(part))
    return _with_character_profile(cleaned, character_profile)


def _stable_camera(camera: str) -> str:
    cleaned = camera.strip()
    low_risk_keywords = ("固定", "中景", "远景", "中远景", "缓慢", "轻微", "推镜", "横移")
    if cleaned and any(keyword in cleaned for keyword in low_risk_keywords):
        return cleaned
    return "固定中景，轻微推镜，角色保持在画面中央或三分线位置"


def _stable_action(action: str, topic: str) -> str:
    # 将奔跑、打斗等复杂动作降级为慢动作表达，提升短视频生成的一致性。
    cleaned = re.sub(r"\s+", " ", action.strip())
    if not cleaned:
        return f"主角围绕{topic}完成一个简单、缓慢、可清楚识别的动作。"
    risk_words = ("奔跑", "跳跃", "打斗", "追逐", "翻滚", "旋转", "快速", "飞奔", "扑向", "多人")
    if any(word in cleaned for word in risk_words):
        return f"主角用缓慢、简洁的动作表达{topic}相关情节，避免剧烈运动。"
    return cleaned[:90]


def _short_dialogue(dialogue: str) -> str:
    cleaned = re.sub(r"\s+", "", dialogue.strip())
    if not cleaned:
        return "我明白了。"
    return cleaned[:24]


def _safe_duration(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "3-5秒"
    numbers = [int(number) for number in re.findall(r"\d+", text)]
    if not numbers:
        return "3-5秒"
    low = max(3, min(5, min(numbers)))
    high = max(low, min(5, max(numbers)))
    return f"{low}-{high}秒" if low != high else f"{low}秒"


def _merge_negative_prompt(value: str) -> str:
    # 用户或模型已有负面提示词时保留，同时强制追加项目的通用稳定性约束。
    return _ensure_sentence_contains(value, STABLE_NEGATIVE_PROMPT)


def _ensure_sentence_contains(value: str, required: str) -> str:
    cleaned = _trim_sentence(value)
    required_clean = _trim_sentence(required)
    if not cleaned:
        return required_clean
    if required_clean in cleaned:
        return cleaned
    return f"{cleaned}。{required_clean}"


def _trim_sentence(value: str) -> str:
    return str(value or "").strip().strip("。；; ")


def _with_character_profile(prompt: str, character_profile: str) -> str:
    cleaned = prompt.strip()
    if not character_profile:
        return cleaned
    if character_profile in cleaned:
        return cleaned
    return (
        f"{cleaned}。主角必须保持一致：{character_profile}。"
        "保持同一脸型、发型、服装、配饰和颜色，不要角色变脸。"
    )


def _clean_character_profile(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())[:1200]


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_topic(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    quoted = re.findall(r"[“‘\"']([^”’\"']{1,40})[”’\"']", text)
    if quoted:
        return quoted[0].strip()

    cleaned = re.sub(
        r"(帮我|请|生成|制作|做一个|做成|改成|短剧|短视频|动画|视频|成语|故事|分镜|剧本|脚本|给我|一个)",
        " ",
        text,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，。！；：.;:!?")
    return cleaned[:40]
