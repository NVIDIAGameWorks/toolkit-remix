"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from pathlib import Path
from unittest.mock import Mock, PropertyMock, patch

import omni.usd
from omni.flux.asset_importer.widget.extension import get_file_listener_instance as _get_file_listener_instance
from omni.flux.asset_importer.widget.listener import FileListener as _FileListener
from omni.flux.asset_importer.widget.texture_import_list import TextureImportItem, TextureImportListModel, TextureTypes
from omni.flux.utils.common.omni_url import OmniUrl


class TestTextureImportListModel(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.maxDiff = None

    async def test_set_preferred_normal_type_should_set_pref_normal_conv(self):
        # Arrange
        model = TextureImportListModel()
        model._pref_normal_conv = TextureTypes.OTHER

        # Act
        model.set_preferred_normal_type(TextureTypes.METALLIC)

        # Assert
        self.assertEqual(model._pref_normal_conv, TextureTypes.METALLIC)

    async def test_refresh_should_set_children_subscribe_to_items_and_call_item_changed(self):
        # Arrange
        model = TextureImportListModel()

        items = [
            (Path("Test/0.png"), TextureTypes.DIFFUSE),
            (Path("Test/1.png"), TextureTypes.OTHER),
            (Path("Test/2.png"), TextureTypes.OTHER),
        ]

        # Act
        with patch.object(TextureImportListModel, "_item_changed") as mock:
            model.refresh(items)

        # Assert
        self.assertEqual(len(items), len(model._children))

        for i in range(len(model._children)):
            self.assertEqual(items[i][0], list(model._children.keys())[i]._path)
            self.assertEqual(items[i][1], list(model._children.keys())[i]._texture_type)

        self.assertEqual(1, mock.call_count)

    async def test_listener_tracks_refresh_remove_and_add_changes(self):
        # Arrange
        await _get_file_listener_instance().deferred_destroy()
        model = TextureImportListModel()
        items = [
            (OmniUrl("Test/0.png"), TextureTypes.DIFFUSE),
            (OmniUrl("Test/1.png"), TextureTypes.OTHER),
            (OmniUrl("Test/2.png"), TextureTypes.OTHER),
        ]

        with (
            patch.object(model, "_on_changed") as changed_mock,
            patch("omni.flux.asset_importer.widget.common.items.ImportItem.is_valid") as mock_exist,
            patch(
                "omni.flux.asset_importer.widget.listener.FileListener.WAIT_TIME", new_callable=PropertyMock
            ) as mock_wait_time,
        ):
            mock_wait_time.return_value = 0.1
            mock_exist.side_effect = [
                (True, ""),
                (True, ""),
                (True, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (False, ""),
                (True, ""),
                (True, ""),
                (True, ""),
            ]

            # Act
            call_counts = await self._run_listener_change_scenario(model, items, changed_mock)

        # Assert
        self.assertEqual(call_counts, (0, 3, 6, 8, 11))

    async def test_refresh_texture_types_should_set_all_children_texture_types(self):
        for is_none in [True, False]:
            with self.subTest(name=f"texture_type_is_none_{is_none}"):
                # Arrange
                initial_types = {
                    "C:/test_01/T_Test_Diffuse.png": TextureTypes.OTHER,
                    "C:/test_01/T_Test_Emissive.png": TextureTypes.OTHER,
                    "C:/test_02/NormalOTH.jpg": TextureTypes.OTHER,
                    "C:/test_02/Metallic.jpg": TextureTypes.OTHER,
                    "C:/test_03/Test.gif": TextureTypes.METALLIC,
                }
                expected_types = {
                    "C:/test_01/T_Test_Diffuse.png": TextureTypes.DIFFUSE,
                    "C:/test_01/T_Test_Emissive.png": TextureTypes.EMISSIVE,
                    "C:/test_02/NormalOTH.jpg": TextureTypes.NORMAL_OTH,
                    "C:/test_02/Metallic.jpg": TextureTypes.METALLIC,
                    "C:/test_03/Test.gif": TextureTypes.OTHER,
                }

                model = TextureImportListModel()
                model._children = [
                    TextureImportItem(OmniUrl(texture_path), texture_type=texture_type)
                    for texture_path, texture_type in initial_types.items()
                ]

                texture_types = None if is_none else expected_types

                with patch.object(TextureImportListModel, "_determine_ideal_types") as type_mock:
                    type_mock.return_value = expected_types

                    # Act
                    model.refresh_texture_types(texture_types=texture_types)

                # Assert
                self.assertEqual(1 if is_none else 0, type_mock.call_count)
                self.assertDictEqual(
                    {c.path.path: c.texture_type for c in model._children},
                    expected_types,
                )

    async def test_child_texture_type_change_notifies_model_subscribers(self):
        """A child type edit reaches consumers through the model-level event."""
        # Arrange
        model = TextureImportListModel()
        model.refresh([(Path("Test/albedo.png"), TextureTypes.DIFFUSE)])
        callback = Mock()
        subscription = model.subscribe_texture_type_changed(callback)
        item = model.get_item_children(None)[0]

        # Act
        item.texture_type = TextureTypes.METALLIC

        # Assert
        self.assertIsNotNone(subscription)
        callback.assert_called_once_with()

    async def test_add_item_should_determine_texture_type_append_subscribe_and_call_item_changed(self):
        # Arrange
        model = TextureImportListModel()

        default_items = {
            TextureImportItem(OmniUrl("./test/metal_01.png"), texture_type=TextureTypes.OTHER): (),
            TextureImportItem(OmniUrl("./test/default_02.jpg"), texture_type=TextureTypes.EMISSIVE): (),
        }
        model._children = default_items.copy()

        diffuse_item = "test/test_diffuse_lss.png"
        albedo_item = "test/test_metal_albedo_upscaled.png"
        emissive_item = "test/test_color_fiber_emissive.png"
        metallic_item = "test/test_metal_01.png"
        normal_ogl_item = "test/test_ogl.png"
        normal_dx_item = "test/test_normal_dx.png"
        normal_oth_item = "test/test_lss_norm_oth.png"
        normal_default_item = "test/test_lss_nrm_02.png"
        roughness_item = "test/test_rough_upscaled_4x.png"
        other_item = "test/lamp_02.png"
        duplicate_item_01 = "test/T_Metal_Pattern_01.png"
        duplicate_item_02 = "test/T_Metal_Pattern_02.png"

        new_items = [
            diffuse_item,
            albedo_item,
            emissive_item,
            metallic_item,
            normal_ogl_item,
            normal_dx_item,
            normal_oth_item,
            normal_default_item,
            roughness_item,
            other_item,
            duplicate_item_01,
            duplicate_item_02,
        ]

        # Act
        with patch.object(TextureImportListModel, "_item_changed") as mock:
            model.add_items(new_items)

        # Assert
        self.assertEqual(len(default_items) + len(new_items), len(model._children))
        self.assertListEqual(
            [
                (TextureTypes.METALLIC, list(default_items.keys())[0].path.path),
                (TextureTypes.OTHER, list(default_items.keys())[1].path.path),
                (TextureTypes.DIFFUSE, diffuse_item),
                (TextureTypes.DIFFUSE, albedo_item),
                (TextureTypes.EMISSIVE, emissive_item),
                (TextureTypes.METALLIC, metallic_item),
                (TextureTypes.NORMAL_OGL, normal_ogl_item),
                (TextureTypes.NORMAL_DX, normal_dx_item),
                (TextureTypes.NORMAL_OTH, normal_oth_item),
                (TextureTypes.NORMAL_OGL, normal_default_item),
                (TextureTypes.ROUGHNESS, roughness_item),
                (TextureTypes.OTHER, other_item),
                (TextureTypes.OTHER, duplicate_item_01),
                (TextureTypes.OTHER, duplicate_item_02),
            ],
            [(c.texture_type, c.path.path) for c in model._children],
        )

        self.assertEqual(1, mock.call_count)

    async def test_remove_item_should_remove_and_call_item_changed(self):
        # Arrange
        model = TextureImportListModel()

        removed_item = Mock()
        items = {Mock(): (), Mock(): (), removed_item: ()}
        model._children = items.copy()

        # Act
        with patch.object(TextureImportListModel, "_item_changed") as mock:
            model.remove_items([removed_item])

        # Assert
        self.assertEqual(len(items) - 1, len(model._children))

        with self.assertRaises(ValueError):
            list(model._children.keys()).index(removed_item)

        self.assertEqual(1, mock.call_count)

    async def test_get_item_children_no_parent_should_return_children(self):
        # Arrange
        model = TextureImportListModel()
        items = {TextureImportItem(Path("Test")): (), Mock(): (), Mock(): ()}
        model._children = items

        # Act
        children = model.get_item_children(None)

        # Assert
        self.assertEqual(list(items), children)

    async def test_get_item_children_with_parent_should_return_empty_array(self):
        # Arrange
        model = TextureImportListModel()
        items = {TextureImportItem(Path("Test")): (), Mock(): (), Mock(): ()}
        model._children = items

        # Act
        children = model.get_item_children(next(iter(items)))

        # Assert
        self.assertEqual([], children)

    async def test_get_item_value_model_should_return_item_value_model(self):
        # Arrange
        model = TextureImportListModel()
        item = TextureImportItem(Path("Test"))

        # Act
        val = model.get_item_value_model(item)

        # Assert
        self.assertEqual(item.value_model.get_value_as_string(), val.get_value_as_string())

    async def test_get_item_value_model_count_should_return_1(self):
        # Arrange
        model = TextureImportListModel()

        # Act
        val = model.get_item_value_model_count(Mock())

        # Assert
        self.assertEqual(1, val)

    @staticmethod
    async def _run_listener_change_scenario(model, source_items, changed_mock) -> tuple[int, ...]:
        """Exercise listener changes across refresh, removal, and re-addition."""
        model.refresh(source_items)
        call_counts = []
        for _ in range(3):
            await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
            call_counts.append(changed_mock.call_count)

        current_items = model.get_item_children(None)
        removed_item = current_items[1]
        model.remove_items([removed_item])
        await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
        call_counts.append(changed_mock.call_count)

        model.add_items([str(removed_item.path)])
        await asyncio.sleep(_FileListener.WAIT_TIME + 0.01)
        call_counts.append(changed_mock.call_count)

        model.remove_items(model.get_item_children(None))
        return tuple(call_counts)
