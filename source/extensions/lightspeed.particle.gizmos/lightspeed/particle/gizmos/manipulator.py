"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ParticleGizmoManipulator"]

from collections import namedtuple

import omni.usd
from lightspeed.trex.viewports.manipulators.global_selection import GlobalSelection
from omni import ui
from omni.ui import scene as sc

PARTICLE_GIZMO_COLOR = (0.0859, 0.8945, 0.7148, 1.0)
SELECTION_HIGHLIGHT_COLOR = (1.0, 0.0, 0.0, 1.0)
EMITTER_HIGHLIGHT_COLOR = (0.8, 0.2, 0.0, 0.8)
EMITTER_WIREFRAME_HIGHLIGHT_COLOR = (1.0, 0.0, 0.0, 0.8)


# generated using snippet at end of file, see: `generate_particle_icon`
class ParticleIcon:
    points = [
        (0.3109, -0.4563, 0.0),
        (0.28673175157233355, -0.33479801022408395, 0.0),
        (0.21790640302672887, -0.23179359697327112, 0.0),
        (0.11490198977591604, -0.16296824842766644, 0.0),
        (-0.006599999999999981, -0.13879999999999998, 0.0),
        (-0.128101989775916, -0.16296824842766644, 0.0),
        (-0.23110640302672883, -0.23179359697327112, 0.0),
        (-0.29993175157233354, -0.33479801022408395, 0.0),
        (-0.3241, -0.45629999999999993, 0.0),
        (-0.2999317515723336, -0.5778019897759159, 0.0),
        (-0.23110640302672888, -0.6808064030267288, 0.0),
        (-0.1281019897759162, -0.7496317515723334, 0.0),
        (-0.006600000000000058, -0.7738, 0.0),
        (0.11490198977591608, -0.7496317515723334, 0.0),
        (0.21790640302672878, -0.6808064030267289, 0.0),
        (0.2867317515723335, -0.5778019897759161, 0.0),
        (0.16870000000000002, -0.4563, 0.0),
        (0.15535608204922857, -0.38921559430639974, 0.0),
        (0.11735581874200181, -0.3323441812579982, 0.0),
        (0.060484405693600245, -0.2943439179507714, 0.0),
        (-0.0065999999999999896, -0.28099999999999997, 0.0),
        (-0.07368440569360023, -0.2943439179507714, 0.0),
        (-0.13055581874200178, -0.3323441812579982, 0.0),
        (-0.16855608204922856, -0.38921559430639974, 0.0),
        (-0.1819, -0.4563, 0.0),
        (-0.1685560820492286, -0.5233844056936002, 0.0),
        (-0.1305558187420018, -0.5802558187420017, 0.0),
        (-0.07368440569360034, -0.6182560820492286, 0.0),
        (-0.006600000000000032, -0.6315999999999999, 0.0),
        (0.060484405693600286, -0.6182560820492286, 0.0),
        (0.11735581874200177, -0.5802558187420018, 0.0),
        (0.15535608204922854, -0.5233844056936003, 0.0),
        (0.11910000000000001, -0.4563, 0.0),
        (0.10953165723666876, -0.4081966925517082, 0.0),
        (0.08228332239514904, -0.36741667760485097, 0.0),
        (0.041503307448291796, -0.34016834276333124, 0.0),
        (-0.006599999999999992, -0.3306, 0.0),
        (-0.054703307448291785, -0.34016834276333124, 0.0),
        (-0.09548332239514902, -0.36741667760485097, 0.0),
        (-0.12273165723666875, -0.4081966925517082, 0.0),
        (-0.1323, -0.4563, 0.0),
        (-0.12273165723666876, -0.5044033074482918, 0.0),
        (-0.09548332239514905, -0.545183322395149, 0.0),
        (-0.05470330744829186, -0.5724316572366687, 0.0),
        (-0.006600000000000023, -0.582, 0.0),
        (0.04150330744829182, -0.5724316572366688, 0.0),
        (0.08228332239514902, -0.545183322395149, 0.0),
        (0.10953165723666873, -0.5044033074482919, 0.0),
        (-0.47620000000000007, -0.2116, 0.0),
        (-0.4897951154934842, -0.14325273897959495, 0.0),
        (-0.5285107288800827, -0.08531072888008262, 0.0),
        (-0.586452738979595, -0.04659511549348419, 0.0),
        (-0.6548, -0.033, 0.0),
        (-0.723147261020405, -0.04659511549348419, 0.0),
        (-0.7810892711199174, -0.08531072888008262, 0.0),
        (-0.8198048845065159, -0.14325273897959495, 0.0),
        (-0.8334, -0.21159999999999998, 0.0),
        (-0.8198048845065159, -0.279947261020405, 0.0),
        (-0.7810892711199174, -0.3378892711199174, 0.0),
        (-0.7231472610204052, -0.3766048845065158, 0.0),
        (-0.6548, -0.3902, 0.0),
        (-0.5864527389795949, -0.3766048845065158, 0.0),
        (-0.5285107288800827, -0.3378892711199174, 0.0),
        (-0.48979511549348426, -0.2799472610204051, 0.0),
        (0.8333, -0.0331, 0.0),
        (0.8181976992502393, 0.04282439298123381, 0.0),
        (0.775189985387411, 0.10718998538741104, 0.0),
        (0.7108243929812339, 0.1501976992502393, 0.0),
        (0.6349, 0.1653, 0.0),
        (0.5589756070187663, 0.1501976992502393, 0.0),
        (0.494610014612589, 0.10718998538741104, 0.0),
        (0.4516023007497607, 0.04282439298123384, 0.0),
        (0.4365, -0.03309999999999997, 0.0),
        (0.4516023007497607, -0.10902439298123379, 0.0),
        (0.49461001461258897, -0.173389985387411, 0.0),
        (0.5589756070187661, -0.21639769925023922, 0.0),
        (0.6349, -0.23149999999999998, 0.0),
        (0.7108243929812339, -0.21639769925023924, 0.0),
        (0.775189985387411, -0.17338998538741104, 0.0),
        (0.8181976992502392, -0.10902439298123393, 0.0),
        (-0.24470000000000003, 0.377, 0.0),
        (-0.26131709805278613, 0.4605397932852991, 0.0),
        (-0.30863858966697666, 0.5313614103330233, 0.0),
        (-0.37946020671470093, 0.578682901947214, 0.0),
        (-0.463, 0.5952999999999999, 0.0),
        (-0.5465397932852991, 0.578682901947214, 0.0),
        (-0.6173614103330234, 0.5313614103330233, 0.0),
        (-0.6646829019472139, 0.46053979328529915, 0.0),
        (-0.6813, 0.377, 0.0),
        (-0.6646829019472139, 0.2934602067147009, 0.0),
        (-0.6173614103330234, 0.2226385896669767, 0.0),
        (-0.5465397932852992, 0.17531709805278617, 0.0),
        (-0.4630000000000001, 0.1587, 0.0),
        (-0.3794602067147009, 0.17531709805278614, 0.0),
        (-0.30863858966697677, 0.22263858966697664, 0.0),
        (-0.2613170980527862, 0.29346020671470074, 0.0),
        (0.2778, 0.6151, 0.0),
        (0.2611829019472139, 0.698639793285299, 0.0),
        (0.21386141033302333, 0.7694614103330233, 0.0),
        (0.1430397932852991, 0.8167829019472139, 0.0),
        (0.05950000000000001, 0.8333999999999999, 0.0),
        (-0.024039793285299094, 0.8167829019472139, 0.0),
        (-0.09486141033302331, 0.7694614103330233, 0.0),
        (-0.1421829019472139, 0.6986397932852991, 0.0),
        (-0.1588, 0.6151, 0.0),
        (-0.14218290194721392, 0.531560206714701, 0.0),
        (-0.09486141033302337, 0.4607385896669767, 0.0),
        (-0.02403979328529922, 0.41341709805278615, 0.0),
        (0.059499999999999956, 0.3968, 0.0),
        (0.14303979328529914, 0.41341709805278615, 0.0),
        (0.21386141033302328, 0.4607385896669766, 0.0),
        (0.26118290194721383, 0.5315602067147007, 0.0),
        (0.4365, 0.1852, 0.0),
        (0.42642926215124327, 0.23582901810190138, 0.0),
        (0.3977502271509803, 0.27875022715098025, 0.0),
        (0.35482901810190143, 0.3074292621512432, 0.0),
        (0.3042, 0.3175, 0.0),
        (0.2535709818980987, 0.3074292621512432, 0.0),
        (0.2106497728490198, 0.27875022715098025, 0.0),
        (0.18197073784875678, 0.2358290181019014, 0.0),
        (0.17190000000000003, 0.18520000000000003, 0.0),
        (0.18197073784875678, 0.13457098189809863, 0.0),
        (0.21064977284901976, 0.09164977284901978, 0.0),
        (0.25357098189809857, 0.0629707378487568, 0.0),
        (0.3042, 0.0529, 0.0),
        (0.35482901810190143, 0.06297073784875679, 0.0),
        (0.39775022715098024, 0.09164977284901975, 0.0),
        (0.4264292621512432, 0.13457098189809855, 0.0),
        (0.13220094463242862, 0.4524184519868332, 0.0),
        (-0.019800944632428624, 0.46018154801316674, 0.0),
        (-0.05290094463242863, -0.1879184519868332, 0.0),
        (0.09910094463242862, -0.19568154801316678, 0.0),
        (-0.3627295898953226, 0.3532679466333959, 0.0),
        (-0.4970704101046774, 0.2817320533666041, 0.0),
        (-0.2258704101046774, -0.22756794663339586, 0.0),
        (-0.09152958989532262, -0.15603205336660414, 0.0),
        (0.5983822689317942, -0.1297481397422462, 0.0),
        (0.5260177310682058, 0.00414813974224619, 0.0),
        (0.15891773106820584, -0.19425186025775382, 0.0),
        (0.23128226893179415, -0.32814813974224616, 0.0),
    ]
    indices = [
        0,
        1,
        16,
        16,
        17,
        1,
        1,
        2,
        17,
        17,
        18,
        2,
        2,
        3,
        18,
        18,
        19,
        3,
        3,
        4,
        19,
        19,
        20,
        4,
        4,
        5,
        20,
        20,
        21,
        5,
        5,
        6,
        21,
        21,
        22,
        6,
        6,
        7,
        22,
        22,
        23,
        7,
        7,
        8,
        23,
        23,
        24,
        8,
        8,
        9,
        24,
        24,
        25,
        9,
        9,
        10,
        25,
        25,
        26,
        10,
        10,
        11,
        26,
        26,
        27,
        11,
        11,
        12,
        27,
        27,
        28,
        12,
        12,
        13,
        28,
        28,
        29,
        13,
        13,
        14,
        29,
        29,
        30,
        14,
        14,
        15,
        30,
        30,
        31,
        15,
        15,
        0,
        31,
        31,
        16,
        0,
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
        48,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        76,
        77,
        78,
        79,
        80,
        81,
        82,
        83,
        84,
        85,
        86,
        87,
        88,
        89,
        90,
        91,
        92,
        93,
        94,
        95,
        96,
        97,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        110,
        111,
        112,
        113,
        114,
        115,
        116,
        117,
        118,
        119,
        120,
        121,
        122,
        123,
        124,
        125,
        126,
        127,
        128,
        129,
        130,
        131,
        132,
        133,
        134,
        135,
        136,
        137,
        138,
        139,
    ]
    poly_counts = [
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        3,
        16,
        16,
        16,
        16,
        16,
        16,
        4,
        4,
        4,
    ]
    num_indices = len(indices)
    colors = [PARTICLE_GIZMO_COLOR] * num_indices
    colors_selected = [SELECTION_HIGHLIGHT_COLOR] * num_indices


