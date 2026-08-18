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

__all__ = ["get_local_output_path", "publish_remote_outputs"]

import asyncio
import pathlib
import uuid
from urllib.request import url2pathname

import carb
from omni.client import CopyBehavior, Result as ClientResult
from omni.client import (
    break_url,
    combine_urls,
    copy_async,
    create_folder_async,
    delete_async,
    is_local_url,
    move_async,
    stat_async,
)
from omni.flux.job_queue.core.job import JobProgress, JobProgressCallback

from .worker import await_settled, run_in_worker_thread


def get_local_output_path(output_url: str) -> pathlib.Path | None:
    """Convert a local publication URL to a path and reject remote URLs.

    Args:
        output_url: Local path, file URL, or remote URL.

    Returns:
        Local filesystem path, or None for a remote URL.
    """
    if not is_local_url(output_url):
        return None
    output_parts = break_url(output_url)
    return pathlib.Path(url2pathname(output_parts.path) if output_parts.scheme == "file" else output_url)


async def publish_remote_outputs(
    local_output_dir: pathlib.Path,
    primary_outputs: list[pathlib.Path],
    remote_output_url: str,
    asset_count: int,
    progress_callback: JobProgressCallback,
) -> list[str]:
    """Publish every pipeline output and sidecar to one remote directory.

    Args:
        local_output_dir: Local directory containing only final pipeline outputs.
        primary_outputs: Primary output paths in request order.
        remote_output_url: Remote directory receiving the batch.
        asset_count: Stable request-asset count used for structured progress.
        progress_callback: Async callback receiving publication progress.

    Returns:
        Remote primary URLs in request order.

    Raises:
        RuntimeError: If the remote directory or any output cannot be published.
    """
    await progress_callback(JobProgress(completed=asset_count, total=asset_count, detail="Save processed assets"))
    output_files = await run_in_worker_thread(_list_output_files, local_output_dir)
    await _publish_remote_batch(output_files, local_output_dir, remote_output_url)

    output_directory_url = f"{remote_output_url.rstrip('/')}/"
    return [
        combine_urls(output_directory_url, path.relative_to(local_output_dir).as_posix()) for path in primary_outputs
    ]


def _list_output_files(directory: pathlib.Path) -> list[pathlib.Path]:
    """Return the directory's files in deterministic order.

    Args:
        directory: Local pipeline output directory to enumerate from a worker thread.

    Returns:
        Sorted files from the complete directory tree ready for remote publication.
    """
    return sorted(path for path in directory.rglob("*") if path.is_file())


async def _publish_remote_batch(
    source_paths: list[pathlib.Path],
    source_root: pathlib.Path,
    remote_output_url: str,
) -> None:
    """Stage and atomically swap one complete remote output directory.

    Existing output content is cloned into a sibling staging directory before the new batch is overlaid. The final
    directory is replaced only after every source file reaches staging, and the previous directory remains available
    as a rollback backup until the swap succeeds.

    Args:
        source_paths: Local files to publish as one transaction.
        source_root: Local root preserved below the remote directory.
        remote_output_url: Final remote directory receiving the complete batch.

    Raises:
        RuntimeError: If staging, commit, or rollback fails.
    """
    final_url = remote_output_url.rstrip("/")
    transaction_id = uuid.uuid4().hex
    staging_url = f"{final_url}.asset_pipeline_staging_{transaction_id}"
    backup_url = f"{final_url}.asset_pipeline_backup_{transaction_id}"
    final_exists = False
    backup_exists = False
    final_move_operation: asyncio.Future[tuple[ClientResult, bool]] | None = None

    try:
        stat_result, _entry = await await_settled(stat_async(final_url))
        if stat_result == ClientResult.OK:
            final_exists = True
            copy_result = await await_settled(copy_async(final_url, staging_url, CopyBehavior.ERROR_IF_EXISTS))
            _require_remote_success(copy_result, "clone the current asset output directory")
        elif stat_result == ClientResult.ERROR_NOT_FOUND:
            create_result = await await_settled(create_folder_async(staging_url))
            _require_remote_success(create_result, "create the asset publication staging directory")
        else:
            raise RuntimeError(f"Could not inspect the asset output directory ({stat_result})")

        for source_path in source_paths:
            relative_path = source_path.relative_to(source_root)
            await _ensure_remote_directories(staging_url, relative_path.parent)
            destination_url = combine_urls(f"{staging_url}/", relative_path.as_posix())
            copy_result = await await_settled(copy_async(str(source_path), destination_url, CopyBehavior.OVERWRITE))
            _require_remote_success(copy_result, f"stage processed asset {relative_path.as_posix()}")

        if final_exists:
            move_result, _copied = await await_settled(move_async(final_url, backup_url, CopyBehavior.ERROR_IF_EXISTS))
            _require_remote_success(move_result, "retain the current asset output directory")
            backup_exists = True

        final_move_operation = asyncio.ensure_future(move_async(staging_url, final_url, CopyBehavior.ERROR_IF_EXISTS))
        move_result, _copied = await await_settled(final_move_operation)
        if move_result != ClientResult.OK:
            raise RuntimeError(f"Could not commit the processed asset batch ({move_result})")
    except (asyncio.CancelledError, RuntimeError) as publication_error:
        rollback_error = await _rollback_remote_publication(
            final_url,
            staging_url,
            backup_url,
            final_destination_owned=_move_owns_destination(final_move_operation),
        )
        if rollback_error is not None:
            raise RuntimeError(
                f"Asset publication failed and rollback could not restore the previous output: {rollback_error}"
            ) from publication_error
        raise
    else:
        if backup_exists:
            await _delete_remote_path(backup_url, required=False)


