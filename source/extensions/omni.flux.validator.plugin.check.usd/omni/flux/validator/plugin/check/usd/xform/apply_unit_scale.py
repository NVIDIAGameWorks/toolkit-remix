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

from functools import partial
from typing import Any, Tuple

import omni.ui as ui
import omni.usd
from omni.flux.info_icon.widget import InfoIconWidget as _InfoIconWidget
from omni.flux.validator.factory import SetupDataTypeVar as _SetupDataTypeVar
from pxr import UsdGeom
from pydantic import Field, field_validator

from ..base.check_base_usd import CheckBaseUSD as _CheckBaseUSD  # noqa PLE0402


class ApplyUnitScale(_CheckBaseUSD):
    DEFAULT_UI_WIDTH_PIXEL = 120

    _METADATA_KEY = "metersPerUnit"

    class Data(_CheckBaseUSD.Data):
        scale_target: float = Field(default=1.0)

        @field_validator("scale_target", mode="before")
        @classmethod
        def non_zero_positive_number(cls, v: float) -> float:
            if v <= 0:
                raise ValueError("The target scale should be a non-zero positive number")
            return v

    name = "ApplyUnitScale"
    tooltip = "This plugin will apply the meshes' metersPerUnit scaling to their XForm scale."
    data_type = Data
    display_name = "Apply Unit Scale to Mesh"

    def __init__(self):
        super().__init__()

        self._unit_scale_field_validate_sub = None

    @omni.usd.handle_exception
    async def _check(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to check the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns:
            bool: True if the check passed, False if not. If the check is True, it will NOT run the fix
            str: the message you want to show, like "Succeeded to check this"
            any: data that you want to pass. For now this is used no where. So you can pass whatever you want (None)
        """
        message = "Check:\n"
        progress = 0
        success = True

        self.on_progress(progress, "Start", success)

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        meters_per_unit = stage.GetMetadata(self._METADATA_KEY)
        if not meters_per_unit:
            message += "- SKIPPED: Unable to get the layer's unit scale"
            return True, message, None

        is_valid = meters_per_unit == (1 / schema_data.scale_target)
        message += (
            "- OK: Layer is using the appropriate unit scale"
            if is_valid
            else "- INVALID: Layer scale needs to be applied to the asset"
        )

        return is_valid, message, None

    @omni.usd.handle_exception
    async def _fix(
        self, schema_data: Data, context_plugin_data: _SetupDataTypeVar, selector_plugin_data: Any
    ) -> Tuple[bool, str, Any]:
        """
        Function that will be executed to fix the data

        Args:
            schema_data: the data from the schema.
            context_plugin_data: the data from the context plugin
            selector_plugin_data: the data from the selector plugin

        Returns: True if the data where fixed, False if not
        """
        message = "Fix:\n"
        progress = 0

        self.on_progress(progress, "Start", True)

        stage = omni.usd.get_context(context_plugin_data).get_stage()
        meters_per_unit = stage.GetMetadata(self._METADATA_KEY)

        if selector_plugin_data:
            progress_delta = 1 / len(selector_plugin_data)
            for prim in selector_plugin_data:
                if not prim.IsA(UsdGeom.Xform):
                    progress_message = f"SKIPPED: {prim.GetPath()} is not an XForm prim"
                    message += f"- {progress_message}\n"
                    progress += progress_delta
                    self.on_progress(progress, progress_message, True)
                    continue

                xform = UsdGeom.Xformable(prim)
                xform_ops = xform.GetOrderedXformOps()
                for xform_op in xform_ops:
                    if xform_op.GetOpType() != UsdGeom.XformOp.TypeScale:
                        continue
                    xform_op.Set(xform_op.Get() * (schema_data.scale_target / meters_per_unit))

                progress_message = f"FIXED: {prim.GetPath()}"
                message += f"- {progress_message}\n"
                progress += progress_delta
                self.on_progress(progress, progress_message, True)

        stage.SetMetadata(self._METADATA_KEY, 1 / schema_data.scale_target)
        message += "- FIXED: Updated layer unit scale\n"

        return True, message, None

    def _on_unit_scale_field_edit_end(self, schema_data: Data, model):
        try:
            schema_data.scale_target = model.get_value_as_float()
        except ValueError:
            model.set_value(schema_data.scale_target)

    @omni.usd.handle_exception
    async def _mass_build_ui(self, schema_data: Data) -> Any:
        """
        Build the mass UI of a plugin. A mass UI is a UI that will expose some UI for mass processing. Mass processing
        will call multiple validation core. So this UI exposes controllers that will be passed to each schema.

        Args:
            schema_data: the data of the plugin from the schema

        Returns:
            Anything from the implementation
        """
        await self._build_ui(schema_data)

    @omni.usd.handle_exception
    async def _build_ui(self, schema_data: Data) -> Any:
        """
        Build the UI for the plugin
        """
        with ui.VStack():
            with ui.HStack():
                with ui.HStack(width=ui.Pixel(self.DEFAULT_UI_WIDTH_PIXEL)):
                    ui.Spacer()
                    ui.Label("Asset Scale Factor", width=0, name="PropertiesWidgetLabel")
                ui.Spacer(height=0, width=ui.Pixel(8))
                unit_scale_field = ui.StringField()

                unit_scale_field.model.set_value(schema_data.scale_target)
                self._unit_scale_field_validate_sub = unit_scale_field.model.subscribe_end_edit_fn(
                    partial(self._on_unit_scale_field_edit_end, schema_data)
                )
                ui.Spacer(width=ui.Pixel(8))
                with ui.VStack(width=0):
                    ui.Spacer(width=0)
                    _InfoIconWidget(
                        "This plugin will apply the given scale to a wrapping `XForm` prim on the ingested asset.\n\n"
                        "Larger values will increase the size of the ingested asset.\n\n"
                        "Example:\n"
                        "If your project is using 1 unit equal to 1 meter, but your asset is using 1 unit equal to 1 "
                        "centimeter,\n"
                        "then a scale factor of 100 will bring the asset in at the appropriate size."
                    )
                    ui.Spacer(width=0)

    def destroy(self):
        self._unit_scale_field_validate_sub = None
