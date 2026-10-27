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

from unittest.mock import AsyncMock, patch

from lightspeed.trex.comfyui.core.api import ComfyUIAPI
from lightspeed.trex.comfyui.core.constants import COMFYUI_WORKFLOWS_ROUTE
from lightspeed.trex.comfyui.core.core import ComfyUICore
from lightspeed.trex.comfyui.core.enums import RemixType
from lightspeed.trex.comfyui.core.resolvers import ConstantResolver, SelectedTextureResolver
from lightspeed.trex.comfyui.widget.workflow import widget
from omni import ui
from omni.kit import ui_test
from omni.kit.test import AsyncTestCase

__all__ = ("TestNodePackInputTypesUIE2E",)

_WORKFLOW_NAME = "node_pack_input_types_ui_e2e"
_WORKFLOW_DISPLAY = "Node Pack Input Types UI E2E"
_WINDOW_WIDTH = ui.Pixel(900)
_WINDOW_HEIGHT = ui.Pixel(900)

# Each tagged port belongs to a separate node, as in a node pack API export. The last three rows stand in for types
# that a newer node pack can add before the Toolkit knows them.
_TAGGED_INPUTS = (
    ("1", "CLIPTextEncode", "text", "a mossy brick wall", "str", str, "prompt", "Prompt"),
    ("2", "KSampler", "cfg", 1, "float", float, "auto", "CFG"),
    ("3", "KSampler", "steps", 20, "int", int, "auto", "Steps"),
    ("4", "PrimitiveBoolean", "value", True, "bool", bool, "auto", "Enabled"),
    ("5", "PrimitiveString", "value", "/RootNode/Looks/Material", "str", str, "texture_prim_path", "Texture Prim"),
    ("6", "PrimitiveString", "value", "/RootNode/meshes/Mesh", "str", str, "mesh_prim_path", "Mesh Prim"),
    ("7", "PrimitiveString", "value", "mod.usda", "str", str, "layer_identifier", "Layer Identifier"),
    ("8", "LoadImage", "image", "example.png", "str", str, "texture_file_path", "Input Texture"),
    ("10", "FutureNode", "value", "future", "str", str, "future_remix_type", "Future Remix Type"),
    ("11", "FutureNode", "value", ["1", 0], "future_primitive", str, "auto", "Future Primitive"),
    ("12", "FutureNode", "value", 3, "future_primitive", int, "auto", "Future Integer"),
)
_API_WORKFLOW = {
    node_id: {
        "inputs": {port: value},
        "class_type": class_type,
        "_meta": {
            "title": class_type,
            "rtx-remix": {
                "inputs": {
                    port: {
                        "name": label,
                        "type": type_str,
                        "remix_type": remix_type,
                        "order": order,
                        "additional_data": {},
                    }
                }
            },
        },
    }
    for order, (node_id, class_type, port, value, type_str, _native_type, remix_type, label) in enumerate(
        _TAGGED_INPUTS
    )
}
_API_WORKFLOW["9"] = {
    "inputs": {"images": ["8", 0], "filename_prefix": "node_pack_input_types"},
    "class_type": "SaveImage",
    "_meta": {
        "title": "Save Image",
        "rtx-remix": {
            "output": {
                "name": "Output Texture",
                "type": "str",
                "remix_type": "texture_file_path",
                "order": 0,
                "additional_data": {"texture_type": "albedo"},
            }
        },
    },
}
# ComfyUI writes the float 1.0 as the JSON integer 1, also in the active preset.
_FULL_WORKFLOW = {
    "extra": {
        "rtx-remix": {
            "presets": {"Default": {"inputs": {"2.cfg": {"value": 1}, "12.value": {"value": 4}}}},
            "activePreset": "Default",
        }
    }
}
_CATALOG = {
    "workflows": {
        "api": {"rtx-remix": [], "user": [{"name": _WORKFLOW_NAME, "displayName": _WORKFLOW_DISPLAY}]},
        "full": {"rtx-remix": [], "user": []},
    }
}
# HTTP responses by route, so the real client fetches and checks the exported workflow. Other routes get the catalog.
_RESPONSES = {
    f"{COMFYUI_WORKFLOWS_ROUTE}/api/user/{_WORKFLOW_NAME}": {"data": _API_WORKFLOW},
    f"{COMFYUI_WORKFLOWS_ROUTE}/full/user/{_WORKFLOW_NAME}": {"data": _FULL_WORKFLOW},
}