async def _ensure_remote_directories(root_url: str, relative_directory: pathlib.Path) -> None:
    """Create each missing remote directory below one existing transaction root.

    Args:
        root_url: Existing remote staging root.
        relative_directory: Relative local directory hierarchy to reproduce remotely.

    Raises:
        RuntimeError: If a destination directory cannot be inspected or created.
    """
    current_url = root_url
    for part in relative_directory.parts:
        current_url = combine_urls(f"{current_url.rstrip('/')}/", part)
        stat_result, _entry = await await_settled(stat_async(current_url))
        if stat_result == ClientResult.OK:
            continue
        if stat_result != ClientResult.ERROR_NOT_FOUND:
            raise RuntimeError(f"Could not inspect asset publication directory {current_url} ({stat_result})")
        create_result = await await_settled(create_folder_async(current_url))
        _require_remote_success(create_result, f"create asset publication directory {current_url}")


async def _rollback_remote_publication(
    final_url: str,
    staging_url: str,
    backup_url: str,
    *,
    final_destination_owned: bool = False,
) -> str | None:
    """Restore the previous directory before removing incomplete publication data.

    Args:
        final_url: Final remote output directory.
        staging_url: Transaction staging directory.
        backup_url: Transaction backup directory.
        final_destination_owned: Whether this transaction created or copied the final destination.

    Returns:
        Combined user-readable rollback errors, or ``None`` when rollback completed.
    """
    rollback_errors: list[str] = []
    backup_result, _entry = await await_settled(stat_async(backup_url))
    if backup_result == ClientResult.OK:
        restore_backup = final_destination_owned
        if final_destination_owned:
            try:
                await _delete_remote_path(final_url, required=True)
            except (asyncio.CancelledError, RuntimeError) as rollback_error:
                rollback_errors.append(str(rollback_error))
        else:
            final_result, _final_entry = await await_settled(stat_async(final_url))
            if final_result == ClientResult.ERROR_NOT_FOUND:
                restore_backup = True
            elif final_result != ClientResult.OK:
                rollback_errors.append(f"Could not inspect the current asset output ({final_result})")

        try:
            if restore_backup:
                move_result, _copied = await await_settled(
                    move_async(backup_url, final_url, CopyBehavior.ERROR_IF_EXISTS)
                )
                _require_remote_success(move_result, "restore the previous asset output directory")
            elif not rollback_errors:
                await _delete_remote_path(backup_url, required=True)
        except (asyncio.CancelledError, RuntimeError) as rollback_error:
            rollback_errors.append(str(rollback_error))
    elif backup_result != ClientResult.ERROR_NOT_FOUND:
        rollback_errors.append(f"Could not inspect the rollback backup ({backup_result})")
    elif final_destination_owned:
        try:
            await _delete_remote_path(final_url, required=True)
        except (asyncio.CancelledError, RuntimeError) as rollback_error:
            rollback_errors.append(str(rollback_error))

    try:
        await _delete_remote_path(staging_url, required=True)
    except (asyncio.CancelledError, RuntimeError) as rollback_error:
        rollback_errors.append(str(rollback_error))

    return "; ".join(filter(None, rollback_errors)) or None


def _move_owns_destination(operation: asyncio.Future[tuple[ClientResult, bool]] | None) -> bool:
    """Return whether a settled move created or copied its destination.

    Args:
        operation: Settled final move operation, or ``None`` before commit begins.

    Returns:
        ``True`` when the transaction owns destination content that rollback may delete.
    """
    if operation is None or not operation.done() or operation.cancelled() or operation.exception() is not None:
        return False
    result, copied = operation.result()
    return result == ClientResult.OK or copied


async def _delete_remote_path(url: str, *, required: bool) -> None:
    """Delete one remote transaction path.

    Args:
        url: Remote file or directory URL.
        required: Whether deletion failure must fail the transaction.

    Raises:
        RuntimeError: If required cleanup fails.
    """
    delete_result = await await_settled(delete_async(url))
    if delete_result in (ClientResult.OK, ClientResult.ERROR_NOT_FOUND):
        return
    if required:
        raise RuntimeError(f"Could not remove incomplete asset output ({delete_result})")
    carb.log_warn(f"Could not remove asset publication backup {url} ({delete_result})")


def _require_remote_success(result: ClientResult, action: str) -> None:
    """Require one successful remote transaction operation.

    Args:
        result: Client operation result.
        action: User-readable operation description.

    Raises:
        RuntimeError: If the operation did not succeed.
    """
    if result != ClientResult.OK:
        raise RuntimeError(f"Could not {action} ({result})")
