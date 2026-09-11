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

from __future__ import annotations

__all__ = [
    "MetadataApplyReceipt",
    "capture_metadata_receipt",
    "get_current_validation_extensions",
    "revert_metadata",
    "write_input_sidecars",
    "write_metadata_for_paths",
]

import copy
import hashlib
import json
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass

import carb
import carb.tokens
import omni.client
import omni.kit.app
from omni.client import is_local_url
from omni.flux.utils.common.path_utils import hash_file, write_metadata

from .constants import BASE_HASH_KEY, VALIDATION_EXTENSIONS_KEY, VALIDATION_PASSED_KEY


@dataclass(frozen=True, slots=True)
class MetadataApplyReceipt:
    """Durable pre-Apply state for metadata sidecar writes.

    Attributes:
        prior_meta: One ``(meta_path, prior_json)`` pair for each output sidecar, in write order. ``prior_json``
            is the sidecar's full prior text, or ``None`` when no sidecar existed before Apply.
    """

    prior_meta: tuple[tuple[pathlib.Path | str, str | None], ...]


def _read_remote_bytes(url: str) -> bytes | None:
    """Read one remote file, or return ``None`` when it does not exist."""
    result, _, content = omni.client.read_file(url)
    if result == omni.client.Result.ERROR_NOT_FOUND:
        return None
    if result != omni.client.Result.OK:
        raise OSError(f"Cannot read remote file {url}: {result}")
    return memoryview(content).tobytes()


def _read_remote_text(url: str) -> str | None:
    """Read one remote UTF-8 text file when it exists."""
    content = _read_remote_bytes(url)
    return content.decode("utf-8") if content is not None else None


def _write_remote_text(url: str, text: str) -> None:
    """Write one remote UTF-8 text file."""
    result = omni.client.write_file(url, text.encode("utf-8"))
    if result != omni.client.Result.OK:
        raise OSError(f"Cannot write remote file {url}: {result}")


def _delete_remote_file(url: str) -> None:
    """Delete one remote file when it exists."""
    result = omni.client.delete(url)
    if result not in (omni.client.Result.OK, omni.client.Result.ERROR_NOT_FOUND):
        raise OSError(f"Cannot delete remote file {url}: {result}")


def _write_remote_metadata(
    asset_url: str,
    validation_extensions: list[dict],
    validation_passed: bool,
) -> None:
    """Hash one remote output and update its JSON sidecar."""
    content = _read_remote_bytes(asset_url)
    if content is None:
        raise FileNotFoundError(f"Apply output cannot be hashed before metadata write: {asset_url}")
    meta_url = f"{asset_url}.meta"
    prior_json = _read_remote_text(meta_url)
    data = json.loads(prior_json) if prior_json is not None else {}
    if not isinstance(data, dict):
        raise ValueError(f"Remote metadata sidecar must contain a JSON object: {meta_url}")
    data[BASE_HASH_KEY] = hashlib.md5(content).hexdigest()
    data[VALIDATION_PASSED_KEY] = validation_passed
    data[VALIDATION_EXTENSIONS_KEY] = validation_extensions
    _write_remote_text(meta_url, json.dumps(data, indent=4))


def capture_metadata_receipt(paths: Iterable[pathlib.Path | str]) -> MetadataApplyReceipt:
    """Read each prior sidecar before Apply overwrites it.

    Args:
        paths: Local or remote files that will receive sidecars, including consumed inputs.

    Returns:
        A receipt that carries each sidecar path with its prior content, or ``None`` when none existed.

    Raises:
        OSError: If a remote sidecar cannot be read.
    """
    prior_meta = []
    for path in paths:
        path_value = str(path)
        if is_local_url(path_value):
            resolved = pathlib.Path(str(carb.tokens.get_tokens_interface().resolve(path_value)))
            meta_path: pathlib.Path | str = resolved.with_suffix(resolved.suffix + ".meta")
            prior_json = meta_path.read_text() if meta_path.is_file() else None
        else:
            meta_path = f"{path_value}.meta"
            prior_json = _read_remote_text(meta_path)
        prior_meta.append((meta_path, prior_json))
    return MetadataApplyReceipt(prior_meta=tuple(prior_meta))