class TestNodePackInputTypesUIE2E(AsyncTestCase):
    """Exercise the real picker, input parser, and editor with node pack export metadata.

    The ComfyUI client receives fixture HTTP responses. This test does not cover the server or the HTTP transport.
    """

    def setUp(self) -> None:
        """Build a real core and workflow widget without a stage or job queue."""
        for started_patch in (
            patch.object(ComfyUIAPI, "ping", new=AsyncMock(return_value={})),
            patch.object(ComfyUIAPI, "get_workflow_types", new=AsyncMock(return_value=[])),
            patch.object(
                ComfyUIAPI,
                "_send_request",
                new=AsyncMock(side_effect=lambda _method, route, *_args, **_kwargs: _RESPONSES.get(route, _CATALOG)),
            ),
        ):
            started_patch.start()
            self.addCleanup(started_patch.stop)

        self._core = ComfyUICore("")
        self.addCleanup(self._core.destroy)
        self._window = ui.Window(type(self).__name__, visible=True, width=_WINDOW_WIDTH, height=_WINDOW_HEIGHT)
        self.addCleanup(self._window.destroy)
        with patch.object(widget, "get_comfyui_core_instance", return_value=self._core):
            with self._window.frame:
                self._widget = widget.WorkflowSetupWidget(context_name="")
        self.addCleanup(self._widget.destroy)

    async def test_pick_node_pack_workflow_shows_all_tagged_inputs_and_prompt_editor(self) -> None:
        """Keep all node pack input types in the tree and expose the Prompt text editor."""
        await self._core.connect()
        await ui_test.human_delay(5)

        # Select the exported workflow through the same catalog popup that the user opens.
        picker = ui_test.find(f"{self._window.title}//Frame/**/SectionedComboBox[*].identifier=='ComfyWorkflowPicker'")
        self.assertIsNotNone(picker)
        await picker.click()
        await ui_test.human_delay()
        entries = ui_test.find_all("SectionedComboPopup//Frame/**/Label[*].name=='SectionedComboItemLabel'")
        self.assertEqual([entry.widget.text for entry in entries], [_WORKFLOW_DISPLAY])
        await entries[0].click()
        await ui_test.human_delay(5)
        if self._widget._workflow_load_task is not None:
            await self._widget._workflow_load_task
        await ui_test.human_delay(5)

        # Every tagged input must appear, not just the previously supported texture file input.
        rows = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].identifier=='ComfyWorkflowItemName'")
        row_labels = [row.widget.text for row in rows]
        for *_, label in _TAGGED_INPUTS:
            self.assertIn(label, row_labels)

        workflow = self._core.workflow
        if workflow is None:
            self.fail("The picker did not load the exported workflow")
        inputs = {item.label: item for item in workflow.inputs}
        self.assertEqual(set(inputs), {label for *_, label in _TAGGED_INPUTS})
        for *_, native_type, remix_type, label in _TAGGED_INPUTS:
            with self.subTest(input_label=label):
                workflow_input = inputs[label]
                if remix_type == "texture_file_path":
                    self.assertIs(type(workflow_input.value), SelectedTextureResolver)
                    self.assertIs(workflow_input.remix_type, RemixType.TEXTURE_FILE_PATH)
                else:
                    self.assertIs(type(workflow_input.value), ConstantResolver)
                    self.assertIs(workflow_input.value.value_type, native_type)
                    self.assertIs(workflow_input.native_type, native_type)
                    self.assertIsNone(workflow_input.remix_type)
        self.assertEqual(inputs["CFG"].value.value, 1.0)
        self.assertEqual(inputs["Future Integer"].value.value, 4)

        # Open Prompt to prove that its default getter supplies a native string editor.
        await next(row for row in rows if row.widget.text == "Prompt").click()
        await ui_test.human_delay()
        self.assertIsNotNone(
            ui_test.find(f"{self._window.title}//Frame/**/StringField[*].identifier=='NativePropertyValue'")
        )
        property_labels = ui_test.find_all(f"{self._window.title}//Frame/**/Label[*].name=='PropertiesWidgetLabel'")
        self.assertIn("Text Constant", [label.widget.text for label in property_labels])
