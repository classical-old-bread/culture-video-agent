# Local Knowledge Base

Place local `.txt`, `.md`, `.markdown`, or `.json` documents in `docs/`.

Build the Chroma vector index from the backend directory:

```powershell
pip install -r requirements-rag.txt
python scripts\build_knowledge_base.py
```

The runtime tool still falls back to DeepSeek if the knowledge base is empty, missing, or has no relevant hits.
