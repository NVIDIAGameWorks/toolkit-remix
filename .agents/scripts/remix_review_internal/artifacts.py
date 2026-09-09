"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import contextlib
import hashlib
import json
from pathlib import Path


__all__ = ["canonical_hash", "file_hash", "write_bytes", "write_json", "write_json_atomic"]


def canonical_hash(value) -> str:
    """Return a stable SHA-256 hash for a JSON-compatible value."""
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: str | Path) -> str | None:
    """Hash one existing artifact, or return none when the path is not a file on disk."""
    artifact = Path(path)
    return hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.is_file() else None


def write_json(path: str | Path, value) -> None:
    """Write one JSON artifact."""
    write_bytes(path, _json_bytes(value))


def write_json_atomic(path: str | Path, value) -> None:
    """Replace one JSON artifact without exposing a partial write."""
    path = Path(path)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        write_bytes(temporary, _json_bytes(value))
        temporary.replace(path)
    except BaseException:
        # A failed write or replace must not leave the temporary file behind. The cleanup is
        # best effort: it must never replace the original failure with its own.
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def write_bytes(path: str | Path, payload: bytes) -> None:
    """Write one binary artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _json_bytes(value) -> bytes:
    """Encode one stable, human-readable JSON artifact."""
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
