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

from .my_name import MyName

_INSTANCE = None


def get_instance():
    """Expose the created instance of the tool"""
    return _INSTANCE


class MyNameExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super(MyNameExtension, self).__init__(*args, **kwargs)
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed_example.my_name] startup")
        _INSTANCE = MyName()

    def on_shutdown(self):
        global _INSTANCE
        carb.log_info("[lightspeed_example.my_name] shutdown")
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
        _INSTANCE.destroy()
        _INSTANCE = None
