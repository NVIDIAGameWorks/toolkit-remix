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

from __future__ import annotations

import asyncio
import ctypes
import time
from enum import Enum
from typing import Callable

import carb
import omni.kit.app

_instance: None | RemixExtern = None
_GLOBAL_OBJECTPICKING_REQUEST_ID: int = 0


class RemixSupport(Enum):
    WAITING_FOR_INIT = -1
    NOT_SUPPORTED = 0
    SUPPORTED = 1


_hdremix_support_level: RemixSupport = RemixSupport.WAITING_FOR_INIT
_hdremix_error_message: str = "<HdRemixFinalizer.check_support was not called>"


def is_remix_supported() -> tuple[RemixSupport, str]:
    return (_hdremix_support_level, _hdremix_error_message)


def request_dict_push(request_dict: dict[int, tuple[int, Callable]], request_id: int, callback: Callable):
    """
    Adds or updates a reference-counted callback in the request dictionary.

    Works with request_dict_pop() to track callbacks by request_id. The count tracks
    how many active references exist to a request_id to ensure we retain the latest callback if a
    request is outstanding.
    """
    pre_existing = request_dict.get(request_id)
    if pre_existing is None:
        count = 0
    else:
        count, stored_callback = pre_existing
        if stored_callback != callback:
            carb.log_warn(
                f"request_dict_push: Trying to push a new key-value pair: key={str(request_id)} already exists, "
                "so expecting existing value to match the value that is being added, "
                "however they mismatch. Overwriting the old one."
            )
            count = 0

    request_dict[request_id] = (count + 1, callback)


def request_dict_pop(request_dict: dict[int, tuple[int, Callable]], request_id: int) -> Callable | None:
    """
    Pops a callback from the request dictionary.

    Works with request_dict_push().
    """
    found = request_dict.get(request_id)
    if found:
        count, callback = found
        if count > 1:
            request_dict[request_id] = (count - 1, callback)
        else:
            request_dict.pop(request_id)
        return callback
    return None


