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

from pathlib import Path
from unittest.mock import patch

import omni.kit.app
import omni.kit.test
import omni.usd
from omni.flux.stage_manager.factory import StageManagerItem
from omni.flux.utils.common.omni_url import OmniUrl
from omni.flux.utils.tests.context_managers import open_test_project
from pxr import Usd

from lightspeed.trex.stage_manager.plugin.filter.usd import scene_edit_state as _scene_edit_state
from lightspeed.trex.stage_manager.plugin.filter.usd.scene_edit_state import SceneEditFilterPlugin, SceneEditState

__all__ = ["TestSceneEditFilterE2E"]

_CONTEXT_NAME = "lightspeed.layer_manager.core"
_TEST_PROJECT = "usd/full_project/full_project.usda"
_LIGHT_PATH = "/RootNode/lights/light_9907D0B07D040077"
_MATERIAL_SHADER_PATH = "/RootNode/Looks/mat_8D1946B4993CE5A3/Shader"
_INSTANCE_PATH = "/RootNode/instances/inst_6CA2F12444DEBE09_0"
_MESH_PATH = "/RootNode/meshes/mesh_6CA2F12444DEBE09"


class _NoopLayerEventStream:
    def create_subscription_to_pop(self, *_args, **_kwargs):
        return object()


class _NoopLayers:
    def get_event_stream(self):
        return _NoopLayerEventStream()


def _layer_name(identifier: str) -> str:
    return Path(OmniUrl(identifier).path).name


def _stage() -> Usd.Stage:
    return omni.usd.get_context(_CONTEXT_NAME).get_stage()


def _item_for_prim(stage: Usd.Stage, prim_path: str) -> StageManagerItem:
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        raise AssertionError(f'Prim "{prim_path}" was not found in the test project')
    return StageManagerItem(prim_path, prim)


class TestSceneEditFilterE2E(omni.kit.test.AsyncTestCase):
    """E2E coverage for SceneEditFilterPlugin against the centralized full-project fixture."""

    @staticmethod
    def _build_plugin(mode: SceneEditState) -> SceneEditFilterPlugin:
        plugin = SceneEditFilterPlugin(mode=mode)
        with patch.object(_scene_edit_state, "get_layers", return_value=_NoopLayers()):
            plugin.set_context_name(_CONTEXT_NAME)
        return plugin

    @staticmethod
    def _mod_layer_ids_by_name(plugin: SceneEditFilterPlugin) -> dict[str, str]:
        return {_layer_name(identifier): identifier for identifier in plugin.mod_layer_ids}

    async def test_scene_edit_state_entries_should_carry_value_and_label(self):
        self.assertEqual(
            [(state.value, state.label) for state in SceneEditState],
            [
                ("all", "Show all prims"),
                ("modified", "Modified prims"),
                ("unedited", "Unedited prims"),
                ("unused_edits", "Unused edits"),
            ],
        )

    async def test_modes_should_filter_real_full_project_prim_stacks(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            modified_plugin = None
            unedited_plugin = None
            try:
                stage = _stage()
                modified_plugin = self._build_plugin(SceneEditState.MODIFIED)
                unedited_plugin = self._build_plugin(SceneEditState.UNEDITED)

                self.assertTrue(modified_plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertTrue(modified_plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
                self.assertTrue(modified_plugin.filter_predicate(_item_for_prim(stage, _INSTANCE_PATH)))
                self.assertFalse(modified_plugin.filter_predicate(_item_for_prim(stage, _MESH_PATH)))

                self.assertFalse(unedited_plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertFalse(unedited_plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
                self.assertFalse(unedited_plugin.filter_predicate(_item_for_prim(stage, _INSTANCE_PATH)))
                self.assertTrue(unedited_plugin.filter_predicate(_item_for_prim(stage, _MESH_PATH)))
            finally:
                if modified_plugin is not None:
                    modified_plugin.destroy()
                if unedited_plugin is not None:
                    unedited_plugin.destroy()

    async def test_selected_source_layers_should_limit_modified_results(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                stage = _stage()
                plugin = self._build_plugin(SceneEditState.MODIFIED)
                layer_ids_by_name = self._mod_layer_ids_by_name(plugin)

                plugin.set_selected_layer_ids({layer_ids_by_name["sublayer_child_01.usda"]})

                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
                self.assertFalse(plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertFalse(plugin.filter_predicate(_item_for_prim(stage, _INSTANCE_PATH)))
            finally:
                if plugin is not None:
                    plugin.destroy()

    async def test_filter_predicate_inactive_filter_should_pass_all_prims(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                stage = _stage()
                plugin = self._build_plugin(SceneEditState.MODIFIED)
                plugin.filter_active = False

                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _MESH_PATH)))
            finally:
                if plugin is not None:
                    plugin.destroy()

    async def test_all_mode_should_pass_real_full_project_prims(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                stage = _stage()
                plugin = self._build_plugin(SceneEditState.ALL)

                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _MESH_PATH)))
            finally:
                if plugin is not None:
                    plugin.destroy()

    async def test_layer_change_sync_should_prune_vanished_source_layer_ids(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                plugin = self._build_plugin(SceneEditState.MODIFIED)
                layer_ids_by_name = self._mod_layer_ids_by_name(plugin)
                selected_id = layer_ids_by_name["sublayer_child_01.usda"]

                plugin.set_selected_layer_ids({selected_id, "vanished_mod_layer.usda"})
                plugin.sync_to_layer_changes()

                self.assertEqual({selected_id}, plugin.selected_layer_ids)
            finally:
                if plugin is not None:
                    plugin.destroy()

    async def test_unused_edits_should_find_shadowed_real_mod_opinions(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                stage = _stage()
                light_prim = stage.GetPrimAtPath(_LIGHT_PATH)
                with Usd.EditContext(stage, Usd.EditTarget(stage.GetRootLayer())):
                    light_prim.GetAttribute("intensity").Set(200.0)

                plugin = self._build_plugin(SceneEditState.UNUSED_EDITS)

                self.assertTrue(plugin.filter_predicate(_item_for_prim(stage, _LIGHT_PATH)))
                self.assertFalse(plugin.filter_predicate(_item_for_prim(stage, _MATERIAL_SHADER_PATH)))
            finally:
                if plugin is not None:
                    plugin.destroy()

    async def test_stage_open_should_clear_explicit_layer_selection_when_context_is_reused(self):
        async with open_test_project(_TEST_PROJECT, _CONTEXT_NAME, context_name=_CONTEXT_NAME):
            plugin = None
            try:
                plugin = self._build_plugin(SceneEditState.MODIFIED)
                plugin.set_selected_layer_ids({"old_context_mod.usda"})

                await omni.usd.get_context(_CONTEXT_NAME).new_stage_async()
                await omni.kit.app.get_app().next_update_async()

                self.assertIsNone(plugin.selected_layer_ids)
            finally:
                if plugin is not None:
                    plugin.destroy()
