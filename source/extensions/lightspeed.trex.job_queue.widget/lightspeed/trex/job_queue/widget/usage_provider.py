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

import asyncio
import os
import pathlib

import carb
from omni.flux.job_queue.core.models import FileReference, UsageSnapshot
from omni.flux.utils.common.path_utils import get_local_path
from omni.usd import get_context_from_stage
from pxr import Tf, UsdUtils

__all__ = ("get_usage_snapshot",)

_USD_SUFFIXES = frozenset((".usd", ".usda", ".usdc", ".usdz"))


def _raise(error: OSError) -> None:
    """Propagate a filesystem scan error to the project scan."""
    raise error


def _project_usd_files(folder: pathlib.Path) -> list[str]:
    """Return every USD file below a project folder. Linked folders such as `deps` belong to other projects."""
    files = []
    for parent, folders, names in os.walk(folder, onerror=_raise):
        folders[:] = [name for name in folders if not pathlib.Path(parent, name).is_junction()]
        files += [os.path.join(parent, name) for name in names if pathlib.Path(name).suffix.lower() in _USD_SUFFIXES]
    return files


async def get_usage_snapshot() -> UsageSnapshot:
    """Collect stage roots on the UI loop, scan project files on a worker, then capture live dependencies.

    Live dependency scans run on the UI loop and return without another await.
    """
    used, references, roots = set(), set(), set()

    def scan(identifier: str, referrer: str | None = None) -> bool:
        """Add the dependencies of one layer and return False if the layer cannot open."""
        layers, assets, unresolved = UsdUtils.ComputeAllDependencies(identifier)
        # A missing file cannot break more, but its folder stays.
        paths = (*(layer.realPath for layer in layers if layer.realPath), *assets, *unresolved)
        if referrer is None:
            used.update(paths)
        else:
            references.update(FileReference(path=path, referrer=referrer) for path in paths)
        return bool(layers)

    for stage in UsdUtils.StageCache.Get().GetAllStages():
        if not get_context_from_stage(stage):
            continue
        if (root := stage.GetRootLayer().realPath) and (local := get_local_path(root)):
            roots.add(local.parent)

    def scan_projects() -> UsageSnapshot:
        """Inspect project files and normalize their references without access to open stages."""
        folders = {pathlib.Path(os.path.normcase(os.path.realpath(root))) for root in roots}
        complete = True
        # Each delete opens every closed USD file in the project.
        for folder in folders:
            try:
                # Keep dependencies from later files even if an earlier file cannot open.
                for path in _project_usd_files(folder):
                    if not scan(path, path):
                        complete = False
            except (OSError, Tf.ErrorException) as error:
                complete = False
                carb.log_warn(f"Cannot inspect USD files for job cleanup in {folder}: {error}")
        # An unread file can reference outputs in any project folder.
        return UsageSnapshot.from_urls(verified_roots=map(str, folders) if complete else (), references=references)

    snapshot = await asyncio.to_thread(scan_projects)
    # Undo history is not scanned. An undo of an Apply after its graph is deleted can reference a removed file.
    for stage in UsdUtils.StageCache.Get().GetAllStages():
        if get_context_from_stage(stage):
            for layer in stage.GetUsedLayers():
                scan(layer.identifier)
    return UsageSnapshot(
        used=UsageSnapshot.from_urls(used).used,
        verified_roots=snapshot.verified_roots,
        references=snapshot.references,
    )
