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
from lightspeed.events_manager.core import EVENTS_MANAGER_INSTANCE as _EVENTS_MANAGER_INSTANCE

from .core import EventSaveRecentCore


class EventSaveRecentExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {"_core": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    # noinspection PyUnusedLocal
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.event.save_recent] Lightspeed Event Save Recent startup")
        self._core = EventSaveRecentCore()
        _EVENTS_MANAGER_INSTANCE.register_event(self._core)

    def on_shutdown(self):
        carb.log_info("[lightspeed.event.save_recent] Lightspeed Events Save Recent shutdown")
        _EVENTS_MANAGER_INSTANCE.unregister_event(self._core)
        for attr, value in self.default_attr.items():
            m_attr = getattr(self, attr)
            if isinstance(m_attr, list):
                m_attrs = m_attr
            else:
                m_attrs = [m_attr]
            for m_attr in m_attrs:
                destroy = getattr(m_attr, "destroy", None)
                if callable(destroy):
                    destroy()
                del m_attr
                setattr(self, attr, value)
