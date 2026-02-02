# noqa PLC0302

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

import stat
import tempfile
import weakref
from functools import partial
from pathlib import Path
from typing import List, Optional
from unittest.mock import Mock, call, patch

import omni.kit
import omni.kit.test
import omni.usd
from omni.flux.layer_tree.usd.core import LayerCustomData as _LayerCustomData
from omni.flux.layer_tree.usd.widget import LayerItem, LayerModel
from omni.kit import commands
from omni.kit.usd.layers import LayerUtils
from omni.kit.window.popup_dialog import MessageDialog
from pxr import Sdf


class TestModel(omni.kit.test.AsyncTestCase):
    EXPECTED_FILE_EXTENSIONS = [
        ("*.usda", "Human-readable USD File"),
        ("*.usd", "Binary or Ascii USD File"),
        ("*.usdc", "Binary USD File"),
    ]

    # Before running each test
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.context = omni.usd.get_context()
        self.stage = self.context.get_stage()
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
        self.temp_dir.cleanup()
        self.context = None
        self.stage = None
        self.temp_dir = None

    async def test_refresh_no_sublayers(self):
        # Arrange
        model = LayerModel()

        # Act
        await model._deferred_refresh()  # noqa PLW0212

        # Assert
        self.assertEqual(1, model.get_items_count())
        self.assertEqual(1, len(model.get_item_children()))
        self.assertEqual(0, len(model.get_item_children(model.get_item_children()[0])))

    async def test_refresh_with_multi_level_sublayers(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"
        layer2_path = Path(self.temp_dir.name) / "layer2.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))
        layer2 = Sdf.Layer.CreateNew(str(layer2_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)
        layer1.subLayerPaths.append(layer2.identifier)

        model = LayerModel()

        # Act
        await model._deferred_refresh()  # noqa PLW0212
        items = model.get_item_children(recursive=False)

        # Assert
        # Immediate children of the model
        self.assertEqual(1, len(items))

        # Root layer
        root_item = items[0]
        self.assertTrue(root_item.can_have_children)
        self.assertTrue(root_item.enabled)
        self.assertEqual(None, root_item.parent)
        self.assertEqual(2, len(root_item.children))

        # Sublayers of the root layer
        layer0_item = model.get_item_children(parent=root_item, recursive=False)[0]
        layer1_item = model.get_item_children(parent=root_item, recursive=False)[1]
        self.assertEqual(layer0, root_item.children[0].data["layer"])
        self.assertEqual(layer1, root_item.children[1].data["layer"])
        self.assertEqual(layer0, layer0_item.data["layer"])
        self.assertEqual(layer1, layer1_item.data["layer"])

        # layer0
        self.assertTrue(layer0_item.can_have_children)
        self.assertTrue(layer0_item.enabled)
        self.assertEqual(root_item, layer0_item.parent)
        self.assertEqual(0, len(layer0_item.children))

        # layer1
        self.assertTrue(layer1_item.can_have_children)
        self.assertTrue(layer1_item.enabled)
        self.assertEqual(root_item, layer1_item.parent)
        self.assertEqual(1, len(layer1_item.children))

        # Sublayers of layer1
        layer2_item = model.get_item_children(parent=layer1_item, recursive=False)[0]
        self.assertEqual(layer2, layer1_item.children[0].data["layer"])
        self.assertEqual(layer2, layer2_item.data["layer"])

        # layer2
        self.assertTrue(layer2_item.can_have_children)
        self.assertTrue(layer2_item.enabled)
        self.assertEqual(layer1_item, layer2_item.parent)
        self.assertEqual(0, len(layer2_item.children))

    async def test_refresh_sublayers_item_data_excludes(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"
        layer2_path = Path(self.temp_dir.name) / "layer2.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))
        layer2 = Sdf.Layer.CreateNew(str(layer2_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)
        root.subLayerPaths.append(layer2.identifier)

        # Layer0 should be excluded via the exclude functions
        model = LayerModel(
            exclude_remove_fn=lambda *_: [layer0.identifier],
            exclude_lock_fn=lambda *_: [layer0.identifier],
            exclude_mute_fn=lambda *_: [layer0.identifier],
            exclude_edit_target_fn=lambda *_: [layer0.identifier],
            exclude_add_child_fn=lambda *_: [layer0.identifier],
            exclude_move_fn=lambda *_: [layer0.identifier],
        )

        # Layer1 should be excluded via the custom layer data
        custom_data = layer1.customLayerData
        custom_data.update(
            {
                _LayerCustomData.ROOT.value: {
                    _LayerCustomData.EXCLUDE_ADD_CHILD.value: True,
                    _LayerCustomData.EXCLUDE_EDIT_TARGET.value: True,
                    _LayerCustomData.EXCLUDE_LOCK.value: True,
                    _LayerCustomData.EXCLUDE_MOVE.value: True,
                    _LayerCustomData.EXCLUDE_MUTE.value: True,
                    _LayerCustomData.EXCLUDE_REMOVE.value: True,
                },
            }
        )
        layer1.customLayerData = custom_data

        # Act
        await model._deferred_refresh()  # noqa PLW0212
        root_item = model.get_item_children(recursive=False)[0]
        items = model.get_item_children(parent=root_item, recursive=True)

        # Assert
        # layer0
        self.assertTrue(items[0].data["exclude_remove"])
        self.assertTrue(items[0].data["exclude_lock"])
        self.assertTrue(items[0].data["exclude_mute"])
        self.assertTrue(items[0].data["exclude_edit_target"])
        self.assertTrue(items[0].data["exclude_add_child"])
        self.assertTrue(items[0].data["exclude_move"])

        # layer1
        self.assertTrue(items[1].data["exclude_remove"])
        self.assertTrue(items[1].data["exclude_lock"])
        self.assertTrue(items[1].data["exclude_mute"])
        self.assertTrue(items[1].data["exclude_edit_target"])
        self.assertTrue(items[1].data["exclude_add_child"])
        self.assertTrue(items[1].data["exclude_move"])

        # layer1
        self.assertFalse(items[2].data["exclude_remove"])
        self.assertFalse(items[2].data["exclude_lock"])
        self.assertFalse(items[2].data["exclude_mute"])
        self.assertFalse(items[2].data["exclude_edit_target"])
        self.assertFalse(items[2].data["exclude_add_child"])
        self.assertFalse(items[2].data["exclude_move"])

    async def test_refresh_sublayers_item_data_states(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        try:
            layer0 = Sdf.Layer.CreateNew(str(layer0_path))
            layer1 = Sdf.Layer.CreateNew(str(layer1_path))

            layer0.Save()
            layer0_path.chmod(stat.S_IREAD)

            root = self.stage.GetRootLayer()
            root.subLayerPaths.append(layer0.identifier)
            root.subLayerPaths.append(layer1.identifier)

            LayerUtils.set_edit_target(self.stage, layer1.identifier)
            LayerUtils.set_layer_lock_status(root, layer0.identifier, True)
            LayerUtils.set_layer_global_muteness(root, layer0.identifier, True)
            LayerUtils.set_layer_lock_status(root, layer1.identifier, False)
            LayerUtils.set_layer_global_muteness(root, layer1.identifier, False)

            self.stage.DefinePrim("/test", "Scope")

            model = LayerModel()

            # Act
            await model._deferred_refresh()  # noqa PLW0212
            root_item = model.get_item_children(recursive=False)[0]
            items = model.get_item_children(parent=root_item, recursive=True)

            # Assert
            # layer0
            self.assertTrue(items[0].data["locked"])
            self.assertTrue(items[0].data["can_toggle_mute"])
            self.assertFalse(items[0].data["savable"])
            self.assertFalse(items[0].data["visible"])
            self.assertFalse(items[0].data["authoring"])
            self.assertFalse(items[0].data["dirty"])
            self.assertEqual(layer0, items[0].data["layer"])

            # layer1
            self.assertFalse(items[1].data["locked"])
            self.assertFalse(items[1].data["can_toggle_mute"])
            self.assertTrue(items[1].data["savable"])
            self.assertTrue(items[1].data["visible"])
            self.assertTrue(items[1].data["authoring"])
            self.assertTrue(items[1].data["dirty"])
            self.assertEqual(layer1, items[1].data["layer"])

        finally:
            layer0_path.chmod(stat.S_IWRITE)

    async def test_delete_layer_no_parent_quick_return(self):
        # Arrange
        root_item = LayerItem("root")

        model = LayerModel()
        model.set_items([root_item])

        with patch.object(MessageDialog, "show") as mock:
            # Act
            model.delete_layer(root_item)

            # Assert
            self.assertFalse(mock.called)

    async def test_set_authoring_layer(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer0_item = LayerItem("layer0", data={"layer": layer0, "locked": False, "exclude_edit_target": False})

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            model.set_authoring_layer(layer0_item)

            # Assert
            self.assertEqual(1, mock.call_count)
            self.assertEqual(
                call("SetEditTargetCommand", layer_identifier=layer0.identifier, usd_context=""), mock.call_args
            )

    async def test_save_layer(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0", data={"layer": layer0, "savable": True}, parent=root_item)
        root_item.set_children([layer0_item], sort=False)

        model = LayerModel()
        model.set_items([root_item])

        with patch.object(Sdf.Layer, "Save") as save_mock, patch.object(LayerModel, "refresh") as refresh_mock:
            # Act
            model.save_layer(layer0_item)

            # Assert
            self.assertEqual(1, save_mock.call_count)
            self.assertEqual(1, refresh_mock.call_count)

    async def test_save_layer_as_invalid_layer_quick_return(self):
        # Arrange
        layer0_item = LayerItem("layer0", data={"layer": None})

        model = LayerModel()
        model.set_items([layer0_item])

        with patch("weakref.ref") as mock:
            # Act
            model.save_layer_as(layer0_item)

            # Assert
            self.assertFalse(mock.called)

    async def test_save_layer_as_open_file_picker(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        layer0_ref = weakref.ref(layer0)
        root_ref = weakref.ref(root)

        root_item = LayerItem("root", data={"layer": root})
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)

        layer_creation_validation_mock = Mock()
        layer_creation_validation_failed_mock = Mock()

        model = LayerModel(
            layer_creation_validation_fn=layer_creation_validation_mock,  # noqa
            layer_creation_validation_failed_callback=layer_creation_validation_failed_mock,  # noqa
        )
        model.set_items([root_item])

        with (
            patch("weakref.ref") as ref_mock,
            patch("omni.flux.layer_tree.usd.widget.layer_tree.model._open_file_picker") as file_picker_mock,
            patch("omni.flux.layer_tree.usd.widget.layer_tree.model._save_layer_as") as save_as_mock,
            patch.object(LayerModel, "_on_save_layer_as_internal") as save_done_mock,
        ):
            ref_mock.side_effect = [layer0_ref, root_ref]

            # Act
            model.save_layer_as(layer0_item)

            # Assert
            self.assertEqual(2, ref_mock.call_count)  # Layer & Parent refs
            self.assertEqual(1, file_picker_mock.call_count)

            args, kwargs = file_picker_mock.call_args
            self.assertEqual("Save layer as", args[0])
            # Compare strings since the "partial" instances won't be the same, but we expect all args to be equal,
            # including the function passed. (Strings include position in memory, etc.)
            self.assertEqual(str(partial(save_as_mock, "", True, layer0_ref, root_ref, save_done_mock)), str(args[1]))
            self.assertEqual(
                {
                    "apply_button_label": "Save As",
                    "current_file": layer0.realPath,
                    "file_extension_options": self.EXPECTED_FILE_EXTENSIONS,
                    "validate_selection": layer_creation_validation_mock,
                    "validation_failed_callback": layer_creation_validation_failed_mock,
                },
                kwargs,
            )

    async def test_export_layer_open_file_picker(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)
        root_item.set_children([root_item], sort=False)

        layer_creation_validation_mock = Mock()
        layer_creation_validation_failed_mock = Mock()

        model = LayerModel(
            layer_creation_validation_fn=layer_creation_validation_mock,  # noqa
            layer_creation_validation_failed_callback=layer_creation_validation_failed_mock,  # noqa
        )
        model.set_items([root_item])

        with (
            patch("omni.flux.layer_tree.usd.widget.layer_tree.model._open_file_picker") as file_picker_mock,
            patch.object(LayerModel, "_on_export_layer_internal") as export_mock,
        ):
            # Act
            model.export_layer(layer0_item)

            # Assert
            self.assertEqual(1, file_picker_mock.call_count)

            args, kwargs = file_picker_mock.call_args
            self.assertEqual("Export the layer file", args[0])
            # Compare strings since the "partial" instances won't be the same, but we expect all args to be equal,
            # including the function passed. (Strings include position in memory, etc.)
            self.assertEqual(str(partial(export_mock, layer0_item)), str(args[1]))
            self.assertEqual(
                {
                    "apply_button_label": "Export",
                    "current_file": layer0.realPath,
                    "file_extension_options": self.EXPECTED_FILE_EXTENSIONS,
                    "validate_selection": layer_creation_validation_mock,
                    "validation_failed_callback": layer_creation_validation_failed_mock,
                },
                kwargs,
            )

    async def test_toggle_lock_layer_lock(self):
        await self.__run_test_toggle_lock_layer(False)

    async def test_toggle_lock_layer_unlock(self):
        await self.__run_test_toggle_lock_layer(True)

    async def test_toggle_mute_layer_mute(self):
        await self.__run_test_toggle_mute_layer(False)

    async def test_toggle_mute_layer_unmute(self):
        await self.__run_test_toggle_mute_layer(True)

    async def test_move_sublayer_change_parent(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)

        root_item = LayerItem("root", data={"layer": root})
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)
        layer1_item = LayerItem("layer1", data={"layer": layer1}, parent=root_item)
        root_item.set_children([layer0_item, layer1_item], sort=False)

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            model.move_sublayer(layer1_item, layer0_item)

            # Assert
            args, kwargs = mock.call_args
            self.assertEqual(1, mock.call_count)
            self.assertEqual(("MoveSublayerCommand",), args)
            self.assertEqual(
                {
                    "from_parent_layer_identifier": root.identifier,
                    "from_sublayer_position": 1,
                    "to_parent_layer_identifier": layer0.identifier,
                    "to_sublayer_position": -1,
                    "remove_source": True,
                    "usd_context": "",
                },
                kwargs,
            )

    async def test_move_sublayer_change_position(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)

        root_item = LayerItem("root", data={"layer": root})
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)
        layer1_item = LayerItem("layer1", data={"layer": layer1}, parent=root_item)
        root_item.set_children([layer0_item, layer1_item], sort=False)

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            model.move_sublayer(layer0_item, root_item, 1)

            # Assert
            args, kwargs = mock.call_args
            self.assertEqual(1, mock.call_count)
            self.assertEqual(("MoveSublayerCommand",), args)
            self.assertEqual(
                {
                    "from_parent_layer_identifier": root.identifier,
                    "from_sublayer_position": 0,
                    "to_parent_layer_identifier": root.identifier,
                    "to_sublayer_position": 1,
                    "remove_source": True,
                    "usd_context": "",
                },
                kwargs,
            )

    async def test_move_sublayer_no_parent_early_return(self):
        # Arrange
        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0")

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            model.move_sublayer(root_item, layer0_item)

            # Assert
            self.assertFalse(mock.called)

    async def test_move_sublayer_no_new_parent_early_return(self):
        # Arrange
        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0", parent=root_item)
        root_item.set_children([layer0_item], sort=False)

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            model.move_sublayer(layer0_item, None)  # noqa

            # Assert
            self.assertFalse(mock.called)

    async def test_merge_layers_should_call_command_in_order(self):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"
        layer2_path = Path(self.temp_dir.name) / "layer2.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))
        layer2 = Sdf.Layer.CreateNew(str(layer2_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        root.subLayerPaths.append(layer1.identifier)
        layer0.subLayerPaths.append(layer2.identifier)

        root_item = LayerItem("root", data={"layer": root})
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)
        layer1_item = LayerItem("layer1", data={"layer": layer1}, parent=root_item)
        layer2_item = LayerItem("layer2", data={"layer": layer2}, parent=layer0_item)
        layer0_item.set_children([layer2_item], sort=False)
        root_item.set_children([layer0_item, layer1_item], sort=False)

        model = LayerModel()

        with patch.object(commands, "execute") as mock:
            # Act
            # Pseudo-random layer order to test ordering
            model.merge_layers([layer2_item, layer0_item, layer1_item])

            # Assert
            self.assertEqual(2, mock.call_count)

            # Expected order: Layer1 -> Layer2 then Layer2 -> Layer0
            args0, kwargs0 = mock.call_args_list[0]
            self.assertEqual(("MergeLayersCommand",), args0)
            self.assertEqual(
                {
                    "dst_parent_layer_identifier": layer0.identifier,
                    "dst_layer_identifier": layer2.identifier,
                    "src_parent_layer_identifier": root.identifier,
                    "src_layer_identifier": layer1.identifier,
                    "dst_stronger_than_src": True,
                    "usd_context": "",
                },
                kwargs0,
            )

            args1, kwargs1 = mock.call_args_list[1]
            self.assertEqual(("MergeLayersCommand",), args1)
            self.assertEqual(
                {
                    "dst_parent_layer_identifier": root.identifier,
                    "dst_layer_identifier": layer0.identifier,
                    "src_parent_layer_identifier": layer0.identifier,
                    "src_layer_identifier": layer2.identifier,
                    "dst_stronger_than_src": True,
                    "usd_context": "",
                },
                kwargs1,
            )

    async def test_transfer_layer_overrides_existing_file_should_call_create_layer(self):
        await self.__run_test_transfer_layer_overrides(True)

    async def test_transfer_layer_overrides_new_file_should_call_create_layer(self):
        await self.__run_test_transfer_layer_overrides(False)

    async def test_is_layer_locked_locked(self):
        await self.__run_test_is_layer_locked(True)

    async def test_is_layer_locked_unlocked(self):
        await self.__run_test_is_layer_locked(False)

    async def test_append_item_with_parent_sort_force(self):
        # Arrange
        root_item = LayerItem("c_root")

        model = LayerModel()
        model.set_items([root_item])

        # Act - force=True allows items with duplicate titles (separate instances)
        layer0_item = LayerItem("a_layer0")
        layer1_item = LayerItem("b_layer1")
        layer1_item_dup = LayerItem("b_layer1")  # Same title, different instance

        model.append_item(layer1_item, parent=root_item, sort=True, force=True)
        model.append_item(layer1_item_dup, parent=root_item, sort=True, force=True)
        model.append_item(layer0_item, parent=root_item, sort=True, force=True)

        # Assert
        self.assertEqual(3, len(root_item.children))
        self.assertEqual(layer0_item, root_item.children[0])
        self.assertEqual(layer1_item, root_item.children[1])
        self.assertEqual(layer1_item_dup, root_item.children[2])

    async def test_append_item_with_parent_no_sort_no_force(self):
        # Arrange
        root_item = LayerItem("c_root")

        model = LayerModel()
        model.set_items([root_item])

        # Act
        layer0_item = LayerItem("a_layer0")
        layer1_item = LayerItem("b_layer1")
        model.append_item(layer1_item, parent=root_item, sort=False, force=False)
        model.append_item(layer1_item, parent=root_item, sort=False, force=False)
        model.append_item(layer0_item, parent=root_item, sort=False, force=False)

        # Assert
        self.assertEqual(2, len(root_item.children))
        self.assertEqual(layer1_item, root_item.children[0])
        self.assertEqual(layer0_item, root_item.children[1])

    async def test_append_item_no_parent_sort_force(self):
        # Arrange
        root_item = LayerItem("c_root")

        model = LayerModel()
        model.set_items([root_item])

        # Act
        layer0_item = LayerItem("a_layer0")
        layer1_item = LayerItem("b_layer1")
        model.append_item(layer1_item, sort=True, force=True)
        model.append_item(layer1_item, sort=True, force=True)
        model.append_item(layer0_item, sort=True, force=True)

        # Assert
        self.assertEqual(4, len(model.get_item_children()))
        self.assertEqual(layer0_item, model.get_item_children()[0])
        self.assertEqual(layer1_item, model.get_item_children()[1])
        self.assertEqual(layer1_item, model.get_item_children()[2])
        self.assertEqual(root_item, model.get_item_children()[3])

    async def test_append_item_no_parent_no_sort_no_force(self):
        # Arrange
        root_item = LayerItem("c_root")

        model = LayerModel()
        model.set_items([root_item])

        # Act
        layer0_item = LayerItem("a_layer0")
        layer1_item = LayerItem("b_layer1")
        model.append_item(layer1_item, sort=False, force=False)
        model.append_item(layer1_item, sort=False, force=False)
        model.append_item(layer0_item, sort=False, force=False)

        # Assert
        self.assertEqual(3, len(model.get_item_children()))
        self.assertEqual(root_item, model.get_item_children()[0])
        self.assertEqual(layer1_item, model.get_item_children()[1])
        self.assertEqual(layer0_item, model.get_item_children()[2])

    async def test_find_item_with_parent_return_item(self):
        await self.__run_test_find_item("layer2", "layer2_item", "layer0_item")

    async def test_find_item_with_parent_return_none(self):
        await self.__run_test_find_item("root", None, "layer0_item")

    async def test_find_item_no_parent_return_item(self):
        await self.__run_test_find_item("layer2", "layer2_item", None)

    async def test_find_item_no_parent_return_none(self):
        await self.__run_test_find_item("non_existent", None, None)

    async def test_get_item_children_with_parent_no_recursive(self):
        await self.__run_test_get_item_children(False, ["layer1_item"], "layer0_item")

    async def test_get_item_children_with_parent_recursive(self):
        await self.__run_test_get_item_children(True, ["layer1_item", "layer2_item"], "layer0_item")

    async def test_get_item_children_no_parent_no_recursive(self):
        await self.__run_test_get_item_children(False, ["root_item"], None)

    async def test_get_item_children_no_parent_recursive(self):
        await self.__run_test_get_item_children(True, ["root_item", "layer0_item", "layer1_item", "layer2_item"], None)

    async def test_drop_accepted_valid(self):
        await self.__run_test_drop_accepted(True, "layer0_item", "layer2_item", -1)

    async def test_drop_accepted_source_same_as_target_invalid(self):
        await self.__run_test_drop_accepted(False, "layer0_item", "layer0_item", -1)

    async def test_drop_accepted_target_is_none_invalid(self):
        await self.__run_test_drop_accepted(False, None, "layer0_item", -1)  # noqa

    async def test_drop_accepted_reorder_parent_not_valid_invalid(self):
        # Parent is invalid because of exclude_child policy
        await self.__run_test_drop_accepted(False, "layer7_item", "layer6_item", 1)

    async def test_drop_accepted_source_exclude_move_invalid(self):
        await self.__run_test_drop_accepted(False, "layer0_item", "layer4_item", -1)

    async def test_drop_accepted_target_is_locked_invalid(self):
        await self.__run_test_drop_accepted(False, "layer3_item", "layer0_item", -1)

    async def test_drop_accepted_target_exclude_add_child_invalid(self):
        await self.__run_test_drop_accepted(False, "layer5_item", "layer0_item", -1)

    async def test_drop_accepted_target_is_source_child_invalid(self):
        await self.__run_test_drop_accepted(False, "layer2_item", "layer0_item", -1)

    async def __run_test_toggle_lock_layer(self, is_locked: bool):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer0_item = LayerItem("layer0", data={"layer": layer0, "locked": is_locked, "exclude_lock": False})

        model = LayerModel()

        with patch.object(commands, "execute") as mock, patch.object(LayerModel, "is_layer_locked") as is_locked_mock:
            is_locked_mock.return_value = is_locked

            # Act
            model.toggle_lock_layer(layer0_item)

            # Assert
            args, kwargs = mock.call_args
            self.assertEqual(1, mock.call_count)
            self.assertEqual(("LockLayer",), args)
            self.assertEqual(
                {"layer_identifier": layer0.identifier, "locked": not is_locked, "usd_context": ""}, kwargs
            )

    async def __run_test_toggle_mute_layer(self, is_muted: bool):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        layer0_item = LayerItem(
            "layer0", data={"layer": layer0, "visible": not is_muted, "exclude_mute": False, "can_toggle_mute": True}
        )

        model = LayerModel()

        with (
            patch.object(commands, "execute") as execute_mock,
            patch.object(LayerModel, "is_layer_muted") as is_muted_mock,
        ):
            is_muted_mock.return_value = is_muted

            # Act
            model.toggle_mute_layer(layer0_item)

            # Assert
            self.assertEqual(1, execute_mock.call_count)
            self.assertEqual(
                call("SetLayerMutenessCommand", layer_identifier=layer0.identifier, muted=not is_muted, usd_context=""),
                execute_mock.call_args,
            )

    async def __run_test_transfer_layer_overrides(self, existing_file: bool):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        root_item = LayerItem("root", data={"layer": root})
        layer0_item = LayerItem("layer0", data={"layer": layer0}, parent=root_item)
        root_item.set_children([layer0_item], sort=False)

        model = LayerModel()

        with (
            patch.object(LayerModel, "create_layer") as create_mock,
            patch.object(LayerModel, "_on_transfer_layer_overrides_internal") as transfer_mock,
        ):
            # Act
            model.transfer_layer_overrides(layer0_item, existing_file)

            # Assert
            self.assertEqual(1, create_mock.call_count)

            args, kwargs = create_mock.call_args
            self.assertEqual((not existing_file,), args)
            self.assertEqual(layer0_item, kwargs.get("parent", "Invalid"))
            # Compare strings since the "partial" instances won't be the same, but we expect all args to be equal,
            # including the function passed. (Strings include position in memory, etc.)
            self.assertEqual(
                str(partial(transfer_mock, layer0_item)), str(kwargs.get("layer_created_callback", "Invalid"))
            )

    async def __run_test_is_layer_locked(self, is_locked: bool):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)

        root_item = LayerItem("root", data={"layer": root, "locked": False})
        layer0_item = LayerItem("layer0", data={"layer": layer0, "locked": is_locked}, parent=root_item)
        root_item.set_children([layer0_item], sort=False)

        model = LayerModel()
        model.set_items([root_item])

        # Act
        LayerUtils.set_layer_lock_status(root, layer0.identifier, is_locked)

        # Assert
        self.assertEqual(is_locked, model.is_layer_locked(layer0_item))

    async def __run_test_find_item(self, value: str, expected_result: Optional[str], parent: Optional[str]):
        # Arrange
        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0", parent=root_item)
        layer1_item = LayerItem("layer1", parent=layer0_item)
        layer2_item = LayerItem("layer2", parent=layer0_item)

        layer0_item.set_children([layer1_item, layer2_item], sort=False)
        root_item.set_children([layer0_item], sort=False)

        items = {
            "root_item": root_item,
            "layer0_item": layer0_item,
            "layer1_item": layer1_item,
            "layer2_item": layer2_item,
        }

        model = LayerModel()
        model.set_items([root_item])

        # Act
        result = model.find_item(value, lambda i, v: i.title == v, parent=items.get(parent))

        # Assert
        self.assertEqual(items.get(expected_result), result)

    async def __run_test_get_item_children(self, recursive: bool, expected_results: List[str], parent: Optional[str]):
        # Arrange
        root_item = LayerItem("root")
        layer0_item = LayerItem("layer0", parent=root_item)
        layer1_item = LayerItem("layer1", parent=layer0_item)
        layer2_item = LayerItem("layer2", parent=layer1_item)

        layer1_item.set_children([layer2_item], sort=False)
        layer0_item.set_children([layer1_item], sort=False)
        root_item.set_children([layer0_item], sort=False)

        items = {
            "root_item": root_item,
            "layer0_item": layer0_item,
            "layer1_item": layer1_item,
            "layer2_item": layer2_item,
        }

        model = LayerModel()
        model.set_items([root_item])

        # Act
        result = model.get_item_children(parent=items.get(parent), recursive=recursive)

        # Assert
        self.assertEqual(len(expected_results), len(result))
        for index, item in enumerate(expected_results):
            self.assertEqual(items.get(item), result[index])

    async def __run_test_drop_accepted(self, expected_result: bool, target: str, source: str, location: int):
        # Arrange
        layer0_path = Path(self.temp_dir.name) / "layer0.usda"
        layer1_path = Path(self.temp_dir.name) / "layer1.usda"
        layer2_path = Path(self.temp_dir.name) / "layer2.usda"
        layer3_path = Path(self.temp_dir.name) / "layer3.usda"
        layer4_path = Path(self.temp_dir.name) / "layer4.usda"
        layer5_path = Path(self.temp_dir.name) / "layer5.usda"
        layer6_path = Path(self.temp_dir.name) / "layer6.usda"
        layer7_path = Path(self.temp_dir.name) / "layer7.usda"

        layer0 = Sdf.Layer.CreateNew(str(layer0_path))
        layer1 = Sdf.Layer.CreateNew(str(layer1_path))
        layer2 = Sdf.Layer.CreateNew(str(layer2_path))
        layer3 = Sdf.Layer.CreateNew(str(layer3_path))
        layer4 = Sdf.Layer.CreateNew(str(layer4_path))
        layer5 = Sdf.Layer.CreateNew(str(layer5_path))
        layer6 = Sdf.Layer.CreateNew(str(layer6_path))
        layer7 = Sdf.Layer.CreateNew(str(layer7_path))

        root = self.stage.GetRootLayer()
        root.subLayerPaths.append(layer0.identifier)
        layer0.subLayerPaths.append(layer1.identifier)
        layer1.subLayerPaths.append(layer2.identifier)
        root.subLayerPaths.append(layer3.identifier)
        root.subLayerPaths.append(layer4.identifier)
        root.subLayerPaths.append(layer5.identifier)
        layer5.subLayerPaths.append(layer6.identifier)
        layer5.subLayerPaths.append(layer7.identifier)

        LayerUtils.set_layer_lock_status(root, layer3.identifier, True)

        root_item = LayerItem("root", data={"layer": root, "exclude_move": False, "exclude_add_child": False})
        layer0_item = LayerItem(
            "layer0_valid_level1",
            data={"layer": layer0, "exclude_move": False, "exclude_add_child": False},
            parent=root_item,
        )
        layer1_item = LayerItem(
            "layer1_valid_level2",
            data={"layer": layer1, "exclude_move": False, "exclude_add_child": False},
            parent=layer0_item,
        )
        layer2_item = LayerItem(
            "layer2_valid_level3",
            data={"layer": layer2, "exclude_move": False, "exclude_add_child": False},
            parent=layer1_item,
        )
        layer3_item = LayerItem(
            "layer3_locked",
            data={"layer": layer3, "exclude_move": False, "exclude_add_child": False},
            parent=root_item,
        )
        layer4_item = LayerItem(
            "layer4_exclude_move",
            data={"layer": layer4, "exclude_move": True, "exclude_add_child": False},
            parent=root_item,
        )
        layer5_item = LayerItem(
            "layer5_exclude_add_child",
            data={"layer": layer5, "exclude_move": False, "exclude_add_child": True},
            parent=root_item,
        )
        layer6_item = LayerItem(
            "layer6_invalid_parent",
            data={"layer": layer6, "exclude_move": False, "exclude_add_child": False},
            parent=layer5_item,
        )
        layer7_item = LayerItem(
            "layer7_invalid_parent",
            data={"layer": layer7, "exclude_move": False, "exclude_add_child": False},
            parent=layer5_item,
        )

        layer5_item.set_children([layer6_item, layer7_item], sort=False)
        layer1_item.set_children([layer2_item], sort=False)
        layer0_item.set_children([layer1_item], sort=False)
        root_item.set_children([layer0_item, layer3_item, layer4_item, layer5_item], sort=False)

        items = {
            "root_item": root_item,
            "layer0_item": layer0_item,
            "layer1_item": layer1_item,
            "layer2_item": layer2_item,
            "layer3_item": layer3_item,
            "layer4_item": layer4_item,
            "layer5_item": layer5_item,
            "layer6_item": layer6_item,
            "layer7_item": layer7_item,
        }

        model = LayerModel()
        model.set_items([root_item])

        # Act
        result = model.drop_accepted(items.get(target), items.get(source), drop_location=location)

        # Assert
        self.assertEqual(expected_result, result)
