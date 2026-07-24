from __future__ import annotations

from pathlib import Path, PureWindowsPath


def resolve_resource_path(root_dir: str, stored_path: str) -> Path:
    """Resolve a DB path that may be legacy-absolute or root-relative."""
    raw_path = (stored_path or "").strip()
    if not raw_path:
        raise ValueError("Resource path is empty.")

    normalized = raw_path.replace("\\", "/")
    path = Path(normalized).expanduser()

    # Keep old local databases working when they still store Windows/Linux
    # absolute paths. Relative paths are preferred for Docker/production.
    if path.is_absolute() or PureWindowsPath(normalized).is_absolute():
        return path.resolve()

    root = Path(root_dir).expanduser().resolve()
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Resource path escapes the configured root directory.")
    return candidate