class RemixExtern:

    # expected dll functions
    required_functions: list[str] = [
        "findworldposition_setcallback",
        "findworldposition_request",
        "objectpicking_highlight",
        "objectpicking_request",
        "objectpicking_setcallback_oncomplete",
        "hdremix_setconfigvariable",
    ]

    def __init__(self):
        self.__c_objectpicking_request = None
        self.__c_findworldposition_request = None
        self.__c_objectpicking_highlight = None
        self.__c_hdremix_setconfigvariable = None

        self.__dll = RemixExtern.__load_dll()
        if self.__dll is None:
            return

        #
        # register C functions from the DLL
        #

        # void findworldposition_request( int request_id, int x, int y )
        self.__c_findworldposition_request = self.__dll.findworldposition_request
        self.__c_findworldposition_request.argtypes = (ctypes.c_int32, ctypes.c_int32, ctypes.c_int32)
        self.__c_findworldposition_request.restype = None

        # void objectpicking_request(uint32_t x0, uint32_t y0, uint32_t x1, uint32_t y1)
        self.__c_objectpicking_request = self.__dll.objectpicking_request
        self.__c_objectpicking_request.argtypes = (ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32)
        self.__c_objectpicking_request.restype = None

        # void objectpicking_highlight( const char **, uint32_t )
        self.__c_objectpicking_highlight = self.__dll.objectpicking_highlight
        self.__c_objectpicking_highlight.argtypes = (ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint32)
        self.__c_objectpicking_highlight.restype = None

        # void hdremix_setconfigvariable( const char *, const char * )
        self.__c_hdremix_setconfigvariable = self.__dll.hdremix_setconfigvariable
        self.__c_hdremix_setconfigvariable.argtypes = (ctypes.c_char_p, ctypes.c_char_p)
        self.__c_hdremix_setconfigvariable.restype = None

        #
        # register C->Python callbacks, need to keep references alive
        #

        # callback begin: find world position
        self.__pywrap_findworldposition_oncomplete_t = ctypes.CFUNCTYPE(
            None, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32, ctypes.c_float, ctypes.c_float, ctypes.c_float
        )
        self.__pywrap_findworldposition_oncomplete = self.__pywrap_findworldposition_oncomplete_t(
            RemixExtern.__c_findworldposition_oncomplete
        )
        self.__dll.findworldposition_setcallback(self.__pywrap_findworldposition_oncomplete)
        # callback end

        # callback begin: object picking
        self.__pywrap_objectpicking_oncomplete_t = ctypes.CFUNCTYPE(
            None, ctypes.POINTER(ctypes.c_char_p), ctypes.c_uint32
        )
        self.__pywrap_objectpicking_oncomplete = self.__pywrap_objectpicking_oncomplete_t(
            RemixExtern.__c_objectpicking_oncomplete
        )
        self.__dll.objectpicking_setcallback_oncomplete(self.__pywrap_objectpicking_oncomplete)
        # callback end

        #

        # dict to track findworldposition / objectpicking request callbacks
        self.__requestdict_findworldposition: dict[int, tuple[int, Callable]] = {}
        self.__requestdict_objectpicking: dict[int, tuple[int, Callable]] = {}

    @staticmethod
    def check_support() -> tuple[RemixSupport, str]:
        """Try to load HdRemix and see if it is supported."""
        try:
            dll = ctypes.cdll.LoadLibrary("HdRemix.dll")
        except FileNotFoundError:
            return RemixSupport.WAITING_FOR_INIT, "HdRemix.dll is not loaded into the process yet."

        if not hasattr(dll, "hdremix_issupported"):
            msg = "HdRemix.dll doesn't have 'hdremix_issupported' function.\nAssuming that Remix is not supported."
            carb.log_error(msg)
            return RemixSupport.NOT_SUPPORTED, msg

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
                return RemixSupport.WAITING_FOR_INIT, msg
            carb.log_error(msg)
            return RemixSupport.NOT_SUPPORTED, msg

        carb.log_info("HdRemix.dll loaded.")
        return RemixSupport.SUPPORTED, "Success"

    @classmethod
    def __load_dll(cls):
        try:
            dll = ctypes.cdll.LoadLibrary("HdRemix.dll")
        except FileNotFoundError:
            carb.log_warn("Failed to find HdRemix.dll. Object picking, highlighting are disabled")
            return None

        if not all(hasattr(dll, func) for func in cls.required_functions):
            carb.log_warn(
                "HdRemix.dll doesn't contain the required functions. Object picking and highlighting are disabled"
            )
            return None
        return dll

    def findworldposition_request(
        self, pix_x: int, pix_y: int, callback: Callable[[int, int, float, float, float], None], request_id: int
    ):
        if self.__c_findworldposition_request is None:
            carb.log_error(
                "findworldposition_request fail: Couldn't load HdRemix.dll, "
                "or couldn't find 'findworldposition_request' function in it"
            )
            return
        self.__c_findworldposition_request(request_id, pix_x, pix_y)
        # save callback
        request_dict_push(self.__requestdict_findworldposition, request_id, callback)

    # Called by HdRemix, when find world position request has been completed
    def findworldposition_oncomplete(
        self, request_id: int, pix_x: int, pix_y: int, world_x: float, world_y: float, world_z: float
    ):
        callback = request_dict_pop(self.__requestdict_findworldposition, request_id)
        if callback is not None:
            callback(pix_x, pix_y, world_x, world_y, world_z)

    def objectpicking_request(
        self, x0: int, y0: int, x1: int, y1: int, callback: Callable[[list[str]], None], request_id: int
    ):
        if self.__c_objectpicking_request is None:
            carb.log_error(
                "objectpicking_request fail: Couldn't load HdRemix.dll, "
                "or couldn't find 'objectpicking_request' function in it"
            )
            return
        self.__c_objectpicking_request(x0, y0, x1, y1)
        # save callback
        request_dict_push(self.__requestdict_objectpicking, request_id, callback)

    # Called by HdRemix, when object picking request has been completed
    def objectpicking_oncomplete(self, request_id: int, selected_paths: set[str]):
        callback = request_dict_pop(self.__requestdict_objectpicking, request_id)
        if callback is not None:
            callback(selected_paths)

    def highlight_paths(self, paths: list[str]):
        if self.__c_objectpicking_highlight is None:
            carb.log_error(
                "highlight_paths fail: Couldn't load HdRemix.dll, or couldn't find 'highlight_paths' function in it"
            )
            return
        # allocate const char*[], so C function can fill it
        c_string_array = (ctypes.c_char_p * len(paths))(*[p.encode("utf-8") for p in paths])
        self.__c_objectpicking_highlight(c_string_array, len(c_string_array))

    def set_configvar(self, key: str, value: str):
        if self.__c_hdremix_setconfigvariable is None:
            carb.log_error(
                "set_configvar fail: Couldn't load HdRemix.dll, or "
                "couldn't find 'hdremix_setconfigvariable' function in it"
            )
            return
        c_key = key.encode("utf-8")
        c_value = value.encode("utf-8")
        self.__c_hdremix_setconfigvariable(c_key, c_value)

    # Called by HdRemix, when find world position request has been completed
    @staticmethod
    def __c_findworldposition_oncomplete(
        request_id: int, pix_x: int, pix_y: int, world_x: float, world_y: float, world_z: float
    ):
        if _instance is None:
            return
        _instance.findworldposition_oncomplete(request_id, pix_x, pix_y, world_x, world_y, world_z)

    # Called by HdRemix, when object picking request has been completed
    @staticmethod
    def __c_objectpicking_oncomplete(selectedpaths_cstr_values, selectedpaths_cstr_count):
        if _instance is None:
            return
        cstr_array = ctypes.cast(
            selectedpaths_cstr_values, ctypes.POINTER(ctypes.c_char_p * selectedpaths_cstr_count)
        ).contents
        selected_paths = set()
        for i in range(selectedpaths_cstr_count):
            selected_paths.add(cstr_array[i].decode("utf-8"))
        _instance.objectpicking_oncomplete(_GLOBAL_OBJECTPICKING_REQUEST_ID, selected_paths)


