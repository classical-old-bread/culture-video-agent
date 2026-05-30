from __future__ import annotations

import hashlib
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.services.rag_service import iter_knowledge_documents, read_knowledge_document, split_text_into_chunks  # noqa: E402


def _chunk_id(source: str, index: int, content: str) -> str:
    digest = hashlib.sha1(f"{source}:{index}:{content}".encode("utf-8")).hexdigest()[:16]
    return f"{Path(source).stem}-{index}-{digest}"


def main() -> int:
    settings = get_settings()
    docs_dir = Path(settings.knowledge_base_docs_dir).expanduser().resolve()
    chroma_dir = Path(settings.knowledge_base_chroma_dir).expanduser().resolve()

    documents = iter_knowledge_documents()
    if not documents:
        print(f"No knowledge documents found in: {docs_dir}")
        print("Add .txt, .md, .markdown, or .json files, then run this script again.")
        return 1

    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(f"Missing dependency: {exc}")
        print("Install optional RAG dependencies first:")
        print("  pip install chromadb sentence-transformers")
        return 1

    print(f"Loading embedding model: {settings.knowledge_base_embedding_model}")
    model = SentenceTransformer(settings.knowledge_base_embedding_model)

    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict] = []

    for path in documents:
        source = str(path.relative_to(docs_dir))
        chunks = split_text_into_chunks(read_knowledge_document(path))
        for index, chunk in enumerate(chunks):
            ids.append(_chunk_id(source, index, chunk))
            texts.append(chunk)
            metadatas.append(
                {
                    "source": source,
                    "chunk_index": index,
                    "source_path": str(path),
                }
            )

    if not texts:
        print(f"Documents were found, but no readable text chunks were generated from: {docs_dir}")
        return 1

    print(f"Embedding {len(texts)} chunks from {len(documents)} documents...")
    embeddings = model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=True)
    embedding_lists = [[float(value) for value in vector] for vector in embeddings]

    chroma_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        client.delete_collection(settings.knowledge_base_collection)
    except Exception:
        pass

    collection = client.create_collection(
        name=settings.knowledge_base_collection,
        metadata={"description": "Local culture knowledge base"},
    )
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embedding_lists,
    )

    print(f"Knowledge base built successfully: {chroma_dir}")
    print(f"Collection: {settings.knowledge_base_collection}")
    print(f"Chunks: {len(texts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
