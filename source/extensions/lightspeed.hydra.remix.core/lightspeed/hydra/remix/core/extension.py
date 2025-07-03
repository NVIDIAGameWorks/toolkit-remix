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

import asyncio

import carb
import lightspeed.hydra.remix.core.extern as extern
import omni.ext
import omni.usd
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog

CARB_SETTING_SHOW_REMIX_SUPPORT_POPUP = "exts/lightspeed/hydra/remix/showpopup"


class HdRemixFinalizer(omni.ext.IExt):
    """Loads HdRemix.dll early and shows whether Remix is supported"""

    # Do not call more than once, as it's a heavy operation.
    # Cache the value for frequent use.
    @omni.usd.handle_exception
    async def _check_support(self):
        frames_passed = await extern.load_remix_extern_async()

        hdremix_support_level, hdremix_error_message = extern.is_remix_supported()
        if hdremix_support_level == extern.RemixSupport.SUPPORTED:
            return

        if not carb.settings.get_settings().get_as_bool(CARB_SETTING_SHOW_REMIX_SUPPORT_POPUP):
            return

        # wait until we fully composed a window, so it's centered...
        for _ in range(frames_passed, 10):
            await omni.kit.app.get_app().next_update_async()

        def exit_app():
            omni.kit.app.get_app().post_quit(0)

        self._dialog = _TrexMessageDialog(
            title="RTX Remix Renderer failed to initialize",
            message=hdremix_error_message,
            ok_label="Exit",
            ok_handler=exit_app,
            on_window_closed_fn=exit_app,
            disable_cancel_button=True,
        )

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.hydra.remix.core] Startup")
        asyncio.ensure_future(self._check_support())

    def on_shutdown(self):
        carb.log_info("[lightspeed.hydra.remix.core] Shutdown")
        extern.remix_extern_destroy()
