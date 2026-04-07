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
import omni.kit.undo
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.packaging.window.tree.item import PackagingErrorItem
from lightspeed.trex.packaging.window.tree.model import PackagingErrorModel
from lightspeed.trex.texture_replacements.core.shared import TextureReplacementsCore
from pxr import Sdf


class TestPackagingErrorModelUnit(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        self.maxDiff = None

    async def test_apply_new_paths_remove_reference_missing_texture_single_layer_should_call_replace_textures_with_none(
        self,
    ):
        # Arrange
        layer_identifier = "/path/to/layer_a.usda"
        prim_path = "/RootNode/Looks/mat_X/Shader.inputs:diffuse_texture"
        asset_path = "/missing/texture.dds"

        item = PackagingErrorItem(layer_identifier, prim_path, asset_path)
        item.fixed_asset_path = None  # triggers REMOVE_REFERENCE action

        layer_mock = Mock()

        with (
            patch.object(AssetReplacementsCore, "__init__", return_value=None),
            patch.object(TextureReplacementsCore, "__init__", return_value=None),
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
            patch.object(omni.kit.undo, "group"),
            patch("pxr.Usd.EditContext"),
        ):
            model = PackagingErrorModel(context_name="")
            model._texture_core = Mock()
            model._asset_core = Mock()
            get_context_mock.return_value.get_stage.return_value = Mock()
            find_open_mock.return_value = layer_mock

            # Act
            result = model.apply_new_paths(items=[item])

        # Assert
        self.assertEqual(1, model._texture_core.replace_textures.call_count)
        self.assertEqual(
            call([(str(Sdf.Path(prim_path)), None)], force=True, use_undo_group=False, target_layer=layer_mock),
            model._texture_core.replace_textures.call_args,
        )
        self.assertEqual([], result)
        self.assertEqual(1, find_open_mock.call_count)
        self.assertEqual(call(layer_identifier), find_open_mock.call_args)

    async def test_apply_new_paths_remove_reference_missing_texture_multiple_layers_should_call_replace_textures_for_each_layer(
        self,
    ):
        # Arrange
        layer_identifier_a = "/path/to/layer_a.usda"
        layer_identifier_b = "/path/to/layer_b.usda"
        prim_path_a = "/RootNode/Looks/mat_ABC/Shader.inputs:diffuse_texture"
        prim_path_b = "/RootNode/Looks/mat_DEF/Shader.inputs:diffuse_texture"
        asset_path = "/missing/texture.dds"  # same missing texture on both layers

        item_a = PackagingErrorItem(layer_identifier_a, prim_path_a, asset_path)
        item_a.fixed_asset_path = None  # triggers REMOVE_REFERENCE action

        item_b = PackagingErrorItem(layer_identifier_b, prim_path_b, asset_path)
        item_b.fixed_asset_path = None  # triggers REMOVE_REFERENCE action

        layer_mock_a = Mock()
        layer_mock_b = Mock()

        with (
            patch.object(AssetReplacementsCore, "__init__", return_value=None),
            patch.object(TextureReplacementsCore, "__init__", return_value=None),
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
            patch.object(omni.kit.undo, "group"),
            patch("pxr.Usd.EditContext"),
        ):
            model = PackagingErrorModel(context_name="")
            model._texture_core = Mock()
            model._asset_core = Mock()
            get_context_mock.return_value.get_stage.return_value = Mock()
            find_open_mock.side_effect = [layer_mock_a, layer_mock_b]

            # Act
            result = model.apply_new_paths(items=[item_a, item_b])

        # Assert
        self.assertEqual(2, model._texture_core.replace_textures.call_count)
        self.assertEqual(
            call([(str(Sdf.Path(prim_path_a)), None)], force=True, use_undo_group=False, target_layer=layer_mock_a),
            model._texture_core.replace_textures.call_args_list[0],
        )
        self.assertEqual(
            call([(str(Sdf.Path(prim_path_b)), None)], force=True, use_undo_group=False, target_layer=layer_mock_b),
            model._texture_core.replace_textures.call_args_list[1],
        )
        self.assertEqual([], result)

    async def test_apply_new_paths_remove_reference_missing_texture_split_layers_should_use_correct_edit_context(
        self,
    ):
        # Arrange: same shader prim but different layers — one has the material definition,
        # the other has the texture input assignment (split-layer replacement scenario)
        layer_identifier_a = "/path/to/capture_layer.usda"
        layer_identifier_b = "/path/to/mod_layer.usda"
        prim_path = "/RootNode/Looks/mat_ABC/Shader.inputs:diffuse_texture"
        asset_path = "/missing/texture.dds"

        item_a = PackagingErrorItem(layer_identifier_a, prim_path, asset_path)
        item_a.fixed_asset_path = None  # triggers REMOVE_REFERENCE action

        item_b = PackagingErrorItem(layer_identifier_b, prim_path, asset_path)
        item_b.fixed_asset_path = None  # triggers REMOVE_REFERENCE action

        stage_mock = Mock()
        layer_mock_a = Mock()
        layer_mock_b = Mock()

        with (
            patch.object(AssetReplacementsCore, "__init__", return_value=None),
            patch.object(TextureReplacementsCore, "__init__", return_value=None),
            patch.object(omni.usd, "get_context") as get_context_mock,
            patch.object(Sdf.Layer, "FindOrOpen") as find_open_mock,
            patch.object(omni.kit.undo, "group"),
            patch("pxr.Usd.EditContext") as edit_context_mock,
        ):
            model = PackagingErrorModel(context_name="")
            model._texture_core = Mock()
            model._asset_core = Mock()
            get_context_mock.return_value.get_stage.return_value = stage_mock
            find_open_mock.side_effect = [layer_mock_a, layer_mock_b]

            # Act
            result = model.apply_new_paths(items=[item_a, item_b])

        # Assert — each item's edit context must target its own layer
        self.assertEqual(2, edit_context_mock.call_count)
        self.assertEqual(call(stage_mock, layer_mock_a), edit_context_mock.call_args_list[0])
        self.assertEqual(call(stage_mock, layer_mock_b), edit_context_mock.call_args_list[1])
        self.assertEqual(2, model._texture_core.replace_textures.call_count)
        self.assertEqual([], result)
