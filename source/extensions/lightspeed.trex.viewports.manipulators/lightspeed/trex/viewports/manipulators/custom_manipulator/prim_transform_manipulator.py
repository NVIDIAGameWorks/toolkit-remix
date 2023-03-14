# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
from typing import List, Optional

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
        transformable = self._core.filter_transformable_prims(selection)
        self._model.set_path_redirect(transformable)
        return bool(transformable)