EmitterMesh = namedtuple("EmitterMesh", ["points", "colors", "wireframe_color", "poly_counts", "indices"])


class ClickedGesture(sc.ClickGesture):
    def __init__(self, prim_path, *args, api=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._viewport_api = api
        self._prim_path = prim_path

    def on_ended(self, *args, **kwargs):
        ndc_location = self.sender.transform_space(sc.Space.WORLD, sc.Space.NDC, self.gesture_payload.ray_closest_point)
        pixel_loc, viewport_api = self._viewport_api.map_ndc_to_texture_pixel(ndc_location)
        if pixel_loc and viewport_api:
            GlobalSelection.get_instance().add_manipulator_selection(
                self._viewport_api, pixel_loc, self.sender.gesture_payload.ray_distance, self._prim_path
            )


class ParticleGizmoManipulator(sc.Manipulator):
    def __init__(self, viewport_api, **kwargs):
        super().__init__(**kwargs)

        self._viewport_api = viewport_api
        self._root = sc.Transform()
        self._gizmo_root = sc.Transform()
        self._icon_url = None
        self._polygon_mesh = ParticleIcon()
        self._emitter_poly_mesh: EmitterMesh | None = None
        self._wireframe_thicknesses = [2.0]
        self._is_visible = True

    def destroy(self):
        self._root = None
        self._gizmo_root = None
        self._viewport_api = None
        self.model.destroy()

    def on_build(self):
        """Called when the model is changed and rebuilds the whole gizmo"""
        # self.model.update_from_prim()

        # get up to date state
        # self._update_icon_url()  # SVG icons are fixed in kit-sdk 108

        # note:need to recreate transform to release previously drawn scene items
        self._gizmo_root = sc.Transform(self.model.get_as_floats(self.model.gizmo_transform))
        with self._gizmo_root:
            with sc.Transform(look_at=sc.Transform.LookAt.CAMERA, scale_to=sc.Space.SCREEN):
                with sc.Transform(transform=sc.Matrix44.get_scale_matrix(64.0, 64.0, 1.0)):
                    if self._icon_url:
                        # Use image-based gizmo
                        sc.Image(
                            self._icon_url,
                            width=1.0,
                            height=1.0,
                            gestures=[ClickedGesture(self.model.get_prim_path(), api=self._viewport_api)],
                        )
                    else:
                        # Fallback to polygon mesh if no image is available
                        colors = self._polygon_mesh.colors
                        if self.model.selected.value:
                            colors = self._polygon_mesh.colors_selected
                        sc.PolygonMesh(
                            self._polygon_mesh.points,
                            colors,
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

        # TODO: Look into the toolkit crashing when using PolygonMesh. Otherwise we can disable below this point
        #  to make it stable.
        # if we don't have selection then just return
        if not self.model.selected.value:
            self._root = sc.Transform()
            self._emitter_poly_mesh = None
            return

        # build emitter highlight
        self._root = sc.Transform(self.model.get_as_floats(self.model.transform))
        with self._root:
            emitter = self.model.get_emitter_mesh()
            if not emitter or not emitter.GetPrim().IsValid():
                return
            points = [tuple(p) for p in emitter.GetPointsAttr().Get()]
            poly_counts = list(emitter.GetFaceVertexCountsAttr().Get())
            indices = list(emitter.GetFaceVertexIndicesAttr().Get())
            num_indices = len(indices)
            colors = [EMITTER_HIGHLIGHT_COLOR] * num_indices
            wireframe_color = [EMITTER_WIREFRAME_HIGHLIGHT_COLOR] * num_indices
            self._emitter_poly_mesh = EmitterMesh(points, colors, wireframe_color, poly_counts, indices)
            # highlight emitter if mesh is not visible (avoid z fighting if it is visible)
            if not self.model.visible.value:
                sc.PolygonMesh(
                    self._emitter_poly_mesh.points,
                    self._emitter_poly_mesh.colors,
                    self._emitter_poly_mesh.poly_counts,
                    self._emitter_poly_mesh.indices,
                )
            sc.PolygonMesh(
                self._emitter_poly_mesh.points,
                self._emitter_poly_mesh.wireframe_color,
                self._emitter_poly_mesh.poly_counts,
                self._emitter_poly_mesh.indices,
                wireframe=True,
                thicknesses=self._wireframe_thicknesses,
            )

    def on_model_updated(self, item: sc.AbstractManipulatorItem):
        # Regenerate the mesh
        if not self.model:
            return
        if not self._root:
            return  # build() has not yet been called or destroy() has been called

        match item:
            case self.model.transform:
                # If transform changed, update the root transform
                self._root.transform = self.model.get_as_floats(self.model.transform)
            case self.model.gizmo_transform:
                self._gizmo_root.transform = self.model.get_as_floats(self.model.gizmo_transform)
            case self.model.selected:
                self.invalidate()  # redraw everything
            case self.model.visible:
                self.invalidate()  # redraw everything
            case _:
                raise ValueError("Unexpected item updated on model")

    def _update_icon_url(self):
        """Update the icon URL from the current style"""
        style = ui.Style.get_instance()
        if "Button.Image::ParticleGizmo" in style.default:
            self._icon_url = style.default["Button.Image::ParticleGizmo"]["image_url"]
        else:
            # Fallback to a default particle icon or use the polygon mesh as fallback
            self._icon_url = None

    def _get_context(self):
        return omni.usd.get_context(self._viewport_api.usd_context_name)


# def generate_particle_icon():
#     import math

#     # SVG dimensions and center
#     svg_width, svg_height = 252, 252  # New dimensions from particle.svg (now square)
#     svg_center_x, svg_center_y = 126, 126  # New center (half of width/height)
#     manual_scale_factor = 1.2  # to match light icons
#     max_dim = max(svg_width, svg_height)
#     scale_factor = (max_dim * manual_scale_factor) / 2

#     def normalize_coord(x, y):
#         """Convert SVG coordinates to normalized -1 to 1 range, preserving aspect ratio"""
#         # Use the larger dimension to preserve aspect ratio
#         centered_x = (x - svg_center_x) / scale_factor
#         centered_y = -(y - svg_center_y) / scale_factor  # Flip Y axis
#         return round(centered_x, 4), round(centered_y, 4)

#     def normalize_radius(r):
#         """Convert SVG radius to normalized range, preserving aspect ratio"""
#         return round(r / scale_factor, 4)

#     # Extract exact values from current SVG: particle.svg
#     # From: <circle cx="125" cy="195" r="48" stroke="white" stroke-width="15"/>
#     #       <circle cx="125" cy="195" r="19" fill="white"/>
#     #       <circle cx="27" cy="158" r="27" fill="white"/>
#     #       <circle cx="222" cy="131" r="30" fill="white"/>
#     #       <circle cx="56" cy="69" r="33" fill="white"/>
#     #       <circle cx="135" cy="33" r="33" fill="white"/>
#     #       <circle cx="172" cy="98" r="20" fill="white"/>

#     circles = [
#         (125, 195, 48),  # Large outer circle (center)
#         (125, 195, 19),  # Small inner circle (center)
#         (27, 158, 27),  # Bottom left
#         (222, 131, 30),  # Top right
#         (56, 69, 33),  # Middle left
#         (135, 33, 33),  # Top
#         (172, 98, 20),  # Top right small
#     ]

#     # From: <path d="M134.5 57L129.5 155" stroke="white" stroke-width="15"/>
#     #       <path d="M61 78L102 155" stroke="white" stroke-width="15"/>
#     #       <path d="M211 135.5L155.5 165.5" stroke="white" stroke-width="15"/>

#     pipes = [
#         ((134.5, 57), (129.5, 155)),  # Top to center area
#         ((61, 78), (102, 155)),  # Middle left to bottom left
#         ((211, 135.5), (155.5, 165.5)),  # Top right to bottom right
#     ]

#     # Generate vertices, colors, indices, and poly_counts
#     vertices = []
#     colors = []
#     indices = []
#     poly_counts = []
#     index = 0

#     print(f"Processing {len(circles)} circles and {len(pipes)} pipes...")

#     # Generate circle vertices (16 segments each)
#     segments = 16
#     for i, (cx, cy, r) in enumerate(circles):
#         center_x, center_y = normalize_coord(cx, cy)
#         radius = normalize_radius(r)

#         print(f"Circle {i+1}: SVG({cx}, {cy}, {r}) -> Normalized({center_x}, {center_y}, {radius})")

#         # For the large center circle (first circle), create ring geometry
#         if i == 0:  # Large outer circle
#             # Generate vertices for both outer and inner circles first
#             outer_vertices = []
#             inner_vertices = []

#             for j in range(segments):
#                 angle = 2 * math.pi * j / segments

#                 # Outer circle points
#                 outer_x = center_x + radius * math.cos(angle)
#                 outer_y = center_y + radius * math.sin(angle)
#                 outer_vertices.append((outer_x, outer_y, 0.0))

#                 # Inner circle points
#                 inner_radius = normalize_radius(26.5)  # Inner radius of outer circle
#                 inner_x = center_x + inner_radius * math.cos(angle)
#                 inner_y = center_y + inner_radius * math.sin(angle)
#                 inner_vertices.append((inner_x, inner_y, 0.0))

#             # Add all vertices to the main arrays
#             vertices.extend(outer_vertices)
#             vertices.extend(inner_vertices)
#             colors.extend([[1.0, 1.0, 1.0, 1.0]] * (segments * 2))

#             # Create triangles that reference the vertices by index
#             for j in range(segments):
#                 next_j = (j + 1) % segments

#                 # Indices for current segment
#                 outer_curr = index + j
#                 outer_next = index + next_j
#                 inner_curr = index + segments + j
#                 inner_next = index + segments + next_j

#                 # First triangle: outer_curr -> outer_next -> inner_curr
#                 indices.extend([outer_curr, outer_next, inner_curr])

#                 # Second triangle: inner_curr -> inner_next -> outer_next
#                 indices.extend([inner_curr, inner_next, outer_next])

#             index += segments * 2  # Move index past all vertices
#             poly_counts.extend([3, 3] * segments)  # Two triangles per segment

#         else:
#             # Generate circle perimeter vertices
#             for j in range(segments):
#                 angle = 2 * math.pi * j / segments
#                 x = center_x + radius * math.cos(angle)
#                 y = center_y + radius * math.sin(angle)
#                 vertices.append((x, y, 0.0))
#                 colors.append([1.0, 1.0, 1.0, 1.0])
#                 indices.append(index)
#                 index += 1

#             poly_counts.append(segments)

#     # Generate pipe vertices
#     # Make pipes thicker - 1/4 of the diameter of smaller circles
#     # Use the smallest circle radius (20) as reference, so pipe width = (20 * 2) / 4 = 10
#     pipe_width = normalize_radius(10)  # 1/4 diameter of smallest circle

#     for i, ((start_x, start_y), (end_x, end_y)) in enumerate(pipes):
#         start_nx, start_ny = normalize_coord(start_x, start_y)
#         end_nx, end_ny = normalize_coord(end_x, end_y)

#         print(
#             f"Pipe {i+1}: SVG({start_x},{start_y})->({end_x},{end_y}) -> "
#             "Normalized({start_nx},{start_ny})->({end_nx},{end_ny})"
#         )
#         print(f"  Pipe width: {pipe_width}")

#         # Calculate pipe direction and perpendicular
#         dx = end_nx - start_nx
#         dy = end_ny - start_ny
#         length = math.sqrt(dx * dx + dy * dy)

#         if length > 0:
#             # Perpendicular vector for pipe width
#             perp_x = -dy / length * pipe_width
#             perp_y = dx / length * pipe_width

#             # Four corners of the pipe
#             pipe_corners = [
#                 (start_nx + perp_x, start_ny + perp_y, 0.0),
#                 (start_nx - perp_x, start_ny - perp_y, 0.0),
#                 (end_nx - perp_x, end_ny - perp_y, 0.0),
#                 (end_nx + perp_x, end_ny + perp_y, 0.0),
#             ]

#             for corner in pipe_corners:
#                 vertices.append(corner)
#                 colors.append([1.0, 1.0, 1.0, 1.0])  # White
#                 indices.append(index)
#                 index += 1

#             poly_counts.append(4)

#     print(f"points = {vertices}")
#     print(f"indices = {indices}")
#     print(f"poly_counts = {poly_counts}")
