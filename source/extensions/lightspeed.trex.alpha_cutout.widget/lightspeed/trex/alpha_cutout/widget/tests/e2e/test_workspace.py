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

__all__ = ["TestAlphaCutoutWorkspaceE2E"]

from pathlib import Path

import carb.settings
import numpy as np
import omni.kit.app
import omni.kit.undo
import omni.usd
from lightspeed.common import constants
from lightspeed.common.constants import GlobalEventNames
from lightspeed.events_manager import get_instance as get_event_manager_instance
from lightspeed.trex.alpha_cutout.core import MATERIAL_PRIM_NAME, REPLACEMENT_SUFFIX, cutout_output_path
from lightspeed.trex.alpha_cutout.core.tests.unit.fixtures import write_replacement_file
from lightspeed.trex.asset_replacements.core.shared import Setup as AssetReplacementsCore
from lightspeed.trex.alpha_cutout.widget.workspace import AlphaCutoutWindow
from omni import ui
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase
from PIL import Image
from pxr import Sdf, Usd, UsdGeom, UsdShade

_RESOURCES_EXT = "lightspeed.trex.app.resources"
_PROJECT = "usd/project_example/combined.usda"
_MESH_HASH = "CED45075A077A49A"
_MESH_PATH = f"/RootNode/meshes/mesh_{_MESH_HASH}"
_INSTANCE_PATH = f"/RootNode/instances/inst_{_MESH_HASH}_0"
_SHADER_TEXTURE_ATTR = "/RootNode/Looks/mat_BC868CE5A075ABB1/Shader.inputs:diffuse_texture"
_OUTPUT_FOLDER_SETTING = "/persistent/exts/lightspeed.trex.alpha_cutout.widget/output_folder"
_THICKEN_SETTING = "/persistent/exts/lightspeed.trex.alpha_cutout.widget/thicken"
_SMOOTH_SETTING = "/persistent/exts/lightspeed.trex.alpha_cutout.widget/smooth_normals"
_UP_SETTING = "/persistent/exts/lightspeed.trex.alpha_cutout.widget/up_normals"
_MAX_WAIT_FRAMES = 1200


class _TestWindow(AlphaCutoutWindow):
    """Window under a unique title so widget queries cannot hit the extension's own window."""

    @property
    def title(self) -> str:
        return "Convert Alpha Cards to Mesh Test"


def _write_disc_texture(path: str) -> None:
    size = 64
    rows, cols = np.mgrid[0:size, 0:size]
    alpha = ((((rows - 31.5) ** 2 + (cols - 31.5) ** 2) <= 24**2).astype(np.uint8)) * 255
    rgba = np.dstack([np.full_like(alpha, 90)] * 3 + [alpha])
    Image.fromarray(rgba, "RGBA").save(path)


def _remix_ref_children(prim: Usd.Prim, baseline: set[Sdf.Path] | None = None) -> list[Usd.Prim]:
    """Return the Remix reference children of a prim, excluding the ones listed in the baseline."""
    return [
        child
        for child in prim.GetChildren()
        if child.GetAttribute(constants.IS_REMIX_REF_ATTR).IsValid() and child.GetPath() not in (baseline or set())
    ]


def _baseline(prim: Usd.Prim) -> set[Sdf.Path]:
    return {child.GetPath() for child in _remix_ref_children(prim)}


