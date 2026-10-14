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

__all__ = ["TestConvertAlphaCardsActionWidgetPlugin"]

from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.common.constants import GlobalEventNames
from lightspeed.trex.stage_manager.plugin.widget.usd.action_convert_alpha_cards import (
    ConvertAlphaCardsActionWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuItem
from lightspeed.common import constants
from pxr import Sdf, Usd, UsdGeom, UsdLux

_MODULE = "lightspeed.trex.stage_manager.plugin.widget.usd.action_convert_alpha_cards"
_CAPTURE_CHECK = "lightspeed.trex.alpha_cutout.core.usd_reader._AssetReplacementsCore.prim_is_from_a_capture_reference"
_MESH_ROOT = "/RootNode/meshes/mesh_AAAAAAAAAAAAAAAA"
_EMPTY_ROOT = "/RootNode/meshes/mesh_BBBBBBBBBBBBBBBB"
_INSTANCE = "/RootNode/instances/inst_AAAAAAAAAAAAAAAA_0"
_LIGHT = "/RootNode/lights/light_CCCCCCCCCCCCCCCC"


def _build_stage() -> Usd.Stage:
    """Build a capture-shaped stage with a mesh prototype, an empty prototype, an instance and a light."""
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, _MESH_ROOT)
    UsdGeom.Mesh.Define(stage, f"{_MESH_ROOT}/mesh")
    UsdGeom.Xform.Define(stage, _EMPTY_ROOT)
    instance = UsdGeom.Xform.Define(stage, _INSTANCE).GetPrim()
    instance.GetReferences().AddInternalReference(_MESH_ROOT)
    UsdLux.SphereLight.Define(stage, _LIGHT)
    return stage


def _item(prim: Usd.Prim) -> Mock:
    item = Mock()
    item.data = prim
    return item


class TestConvertAlphaCardsActionWidgetPlugin(omni.kit.test.AsyncTestCase):
    """Test the menu visibility and the conversion request."""

    def setUp(self):
        self._stage = _build_stage()
        self._capture_patch = patch(_CAPTURE_CHECK, return_value=True)
        self._capture_patch.start()

    def tearDown(self):
        self._capture_patch.stop()
        self._stage = None

    async def test_get_menu_items_returns_experimental_submenu_after_ai_tools(self):
        # Arrange
        plugin_class = ConvertAlphaCardsActionWidgetPlugin

        # Act
        with patch(f"{_MODULE}.get_icons", return_value="icon.svg"):
            items = plugin_class._get_menu_items()

        # Assert
        self.assertEqual(len(items), 1)
        descriptor, group, _ = items[0]
        self.assertEqual(group, "MENU:PRIMS_SELECTED")
        self.assertEqual(descriptor["appear_after"], MenuItem.AI_TOOLS.value)
        submenu = descriptor["name"]
        self.assertEqual(list(submenu), [MenuItem.EXPERIMENTAL.value])
        self.assertEqual(submenu[MenuItem.EXPERIMENTAL.value][0]["name"], MenuItem.CONVERT_ALPHA_CARDS.value)
        self.assertEqual(descriptor["show_fn"], plugin_class._is_convertible)
        self.assertEqual(submenu[MenuItem.EXPERIMENTAL.value][0]["onclick_fn"], plugin_class._request_conversion)

    async def test_is_convertible_with_mesh_prototype_descendant_returns_true(self):
        # Arrange
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(f"{_MESH_ROOT}/mesh"))}

        # Act
        result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)

        # Assert
        self.assertTrue(result)

    async def test_is_convertible_with_instance_resolving_to_mesh_prototype_returns_true(self):
        # Arrange
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(_INSTANCE))}

        # Act
        result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)

        # Assert
        self.assertTrue(result)

    async def test_is_convertible_with_prototype_without_mesh_returns_false(self):
        # Arrange
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(_EMPTY_ROOT))}

        # Act
        result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)

        # Assert
        self.assertFalse(result)

    async def test_is_convertible_with_light_returns_false(self):
        # Arrange
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(_LIGHT))}

        # Act
        result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)

        # Assert
        self.assertFalse(result)

    async def test_is_convertible_with_non_capture_mesh_root_returns_false(self):
        # Arrange
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(_MESH_ROOT))}
        self._capture_patch.stop()

        try:
            # Act
            with patch(_CAPTURE_CHECK, return_value=False):
                result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)
        finally:
            self._capture_patch.start()

        # Assert
        self.assertFalse(result)

    async def test_is_convertible_with_mesh_under_remix_reference_returns_true(self):
        # Arrange
        ref_prim = UsdGeom.Xform.Define(self._stage, f"{_MESH_ROOT}/ref_abc").GetPrim()
        ref_prim.CreateAttribute(constants.IS_REMIX_REF_ATTR, Sdf.ValueTypeNames.Bool).Set(True)
        referenced = Sdf.Layer.CreateAnonymous(".usda")
        Usd.Stage.Open(referenced).DefinePrim("/ReferenceTarget", "Xform")
        referenced.defaultPrim = "ReferenceTarget"
        ref_prim.GetReferences().AddReference(referenced.identifier)
        payload = {"right_clicked_item": _item(self._stage.GetPrimAtPath(f"{_MESH_ROOT}/ref_abc"))}

        # Act
        result = ConvertAlphaCardsActionWidgetPlugin._is_convertible(payload)

        # Assert
        self.assertTrue(result)

    async def test_request_conversion_with_selected_instances_emits_deduplicated_prototypes_and_context(self):
        # Arrange
        context = Mock()
        context.get_stage.return_value = self._stage
        event_manager = Mock()
        payload = {
            "context_name": "ctx",
            "selected_paths": [_INSTANCE, f"{_MESH_ROOT}/mesh", _LIGHT],
            "right_clicked_item": _item(self._stage.GetPrimAtPath(_INSTANCE)),
        }

        # Act
        with (
            patch(f"{_MODULE}.omni.usd.get_context", return_value=context),
            patch(f"{_MODULE}._get_event_manager_instance", return_value=event_manager),
        ):
            ConvertAlphaCardsActionWidgetPlugin._request_conversion(payload)

        # Assert
        event_manager.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, [_MESH_ROOT], "ctx"
        )

    async def test_request_conversion_without_selection_uses_right_clicked_item(self):
        # Arrange
        context = Mock()
        context.get_stage.return_value = self._stage
        event_manager = Mock()
        payload = {
            "context_name": "",
            "selected_paths": [],
            "right_clicked_item": _item(self._stage.GetPrimAtPath(f"{_MESH_ROOT}/mesh")),
        }

        # Act
        with (
            patch(f"{_MODULE}.omni.usd.get_context", return_value=context),
            patch(f"{_MODULE}._get_event_manager_instance", return_value=event_manager),
        ):
            ConvertAlphaCardsActionWidgetPlugin._request_conversion(payload)

        # Assert
        event_manager.call_global_custom_event.assert_called_once_with(
            GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, [_MESH_ROOT], ""
        )

    async def test_request_conversion_without_capture_mesh_emits_nothing(self):
        # Arrange
        context = Mock()
        context.get_stage.return_value = self._stage
        event_manager = Mock()
        payload = {"context_name": "", "selected_paths": [_LIGHT], "right_clicked_item": None}

        # Act
        with (
            patch(f"{_MODULE}.omni.usd.get_context", return_value=context),
            patch(f"{_MODULE}._get_event_manager_instance", return_value=event_manager),
        ):
            ConvertAlphaCardsActionWidgetPlugin._request_conversion(payload)

        # Assert
        event_manager.call_global_custom_event.assert_not_called()
