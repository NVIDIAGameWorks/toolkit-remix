# Copyright (c) 2024, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import asyncio
import ctypes

import carb
import omni.ext
from lightspeed.trex.utils.widget import TrexMessageDialog as _TrexMessageDialog

CARB_SETTING_SHOW_REMIX_SUPPORT_POPUP = "exts/lightspeed/hydra/remix/showpopup"


hdremix_issupported = False
hdremix_errormessage = "<HdRemixFinalizer.check_support was not called>"


def is_remix_supported() -> (bool, str):
    return (hdremix_issupported, hdremix_errormessage)


class HdRemixFinalizer(omni.ext.IExt):
    """Request if Remix is supported"""

    # Do not call more than once, as it's a heavy operation.
    # Cache the value for frequent use.
    def check_support(self) -> (bool, str):
        """Request HdRemix about support. This call is blocking, until HdRemix is fully initialized."""
        try:
            dll = ctypes.cdll.LoadLibrary("HdRemix.dll")
        except FileNotFoundError:
            msg = "Failed to load HdRemix.dll.\nAssuming that Remix is not supported."
            carb.log_error(msg)
            return (False, msg)

        if not hasattr(dll, "hdremix_issupported"):
            msg = "HdRemix.dll doesn't have 'hdremix_issupported' function.\nAssuming that Remix is not supported."
            carb.log_error(msg)
            return (False, msg)

        pfn_issupported = dll.hdremix_issupported
        pfn_issupported.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
        pfn_issupported.restype = ctypes.c_int

        out_errormessage_cstr = ctypes.c_char_p("".encode("utf-8"))
        ok = pfn_issupported(ctypes.pointer(out_errormessage_cstr))

        if ok == 0:
            # pylint: disable=no-member
            if out_errormessage_cstr and out_errormessage_cstr.value:
                msg = out_errormessage_cstr.value.decode("utf-8")
            else:
                msg = "Remix error occurred, but no message"
            carb.log_error(msg)
            return (False, msg)
        return (True, "Success")

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.hydra.remix] Startup")

        supported, errormsg = self.check_support()

        global hdremix_issupported, hdremix_errormessage
        hdremix_issupported = supported
        hdremix_errormessage = errormsg

        if not supported and carb.settings.get_settings().get_as_bool(CARB_SETTING_SHOW_REMIX_SUPPORT_POPUP):
            asyncio.ensure_future(self.__show_popup(errormsg))

    async def __show_popup(self, errormsg):
        # wait until we fully composed a window, so it's centered...
        for _ in range(10):
            await omni.kit.app.get_app().next_update_async()

        def exit_app():
            omni.kit.app.get_app().post_quit(0)

        self._dialog = _TrexMessageDialog(
            title="RTX Remix Renderer failed to initialize",
            message=errormsg,
            ok_label="Exit",
            ok_handler=exit_app,
            on_window_closed_fn=exit_app,
            disable_cancel_button=True,
        )

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.hydra.remix] Shutdown")
