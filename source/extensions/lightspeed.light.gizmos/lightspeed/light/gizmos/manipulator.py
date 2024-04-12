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
__all__ = ["LightGizmosManipulator"]

import omni.usd
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from omni.ui import scene as sc

from .model import LightType


# generated using snippet at end of file, see: `generate_light_icon`
class SphereLight:
    points = [
        (-0.03, 0.72, 0.0),
        (0.03, 0.72, 0.0),
        (0.15, 0.42, 0.0),
        (-0.15, 0.42, 0.0),
        (-0.53, 0.488, 0.0),
        (-0.488, 0.53, 0.0),
        (-0.191, 0.403, 0.0),
        (-0.403, 0.191, 0.0),
        (-0.72, -0.03, 0.0),
        (-0.72, 0.03, 0.0),
        (-0.42, 0.15, 0.0),
        (-0.42, -0.15, 0.0),
        (-0.488, -0.53, 0.0),
        (-0.53, -0.488, 0.0),
        (-0.403, -0.191, 0.0),
        (-0.191, -0.403, 0.0),
        (0.03, -0.72, 0.0),
        (-0.03, -0.72, 0.0),
        (-0.15, -0.42, 0.0),
        (0.15, -0.42, 0.0),
        (0.53, -0.488, 0.0),
        (0.488, -0.53, 0.0),
        (0.191, -0.403, 0.0),
        (0.403, -0.191, 0.0),
        (0.72, 0.03, 0.0),
        (0.72, -0.03, 0.0),
        (0.42, -0.15, 0.0),
        (0.42, 0.15, 0.0),
        (0.488, 0.53, 0.0),
        (0.53, 0.488, 0.0),
        (0.403, 0.191, 0.0),
        (0.191, 0.403, 0.0),
        (0.0, 0.35, 0.0),
        (0.206, 0.283, 0.0),
        (0.333, 0.108, 0.0),
        (0.333, -0.108, 0.0),
        (0.206, -0.283, 0.0),
        (0.0, -0.35, 0.0),
        (-0.206, -0.283, 0.0),
        (-0.333, -0.108, 0.0),
        (-0.333, 0.108, 0.0),
        (-0.206, 0.283, 0.0),
    ]
    colors = [
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
    ]
    indices = [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
    ]
    poly_counts = [4, 4, 4, 4, 4, 4, 4, 4, 10]


class RectLight:
    points = [
        (-0.53, 0.488, 0.0),
        (-0.488, 0.53, 0.0),
        (-0.191, 0.403, 0.0),
        (-0.403, 0.191, 0.0),
        (-0.488, -0.53, 0.0),
        (-0.53, -0.488, 0.0),
        (-0.403, -0.191, 0.0),
        (-0.191, -0.403, 0.0),
        (0.53, -0.488, 0.0),
        (0.488, -0.53, 0.0),
        (0.191, -0.403, 0.0),
        (0.403, -0.191, 0.0),
        (0.488, 0.53, 0.0),
        (0.53, 0.488, 0.0),
        (0.403, 0.191, 0.0),
        (0.191, 0.403, 0.0),
        (0.247, 0.247, 0.0),
        (0.247, -0.247, 0.0),
        (-0.247, -0.247, 0.0),
        (-0.247, 0.247, 0.0),
    ]
    colors = [
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
    ]
    indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    poly_counts = [4, 4, 4, 4, 4]


class DiskLight:
    points = [
        (0.609, 0.386, 0.0),
        (0.639, 0.334, 0.0),
        (0.439, 0.08, 0.0),
        (0.289, 0.34, 0.0),
        (-0.03, 0.72, 0.0),
        (0.03, 0.72, 0.0),
        (0.15, 0.42, 0.0),
        (-0.15, 0.42, 0.0),
        (-0.639, 0.334, 0.0),
        (-0.609, 0.386, 0.0),
        (-0.289, 0.34, 0.0),
        (-0.439, 0.08, 0.0),
        (-0.338, 0.091, 0.0),
        (-0.247, 0.247, 0.0),
        (-0.091, 0.338, 0.0),
        (0.091, 0.338, 0.0),
        (0.247, 0.247, 0.0),
        (0.338, 0.091, 0.0),
    ]
    colors = [
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
    ]
    indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    poly_counts = [4, 4, 4, 6]


