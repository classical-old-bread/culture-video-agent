from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


SUPPORTED_KNOWLEDGE_SUFFIXES = {".txt", ".md", ".markdown", ".json"}


@dataclass
class KnowledgeBaseHit:
    content: str
    source: str
    chunk_id: str
    score: float | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "source": self.source,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "metadata": self.metadata or {},
        }


@dataclass
class KnowledgeBaseSearchResult:
    query: str
    status: str
    message: str
    hits: list[KnowledgeBaseHit]
    backend: str

    @property
    def has_hits(self) -> bool:
        return bool(self.hits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "status": self.status,
            "message": self.message,
            "backend": self.backend,
            "results": [hit.to_dict() for hit in self.hits],
        }


def search_knowledge_base(query: str, *, top_k: int | None = None) -> KnowledgeBaseSearchResult:
    settings = get_settings()
    cleaned_query = query.strip()
    limit = max(1, min(top_k or settings.knowledge_base_top_k, 12))

    if not cleaned_query:
        return KnowledgeBaseSearchResult(
            query=query,
            status="empty_query",
            message="知识库检索问题为空。",
            hits=[],
            backend="none",
        )

    chroma_result = _search_chroma(cleaned_query, limit)
    if chroma_result.status in {"success", "empty"}:
        return chroma_result

    return _search_local_documents(cleaned_query, limit, fallback_message=chroma_result.message)


def _search_chroma(query: str, top_k: int) -> KnowledgeBaseSearchResult:
    settings = get_settings()
    chroma_dir = Path(settings.knowledge_base_chroma_dir).expanduser().resolve()
    if not chroma_dir.exists():
        return KnowledgeBaseSearchResult(
            query=query,
            status="not_ready",
            message="Chroma 知识库索引尚未构建。",
            hits=[],
            backend="chroma",
        )

    try:
        import chromadb
    except ImportError:
        return KnowledgeBaseSearchResult(
            query=query,
            status="dependency_missing",
            message="未安装 chromadb，已尝试回退到本地文档关键词检索。",
            hits=[],
            backend="chroma",
        )

    try:
        embedding = _embed_query(query)
    except RuntimeError as exc:
        return KnowledgeBaseSearchResult(
            query=query,
            status="dependency_missing",
            message=f"{exc} 已尝试回退到本地文档关键词检索。",
            hits=[],
            backend="chroma",
        )

    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(settings.knowledge_base_collection)
        payload = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        return KnowledgeBaseSearchResult(
            query=query,
            status="not_ready",
            message=f"Chroma 知识库暂不可用：{type(exc).__name__}: {exc}",
            hits=[],
            backend="chroma",
        )

    documents = (payload.get("documents") or [[]])[0]
    metadatas = (payload.get("metadatas") or [[]])[0]
    distances = (payload.get("distances") or [[]])[0]
    ids = (payload.get("ids") or [[]])[0]

    hits = []
    for index, document in enumerate(documents):
        content = str(document or "").strip()
        if not content:
            continue
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
        distance = distances[index] if index < len(distances) else None
        score = _distance_to_score(distance)
        hits.append(
            KnowledgeBaseHit(
                content=content,
                source=str(metadata.get("source") or "unknown"),
                chunk_id=str(ids[index] if index < len(ids) else metadata.get("chunk_id") or index),
                score=score,
                metadata=metadata,
            )
        )

    if not hits:
        return KnowledgeBaseSearchResult(
            query=query,
            status="empty",
            message="Chroma 知识库没有检索到相关资料。",
            hits=[],
            backend="chroma",
        )

    return KnowledgeBaseSearchResult(
        query=query,
        status="success",
        message=f"从 Chroma 知识库检索到 {len(hits)} 条相关资料。",
        hits=hits,
        backend="chroma",
    )


