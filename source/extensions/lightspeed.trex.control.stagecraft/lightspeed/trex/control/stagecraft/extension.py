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

from .setup import Setup


class TrexStageCraftControlExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self):
        self._setup = None

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.control.stagecraft] Startup")
        self._setup = Setup()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.control.stagecraft] Shutdown")
        self._setup.destroy()
        self._setup = None
