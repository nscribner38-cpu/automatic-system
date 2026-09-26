"""Checksum-verified file writes (brief section 3, "File safety").

write_verified():
  1. backs up an existing target to .backups/ (timestamped) before touching it,
  2. for .py targets, refuses to write text that does not ast.parse,
  3. writes to a temp file in the same folder, fsyncs, then atomically replaces the target,
  4. re-reads the target from disk and compares SHA-256; raises if it does not match.

Bytes are written exactly as given, so callers control line endings. Use
detect_newline() to keep an existing file's CRLF/LF style when rewriting it.
"""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dfs_builder.paths import BACKUPS, ROOT


class WriteVerificationError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_newline(data: bytes) -> str:
    """Return '\\r\\n' if the content uses CRLF line endings, else '\\n'."""
    return "\r\n" if b"\r\n" in data else "\n"


def backup(path: Path) -> Path | None:
    """Copy an existing file into .backups/<relative path>.<UTC timestamp>. Returns the backup path."""
    path = Path(path)
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = Path(path.name)
    dest = BACKUPS / rel.parent / f"{rel.name}.{stamp}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    if sha256_file(dest) != sha256_file(path):
        raise WriteVerificationError(f"backup of {path} did not verify")
    return dest


def write_verified(path: Path, data: bytes | str, *, encoding: str = "utf-8") -> str:
    """Write data to path safely and return the verified SHA-256 of what is on disk."""
    path = Path(path)
    payload = data.encode(encoding) if isinstance(data, str) else data
    if path.suffix == ".py":
        ast.parse(payload.decode(encoding), filename=str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    backup(path)
    expected = sha256_bytes(payload)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    actual = sha256_file(path)
    if actual != expected:
        raise WriteVerificationError(f"{path}: wrote {expected} but disk has {actual}")
    return actual
