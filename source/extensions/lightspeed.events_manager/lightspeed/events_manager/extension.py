"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Optional

import carb
import omni.ext
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .core import EventsManagerCore as _EventsManagerCore

_EVENTS_MANAGER_INSTANCE = None


def get_instance() -> Optional[_EventsManagerCore]:
    return _EVENTS_MANAGER_INSTANCE


class EventsManagerExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {"_events_manager": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    # noinspection PyUnusedLocal
    def on_startup(self, ext_id):
        global _EVENTS_MANAGER_INSTANCE
        carb.log_info("[lightspeed.events_manager] Lightspeed Events Manager startup")
        self._events_manager = _EventsManagerCore()
        _EVENTS_MANAGER_INSTANCE = self._events_manager

    def on_shutdown(self):
        global _EVENTS_MANAGER_INSTANCE
        carb.log_info("[lightspeed.events_manager] Lightspeed Events Manager shutdown")
        _reset_default_attrs(self)
        _EVENTS_MANAGER_INSTANCE = None
