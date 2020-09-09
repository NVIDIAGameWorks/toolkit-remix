# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import asyncio
import omni.ext
import carb.settings


class CreateSetupExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self):
        """ setup the window layout, menu, final configuration of the extensions etc """
        self._settings = carb.settings.get_settings()

    def on_shutdown(self):
        pass
