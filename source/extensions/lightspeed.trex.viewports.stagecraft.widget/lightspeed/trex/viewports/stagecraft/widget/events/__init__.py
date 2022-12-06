# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
__all__ = ["ViewportEventDelegate", "add_event_delegation", "remove_event_delegation", "set_ui_delegate"]

import traceback

import carb

from .delegate import ViewportEventDelegate

_ui_delegate_setup = ViewportEventDelegate
_ui_delegate_list = []


def add_event_delegation(scene_view, viewport_api):
    global _ui_delegate_setup  # noqa
    if _ui_delegate_setup:
        delegate = _ui_delegate_setup(scene_view, viewport_api)
        if delegate:
            _ui_delegate_list.append(delegate)


def remove_event_delegation(in_scene_view):
    global _ui_delegate_list
    new_delegate_list = []
    for delegate in _ui_delegate_list:
        scene_view = delegate.scene_view
        if delegate and scene_view != in_scene_view:
            new_delegate_list.append(delegate)
        elif delegate:
            delegate.destroy()
    _ui_delegate_list = new_delegate_list


def set_ui_delegate(ui_delegate_setup):
    global _ui_delegate_setup, _ui_delegate_list
    _ui_delegate_setup = ui_delegate_setup
    new_delegate_list = []
    if ui_delegate_setup:
        # Transfer all valid event handling to the new delegate
        for delegate in _ui_delegate_list:
            scene_view = delegate.scene_view
            viewport_api = delegate.viewport_api
            if scene_view and viewport_api:
                delegate = ui_delegate_setup(scene_view, viewport_api)
                if delegate:
                    new_delegate_list.append(delegate)

    # Destroy all of the old event delegates
    for delegate in _ui_delegate_list:
        try:
            delegate.destroy()
        except Exception:  # noqa
            carb.log_error(f"Traceback:\n{traceback.format_exc()}")

    _ui_delegate_list = new_delegate_list
