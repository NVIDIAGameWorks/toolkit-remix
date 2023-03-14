# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import carb
import carb.settings
import omni.ext

from .setup_ui import SetupUI

_SETUP_INSTANCE = None


def get_instance():
    return _SETUP_INSTANCE


class TrexStageCraftLayoutExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.menu.workfile] Startup")

        _SETUP_INSTANCE = SetupUI()

    def on_shutdown(self):
        global _SETUP_INSTANCE
        carb.log_info("[lightspeed.trex.menu.workfile] Shutdown")
        if _SETUP_INSTANCE:
            _SETUP_INSTANCE.destroy()
        _SETUP_INSTANCE = None
