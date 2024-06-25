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

from pxr import Gf, Sdf, UsdGeom

ATTR_DISPLAY_NAMES_TABLE = {
    "xformOp:orient": ["Orient  X", "Y", "Z"],
    "xformOp:rotateX": ["Rotation  X"],
    "xformOp:rotateY": ["Rotation  Y"],
    "xformOp:rotateZ": ["Rotation  Z"],
    "xformOp:rotateXYZ": ["Rotation  X", "Y", "Z"],
    "xformOp:rotateXZY": ["Rotation  X", "Z", "Y"],
    "xformOp:rotateYXZ": ["Rotation  Y", "X", "Z"],
    "xformOp:rotateYZX": ["Rotation  Y", "Z", "X"],
    "xformOp:rotateZXY": ["Rotation  Z", "X", "Y"],
    "xformOp:rotateZYX": ["Rotation  Z", "Y", "X"],
    "xformOp:scale": ["Scale  X", "Y", "Z"],
    "xformOp:transform": ["Position  X", "Y", "Z"],
    "xformOp:translate": ["Position  X", "Y", "Z"],
    "xformOp:translate:pivot": ["Pivot Position  X", "Y", "Z"],
}

OPS_ATTR_NAME_TABLE = {
    UsdGeom.XformOp.TypeOrient: "xformOp:orient",
    UsdGeom.XformOp.TypeRotateX: "xformOp:rotateX",
    UsdGeom.XformOp.TypeRotateY: "xformOp:rotateY",
    UsdGeom.XformOp.TypeRotateZ: "xformOp:rotateZ",
    UsdGeom.XformOp.TypeRotateXYZ: "xformOp:rotateXYZ",
    UsdGeom.XformOp.TypeRotateXZY: "xformOp:rotateXZY",
    UsdGeom.XformOp.TypeRotateYXZ: "xformOp:rotateYXZ",
    UsdGeom.XformOp.TypeRotateYZX: "xformOp:rotateYZX",
    UsdGeom.XformOp.TypeRotateZXY: "xformOp:rotateZXY",
    UsdGeom.XformOp.TypeRotateZYX: "xformOp:rotateZYX",
    UsdGeom.XformOp.TypeScale: "xformOp:scale",
    UsdGeom.XformOp.TypeTransform: "xformOp:transform",
    UsdGeom.XformOp.TypeTranslate: "xformOp:translate",
}

OPS_ATTR_TYPE_TABLE = {
    UsdGeom.XformOp.TypeOrient: Sdf.ValueTypeNames.Quatf,
    UsdGeom.XformOp.TypeRotateX: Sdf.ValueTypeNames.Float,
    UsdGeom.XformOp.TypeRotateY: Sdf.ValueTypeNames.Float,
    UsdGeom.XformOp.TypeRotateZ: Sdf.ValueTypeNames.Float,
    UsdGeom.XformOp.TypeRotateXYZ: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeRotateXZY: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeRotateYXZ: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeRotateYZX: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeRotateZXY: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeRotateZYX: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeScale: Sdf.ValueTypeNames.Float3,
    UsdGeom.XformOp.TypeTransform: Sdf.ValueTypeNames.Matrix4d,
    UsdGeom.XformOp.TypeTranslate: Sdf.ValueTypeNames.Float3,
}

OPS_UI_ATTR_OP_ORDER_TABLE = {
    UsdGeom.XformOp.TypeTranslate: 0,
    UsdGeom.XformOp.TypeRotateXYZ: 1,
    UsdGeom.XformOp.TypeRotateXZY: 2,
    UsdGeom.XformOp.TypeRotateYXZ: 3,
    UsdGeom.XformOp.TypeRotateYZX: 4,
    UsdGeom.XformOp.TypeRotateZXY: 5,
    UsdGeom.XformOp.TypeRotateZYX: 6,
    UsdGeom.XformOp.TypeRotateX: 7,
    UsdGeom.XformOp.TypeRotateY: 8,
    UsdGeom.XformOp.TypeRotateZ: 9,
    UsdGeom.XformOp.TypeScale: 10,
    UsdGeom.XformOp.TypeOrient: 11,
    UsdGeom.XformOp.TypeTransform: 12,
    UsdGeom.XformOp.TypeInvalid: 13,
}

# Minimal sets of attributes to display.
# Will display 1 per group, first item is chosen as default if the group doesn't exist
# Each group item is a tuple of XForm Type list and Default Values List
DEFAULT_VIRTUAL_XFORM_OPS = [
    # Translate Group
    [
        ([UsdGeom.XformOp.TypeTranslate], [Gf.Vec3f(0, 0, 0)]),  # Default Op
    ],
    # Scale Group
    [([UsdGeom.XformOp.TypeScale], [Gf.Vec3f(1, 1, 1)])],  # Default Op
    # Rotation Group
    [
        ([UsdGeom.XformOp.TypeRotateXYZ], [Gf.Vec3f(0, 0, 0)]),  # Default Op
        ([UsdGeom.XformOp.TypeRotateXZY], [Gf.Vec3f(0, 0, 0)]),
        ([UsdGeom.XformOp.TypeRotateYXZ], [Gf.Vec3f(0, 0, 0)]),
        ([UsdGeom.XformOp.TypeRotateYZX], [Gf.Vec3f(0, 0, 0)]),
        ([UsdGeom.XformOp.TypeRotateZXY], [Gf.Vec3f(0, 0, 0)]),
        ([UsdGeom.XformOp.TypeRotateZYX], [Gf.Vec3f(0, 0, 0)]),
        ([UsdGeom.XformOp.TypeRotateX, UsdGeom.XformOp.TypeRotateY, UsdGeom.XformOp.TypeRotateZ], [0.0, 0.0, 0.0]),
    ],
]
