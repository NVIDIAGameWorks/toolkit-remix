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

import uuid

from omni.flux.utils.widget.tree_widget.item import TreeItemBase

from .row import Row

__all__ = ("QueueGraphItem", "QueueItem")


class QueueGraphItem(TreeItemBase):
    """A graph root in the queue TreeView.

    Attributes:
        graph_id: Durable graph identifier used to preserve item identity during refresh.
        name: User-facing graph name.
        position: Durable graph order.
    """

    def __init__(self, graph_id: uuid.UUID, name: str, position: int) -> None:
        """Initialize a graph root.

        Args:
            graph_id: Durable graph identifier used for refresh and expansion caching.
            name: User-facing graph name.
            position: Durable graph order.
        """
        super().__init__()
        self.graph_id = graph_id
        self.name = name
        self.position = position

    @property
    def can_have_children(self) -> bool:
        """Return True because every queue graph renders its jobs as children.

        Returns:
            Always True.
        """
        return True


class QueueItem(TreeItemBase):
    """A single item in the queue TreeView, wrapping a Row with UI state."""

    def __init__(self, row: Row, parent: QueueGraphItem | None = None):
        """Initialize a job child.

        Args:
            row: Mutable display row for the job.
            parent: Graph root that owns this job.
        """
        super().__init__(parent=parent)
        self._row = row

    @property
    def default_attr(self) -> dict[str, None]:
        """Return attributes released by the tree-item lifecycle.

        Returns:
            Default lifecycle attribute mapping.
        """
        return {
            **super().default_attr,
            "_row": None,
        }

    @property
    def can_have_children(self) -> bool:
        """Return False because job items are hierarchy leaves.

        Returns:
            Always False.
        """
        return False

    @property
    def row(self) -> Row:
        """Return mutable presentation data for this job.

        Returns:
            Mutable child row.
        """
        return self._row