async def _load_remix_extern_impl(is_async: bool) -> int:
    """Implementation shared between sync and async versions of load_remix_extern."""
    frames_passed = 0
    timeout = 500

    # set global vars
    global _hdremix_support_level, _hdremix_error_message

    # busy wait until Remix has been initialized
    carb.log_info(r"Loading HdRemix.dll with ctypes.cdll.LoadLibrary(\"HdRemix.dll\")...")
    while _hdremix_support_level == RemixSupport.WAITING_FOR_INIT:
        _hdremix_support_level, _hdremix_error_message = RemixExtern.check_support()

        if is_async:
            await omni.kit.app.get_app().next_update_async()
        else:
            time.sleep(0.05)

        frames_passed += 1
        if frames_passed > timeout:
            _hdremix_support_level = RemixSupport.NOT_SUPPORTED
            _hdremix_error_message = f"Remix initialization timeout{' (async)' if is_async else ''}"
            carb.log_error(_hdremix_error_message)
            break
        if _hdremix_support_level == RemixSupport.WAITING_FOR_INIT:
            carb.log_info(f"{_hdremix_error_message}. Will Retry.")

    remix_extern_init()

    return frames_passed


async def load_remix_extern_async() -> int:
    """Function to trigger loading the HdRemix.dll with a timeout."""
    return await _load_remix_extern_impl(is_async=True)


