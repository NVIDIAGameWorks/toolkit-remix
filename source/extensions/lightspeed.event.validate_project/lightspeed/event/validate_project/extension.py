"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import carb
import omni.ext
from lightspeed.events_manager import get_instance as _get_event_manager_instance
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .core import EventValidateProjectCore


class EventValidateProjectExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {"_core": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)
        self._core = None

    # noinspection PyUnusedLocal
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.event.validate_project] Lightspeed Event Validate Project startup")
        self._core = EventValidateProjectCore()
        _get_event_manager_instance().register_event(self._core)

    def on_shutdown(self):
        carb.log_info("[lightspeed.event.validate_project] Lightspeed Events Validate Project shutdown")
        _get_event_manager_instance().unregister_event(self._core)
        _reset_default_attrs(self)