def get_current_validation_extensions() -> list[dict]:
    """Return the validator extensions that the app currently reports.

    This reproduces the legacy ``FileMetadataWritter`` snapshot. It records every extension
    that the extension manager reports whose identifier contains ``omni.flux.validator``,
    including disabled ones, and it removes the local ``path`` entry so the sidecar stays
    machine independent. The list describes the app that produced the file. It does not
    record which extensions ran.

    Call this function on the Kit thread, not inside a worker thread.

    Returns:
        One dictionary for each reported validator extension.
    """
    extensions = omni.kit.app.get_app().get_extension_manager().get_extensions()
    result = []
    for ext in extensions:
        if "omni.flux.validator" in ext["id"]:
            entry = copy.deepcopy(ext)
            entry.pop("path", None)
            result.append(entry)
    return result


def write_input_sidecars(paths: Iterable[pathlib.Path | str]) -> None:
    """Hash local input files and write only ``base_hash`` sidecars.

    The legacy ``FileMetadataWritter`` wrote ``base_hash`` for every consumed input, without
    ``validation_passed``, ``validation_extensions``, or ``fixes_applied``. It hashed with a helper
    that returns ``None`` for a file it cannot read, and it then wrote nothing for that file.

    A missing input is therefore skipped, not an error. Apply runs after processing finished, so a
    source file may have been moved or removed by then, and that must not fail a completed run. An
    unhashable OUTPUT is still an error, because this pipeline produced it.

    Args:
        paths: Local input files consumed by the pipeline.
    """
    for path in paths:
        # Test existence first. ``hash_file`` logs an error for a file it cannot open, and the Kit
        # test harness fails a run that logs one. A consumed input that is already gone is an
        # expected case here, not a fault, so it must stay silent.
        input_path = pathlib.Path(path)
        if not input_path.is_file():
            continue
        file_path = str(input_path)
        file_hash = hash_file(file_path)
        if file_hash is None:
            continue
        write_metadata(file_path, BASE_HASH_KEY, file_hash)


def write_metadata_for_paths(
    paths: Iterable[pathlib.Path | str],
    validation_extensions: list[dict],
    validation_passed: bool = True,
) -> None:
    """Hash and write deterministic ``.meta`` sidecars for local or remote outputs.

    Args:
        paths: Published files to hash and annotate.
        validation_extensions: Validator snapshot taken on the Kit thread.
        validation_passed: Pipeline outcome; ``True`` when no step recorded an error.

    Raises:
        FileNotFoundError: If an output cannot be hashed.
        OSError: If a remote output or sidecar cannot be read or written.
    """
    for path in paths:
        file_path = str(path)
        if not is_local_url(file_path):
            _write_remote_metadata(file_path, validation_extensions, validation_passed)
            continue
        file_hash = hash_file(file_path)
        if file_hash is None:
            raise FileNotFoundError(f"Apply output cannot be hashed before metadata write: {file_path}")
        write_metadata(file_path, BASE_HASH_KEY, file_hash)
        write_metadata(file_path, VALIDATION_PASSED_KEY, validation_passed)
        write_metadata(file_path, VALIDATION_EXTENSIONS_KEY, validation_extensions)


def revert_metadata(receipt: MetadataApplyReceipt) -> None:
    """Restore every local or remote sidecar to its pre-Apply state.

    Args:
        receipt: Durable pre-Apply state captured by ``capture_metadata_receipt``.
    """
    for meta_path, prior_json in receipt.prior_meta:
        if isinstance(meta_path, pathlib.Path):
            if prior_json is None:
                meta_path.unlink(missing_ok=True)
                carb.log_info(f"[SaveMetadata] Revert deleted sidecar {meta_path}")
            else:
                meta_path.write_text(prior_json)
                carb.log_info(f"[SaveMetadata] Revert restored sidecar {meta_path}")
        elif prior_json is None:
            _delete_remote_file(meta_path)
            carb.log_info(f"[SaveMetadata] Revert deleted sidecar {meta_path}")
        else:
            _write_remote_text(meta_path, prior_json)
            carb.log_info(f"[SaveMetadata] Revert restored sidecar {meta_path}")
