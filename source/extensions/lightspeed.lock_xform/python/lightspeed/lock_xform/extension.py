"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import carb
import omni.ext

from .core import LockXformCore

class LightspeedLockXform(omni.ext.IExt):
    """Extension used to manage locking (prevent editing) of transform-related attributes"""
        
    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.lock_xform] Lightspeed Lock Transform startup")
        self._core = LockXformCore()
        
    def on_shutdown(self):
        carb.log_info("[lightspeed.lock_xform] Lightspeed Lock Transform shutdown")
        # There's a weird race condition with stage closure if we don't explicitly do this before Core dtor
        self._core.unsubscribe_from_events()