def _search_local_documents(
    query: str,
    top_k: int,
    *,
    fallback_message: str = "",
) -> KnowledgeBaseSearchResult:
    settings = get_settings()
    docs_dir = Path(settings.knowledge_base_docs_dir).expanduser().resolve()
    if not docs_dir.exists():
        message = "知识库资料目录不存在，请先添加本地资料并构建索引。"
        if fallback_message:
            message = f"{fallback_message} {message}"
        return KnowledgeBaseSearchResult(query=query, status="not_ready", message=message, hits=[], backend="local")

    chunks = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_KNOWLEDGE_SUFFIXES:
            continue
        text = read_knowledge_document(path)
        for index, chunk in enumerate(split_text_into_chunks(text)):
            chunks.append((path, index, chunk))

    if not chunks:
        message = "知识库资料目录为空，或没有可读取的 txt/md/json 文档。"
        if fallback_message:
            message = f"{fallback_message} {message}"
        return KnowledgeBaseSearchResult(query=query, status="not_ready", message=message, hits=[], backend="local")

    scored = []
    for path, index, chunk in chunks:
        score = _keyword_score(query, chunk, path.name)
        if score > 0:
            scored.append((score, path, index, chunk))

    scored.sort(key=lambda item: (-item[0], str(item[1]), item[2]))
    hits = [
        KnowledgeBaseHit(
            content=chunk,
            source=str(path.relative_to(docs_dir)),
            chunk_id=f"{path.stem}-{index}",
            score=round(score, 4),
            metadata={"source_path": str(path)},
        )
        for score, path, index, chunk in scored[:top_k]
    ]

    if not hits:
        return KnowledgeBaseSearchResult(
            query=query,
            status="empty",
            message="本地知识库文档没有检索到相关资料。",
            hits=[],
            backend="local",
        )

    return KnowledgeBaseSearchResult(
        query=query,
        status="success",
        message=f"从本地文档关键词检索到 {len(hits)} 条相关资料。",
        hits=hits,
        backend="local",
    )


def read_knowledge_document(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return text
    return text


def split_text_into_chunks(text: str, *, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    settings = get_settings()
    size = max(200, chunk_size or settings.knowledge_base_chunk_size)
    overlap_size = max(0, min(overlap if overlap is not None else settings.knowledge_base_chunk_overlap, size // 2))
    normalized = re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if not normalized:
        return []

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap_size, start + 1)

    return chunks


def iter_knowledge_documents() -> list[Path]:
    docs_dir = Path(get_settings().knowledge_base_docs_dir).expanduser().resolve()
    if not docs_dir.exists():
        return []
    return [
        path
        for path in sorted(docs_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_SUFFIXES
    ]


@lru_cache(maxsize=1)
def _embedding_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("未安装 sentence-transformers，无法执行向量检索。") from exc

    return SentenceTransformer(get_settings().knowledge_base_embedding_model)


def _embed_query(query: str) -> list[float]:
    model = _embedding_model()
    vector = model.encode([query], normalize_embeddings=True)[0]
    return [float(value) for value in vector]


def _keyword_score(query: str, content: str, source: str) -> float:
    query_terms = _tokenize(query)
    if not query_terms:
        return 0

    normalized_content = _normalize(content)
    normalized_source = _normalize(source)
    score = 0.0
    for term in query_terms:
        if term in normalized_source:
            score += 4
        count = normalized_content.count(term)
        if count:
            score += min(count, 8)

    compact_query = _normalize(query)
    if compact_query and compact_query in normalized_content:
        score += 10
    if compact_query and compact_query in normalized_source:
        score += 8

    return score / math.sqrt(max(len(content), 1))


def _tokenize(text: str) -> list[str]:
    normalized = _normalize(text)
    terms = re.split(r"[\s,，。.!！?？、:：;；《》“”\"'（）()\[\]【】_-]+", text.lower())
    terms = [term.strip() for term in terms if len(term.strip()) >= 2]
    if normalized and len(normalized) >= 2:
        terms.extend(normalized[index : index + 2] for index in range(len(normalized) - 1))
    return sorted(set(terms), key=len, reverse=True)


def _normalize(text: str) -> str:
    return re.sub(r"[\s,，。.!！?？、:：;；《》“”\"'（）()\[\]【】_-]+", "", text.lower())


def _distance_to_score(distance: Any) -> float | None:
    try:
        number = float(distance)
    except (TypeError, ValueError):
        return None
    return round(1 / (1 + max(number, 0)), 4)
