# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import re
from typing import List, Optional

from lightspeed.common import constants
from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from omni.kit.manipulator.prim.prim_transform_manipulator import PrimTransformManipulator as _PrimTransformManipulator
from pxr import Sdf, Usd


class PrimTransformManipulator(_PrimTransformManipulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._core = _AssetReplacementsCore(kwargs["usd_context_name"])

    def destroy(self):
        if self._core:
            self._core.destroy()
            self._core = None
        super().destroy()

    def on_selection_changed(self, stage: Usd.Stage, selection: Optional[List[Sdf.Path]], *args, **kwargs) -> bool:
        """
        Be default when the user click, it can't move anything. It will need to click on the reference on the
        selection panel to enable the manipulator
        """
        super().on_selection_changed(stage, selection, *args, **kwargs)

        new_prim_paths = []
        regex_in_instance = re.compile(constants.REGEX_IN_INSTANCE_PATH)
        regex_light_pattern = re.compile(constants.REGEX_LIGHT_PATH)
        for path in selection:
            prim = stage.GetPrimAtPath(path)
            if not self._core.filter_xformable_prims([prim]):
                continue
            if regex_light_pattern.match(prim.GetName()):
                # if this is a light instance, we add it. We can move light instance directly
                new_prim_paths.append(str(path))
                continue
            if regex_in_instance.match(str(prim.GetPath())):
                # enable the transform manip only for lights and prim in instances (and light instance)
                # we don't allow moving prim in mesh directly, a prim in an instance has to be selected
                # we don't allow moving an instance directly
                if self._core.prim_is_from_a_capture_reference(prim):
                    # prim from capture can't be moved
                    continue
                corresponding_paths = self._core.get_corresponding_prototype_prims([prim])
                if corresponding_paths:
                    new_prim_paths.extend(corresponding_paths)
        self._model.set_path_redirect(new_prim_paths)
        return bool(new_prim_paths)
