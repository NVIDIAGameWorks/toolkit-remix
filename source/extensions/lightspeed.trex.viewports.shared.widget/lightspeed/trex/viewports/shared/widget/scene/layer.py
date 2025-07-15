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

__all__ = ["ViewportSceneLayer"]


import traceback
import weakref
from typing import Sequence

import carb
import omni.ui as ui
from omni.kit.viewport.registry import RegisterScene
from omni.ui import scene as sc

from ..events import add_event_delegation, remove_event_delegation
from ..interface.i_layer_item import LayerItem as _LayerItem
from .utils import flatten_matrix as _flatten_matrix

INCLUDED_SCENE_LAYERS = [
    "omni.kit.viewport.manipulator.Selection",
    "omni.kit.viewport.manipulator.Camera",
    "omni.kit.lss.viewport.manipulator.prim",
    "omni.kit.lss.viewport.tools.teleport",
    # "omni.kit.viewport.scene.SimpleGrid",  # use legacy grid for now
    "omni.kit.viewport.scene.SimpleOrigin",
    "omni.kit.viewport.scene.CameraAxisLayer",
    "omni.kit.viewport.scene.LegacyGrid",
]


class _SceneItem(_LayerItem):
    def __init__(self, transform, instance):
        self.__transform = transform
        self.__instance = instance
        self.__transform.visible = self.__instance.visible

    def __repr__(self) -> str:
        return f"<class {self.__class__.__name__} {self.__instance}>"

    @property
    def name(self) -> str:
        return self.__instance.name

    @property
    def visible(self) -> bool:
        return self.__transform.visible

    @visible.setter
    def visible(self, value: bool):
        self.__transform.visible = bool(value)
        self.__instance.visible = bool(value)

    @property
    def layers(self) -> Sequence:
        return ()

    @property
    def categories(self) -> Sequence:
        return self.__instance.categories

    @property
    def layer(self) -> Sequence:
        return self.__instance

    def destroy(self):
        instance, self.__instance = self.__instance, None
        xform, self.__transform = self.__transform, None
        if xform and callable(getattr(xform, "clear", None)):
            xform.clear()
        if instance and callable(getattr(instance, "destroy", None)):
            try:
                instance.destroy()
            except Exception:  # noqa
                carb.log_error(f"Error destroying {self.__instance}. Traceback:\n{traceback.format_exc()}")
                raise


class ViewportSceneLayer:
    """Viewport Scene Overlay"""

    def __init__(self, factory_args, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__scene_view = None
        self.__dd_handler = None  # noqa PLW0238
        self.__view_change_sub = None  # noqa PLW0238
        self.__scene_items = {}
        self.__factory_args = factory_args
        self.__ui_frame = ui.Frame()
        RegisterScene.add_notifier(self.___scene_type_notification)

    def __del__(self):
        self.destroy()

    @property
    def layers(self):
        return self.__scene_items.values()

    def __view_changed(self, viewport_api):
        self.__scene_view.view = _flatten_matrix(viewport_api.view)
        self.__scene_view.projection = _flatten_matrix(viewport_api.projection)

    def ___scene_type_added(self, factory):
        # Push both our scopes onto the stack, to capture anything that's created
        if factory.factory_id not in INCLUDED_SCENE_LAYERS:
            return

        if not self.__scene_view:
            viewport_api = self.__factory_args.get("viewport_api")
            if not viewport_api:
                raise RuntimeError("Cannot create a ViewportSceneLayer without a viewport")

            with self.__ui_frame:
                self.__scene_view = sc.SceneView(aspect_ratio_policy=sc.AspectRatioPolicy.STRETCH)
                add_event_delegation(weakref.proxy(self.__scene_view), viewport_api)

            # 1030 Tell the ViewportAPI that we have a SceneView we want it to be updating
            if hasattr(viewport_api, "add_scene_view"):
                viewport_api.add_scene_view(self.__scene_view)
                self.__view_change_sub = None  # noqa PLW0238
            else:
                self.__view_change_sub = viewport_api.subscribe_to_view_change(self.__view_changed)  # noqa PLW0238

            # 1030 Fixes menu issue triggering selection (should remove hasattr pre 103-final)
            if hasattr(self.__scene_view, "child_windows_input"):
                self.__scene_view.child_windows_input = False

        with self.__scene_view.scene:
            transform = sc.Transform()
            with transform:
                try:
                    # Shallow copy, but should help keeping any errant extensions from messing with one-another
                    instance = factory(self.__factory_args.copy())
                    if instance:
                        self.__scene_items[factory] = _SceneItem(transform, instance)
                except Exception:  # noqa PLW0718
                    carb.log_error(f"Error loading {factory}. Traceback:\n{traceback.format_exc()}")

    def ___scene_type_removed(self, factory):
        scene = self.__scene_items.get(factory)
        if not scene:
            return

        scene.destroy()
        del self.__scene_items[factory]

        # Cleanup if we know we're empty
        if not self.__scene_items and self.__scene_view:
            self.__scene_view.destroy()
            self.__scene_view = None
            self.__dd_handler = None  # noqa PLW0238

    def ___scene_type_notification(self, factory, loading):
        if loading:
            self.___scene_type_added(factory)
        else:
            self.___scene_type_removed(factory)

    def destroy(self):
        remove_event_delegation(self.__scene_view)
        RegisterScene.remove_notifier(self.___scene_type_notification)
        self.__dd_handler = None  # noqa PLW0238
        for factory, instance in self.__scene_items.items():
            try:
                if hasattr(instance, "destroy"):
                    instance.destroy()
            except Exception:  # noqa PLW0718
                carb.log_error(f"Error destroying {instance} from {factory}. Traceback:\n{traceback.format_exc()}")
        if self.__scene_view:
            scene_view, self.__scene_view = self.__scene_view, None
            scene_view.destroy()
            viewport_api = self.__factory_args.get("viewport_api")
            if viewport_api:
                if hasattr(viewport_api, "remove_scene_view"):
                    viewport_api.remove_scene_view(scene_view)
                else:
                    self.__view_change_sub = None  # noqa PLW0238
        if self.__ui_frame:
            self.__ui_frame.destroy()
            self.__ui_frame = None
        self.__scene_items = {}
        self.__factory_args = None
