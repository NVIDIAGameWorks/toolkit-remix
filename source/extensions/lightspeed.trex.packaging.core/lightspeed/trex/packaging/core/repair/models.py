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

__all__ = ["PackagingRepairRequest", "PackagingRepairResult", "RepairState"]

from collections.abc import Callable
from dataclasses import dataclass, field

from pxr import Sdf

from .enum import PackagingRepairAction


@dataclass
class PackagingRepairRequest:
    """
    Data for one unresolved asset repair requested by the packaging UI.
    """

    layer_identifier: str
    prim_path: Sdf.Path | str
    asset_path: str
    fixed_asset_path: str | None

    def __post_init__(self):
        self.prim_path = Sdf.Path(str(self.prim_path))

    @property
    def action(self) -> PackagingRepairAction:
        """Get the repair action implied by the fixed asset path.

        Returns:
            The action to apply for this repair request.
        """
        if not self.fixed_asset_path:
            return PackagingRepairAction.REMOVE_REFERENCE
        if self.fixed_asset_path != self.asset_path:
            return PackagingRepairAction.REPLACE_ASSET
        return PackagingRepairAction.IGNORE


@dataclass
class PackagingRepairFailure:
    """
    Failed repair data returned after applying packaging repairs.
    """

    layer_identifier: str
    prim_path: str
    asset_path: str
    message: str


@dataclass
class PackagingRepairResult:
    """
    Result data returned after applying packaging repairs.
    """

    ignored_items: list[tuple[str, str, str]] = field(default_factory=list)
    failed_repairs: list[PackagingRepairFailure] = field(default_factory=list)


@dataclass
class RepairState:
    """
    Mutable state shared by a packaging repair run.
    """

    root_layer_identifier: str | None
    is_cancelled: Callable[[], bool] | None
    use_editable_layer_copies: bool = False
    ignored_items: list[tuple[str, str, str]] = field(default_factory=list)
    failed_repairs: list[PackagingRepairFailure] = field(default_factory=list)
    reference_repair_keys: set[tuple] = field(default_factory=set)
    reference_group_repair_keys: set[tuple] = field(default_factory=set)
    references_by_asset_path: dict[
        tuple[str, str], dict[str, list[tuple[Sdf.Path, Sdf.Reference, list[Sdf.Reference]]]]
    ] = field(default_factory=dict)
    texture_repair_keys: set[tuple] = field(default_factory=set)
    local_references: list[tuple[Sdf.Path, str, Sdf.Layer, Sdf.Reference]] | None = None
    local_references_by_target_layer: dict[str, list[tuple[Sdf.Path, str, Sdf.Layer, Sdf.Reference]]] | None = None
    read_layers: dict[str, Sdf.Layer] = field(default_factory=dict)
    editable_layers: dict[str, tuple[str, Sdf.Layer]] | None = None
    dirty_editable_layer_keys: set[str] = field(default_factory=set)
    local_layers: dict[str, tuple[str, Sdf.Layer]] | None = None

    def __post_init__(self):
        if self.use_editable_layer_copies and self.editable_layers is None:
            self.editable_layers = {}

    def is_cancelled_requested(self) -> bool:
        """Check whether the caller requested cancellation.

        Returns:
            Whether the repair run should stop before the next cancellable step.
        """
        return bool(self.is_cancelled and self.is_cancelled())

    def add_ignored_request(self, request: PackagingRepairRequest):
        """Track a repair request the user chose to ignore.

        Args:
            request: The repair request to add to the ignored result list.
        """
        ignored_item = (request.layer_identifier, str(request.prim_path), request.asset_path)
        if ignored_item not in self.ignored_items:
            self.ignored_items.append(ignored_item)

    def add_failed_request(self, request: PackagingRepairRequest, message: str):
        """Track a repair request whose selected operation failed.

        Args:
            request: The failed repair request.
            message: User-facing failure context.
        """
        failure_key = (request.layer_identifier, str(request.prim_path), request.asset_path)
        if any(
            (failure.layer_identifier, failure.prim_path, failure.asset_path) == failure_key
            for failure in self.failed_repairs
        ):
            return
        self.failed_repairs.append(
            PackagingRepairFailure(request.layer_identifier, str(request.prim_path), request.asset_path, message)
        )
