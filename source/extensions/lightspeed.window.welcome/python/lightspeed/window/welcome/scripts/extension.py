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
import omni.kit.app

from .ui import WelcomeWindow


class WelcomeWindowExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super(WelcomeWindowExtension, self).__init__(*args, **kwargs)
        self.default_attr = {"_window": None}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.window.welcome] Lightspeed Welcome Window startup")
        extension_path = omni.kit.app.get_app().get_extension_manager().get_extension_path(ext_id)
        self._window = WelcomeWindow(extension_path)

    def on_shutdown(self):
        carb.log_info("[lightspeed.window.welcome] Lightspeed Welcome Window shutdown")
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