class CylinderLight:
    points = [
        (-0.587, 0.544, 0.0),
        (-0.544, 0.587, 0.0),
        (-0.247, 0.46, 0.0),
        (-0.46, 0.247, 0.0),
        (-0.65, -0.03, 0.0),
        (-0.65, 0.03, 0.0),
        (-0.35, 0.15, 0.0),
        (-0.35, -0.15, 0.0),
        (-0.544, -0.587, 0.0),
        (-0.587, -0.544, 0.0),
        (-0.46, -0.247, 0.0),
        (-0.247, -0.46, 0.0),
        (0.587, -0.544, 0.0),
        (0.544, -0.587, 0.0),
        (0.247, -0.46, 0.0),
        (0.46, -0.247, 0.0),
        (0.65, 0.03, 0.0),
        (0.65, -0.03, 0.0),
        (0.35, -0.15, 0.0),
        (0.35, 0.15, 0.0),
        (0.544, 0.587, 0.0),
        (0.587, 0.544, 0.0),
        (0.46, 0.247, 0.0),
        (0.247, 0.46, 0.0),
        (0.1235, 0.433, 0.0),
        (0.1235, -0.433, 0.0),
        (-0.1235, -0.433, 0.0),
        (-0.1235, 0.433, 0.0),
    ]
    colors = [
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
        [1.0, 0.9, 0.5, 0.9],
    ]
    indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
    poly_counts = [4, 4, 4, 4, 4, 4, 4]


class DistantLight:
    points = [
        (-0.015, 0.5, 0.0),
        (0.015, 0.5, 0.0),
        (0.15, -0.3, 0.0),
        (-0.15, -0.3, 0.0),
        (-0.263, 0.426, 0.0),
        (-0.237, 0.441, 0.0),
        (0.28, -0.185, 0.0),
        (0.02, -0.335, 0.0),
        (-0.441, 0.237, 0.0),
        (-0.426, 0.263, 0.0),
        (0.335, -0.02, 0.0),
        (0.185, -0.28, 0.0),
        (-0.5, -0.015, 0.0),
        (-0.5, 0.015, 0.0),
        (0.3, 0.15, 0.0),
        (0.3, -0.15, 0.0),
        (-0.426, -0.263, 0.0),
        (-0.441, -0.237, 0.0),
        (0.185, 0.28, 0.0),
        (0.335, 0.02, 0.0),
        (-0.237, -0.441, 0.0),
        (-0.263, -0.426, 0.0),
        (0.02, 0.335, 0.0),
        (0.28, 0.185, 0.0),
        (0.015, -0.5, 0.0),
        (-0.015, -0.5, 0.0),
        (-0.15, 0.3, 0.0),
        (0.15, 0.3, 0.0),
        (0.263, -0.426, 0.0),
        (0.237, -0.441, 0.0),
        (-0.28, 0.185, 0.0),
        (-0.02, 0.335, 0.0),
        (0.441, -0.237, 0.0),
        (0.426, -0.263, 0.0),
        (-0.335, 0.02, 0.0),
        (-0.185, 0.28, 0.0),
        (0.5, 0.015, 0.0),
        (0.5, -0.015, 0.0),
        (-0.3, -0.15, 0.0),
        (-0.3, 0.15, 0.0),
        (0.426, 0.263, 0.0),
        (0.441, 0.237, 0.0),
        (-0.185, -0.28, 0.0),
        (-0.335, -0.02, 0.0),
        (0.237, 0.441, 0.0),
        (0.263, 0.426, 0.0),
        (-0.02, -0.335, 0.0),
        (-0.28, -0.185, 0.0),
    ]
    colors = [
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
        [1.0, 0.8, 0.2, 1.0],
    ]
    indices = [
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
    ]
    poly_counts = [4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4]


