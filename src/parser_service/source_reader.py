from __future__ import annotations

import hashlib
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceFile:
    absolute_path: Path
    relative_path: str

    source: str
    content_hash: str

    size_bytes: int
    line_count: int


def normalize_relative_path(path: Path) -> str:
    """Chuyển path về dạng POSIX để ID ổn định trên Windows/Linux."""
    return path.as_posix()


def calculate_content_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def read_source_file(
    repo_root: str | Path,
    relative_path: str,
) -> SourceFile:
    root = Path(repo_root).resolve()
    absolute_path = (root / relative_path).resolve()

    try:
        relative = absolute_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"File nằm ngoài repository: {absolute_path}"
        ) from exc

    if not absolute_path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file: {absolute_path}"
        )

    if not absolute_path.is_file():
        raise ValueError(
            f"Path không phải file: {absolute_path}"
        )

    if absolute_path.suffix.lower() != ".py":
        raise ValueError(
            f"Không phải file Python: {absolute_path}"
        )

    raw_bytes = absolute_path.read_bytes()

    # tokenize.open() tự xử lý encoding declaration của Python.
    with tokenize.open(absolute_path) as source_file:
        source = source_file.read()

    return SourceFile(
        absolute_path=absolute_path,
        relative_path=normalize_relative_path(relative),
        source=source,
        content_hash=calculate_content_hash(raw_bytes),
        size_bytes=len(raw_bytes),
        line_count=len(source.splitlines()),
    )


def get_git_commit_sha(repo_root: str | Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(Path(repo_root).resolve()),
            "rev-parse",
            "HEAD",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()