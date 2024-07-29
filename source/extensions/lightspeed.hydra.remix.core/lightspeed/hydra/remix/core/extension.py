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
import ctypes
from enum import Enum
from typing import Tuple

import carb
import lightspeed.hydra.remix.core.extern as extern
import omni.ext
import omni.usd
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog

CARB_SETTING_SHOW_REMIX_SUPPORT_POPUP = "exts/lightspeed/hydra/remix/showpopup"


class RemixSupport(Enum):
    WAITING_FOR_INIT = -1
    NOT_SUPPORTED = 0
    SUPPORTED = 1


hdremix_issupported = RemixSupport.WAITING_FOR_INIT
hdremix_errormessage = "<HdRemixFinalizer.check_support was not called>"


def is_remix_supported() -> Tuple[RemixSupport, str]:
    return (hdremix_issupported, hdremix_errormessage)


class HdRemixFinalizer(omni.ext.IExt):
    """Request if Remix is supported"""

    # Do not call more than once, as it's a heavy operation.
    # Cache the value for frequent use.
    def check_support(self) -> Tuple[RemixSupport, str]:
        """Request HdRemix about support."""
        try:
            dll = ctypes.cdll.LoadLibrary("HdRemix.dll")
        except FileNotFoundError:
            msg = "HdRemix.dll is not loaded into the process."
            carb.log_warn(msg + " Retrying LoadLibrary...")
            return (RemixSupport.WAITING_FOR_INIT, msg)

        if not hasattr(dll, "hdremix_issupported"):
            msg = "HdRemix.dll doesn't have 'hdremix_issupported' function.\nAssuming that Remix is not supported."
            carb.log_error(msg)
            return (RemixSupport.NOT_SUPPORTED, msg)

        pfn_issupported = dll.hdremix_issupported
        pfn_issupported.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        pfn_issupported.restype = ctypes.c_int

        out_errormessage_cstr = ctypes.c_char_p("".encode("utf-8"))
        ok = pfn_issupported(ctypes.pointer(out_errormessage_cstr))

        if ok != 1:
            # pylint: disable=no-member
            if out_errormessage_cstr and out_errormessage_cstr.value:
                msg = out_errormessage_cstr.value.decode("utf-8")
            else:
                msg = "Remix error occurred, but no message" if ok == 0 else "Remix is being initialized..."
            if ok == -1:
                return (RemixSupport.WAITING_FOR_INIT, msg)
            carb.log_error(msg)
            return (RemixSupport.NOT_SUPPORTED, msg)
        return (RemixSupport.SUPPORTED, "Success")

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.hydra.remix.core] Startup")
        asyncio.ensure_future(self.__check_support())

    @omni.usd.handle_exception
    async def __check_support(self):
        frames_passed = 0
        timeout = 500

        # set global vars
        global hdremix_issupported, hdremix_errormessage

        # busy wait until Remix has been initialized
        while hdremix_issupported == RemixSupport.WAITING_FOR_INIT:
            hdremix_issupported, hdremix_errormessage = self.check_support()
            await omni.kit.app.get_app().next_update_async()
            frames_passed += 1
            if frames_passed > timeout:
                hdremix_issupported = RemixSupport.NOT_SUPPORTED
                hdremix_errormessage = "Remix initialization timeout"
                return

        if hdremix_issupported == RemixSupport.SUPPORTED:
            extern.remix_extern_init()
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
            message=hdremix_errormessage,
            ok_label="Exit",
            ok_handler=exit_app,
            on_window_closed_fn=exit_app,
            disable_cancel_button=True,
        )

    def on_shutdown(self):
        carb.log_info("[lightspeed.hydra.remix.core] Shutdown")
        extern.remix_extern_destroy()