def load_remix_extern() -> int:
    """Blocking function to trigger loading the HdRemix.dll with a timeout."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No event loop running, safe to create one
        return asyncio.run(_load_remix_extern_impl(is_async=False))
    raise RuntimeError(
        "Cannot call load_remix_extern() from within a running event loop. Use load_remix_extern_async() instead."
    )


def remix_extern_init():
    global _instance

    if not _instance:
        _instance = RemixExtern()


def remix_extern_destroy():
    global _instance
    _instance = None


def safe_remix_extern() -> RemixExtern:
    """Function to call if a RemixExtern is required. If not loaded yet, it will block until loaded."""
    global _instance  # noqa PLW0602 - required to get updated value after load

    if not _instance:
        load_remix_extern()
    assert _instance, "load_remix_extern() should have set _instance"
    return _instance


# Function ID to signed int32
def __callbackid_int32(callback: Callable, pix_x: int, pix_y: int) -> int:
    # incorporate pixel to increase chances of a unique request id
    return hash(id(callback) + 10 * pix_x + pix_y) & 0x7FFFFFFF


# callback( pix_x, pix_y, worldpos_x, worldpos_y, worldpos_z )
def hdremix_findworldposition_request(
    pix_x: int, pix_y: int, callback: Callable[[int, int, float, float, float], None]
):
    safe_remix_extern().findworldposition_request(pix_x, pix_y, callback, __callbackid_int32(callback, pix_x, pix_y))


# callback( set_of_selected_usd_paths )
def hdremix_objectpicking_request(x0: int, y0: int, x1: int, y1: int, callback: Callable[[list[str]], None]):
    safe_remix_extern().objectpicking_request(x0, y0, x1, y1, callback, _GLOBAL_OBJECTPICKING_REQUEST_ID)


def hdremix_highlight_paths(paths: list[str]) -> None:
    safe_remix_extern().highlight_paths(paths)


# Directly set RtxOption of the Remix Renderer.
# Usage example: hdremix_set_configvar("rtx.fallbackLightType", "1")
# For the list of available options, see:
# https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/RtxOptions.md
def hdremix_set_configvar(key: str, value: str) -> None:
    safe_remix_extern().set_configvar(key, value)


class RemixRequestQueryType(Enum):
    PATH_AND_WORLDPOS = 0
    ONLY_WORLDPOS = 1
    ONLY_PATH = 2


# Compatibility function to replace viewport_api.request_query()
# callback( path, worldpos, pixel )
def viewport_api_request_query_hdremix(
    pixel: carb.Uint2,
    callback: Callable[[str, carb.Double3 | None, carb.Uint2], None] = None,
    query_name: str = "",
    request_query_type=RemixRequestQueryType.PATH_AND_WORLDPOS,
):
    if request_query_type == RemixRequestQueryType.ONLY_WORLDPOS:

        def get_only_worldpos(pix_x: int, pix_y: int, worldpos_x, worldpos_y, worldpos_z):
            callback("", carb.Double3(worldpos_x, worldpos_y, worldpos_z), carb.Uint2(pix_x, pix_y))

        hdremix_findworldposition_request(pixel[0], pixel[1], get_only_worldpos)
    elif request_query_type == RemixRequestQueryType.ONLY_PATH:

        def get_only_path(set_of_selected_usd_paths):
            path = next(iter(set_of_selected_usd_paths)) if len(set_of_selected_usd_paths) > 0 else ""
            callback(path, None, carb.Uint2(pixel[0], pixel[1]))

        hdremix_objectpicking_request(pixel[0], pixel[1], pixel[0] + 1, pixel[1] + 1, get_only_path)
    else:

        def get_path(set_of_selected_usd_paths):
            def get_worldpos(pix_x: int, pix_y: int, worldpos_x, worldpos_y, worldpos_z):
                path = next(iter(set_of_selected_usd_paths)) if len(set_of_selected_usd_paths) > 0 else ""
                worldpos = carb.Double3(worldpos_x, worldpos_y, worldpos_z) if path else None
                callback(path, worldpos, carb.Uint2(pix_x, pix_y))

            hdremix_findworldposition_request(pixel[0], pixel[1], get_worldpos)

        hdremix_objectpicking_request(pixel[0], pixel[1], pixel[0] + 1, pixel[1] + 1, get_path)
