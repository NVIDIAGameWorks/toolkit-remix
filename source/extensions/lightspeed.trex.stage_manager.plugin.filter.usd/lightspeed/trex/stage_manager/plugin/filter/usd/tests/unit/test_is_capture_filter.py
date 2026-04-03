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

from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.stage_manager.plugin.filter.usd.is_capture import IsCaptureFilterPlugin, ReferenceType

__all__ = ["TestIsCaptureFilterUnit"]

_CAPTURE_PATCH = (
    "lightspeed.trex.stage_manager.plugin.filter.usd.is_capture._AssetReplacementCore.prim_is_from_a_capture_reference"
)
_PRIM_UTILS_PATCH = "lightspeed.trex.stage_manager.plugin.filter.usd.is_capture.prim_utils"
_LAYER_MGR_PATCH = "lightspeed.trex.stage_manager.plugin.filter.usd.is_capture.LayerManagerCore"


def _make_item(prim=None):
    item = Mock()
    item.data = prim or Mock()
    return item


class TestIsCaptureFilterUnit(omni.kit.test.AsyncTestCase):
    # ------------------------------------------------------------------
    # filter_predicate — ALL
    # ------------------------------------------------------------------

    async def test_filter_predicate_all_returns_true(self):
        # Arrange
        item = _make_item()

        # Act
        with patch(_LAYER_MGR_PATCH):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.ALL)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # filter_predicate — CAPTURED
    # ------------------------------------------------------------------

    async def test_filter_predicate_captured_returns_true_for_capture_prim(self):
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=True),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_captured_returns_false_for_non_capture_prim(self):
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=False),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # filter_predicate — REPLACED
    # ------------------------------------------------------------------

    async def test_filter_predicate_replaced_returns_false_for_capture_prim(self):
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=True),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.REPLACED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_filter_predicate_replaced_returns_true_for_non_capture_prim(self):
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=False),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.REPLACED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # filter_predicate — DELETED
    # ------------------------------------------------------------------

    async def test_filter_predicate_deleted_returns_false_for_non_capture_prim(self):
        """A non-capture prim can never be 'deleted' in the capture sense."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=False),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_filter_predicate_deleted_returns_true_for_ghost_prim(self):
        """A ghost prim should match DELETED."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=True),
            patch(_PRIM_UTILS_PATCH) as prim_utils_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            prim_utils_mock.is_ghost_prim.return_value = True
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_deleted_returns_false_when_capture_refs_remain(self):
        """If the prim still has capture references, it is not deleted."""
        # Arrange
        prim = Mock()
        item = _make_item(prim)
        ref_items = [(prim, Mock(), Mock(), 0)]

        # Act
        with (
            patch(_LAYER_MGR_PATCH),
            patch(_CAPTURE_PATCH, return_value=True),
            patch(_PRIM_UTILS_PATCH) as prim_utils_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            prim_utils_mock.is_ghost_prim.return_value = False
            prim_utils_mock.find_prim_with_references.return_value = (prim, ref_items)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_filter_predicate_deleted_returns_true_when_replacement_ref_edits_exist(self):
        """A capture prim with no remaining refs but replacement ref edits is deleted."""
        # Arrange
        prim = Mock()
        item = _make_item(prim)

        # Act
        with (
            patch(_CAPTURE_PATCH, return_value=True),
            patch(_PRIM_UTILS_PATCH) as prim_utils_mock,
            patch(_LAYER_MGR_PATCH) as layer_mgr_cls,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            prim_utils_mock.is_ghost_prim.return_value = False
            prim_utils_mock.find_prim_with_references.return_value = (prim, [])
            prim_utils_mock.has_replacement_ref_edits.return_value = True
            layer_mgr_cls.return_value.get_replacement_layers.return_value = {Mock()}
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    async def test_filter_predicate_deleted_returns_false_when_no_ref_edits(self):
        """A capture prim with no refs and no replacement layer edits is not 'deleted'."""
        # Arrange
        prim = Mock()
        item = _make_item(prim)

        # Act
        with (
            patch(_CAPTURE_PATCH, return_value=True),
            patch(_PRIM_UTILS_PATCH) as prim_utils_mock,
            patch(_LAYER_MGR_PATCH) as layer_mgr_cls,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            prim_utils_mock.is_ghost_prim.return_value = False
            prim_utils_mock.find_prim_with_references.return_value = (prim, [])
            prim_utils_mock.has_replacement_ref_edits.return_value = False
            layer_mgr_cls.return_value.get_replacement_layers.return_value = {Mock()}
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