class TestAlphaCutoutWorkspaceE2E(AsyncTestCase):
    """Drive the real window against the example project."""

    async def setUp(self):
        self._settings = carb.settings.get_settings()
        self._previous_output_folder = self._settings.get_as_string(_OUTPUT_FOLDER_SETTING)
        self._previous_thicken = self._settings.get_as_bool(_THICKEN_SETTING)
        self._previous_smooth = self._settings.get_as_bool(_SMOOTH_SETTING)
        self._previous_up = self._settings.get_as_bool(_UP_SETTING)

    async def tearDown(self):
        self._settings.set(_OUTPUT_FOLDER_SETTING, self._previous_output_folder)
        self._settings.set(_THICKEN_SETTING, self._previous_thicken)
        self._settings.set(_SMOOTH_SETTING, self._previous_smooth)
        self._settings.set(_UP_SETTING, self._previous_up)

    def _find(self, window: ui.Window, widget_type: str, identifier: str):
        return ui_test.find(f"{window.title}//Frame/**/{widget_type}[*].identifier=='{identifier}'")

    def _find_all(self, window: ui.Window, widget_type: str, identifier: str):
        return ui_test.find_all(f"{window.title}//Frame/**/{widget_type}[*].identifier=='{identifier}'") or []

    async def _wait_for_results(self, window: ui.Window, pane):
        for _ in range(_MAX_WAIT_FRAMES):
            await omni.kit.app.get_app().next_update_async()
            if not pane.job_running and self._find_all(window, "Label", "alpha_cutout_result_row"):
                return
        self.fail("The conversion did not finish in time.")

    async def _prepare_project(self, project_url: OmniUrl) -> tuple[Usd.Stage, str]:
        """Point the fixture material at a texture with transparency and target the replacement layer."""
        stage = omni.usd.get_context().get_stage()
        project_dir = OmniUrl(project_url.parent_url)
        texture = str(project_dir / "disc.png")
        _write_disc_texture(texture)
        replacement_layer = Sdf.Layer.FindOrOpen(str(project_dir / "replacements.usda"))
        stage.SetEditTarget(Usd.EditTarget(replacement_layer))
        stage.GetAttributeAtPath(_SHADER_TEXTURE_ATTR).Set(Sdf.AssetPath(texture))
        return stage, str(project_dir / "cutout_out")

    async def test_convert_request_opens_window_and_converting_replaces_the_capture_mesh(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            stage, output_folder = await self._prepare_project(project_url)
            baseline = _baseline(stage.GetPrimAtPath(_MESH_PATH))
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()

            # The Stage Manager action sends the instance; the window must show the prototype in its list.
            workspace.open_with_meshes([_MESH_PATH], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            pane = workspace._content
            self.assertEqual(pane.target.prim_path, _MESH_PATH)
            self.assertEqual(self._find(window, "Label", "alpha_cutout_mesh_path").widget.text, _MESH_PATH)

            # The user picks an output folder and converts.
            output_field = self._find(window, "StringField", "alpha_cutout_output_field")
            output_field.widget.model.set_value(output_folder)
            await ui_test.wait_n_updates(2)
            convert_button = self._find(window, "Button", "alpha_cutout_convert_button")
            self.assertTrue(convert_button.widget.enabled)
            await convert_button.click()
            await self._wait_for_results(window, pane)

            # The replacement file exists, is referenced through a Remix reference child and binds the material copy.
            output_path = cutout_output_path(output_folder, _MESH_HASH)
            self.assertTrue(OmniUrl(output_path).exists)
            self.assertTrue(OmniUrl(output_path + ".meta").exists)
            prim = stage.GetPrimAtPath(_MESH_PATH)
            children = _remix_ref_children(prim, baseline)
            self.assertEqual(len(children), 1)
            cutout_mesh = next(child for child in Usd.PrimRange(children[0]) if child.IsA(UsdGeom.Mesh))
            self.assertGreater(len(UsdGeom.Mesh(cutout_mesh).GetFaceVertexCountsAttr().Get()), 2)
            bound, _ = UsdShade.MaterialBindingAPI(cutout_mesh).ComputeBoundMaterial()
            self.assertEqual(bound.GetPrim().GetName(), MATERIAL_PRIM_NAME)
            self.assertEqual(UsdShade.Shader(bound.GetPrim().GetChild("Shader")).GetInput("alpha_test_type").Get(), 7)
            result_rows = self._find_all(window, "Label", "alpha_cutout_result_row")
            self.assertIn("triangles", result_rows[0].widget.text)

            # One undo reverts the stage edits of the run, and redo brings the replacement back.
            omni.kit.undo.undo()
            await ui_test.wait_n_updates(2)
            self.assertEqual(_remix_ref_children(prim, baseline), [])
            omni.kit.undo.redo()
            await ui_test.wait_n_updates(2)
            self.assertEqual(len(_remix_ref_children(prim, baseline)), 1)

            # Converting again overwrites the file without adding a second reference.
            await convert_button.click()
            await self._wait_for_results(window, pane)
            self.assertEqual(len(_remix_ref_children(prim, baseline)), 1)
            self.assertIn("overwritten", self._find_all(window, "Label", "alpha_cutout_result_row")[0].widget.text)

    async def test_convert_with_capture_edit_target_is_refused_and_leaves_the_stage_untouched(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            stage, output_folder = await self._prepare_project(project_url)
            capture_layer = Sdf.Layer.FindOrOpen(str(OmniUrl(project_url.parent_url) / "deps/captures/capture.usda"))
            stage.SetEditTarget(Usd.EditTarget(capture_layer))
            baseline = _baseline(stage.GetPrimAtPath(_MESH_PATH))
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()
            workspace.open_with_meshes([_MESH_PATH], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            self._find(window, "StringField", "alpha_cutout_output_field").widget.model.set_value(output_folder)
            await ui_test.wait_n_updates(2)

            # Converting against the capture layer shows the refusal dialog and changes nothing.
            await self._find(window, "Button", "alpha_cutout_convert_button").click()
            await ui_test.wait_n_updates(6)
            prompt = ui_test.find("Invalid Edit Target")
            self.assertIsNotNone(prompt)
            prompt.widget.visible = False
            self.assertEqual(_remix_ref_children(stage.GetPrimAtPath(_MESH_PATH), baseline), [])
            self.assertFalse(OmniUrl(cutout_output_path(output_folder, _MESH_HASH)).exists)

    async def test_selecting_a_capture_instance_while_the_window_is_open_updates_the_mesh(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT):
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()
            workspace.open_with_meshes([], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            self.assertIsNone(workspace._content.target)

            # Selecting an instance in the viewport or Stage Manager queues its prototype.
            omni.usd.get_context().get_selection().set_selected_prim_paths([_INSTANCE_PATH], True)
            await ui_test.wait_n_updates(4)
            self.assertEqual(workspace._content.target.prim_path, _MESH_PATH)
            self.assertEqual(self._find(window, "Label", "alpha_cutout_mesh_path").widget.text, _MESH_PATH)

            # Selecting something that is not a capture mesh clears it.
            omni.usd.get_context().get_selection().set_selected_prim_paths(["/RootNode/Looks"], True)
            await ui_test.wait_n_updates(4)
            self.assertIsNone(workspace._content.target)

    async def test_thicken_checkbox_enables_the_thickness_controls(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT):
            self._settings.set(_THICKEN_SETTING, False)
            self._settings.set(_SMOOTH_SETTING, True)
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()
            workspace.open_with_meshes([], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            thickness = self._find(window, "FloatDrag", "alpha_cutout_thickness")
            back_face = self._find(window, "CheckBox", "alpha_cutout_thicken_back_face")
            anti_stretch = self._find(window, "CheckBox", "alpha_cutout_thicken_anti_stretch")
            smooth = self._find(window, "CheckBox", "alpha_cutout_smooth_normals")
            smoothing = self._find(window, "FloatSlider", "alpha_cutout_smoothing")
            self.assertFalse(thickness.widget.enabled)
            self.assertFalse(back_face.widget.enabled)
            self.assertFalse(anti_stretch.widget.enabled)
            self.assertFalse(smooth.widget.enabled)
            self.assertFalse(smoothing.widget.enabled)
            self.assertEqual(thickness.widget.style_type_name_override, "DragField")
            self.assertIsNotNone(self._find(window, "IntSlider", "alpha_cutout_trace_resolution"))

            # Turning thickening on enables its controls and persists the flag.
            self._find(window, "CheckBox", "alpha_cutout_thicken").widget.model.set_value(True)
            await ui_test.wait_n_updates(2)
            self.assertTrue(thickness.widget.enabled)
            self.assertTrue(back_face.widget.enabled)
            self.assertTrue(anti_stretch.widget.enabled)
            self.assertTrue(smooth.widget.enabled)
            self.assertTrue(smoothing.widget.enabled)
            self.assertTrue(self._settings.get_as_bool(_THICKEN_SETTING))

            # The reset dot of the thicken row lights up, the header says ON, and clicking the dot resets it.
            dot = self._find(window, "Circle", "alpha_cutout_thicken_reset")
            self.assertEqual(dot.widget.style_type_name_override, "OverrideIndicator")
            self.assertEqual(workspace._content._thicken_frame.root.title, "THICKEN (ON)")
            workspace._content._on_reset_pressed(
                0,
                next(
                    r
                    for r in workspace._content._setting_rows
                    if r.widget is self._find(window, "CheckBox", "alpha_cutout_thicken").widget
                ),
            )
            await ui_test.wait_n_updates(2)
            self.assertFalse(self._settings.get_as_bool(_THICKEN_SETTING))
            self.assertEqual(dot.widget.style_type_name_override, "OverrideIndicatorForceDisabled")
            self.assertEqual(workspace._content._thicken_frame.root.title, "THICKEN (OFF)")
            self._find(window, "CheckBox", "alpha_cutout_thicken").widget.model.set_value(True)
            await ui_test.wait_n_updates(2)

            # Smoothing follows its own checkbox while thickening stays on.
            smooth.widget.model.set_value(False)
            await ui_test.wait_n_updates(2)
            self.assertFalse(smoothing.widget.enabled)
            self.assertFalse(self._settings.get_as_bool(_SMOOTH_SETTING))

    async def test_up_normals_checkbox_enables_the_up_amount_field(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT):
            self._settings.set(_UP_SETTING, False)
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()
            workspace.open_with_meshes([], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            amount = self._find(window, "FloatSlider", "alpha_cutout_up_amount")
            self.assertFalse(amount.widget.enabled)

            self._find(window, "CheckBox", "alpha_cutout_up_normals").widget.model.set_value(True)
            await ui_test.wait_n_updates(2)
            self.assertTrue(amount.widget.enabled)
            self.assertTrue(self._settings.get_as_bool(_UP_SETTING))

    async def test_selecting_a_replacement_mesh_lists_it_ticked_and_converts_into_a_suffixed_copy(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT) as project_url:
            stage, _ = await self._prepare_project(project_url)
            project_dir = OmniUrl(project_url.parent_url)
            original = write_replacement_file(Path(project_dir.path) / "fern01.usda", str(project_dir / "disc.png"))
            core = AssetReplacementsCore("")
            self.addCleanup(core.destroy)
            _, ref_path = core.add_new_reference(
                stage,
                Sdf.Path(_MESH_PATH),
                original,
                AssetReplacementsCore.get_ref_default_prim_tag(),
                stage.GetEditTarget().GetLayer(),
            )
            card_path = f"{ref_path}/XForms/card/mesh"
            omni.usd.get_context().get_selection().set_selected_prim_paths([card_path], True)
            await ui_test.wait_n_updates(4)
            workspace = _TestWindow("")
            self.addCleanup(workspace.cleanup)
            workspace.create_window()

            # The window lists the card ticked and locks the output to the suffixed path next to the original.
            workspace.open_with_meshes([card_path], "")
            await ui_test.wait_n_updates(4)
            window = workspace.get_window()
            pane = workspace._content
            self.assertTrue(pane.target.is_replacement)
            toggles = self._find_all(window, "CheckBox", "alpha_cutout_mesh_toggle")
            self.assertEqual(len(toggles), 1)
            self.assertTrue(toggles[0].widget.model.get_value_as_bool())
            output_field = self._find(window, "StringField", "alpha_cutout_output_field")
            self.assertFalse(output_field.widget.enabled)
            self.assertTrue(
                output_field.widget.model.get_value_as_string().endswith(f"fern01{REPLACEMENT_SUFFIX}.usda")
            )
            convert_button = self._find(window, "Button", "alpha_cutout_convert_button")
            self.assertTrue(convert_button.widget.enabled)

            # Unticking the only mesh disables Convert; ticking it again and converting swaps the reference.
            toggles[0].widget.model.set_value(False)
            await ui_test.wait_n_updates(2)
            self.assertFalse(convert_button.widget.enabled)
            toggles[0].widget.model.set_value(True)
            await ui_test.wait_n_updates(2)
            await convert_button.click()
            await self._wait_for_results(window, pane)
            self.assertTrue(OmniUrl(pane.target.output_file).exists)
            references = [
                r for r, _ in omni.usd.get_composed_references_from_prim(stage.GetPrimAtPath(ref_path), False)
            ]
            self.assertEqual(len(references), 1)
            self.assertTrue(references[0].assetPath.endswith(f"fern01{REPLACEMENT_SUFFIX}.usda"))
            self.assertIn(
                "reference now points", self._find_all(window, "Label", "alpha_cutout_result_row")[0].widget.text
            )

    async def test_global_event_seeds_the_extension_window(self):
        async with open_test_project(_PROJECT, _RESOURCES_EXT):
            # The Stage Manager plugin fires the global event; the extension window must open with the paths.
            get_event_manager_instance().call_global_custom_event(
                GlobalEventNames.ALPHA_CUTOUT_CONVERT_REQUEST.value, [_MESH_PATH, _MESH_PATH], ""
            )
            await ui_test.wait_n_updates(4)

            window = ui.Workspace.get_window(constants.WindowNames.ALPHA_CUTOUT.value)
            self.assertIsNotNone(window)
            self.assertTrue(window.visible)
            self.assertEqual(self._find(window, "Label", "alpha_cutout_mesh_path").widget.text, _MESH_PATH)
            window.visible = False
