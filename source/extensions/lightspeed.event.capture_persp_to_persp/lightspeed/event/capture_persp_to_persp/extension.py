"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.ext
from lightspeed.events_manager.core import EVENTS_MANAGER_INSTANCE as _EVENTS_MANAGER_INSTANCE
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .core import CopyCapturePerspToPerspCore as _CopyCapturePerspToPerspCore


class EventCopyCapturePerspToPerspExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {"_core": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    # noinspection PyUnusedLocal
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.event.capture_persp_to_persp] Lightspeed Event Copy Capture Persp to Persp startup")
        self._core = _CopyCapturePerspToPerspCore()
        _EVENTS_MANAGER_INSTANCE.register_event(self._core)

    def on_shutdown(self):
        carb.log_info("[lightspeed.event.capture_persp_to_persp] Lightspeed Event Copy Capture Persp to Persp shutdown")
        _EVENTS_MANAGER_INSTANCE.unregister_event(self._core)
        _reset_default_attrs(self)
