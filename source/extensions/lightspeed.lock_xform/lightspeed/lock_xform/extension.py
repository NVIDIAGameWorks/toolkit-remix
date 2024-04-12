"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
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
