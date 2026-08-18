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

import uuid
from unittest.mock import MagicMock

import omni.kit.test
from omni.flux.job_queue.widget.queue_item import QueueGraphItem, QueueItem

__all__ = ("TestQueueItem",)


class TestQueueItem(omni.kit.test.AsyncTestCase):
    """Verify queue tree ownership and stable graph identity."""

    async def test_parenting_job_to_graph_exposes_child(self):
        """A graph root owns its job child through the native tree item contract."""
        # Arrange
        graph = QueueGraphItem(uuid.uuid4(), "Graph", 0)
        row = MagicMock()

        # Act
        child = QueueItem(row, parent=graph)

        # Assert
        self.assertEqual(graph.children, [child])
        self.assertTrue(graph.can_have_children)
        self.assertFalse(child.can_have_children)
