# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import carb
import omni.ext

from .setup_ui import SetupUI as _SetupUI

_INSTANCE = None


def get_instance():
    return _INSTANCE


class ViewportMenuBarRenderExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed.trex.viewports.menubar.render] Startup")
        _INSTANCE = _SetupUI()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.viewports.menubar.render] Shutdown")
        global _INSTANCE
        if _INSTANCE:
            _INSTANCE.destroy()
        _INSTANCE = None
