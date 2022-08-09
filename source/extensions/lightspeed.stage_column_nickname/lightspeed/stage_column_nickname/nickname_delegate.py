# Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
from typing import Optional

import omni.ui as ui
from lightspeed.common import constants
from omni.kit.widget.stage.abstract_stage_column_delegate import AbstractStageColumnDelegate, StageColumnItem
from omni.kit.widget.stage.usd_property_watch import UsdPropertyWatch, UsdPropertyWatchModel
from pxr import Sdf, UsdGeom, UsdShade


class UsdNicknameWatchModel(UsdPropertyWatchModel):
    """The value model that is reimplemented in Python to watch the visibility of the selection"""

    def __init__(self, stage, path):
        """
        ## Arguments:
            `stage`: USD Stage
            `path`: The full path to the watched property
        """
        UsdPropertyWatchModel.__init__(self, stage, path)
        if not self._path:
            self._path = path

    def get_value_as_string(self) -> str:
        """Reimplemented get string"""
        prop = self._get_prop()
        if prop:
            return prop.Get()
        return ""

    def set_value(self, value: str):
        """Reimplemented set string"""
        if self._path:
            prop = self._get_prop()
            if not prop:
                prim = self._get_stage().GetPrimAtPath(self._path.GetPrimPath())
                prop = prim.CreateAttribute(constants.LSS_NICKNAME, Sdf.ValueTypeNames.String)
            prop.Set(value)


class NicknameStageColumnDelegate(AbstractStageColumnDelegate):
    """The column delegate that represents the nickname column"""

    def __init__(self):
        super().__init__()
        self._nickname_watch: Optional[UsdPropertyWatch] = None

    def destroy(self):
        if self._nickname_watch:
            self._nickname_watch.destroy()
            self._nickname_watch = None

    @property
    def initial_width(self):
        """The width of the column"""
        return ui.Pixel(256)

    def build_header(self):
        """Build the header"""
        with ui.HStack():
            ui.Spacer()
            with ui.VStack(width=0):
                ui.Spacer()
                ui.Label("Nickname", name="nickname_column_label")
                ui.Spacer()
            ui.Spacer()

    def _on_label_click(self, label, field):
        label.visible = False
        field.visible = True

    async def build_widget(self, item: StageColumnItem):
        """Build the widget"""
        if not item or not item.stage:
            return

        prim = item.stage.GetPrimAtPath(item.path)
        if not prim or not prim.IsValid() or not (prim.IsA(UsdGeom.Xform) or (prim.IsA(UsdShade.Material))):
            return

        if self._nickname_watch is None:
            self._nickname_watch = UsdPropertyWatch(
                item.stage, constants.LSS_NICKNAME, model_type=UsdNicknameWatchModel
            )

        watch_model = self._nickname_watch.get_model(item.path)

        text = watch_model.get_value_as_string()
        if not text:
            text = "<Click to Set Nickname>"
        stack = ui.ZStack(height=20)
        with stack:
            ui.Spacer(width=1)
            label = ui.Label(text, width=0, name=text + "_label_name", style_type_name_override="TreeView.Item")
            string_field = ui.StringField(model=watch_model, name=text + "_label_name", visible=False)
            stack.set_mouse_pressed_fn(lambda x, y, b, _: self._on_label_click(label, string_field))
            # Min size
            ui.Spacer(width=1)
