# Copyright (c) 2018-2020, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import omni.ext
from .kit_splash import KitSplash
import asyncio

class SetupSplashExtension(omni.ext.IExt):
    """"""

    def __init__(self):
        pass

    async def __few_frame_rendered(self):
        for i in range(5):
            await omni.kit.app.get_app().next_update_async()
        
        self._splash.stop()

    def on_startup(self, ext_id):
        self._splash = KitSplash()
        self._splash.start()

        self.__close_splash = asyncio.ensure_future(self.__few_frame_rendered())

    def on_shutdown(self):
        pass
