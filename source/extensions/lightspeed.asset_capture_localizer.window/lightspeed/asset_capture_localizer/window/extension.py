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
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .setup_ui import AssetCaptureLocalizerWindow

_INSTANCE = None


def get_instance():
    """Expose the created instance of the tool"""
    return _INSTANCE


class AssetCaptureLocalizerExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed.asset_capture_localizer.window] startup")
        _INSTANCE = AssetCaptureLocalizerWindow()

    def on_shutdown(self):
        global _INSTANCE
        _reset_default_attrs(self)
        _INSTANCE.destroy()
        _INSTANCE = None
