"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.path_utils import read_json_file as _read_json_file
from omni.flux.validator.manager.core import ManagerCore
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget


class AssetValidationPane:
    def __init__(self, context_name: str, schema_path: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_schema": None,
            "_context": None,
            "_root_frame": None,
            "_asset_validation_collapsable_frame": None,
            "_validation_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

        self._schema = _read_json_file(carb.tokens.get_tokens_interface().resolve(schema_path))
        self._context = omni.usd.get_context(context_name)

        self.__create_ui()

    def __create_ui(self):
        self._root_frame = ui.Frame()
        with self._root_frame:
            with ui.ScrollingFrame(
                name="PropertiesPaneSection",
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_ALWAYS_OFF,
            ):
                with ui.VStack():
                    ui.Spacer(height=ui.Pixel(24))
                    with ui.HStack():
                        ui.Spacer(width=ui.Pixel(8))
                        self._validation_widget = _ValidatorManagerWidget(
                            core=ManagerCore(self._schema), use_global_style=True
                        )
                    ui.Spacer(height=ui.Pixel(8))

    def show(self, value):
        self._root_frame.visible = value
        if value:
            self._validation_widget.refresh()

    def destroy(self):
        _reset_default_attrs(self)
