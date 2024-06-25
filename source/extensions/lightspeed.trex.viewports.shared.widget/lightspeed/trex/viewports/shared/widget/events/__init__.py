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
