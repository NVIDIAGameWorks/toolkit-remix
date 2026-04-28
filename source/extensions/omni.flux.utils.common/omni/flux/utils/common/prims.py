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

from collections.abc import Iterable

from pxr import Sdf, Usd


def get_proto_from_prim(prim: Usd.Prim) -> Usd.Prim:
    """Resolve a prim to its composition source (prototype) via PrimIndex.

    For prims composed via references (e.g. instances referencing a prototype),
    returns the source prim by following the first composition arc. Falls back
    to the input prim if no composition children exist.

    Args:
        prim: The USD prim to resolve.

    Returns:
        The prototype prim if one exists, otherwise the input prim.
    """
    prim_index = prim.GetPrimIndex()
    root_node = prim_index.rootNode
    if root_node and root_node.children:
        proto_path = root_node.children[0].path
        stage = prim.GetStage()
        proto_prim = stage.GetPrimAtPath(proto_path)
        if proto_prim and proto_prim.IsValid():
            return proto_prim
    return prim


def unique_prim_sequence(
    prim_seq: Iterable[Usd.Prim],
    prototypes_only: bool = False,
) -> list[Usd.Prim]:
    """Return unique prims in last-occurrence order after optional prototype normalization.

    Invalid prims are skipped. When ``prototypes_only`` is true, each valid
    prim is first resolved through ``get_proto_from_prim()`` before dedupe.

    Args:
        prim_seq: Prims to deduplicate in incoming selection order.
        prototypes_only: Whether to resolve each prim to its prototype before
            deduping.

    Returns:
        Unique valid prims in last-occurrence order.
    """
    prims_by_path: dict[str, Usd.Prim] = {}
    for prim in prim_seq:
        if not prim or not prim.IsValid():
            continue

        normalized_prim = get_proto_from_prim(prim) if prototypes_only else prim
        if not normalized_prim or not normalized_prim.IsValid():
            continue

        path_key = str(normalized_prim.GetPath())
        if path_key in prims_by_path:
            prims_by_path.pop(path_key)
        prims_by_path[path_key] = normalized_prim

    return list(prims_by_path.values())


def get_omni_prims() -> set[Sdf.Path]:
    """Return the set of reserved prim paths created by Omniverse Kit.

    These are built-in prims (cameras, light rigs, render settings) that
    should typically be excluded from user-facing prim lists, selectors,
    and validation passes.

    Returns:
        A set of ``Sdf.Path`` for Kit's default prims.
    """
    return {
        Sdf.Path("/OmniverseKit_Persp"),
        Sdf.Path("/OmniverseKit_Front"),
        Sdf.Path("/OmniverseKit_Top"),
        Sdf.Path("/OmniverseKit_Right"),
        Sdf.Path("/OmniKit_Viewport_LightRig"),
        Sdf.Path("/Render"),
    }
