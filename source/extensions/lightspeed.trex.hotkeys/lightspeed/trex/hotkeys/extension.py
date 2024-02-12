"""
* Copyright (c) 2023, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import carb
import omni.ext

from .app import create_global_hotkey_manager, destroy_global_hotkey_manager, register_global_hotkeys


class TrexHotkeysExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.hotkeys] Startup")
        create_global_hotkey_manager()
        register_global_hotkeys()

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.hotkeys] Shutdown")
        destroy_global_hotkey_manager()
