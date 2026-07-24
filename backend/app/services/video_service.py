from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import MediaResource


DEFAULT_MEDIA_SEARCH_LIMIT = 3
QUERY_FILLER_WORDS = [
    "播放",
    "放一下",
    "放一首",
    "来一首",
    "来一段",
    "听一下",
    "听听",
    "想听",
    "我想听",
    "帮我",
    "请",
    "介绍",
    "一下",
    "讲讲",
    "说说",
    "相关",
    "资源",
    "作品",
    "视频",
    "音频",
    "歌曲",
    "音乐",
    "民歌",
    "mp3",
    "mp4",
    "play",
]
TOKEN_SPLIT_PATTERN = r"[\s,，。.!！?？、:：;；《》“”\"'（）()\[\]【】_-]+"


@dataclass(frozen=True)
class MusicTrack:
    id: int
    video_name: str
    file_path: str
    category: str
    media_type: str
    media_kind: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "video_name": self.video_name,
            "file_path": self.file_path,
            "category": self.category,
            "media_type": self.media_type,
            "media_kind": self.media_kind,
        }


def search_videos_by_keywords(
    keywords: list[str],
    limit: int = DEFAULT_MEDIA_SEARCH_LIMIT,
    *,
    prefer_video: bool = True,
    db: Session,
) -> list[dict]:
    if db is None:
        raise RuntimeError("Media search requires a database session.")

    queries = [keyword.strip() for keyword in keywords if keyword and keyword.strip()]
    if not queries:
        return []

    query = " ".join(queries)
    terms = re.split(TOKEN_SPLIT_PATTERN, query)
    library = _load_media_library_from_db(db)
    scored = [
        (score, track)
        for track in library
        if (score := _score_track(track, query, terms)) > 0
    ]

    scored.sort(
        key=lambda item: (
            *(_media_sort_priority(item[1]) if prefer_video else (0, 0)),
            -item[0],
            item[1].category,
            item[1].video_name,
        )
    )
    tracks = [track for _, track in scored] if scored else _fallback_ranked_tracks(library)
    return [track.to_dict() for track in tracks[: max(1, limit)]]


def get_video_by_id(video_id: int, db: Session) -> dict | None:
    if db is None:
        raise RuntimeError("Media playback requires a database session.")

    row = db.query(MediaResource).filter(MediaResource.id == video_id).first()
    if not row:
        return None
    return _track_from_media_resource(row).to_dict()


def _load_media_library_from_db(db: Session) -> tuple[MusicTrack, ...]:
    rows = db.query(MediaResource).order_by(MediaResource.id.asc()).all()
    return tuple(_track_from_media_resource(row) for row in rows)


def _track_from_media_resource(row: MediaResource) -> MusicTrack:
    return MusicTrack(
        id=row.id,
        video_name=row.title,
        file_path=row.file_path,
        category=row.category or "",
        media_type=row.media_type or ("video/mp4" if row.media_kind == "video" else "audio/mpeg"),
        media_kind=row.media_kind or "audio",
    )


def _normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\.(mp3|wav|m4a|aac|ogg|flac|mp4|m4v|mov|webm)$", "", value)
    return re.sub(TOKEN_SPLIT_PATTERN, "", value)


def _clean_query(query: str) -> str:
    cleaned = query.strip()
    for word in QUERY_FILLER_WORDS:
        cleaned = cleaned.replace(word, " ")
    return cleaned.strip()


def _longest_common_substring_length(left: str, right: str) -> int:
    if not left or not right:
        return 0
    max_length = min(len(left), len(right), 8)
    for size in range(max_length, 1, -1):
        for start in range(0, len(left) - size + 1):
            if left[start : start + size] in right:
                return size
    return 0


def _score_track(track: MusicTrack, query: str, terms: list[str]) -> int:
    title = _normalize_text(track.video_name)
    category = _normalize_text(track.category)
    cleaned_query = _normalize_text(_clean_query(query))
    raw_query = _normalize_text(query)

    score = 0
    if cleaned_query and cleaned_query == title:
        score += 200
    if cleaned_query and title in cleaned_query:
        score += 120
    if cleaned_query and cleaned_query in title:
        score += 90
    if raw_query and title in raw_query:
        score += 80
    if category and category in cleaned_query:
        score += 70
    if category and category in raw_query:
        score += 50

    title_overlap = _longest_common_substring_length(cleaned_query or raw_query, title)
    if title_overlap >= 2:
        score += title_overlap * 30

    category_overlap = _longest_common_substring_length(cleaned_query or raw_query, category)
    if category_overlap >= 2:
        score += category_overlap * 15

    for term in terms:
        normalized = _normalize_text(term)
        if not normalized:
            continue
        if normalized == title:
            score += 120
        elif normalized in title:
            score += 60
        elif normalized in category:
            score += 20

    return score


def _media_sort_priority(track: MusicTrack) -> tuple[int, int]:
    file_path = track.file_path.lower()
    return (
        0 if track.media_kind == "video" else 1,
        0 if file_path.endswith(".mp4") else 1,
    )


def _fallback_ranked_tracks(library: tuple[MusicTrack, ...]) -> list[MusicTrack]:
    return sorted(
        library,
        key=lambda track: (
            *_media_sort_priority(track),
            track.category,
            track.video_name,
        ),
    )
