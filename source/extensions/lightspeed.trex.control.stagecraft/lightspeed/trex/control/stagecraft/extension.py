# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import carb
import carb.settings
import omni.ext

from .setup import Setup

# make accessible for tests
_stagecraft_control_instance: Setup | None = None


def _create_instance():
    global _stagecraft_control_instance
    _stagecraft_control_instance = Setup()
    return _stagecraft_control_instance


def get_instance():
    return _stagecraft_control_instance


class TrexStageCraftControlExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.control.stagecraft] Startup")
        _create_instance()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.control.stagecraft] Shutdown")
        global _stagecraft_control_instance
        if _stagecraft_control_instance:
            _stagecraft_control_instance.destroy()
        _stagecraft_control_instance = None
