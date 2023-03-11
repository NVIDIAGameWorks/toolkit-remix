"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.kit.app
import omni.ui as ui
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.validator.manager.widget import ValidatorManagerWidget as _ValidatorManagerWidget


class AssetValidationPane:
    def __init__(self, context_name: str):
        """Nvidia StageCraft Components Pane"""

        self._default_attr = {
            "_root_frame": None,
            "_asset_validation_collapsable_frame": None,
            "_validation_widget": None,
        }
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

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
                        # use default manager. Default manager will take the
                        # settings "omni.flux.validator.manager.widget.schema"
                        self._validation_widget = _ValidatorManagerWidget(use_global_style=True)
                    ui.Spacer(height=ui.Pixel(8))

    def show(self, value):
        self._root_frame.visible = value

    def destroy(self):
        _reset_default_attrs(self)