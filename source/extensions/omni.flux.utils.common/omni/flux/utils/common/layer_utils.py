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

__all__ = ["FILE_DIALOG_EXTENSIONS", "create_layer", "save_layer_as", "validate_edit_target"]

import weakref
from collections.abc import Callable

import carb
import omni.kit
import omni.usd
from omni.kit.usd.layers import LayerUtils
from pxr import Sdf

# For CLIs, we don't want to import UI dependencies so this extension will not be available
try:
    import omni.kit.window.file

    _omni_kit_window_file_present = True
except ModuleNotFoundError:
    _omni_kit_window_file_present = False

FILE_DIALOG_EXTENSIONS = [
    ("*.usda", "Human-readable USD File"),
    ("*.usd", "Binary or Ascii USD File"),
    ("*.usdc", "Binary USD File"),
]


def create_layer(layer_identifier: str):
    layer = Sdf.Layer.FindOrOpen(layer_identifier)
    if layer:
        layer.Clear()
    else:
        layer = Sdf.Layer.CreateNew(layer_identifier)
    return layer


def save_layer_as(
    context_name: str,
    replace: bool,
    layer_weakref: weakref,
    parent_weakref: weakref,
    on_save_done: Callable[[bool, str, list[str]], None],
    file_path: str,
):
    """Save layer as new layer.

    Args:
        context_name: The context name.
        replace: After saving the layer, should it replace the current layer in the stage.
        layer_weakref: Weakref to the layer to be saved as.
        parent_weakref: Weakref to the parent of the layer to be saved as.
        on_save_done: Callback for when an error occurs or the file is saved successfully.
                      Parameters of the callback are: Success, ErrorMessage, LayerIdentifiers
        file_path: path to the new layer file to be saved
    """
    layer_ref = layer_weakref()
    if not layer_ref:
        return

    new_layer = create_layer(file_path)
    if not new_layer:
        carb.log_error(f"Save layer failed. Failed to create layer {file_path}")
        return
    new_layer.TransferContent(layer_ref)

    LayerUtils.resolve_paths(layer_ref, new_layer)
    LayerUtils.create_checkpoint(new_layer.identifier, "")

    if not new_layer.Save():
        if on_save_done:
            on_save_done(False, f"Save layer {layer_ref.identifier} failed.", [])
        return

    if not replace:
        if on_save_done:
            on_save_done(True, "", [new_layer.identifier])
        return

    if parent_weakref is None:
        # Root layer was changed, simply load it in the stage
        if _omni_kit_window_file_present:
            omni.kit.window.file.open_stage(new_layer.realPath)
        else:
            omni.usd.get_context(context_name).open_stage(new_layer.realPath)
    else:
        parent_ref = parent_weakref()
        position = LayerUtils.get_sublayer_position_in_parent(parent_ref.identifier, layer_ref.identifier)
        omni.kit.commands.execute(
            "ReplaceSublayer",
            layer_identifier=parent_ref.identifier,
            sublayer_position=position,
            new_layer_path=new_layer.realPath,
            usd_context=context_name,
        )

    validate_edit_target(context_name)

    if on_save_done:
        on_save_done(True, "", [new_layer.identifier])


def validate_edit_target(context_name: str):
    """
    Validate the edit target is in layer stack or session layer.
    """
    stage = omni.usd.get_context(context_name).get_stage()
    edit_target = stage.GetEditTarget()
    edit_target_identifier = LayerUtils.get_edit_target(stage)
    if (
        edit_target_identifier == stage.GetSessionLayer().identifier
        or edit_target.GetLayer() not in stage.GetLayerStack()
    ):
        LayerUtils.set_edit_target(stage, stage.GetRootLayer().identifier)
