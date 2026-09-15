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

from unittest.mock import MagicMock, call, patch

import omni.kit.commands
import omni.kit.undo
import omni.usd
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.properties_pane.mesh.widget import setup_ui as setup_ui_module
from lightspeed.trex.properties_pane.mesh.widget.setup_ui import SetupUI
from omni.kit.test import AsyncTestCase
from pxr import Sdf, Usd


class TestSetupUI(AsyncTestCase):
    """Tests the mesh properties setup UI."""

    async def setUp(self):
        """Create a clean default USD context and real command-owning core."""
        self._context = omni.usd.get_context()
        await self._context.new_stage_async()
        self._core = _AssetReplacementsCore("")
        omni.kit.undo.clear_history()

    async def tearDown(self):
        """Release the real core and close the test stage."""
        omni.kit.undo.clear_history()
        self._core.destroy()
        if self._context.can_close_stage():
            await self._context.close_stage_async()
        self._context = None

    async def test_migrate_deprecated_remix_categories_with_active_decal_updates_usd_attributes(self):
        """Switch an active legacy decal category to Decal through USD commands."""
        # Arrange
        stage = self._context.get_stage()
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        mesh_prim.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(True)
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        setup_ui._core = self._core
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
        }

        # Act
        with (
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(setup_ui_module, "_DEPRECATED_REMIX_CATEGORIES", ("Decal Dynamic",)),
        ):
            setup_ui._migrate_deprecated_remix_categories([mesh_prim])

        # Assert
        self.assertTrue(mesh_prim.GetAttribute("remix_category:decal_Static").Get())
        self.assertFalse(mesh_prim.GetAttribute("remix_category:decal_dynamic").Get())

    async def test_migrate_deprecated_remix_categories_undo_restores_usd_attributes(self):
        """Restore legacy decal state with one undo of the grouped migration commands."""
        # Arrange
        stage = self._context.get_stage()
        root_layer = stage.GetRootLayer()
        weaker_layer = Sdf.Layer.CreateAnonymous("deprecated_decal")
        root_layer.subLayerPaths.append(weaker_layer.identifier)
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        stage.SetEditTarget(weaker_layer)
        mesh_prim.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(True)
        stage.SetEditTarget(root_layer)
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        setup_ui._core = self._core
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
        }
        with (
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(setup_ui_module, "_DEPRECATED_REMIX_CATEGORIES", ("Decal Dynamic",)),
        ):
            setup_ui._migrate_deprecated_remix_categories([mesh_prim])
        self.assertTrue(mesh_prim.GetAttribute("remix_category:decal_Static").Get())
        self.assertFalse(mesh_prim.GetAttribute("remix_category:decal_dynamic").Get())

        # Act
        omni.kit.undo.undo()

        # Assert
        self.assertTrue(mesh_prim.GetAttribute("remix_category:decal_dynamic").Get())
        self.assertFalse(mesh_prim.GetAttribute("remix_category:decal_Static"))
        self.assertIsNone(root_layer.GetPropertyAtPath("/Mesh.remix_category:decal_dynamic"))
        self.assertIsNone(root_layer.GetPropertyAtPath("/Mesh.remix_category:decal_Static"))

    async def test_migrate_deprecated_remix_categories_undo_restores_existing_local_opinions(self):
        """Restore existing local canonical and deprecated opinions with one undo."""
        # Arrange
        stage = self._context.get_stage()
        root_layer = stage.GetRootLayer()
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        mesh_prim.CreateAttribute("remix_category:decal_Static", Sdf.ValueTypeNames.Bool).Set(False)
        mesh_prim.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(True)
        original_layer_contents = root_layer.ExportToString()
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        setup_ui._core = self._core
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
        }
        with (
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(setup_ui_module, "_DEPRECATED_REMIX_CATEGORIES", ("Decal Dynamic",)),
        ):
            setup_ui._migrate_deprecated_remix_categories([mesh_prim])
        self.assertTrue(mesh_prim.GetAttribute("remix_category:decal_Static").Get())
        self.assertFalse(mesh_prim.GetAttribute("remix_category:decal_dynamic").Get())

        # Act
        omni.kit.undo.undo()

        # Assert
        self.assertFalse(mesh_prim.GetAttribute("remix_category:decal_Static").Get())
        self.assertTrue(mesh_prim.GetAttribute("remix_category:decal_dynamic").Get())
        self.assertEqual(root_layer.ExportToString(), original_layer_contents)

    def test_migrate_deprecated_remix_categories_with_multiple_meshes_migrates_each_mesh(self):
        """Migrate every displayed mesh that has an active deprecated decal."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        first_mesh = stage.DefinePrim("/FirstMesh", "Mesh")
        first_mesh.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(True)
        second_mesh = stage.DefinePrim("/SecondMesh", "Mesh")
        second_mesh.CreateAttribute("remix_category:decal_no_offset", Sdf.ValueTypeNames.Bool).Set(True)
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
            "Decal No Offset": {"attr": "remix_category:decal_no_offset"},
        }

        # Act
        with (
            patch.object(omni.kit.commands, "execute") as execute_mock,
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(
                setup_ui_module,
                "_DEPRECATED_REMIX_CATEGORIES",
                ("Decal Dynamic", "Decal No Offset"),
            ),
        ):
            setup_ui._migrate_deprecated_remix_categories([first_mesh, second_mesh])

        # Assert
        self.assertEqual(execute_mock.call_count, 4)
        execute_mock.assert_has_calls(
            [
                call(
                    "CreateUsdAttribute",
                    prim=first_mesh,
                    attr_name="remix_category:decal_Static",
                    attr_value=True,
                    attr_type=Sdf.ValueTypeNames.Bool,
                ),
                call(
                    "ChangeProperty",
                    prop_path=Sdf.Path("/FirstMesh.remix_category:decal_dynamic"),
                    value=False,
                    prev=None,
                    target_layer=stage.GetRootLayer(),
                    usd_context_name="",
                ),
                call(
                    "CreateUsdAttribute",
                    prim=second_mesh,
                    attr_name="remix_category:decal_Static",
                    attr_value=True,
                    attr_type=Sdf.ValueTypeNames.Bool,
                ),
                call(
                    "ChangeProperty",
                    prop_path=Sdf.Path("/SecondMesh.remix_category:decal_no_offset"),
                    value=False,
                    prev=None,
                    target_layer=stage.GetRootLayer(),
                    usd_context_name="",
                ),
            ]
        )

    def test_migrate_deprecated_remix_categories_with_active_decal_only_disables_deprecated_decal(self):
        """Avoid rewriting Decal when the canonical category is already active."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        mesh_prim.CreateAttribute("remix_category:decal_Static", Sdf.ValueTypeNames.Bool).Set(True)
        mesh_prim.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(True)
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
        }

        # Act
        with (
            patch.object(omni.kit.commands, "execute") as execute_mock,
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(setup_ui_module, "_DEPRECATED_REMIX_CATEGORIES", ("Decal Dynamic",)),
        ):
            setup_ui._migrate_deprecated_remix_categories([mesh_prim])

        # Assert
        execute_mock.assert_called_once_with(
            "ChangeProperty",
            prop_path=Sdf.Path("/Mesh.remix_category:decal_dynamic"),
            value=False,
            prev=None,
            target_layer=stage.GetRootLayer(),
            usd_context_name="",
        )

    def test_migrate_deprecated_remix_categories_without_active_deprecated_decal_does_not_author_attributes(self):
        """Leave false deprecated and unrelated decal attributes unchanged."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        mesh_prim.CreateAttribute("remix_category:decal_dynamic", Sdf.ValueTypeNames.Bool).Set(False)
        mesh_prim.CreateAttribute("remix_category:decal_custom", Sdf.ValueTypeNames.Bool).Set(True)
        setup_ui = object.__new__(SetupUI)
        setup_ui._context_name = ""
        categories = {
            "Decal": {"attr": "remix_category:decal_Static"},
            "Decal Dynamic": {"attr": "remix_category:decal_dynamic"},
        }

        # Act
        with (
            patch.object(omni.kit.commands, "execute") as execute_mock,
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", categories),
            patch.object(setup_ui_module, "_DEPRECATED_REMIX_CATEGORIES", ("Decal Dynamic",)),
        ):
            setup_ui._migrate_deprecated_remix_categories([mesh_prim])

        # Assert
        execute_mock.assert_not_called()

    def test_refresh_remix_categories_without_schema_data_returns_without_error(self):
        """Keep category refresh safe when the categories schema failed to load."""
        # Arrange
        setup_ui = object.__new__(SetupUI)

        # Act
        with patch("lightspeed.trex.properties_pane.mesh.widget.setup_ui._REMIX_CATEGORIES", {}):
            result = setup_ui._refresh_remix_categories([])

        # Assert
        self.assertIsNone(result)

    def test_refresh_remix_categories_without_decal_displays_other_categories(self):
        """Display authored non-Decal categories when the schema has no Decal entry."""
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        mesh_prim = stage.DefinePrim("/Mesh", "Mesh")
        mesh_prim.CreateAttribute("remix_category:world_ui", Sdf.ValueTypeNames.Bool).Set(True)
        setup_ui = object.__new__(SetupUI)
        setup_ui._remix_categories_frame = MagicMock()

        # Act
        with (
            patch.object(setup_ui_module, "_REMIX_CATEGORIES", {"World UI": {"attr": "remix_category:world_ui"}}),
            patch.object(
                setup_ui_module,
                "_REMIX_CATEGORIES_DISPLAY_NAMES",
                {"remix_category:world_ui": "World UI"},
            ),
            patch.object(setup_ui_module.ui, "VStack", return_value=MagicMock()),
            patch.object(setup_ui_module.ui, "HStack", return_value=MagicMock()),
            patch.object(setup_ui_module.ui, "CheckBox", return_value=MagicMock()),
            patch.object(setup_ui_module.ui, "Spacer"),
            patch.object(setup_ui_module.ui, "Label") as label_mock,
        ):
            setup_ui._refresh_remix_categories([mesh_prim])

        # Assert
        label_mock.assert_called_once_with(
            "World UI", name="RemixAttrLabel", alignment=setup_ui_module.ui.Alignment.LEFT
        )
