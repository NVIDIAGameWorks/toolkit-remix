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

from unittest.mock import Mock, call, patch

import omni.kit.test
from lightspeed.trex.stage_manager.plugin.filter.usd import is_capture
from lightspeed.trex.stage_manager.plugin.filter.usd.is_capture import IsCaptureFilterPlugin, ReferenceType

__all__ = ["TestIsCaptureFilterUnit"]


def _make_item(prim=None):
    item = Mock()
    item.data = prim or Mock()
    return item


class TestIsCaptureFilterUnit(omni.kit.test.AsyncTestCase):
    async def test_set_context_name_with_non_default_context_rebinds_deleted_snapshot_layer_manager(self):
        """Snapshot Deleted layers from the layer manager bound to the active context."""
        # Arrange
        replacement_layer = Mock()
        default_manager = Mock()
        rebound_manager = Mock()
        rebound_manager.get_replacement_layers.return_value = {replacement_layer}
        item = _make_item()
        with (
            patch.object(
                is_capture,
                "LayerManagerCore",
                side_effect=[default_manager, rebound_manager],
            ) as layer_manager_class_mock,
            patch.object(
                IsCaptureFilterPlugin,
                "_is_deleted_capture_prim",
                return_value=True,
            ) as deleted_capture_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)

            # Act
            plugin.set_context_name("ingestcraft")
            plugin.set_context_name("ingestcraft")
            predicate = plugin.build_filter_predicate()
            result = predicate(item)

            # Assert
            self.assertTrue(result)
            self.assertEqual(
                [call(""), call("ingestcraft")],
                layer_manager_class_mock.call_args_list,
            )
            default_manager.destroy.assert_called_once_with()
            default_manager.get_replacement_layers.assert_not_called()
            rebound_manager.get_replacement_layers.assert_called_once_with()
            deleted_capture_mock.assert_called_once_with(item.data, {}, {replacement_layer})

    async def test_build_filter_predicate_all_avoids_usd_and_replacement_layer_work(self):
        """Match all items without capture, prim utility, or replacement-layer work."""
        # Arrange
        item = _make_item()
        with (
            patch.object(is_capture, "LayerManagerCore") as layer_manager_class_mock,
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
            ) as capture_mock,
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.ALL)
            predicate = plugin.build_filter_predicate()

            # Act
            result = predicate(item)

        # Assert
        self.assertTrue(result)
        capture_mock.assert_not_called()
        self.assertEqual([], prim_utils_mock.mock_calls)
        layer_manager_class_mock.return_value.get_replacement_layers.assert_not_called()

    async def test_build_filter_predicate_captured_and_replaced_reuse_local_cache_without_layer_work(self):
        """Reuse one local cache for Captured and Replaced without requesting layers."""
        cases = [
            (ReferenceType.CAPTURED, True),
            (ReferenceType.REPLACED, False),
        ]

        for reference_type, capture_result in cases:
            with self.subTest(title=reference_type.value):
                # Arrange
                item = _make_item()
                with (
                    patch.object(is_capture, "LayerManagerCore") as layer_manager_class_mock,
                    patch.object(
                        is_capture._AssetReplacementCore,
                        "prim_is_from_a_capture_reference",
                        return_value=capture_result,
                    ) as capture_mock,
                ):
                    plugin = IsCaptureFilterPlugin(reference_type=reference_type)
                    predicate = plugin.build_filter_predicate()

                    # Act
                    results = [predicate(item), predicate(item)]

                # Assert
                self.assertEqual([True, True], results)
                first_cache = capture_mock.call_args_list[0].args[1]
                second_cache = capture_mock.call_args_list[1].args[1]
                self.assertIs(first_cache, second_cache)
                self.assertEqual({}, first_cache)
                layer_manager_class_mock.return_value.get_replacement_layers.assert_not_called()

    async def test_build_filter_predicate_when_called_twice_creates_independent_caches(self):
        """Create an independent capture-layer cache for each built predicate."""
        # Arrange
        item = _make_item()
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ) as capture_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)
            first_predicate = plugin.build_filter_predicate()
            second_predicate = plugin.build_filter_predicate()

            # Act
            results = [first_predicate(item), second_predicate(item)]

        # Assert
        self.assertEqual(results, [True, True])
        self.assertIsNot(capture_mock.call_args_list[0].args[1], capture_mock.call_args_list[1].args[1])

    async def test_build_filter_predicate_deleted_snapshots_layers_once(self):
        """Snapshot replacement layers once while reusing the Deleted capture cache."""
        # Arrange
        captured_layer = Mock()
        item = _make_item()
        with (
            patch.object(is_capture, "LayerManagerCore") as layer_manager_class_mock,
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ) as capture_mock,
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
        ):
            layer_manager = layer_manager_class_mock.return_value
            layer_manager.get_replacement_layers.return_value = {captured_layer}
            prim_utils_mock.is_ghost_prim.return_value = False
            prim_utils_mock.find_prim_with_references.return_value = (item.data, [])
            prim_utils_mock.has_replacement_ref_edits.return_value = True
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            predicate = plugin.build_filter_predicate()
            layer_manager.get_replacement_layers.return_value = [Mock()]

            # Act
            results = [predicate(item), predicate(item)]

        # Assert
        self.assertEqual(results, [True, True])
        layer_manager.get_replacement_layers.assert_called_once_with()
        expected_layers = {captured_layer}
        self.assertEqual(
            prim_utils_mock.has_replacement_ref_edits.call_args_list,
            [call(item.data, expected_layers), call(item.data, expected_layers)],
        )
        first_cache = capture_mock.call_args_list[0].args[1]
        second_cache = capture_mock.call_args_list[1].args[1]
        self.assertIs(first_cache, second_cache)

    # ------------------------------------------------------------------
    # filter_predicate — ALL
    # ------------------------------------------------------------------

    async def test_filter_predicate_all_returns_true(self):
        """Return true for every item when the filter type is All."""
        # Arrange
        item = _make_item()

        # Act
        with patch.object(is_capture, "LayerManagerCore"):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.ALL)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # filter_predicate — CAPTURED
    # ------------------------------------------------------------------

    async def test_filter_predicate_captured_with_cache_returns_true_for_capture_prim(self):
        """Return true for a capture prim while using the provided cache."""
        # Arrange
        item = _make_item()
        capture_layer_cache = {}

        # Act
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ) as capture_mock,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)
            result = plugin.filter_predicate(item, capture_layer_cache=capture_layer_cache)

        # Assert
        self.assertTrue(result)
        capture_mock.assert_called_once_with(item.data, capture_layer_cache)

    async def test_filter_predicate_captured_returns_false_for_non_capture_prim(self):
        """Return false for a non-capture prim when the filter type is Captured."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=False,
            ),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.CAPTURED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # filter_predicate — REPLACED
    # ------------------------------------------------------------------

    async def test_filter_predicate_replaced_returns_false_for_capture_prim(self):
        """Return false for a capture prim when the filter type is Replaced."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.REPLACED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)

    async def test_filter_predicate_replaced_returns_true_for_non_capture_prim(self):
        """Return true for a non-capture prim when the filter type is Replaced."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=False,
            ),
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
            patch.object(is_capture, "LayerManagerCore") as layer_manager_class_mock,
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=False,
            ),
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
        layer_manager_class_mock.return_value.get_replacement_layers.assert_not_called()

    async def test_filter_predicate_deleted_returns_true_for_ghost_prim(self):
        """A ghost prim should match DELETED."""
        # Arrange
        item = _make_item()

        # Act
        with (
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ),
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
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
            patch.object(is_capture, "LayerManagerCore"),
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ),
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
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
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ),
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
            patch.object(is_capture, "LayerManagerCore") as layer_mgr_cls,
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
            patch.object(
                is_capture._AssetReplacementCore,
                "prim_is_from_a_capture_reference",
                return_value=True,
            ),
            patch.object(is_capture, "prim_utils") as prim_utils_mock,
            patch.object(is_capture, "LayerManagerCore") as layer_mgr_cls,
        ):
            plugin = IsCaptureFilterPlugin(reference_type=ReferenceType.DELETED)
            prim_utils_mock.is_ghost_prim.return_value = False
            prim_utils_mock.find_prim_with_references.return_value = (prim, [])
            prim_utils_mock.has_replacement_ref_edits.return_value = False
            layer_mgr_cls.return_value.get_replacement_layers.return_value = {Mock()}
            result = plugin.filter_predicate(item)

        # Assert
        self.assertFalse(result)