class ClickedGesture(sc.ClickGesture):
    def __init__(self, prim_path, *args, api=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._viewport_api = api
        self._prim_path = prim_path

    def on_ended(self, *args, **kwargs):
        ndc_location = self.sender.transform_space(sc.Space.WORLD, sc.Space.NDC, self.gesture_payload.ray_closest_point)
        pixel_loc, viewport_api = self._viewport_api.map_ndc_to_texture_pixel(ndc_location)
        if pixel_loc and viewport_api:
            GlobalSelection.get_instance().add_light_selection(
                self._viewport_api, pixel_loc, self.sender.gesture_payload.ray_distance, self._prim_path
            )


class LightGizmosManipulator(sc.Manipulator):
    def __init__(self, viewport_api, **kwargs):
        super().__init__(**kwargs)

        self.destroy()
        self._viewport_api = viewport_api
        self._root = sc.Transform()
        self._polygon_mesh = None
        self._is_visible = True

        # image based gizmos crash omniverse just now (105.1.2)
        # style = ui.Style.get_instance()
        # if "Button.Image::LightGizmo" in style.default:
        #    self._icon_url = style.default["Button.Image::LightGizmo"]["image_url"]
        # else:
        #    self._icon_url = None

    def destroy(self):
        self._root = None
        self._viewport_api = None

    def on_build(self):
        """Called when the model is changed and rebuilds the whole gizmo"""
        self.model.update_from_prim()

        # get up to date state
        self._update_root_transform()
        self._update_icon_geometry()
        self._update_visibility()

        if not self._is_visible:
            return

        # build UI
        with self._root:
            with sc.Transform(look_at=sc.Transform.LookAt.CAMERA, scale_to=sc.Space.SCREEN):
                with sc.Transform(transform=sc.Matrix44.get_scale_matrix(64.0, 64.0, 1.0)):
                    # using a polygon mesh here because image icons seem to crash OV
                    sc.PolygonMesh(
                        self._polygon_mesh.points,
                        self._polygon_mesh.colors,
                        self._polygon_mesh.poly_counts,
                        self._polygon_mesh.indices,
                    )
                    # invisible rectangle used for selection area, polygonmesh selection doesnt work so well...
                    sc.Rectangle(
                        width=1.0,
                        height=1.0,
                        color=[1.0, 1.0, 1.0, 0.0],
                        gestures=[ClickedGesture(self.model.get_prim_path(), api=self._viewport_api)],
                    )

    def on_model_updated(self, item):
        # Update the shapes
        if item == self.model.get_item("transform"):
            self._update_root_transform()

        if item == self.model.get_item("light_type"):
            self._update_icon_geometry()

        if item == self.model.get_item("visible"):
            self._update_visibility()

    def _update_root_transform(self):
        transform = self.model.get_as_floats(self.model.get_item("transform"))
        self._root.transform = sc.Matrix44(*transform)

    def _update_icon_geometry(self):
        match self.model.get_item("light_type").value:
            case LightType.DiskLight:
                self._polygon_mesh = DiskLight()
            case LightType.RectLight:
                self._polygon_mesh = RectLight()
            case LightType.CylinderLight:
                self._polygon_mesh = CylinderLight()
            case LightType.DistantLight:
                self._polygon_mesh = DistantLight()
            case _:
                self._polygon_mesh = SphereLight()

    def _update_visibility(self):
        self._is_visible = self.model.get_as_bools(self.model.get_item("visible"))

    def _get_context(self):
        return omni.usd.get_context(self._viewport_api.usd_context_name)


# def generate_light_icon():
#    import math
#    import numpy as np
#
#    vertices = []
#    poly_counts = []
#    indices = []
#    colors = []
#    index = 0
#
#    # circle params
#    segments = 0
#    radius = 0.35
#    circle_phase = np.radians(45.0)
#
#    # spikes params
#    spikes = 12
#    width = 0.3
#    height = 0.8
#    spike_phase = np.radians(0.0)
#    offset = np.array((0.0, 0.1))
#
#    # draw spikes
#    rect_vertices = [np.array((-0.1, 1.0)), np.array(( 0.1, 1.0)), np.array(( 1.0,-1.0)), np.array((-1.0,-1.0))]
#    for i in range(0, spikes):
#        theta = spike_phase + float(i) * math.pi * 2.0 / spikes
#        c, s = np.cos(theta), np.sin(theta)
#        R = np.array(((c, -s), (s, c)))
#
#        for j in range(0, 4):
#            vertex = np.matmul(R, (np.array((width/2, height/2) * rect_vertices[j]) + offset))
#            vertices.append((round(vertex.item(0), 3), round(vertex.item(1), 3), 0.0))
#            indices.append(index)
#            index += 1
#            colors.append([1.0, 0.8, 0.2, 1.0])
#
#        poly_counts.append(4)
#
#    # draw circle
#    for i in range(0, segments):
#        theta = circle_phase + float(i) * math.pi * 2.0 / segments
#        vertices.append((round(math.sin(theta) * radius, 3), round(math.cos(theta) * radius, 3), 0.0))
#        indices.append(index)
#        index += 1
#        colors.append([1.0, 0.9, 0.5, 0.9])
#
#    if segments > 0:
#        poly_counts.append(segments)
#
#    print(f"points = {vertices}")
#    print(f"colors = {colors}")
#    print(f"indices = {indices}")
#    print(f"poly_counts = {poly_counts}")
