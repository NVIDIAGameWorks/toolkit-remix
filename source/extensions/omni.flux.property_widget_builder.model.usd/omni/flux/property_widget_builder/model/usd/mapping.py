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

# We don't use Tf.Type.FindByName(name) directly because the name depends
# on the compiler. For example the line `Sdf.ValueTypeNames.Int64.type`
# resolves to `Tf.Type.FindByName('long')` on Linux and on Windows it's
# `Tf.Type.FindByName('__int64')`.
tf_half = Sdf.ValueTypeNames.Half
tf_float = Sdf.ValueTypeNames.Float
tf_double = Sdf.ValueTypeNames.Double
tf_uchar = Sdf.ValueTypeNames.UChar
tf_uint = Sdf.ValueTypeNames.UInt
tf_int = Sdf.ValueTypeNames.Int
tf_int64 = Sdf.ValueTypeNames.Int64
tf_uint64 = Sdf.ValueTypeNames.UInt64
tf_bool = Sdf.ValueTypeNames.Bool
tf_string = Sdf.ValueTypeNames.String
tf_gf_vec2i = Sdf.ValueTypeNames.Int2
tf_gf_vec2h = Sdf.ValueTypeNames.Half2
tf_gf_vec2f = Sdf.ValueTypeNames.Float2
tf_gf_vec2d = Sdf.ValueTypeNames.Double2
tf_gf_vec3i = Sdf.ValueTypeNames.Int3
tf_gf_vec3h = Sdf.ValueTypeNames.Half3
tf_gf_vec3f = Sdf.ValueTypeNames.Float3
tf_gf_vec3d = Sdf.ValueTypeNames.Double3
tf_gf_col3d = Sdf.ValueTypeNames.Color3d
tf_gf_col3f = Sdf.ValueTypeNames.Color3f
tf_gf_col3h = Sdf.ValueTypeNames.Color3h
tf_gf_col4d = Sdf.ValueTypeNames.Color4d
tf_gf_col4f = Sdf.ValueTypeNames.Color4f
tf_gf_col4h = Sdf.ValueTypeNames.Color4h
tf_gf_vec4i = Sdf.ValueTypeNames.Int4
tf_gf_vec4h = Sdf.ValueTypeNames.Half4
tf_gf_vec4f = Sdf.ValueTypeNames.Float4
tf_gf_vec4d = Sdf.ValueTypeNames.Double4
tf_tf_token = Sdf.ValueTypeNames.Token
tf_sdf_asset_path = Sdf.ValueTypeNames.Asset
tf_sdf_time_code = Sdf.ValueTypeNames.TimeCode

# Value type names for numeric bounds checks (e.g. OGN field builders for sliders).
FLOAT_TYPES = (
    tf_half,
    tf_float,
    tf_double,
)

INT_TYPES = (
    tf_int,
    tf_int64,
    tf_uint,
    tf_uint64,
)

VecType = (
    Gf.Vec2d
    | Gf.Vec2f
    | Gf.Vec2h
    | Gf.Vec2i
    | Gf.Vec3d
    | Gf.Vec3f
    | Gf.Vec3h
    | Gf.Vec3i
    | Gf.Vec4d
    | Gf.Vec4f
    | Gf.Vec4h
    | Gf.Vec4i
)
VEC_TYPES = (
    Gf.Vec2d,
    Gf.Vec2f,
    Gf.Vec2h,
    Gf.Vec2i,
    Gf.Vec3d,
    Gf.Vec3f,
    Gf.Vec3h,
    Gf.Vec3i,
    Gf.Vec4d,
    Gf.Vec4f,
    Gf.Vec4h,
    Gf.Vec4i,
)


GF_TO_PYTHON_TYPE = {
    tf_half: float,
    tf_float: float,
    tf_double: float,
    tf_uchar: int,
    tf_uint: int,
    tf_int: int,
    tf_int64: int,
    tf_uint64: int,
    tf_bool: bool,
    tf_string: str,
    tf_gf_vec2i: float,  # TODO: Improve data type handling so PropertyWidgets don't need hardcoded conversions anymore.
    tf_gf_vec2h: float,
    tf_gf_vec2f: float,
    tf_gf_vec2d: float,
    tf_gf_vec3i: float,
    tf_gf_vec3h: float,
    tf_gf_vec3f: float,
    tf_gf_vec3d: float,
    tf_gf_vec4i: float,
    tf_gf_vec4h: float,
    tf_gf_vec4f: float,
    tf_gf_vec4d: float,
    tf_gf_col3d: float,
    tf_gf_col3f: float,
    tf_gf_col3h: float,
    tf_gf_col4d: float,
    tf_gf_col4f: float,
    tf_gf_col4h: float,
    tf_tf_token: str,
    tf_sdf_asset_path: None,  # todo
    tf_sdf_time_code: None,  # todo
}

CHANNEL_ELEMENT_BUILDER_TABLE = {
    tf_half: 1,
    tf_float: 1,
    tf_double: 1,
    tf_uchar: 1,
    tf_uint: 1,
    tf_int: 1,
    tf_int64: 1,
    tf_uint64: 1,
    tf_bool: 1,
    tf_string: 1,
    tf_gf_vec2i: 2,
    tf_gf_vec2h: 2,
    tf_gf_vec2f: 2,
    tf_gf_vec2d: 2,
    tf_gf_vec3i: 3,
    tf_gf_vec3h: 3,
    tf_gf_vec3f: 3,
    tf_gf_vec3d: 3,
    tf_gf_vec4i: 4,
    tf_gf_vec4h: 4,
    tf_gf_vec4f: 4,
    tf_gf_vec4d: 4,
    tf_gf_col3d: 1,
    tf_gf_col3f: 1,
    tf_gf_col3h: 1,
    tf_gf_col4d: 1,
    tf_gf_col4f: 1,
    tf_gf_col4h: 1,
    tf_tf_token: 1,
    tf_sdf_asset_path: 1,
    tf_sdf_time_code: 1,
}

MULTICHANNEL_BUILDER_TABLE = {
    tf_half: False,
    tf_float: False,
    tf_double: False,
    tf_uchar: False,
    tf_uint: False,
    tf_int: False,
    tf_int64: False,
    tf_uint64: False,
    tf_bool: False,
    tf_string: False,
    tf_gf_vec2i: True,
    tf_gf_vec2h: True,
    tf_gf_vec2f: True,
    tf_gf_vec2d: True,
    tf_gf_vec3i: True,
    tf_gf_vec3h: True,
    tf_gf_vec3f: True,
    tf_gf_vec3d: True,
    tf_gf_vec4i: True,
    tf_gf_vec4h: True,
    tf_gf_vec4f: True,
    tf_gf_vec4d: True,
    tf_gf_col3d: False,
    tf_gf_col3f: False,
    tf_gf_col3h: False,
    tf_gf_col4d: False,
    tf_gf_col4f: False,
    tf_gf_col4h: False,
    tf_tf_token: False,
    tf_sdf_asset_path: False,
    tf_sdf_time_code: False,
}

DEFAULT_VALUE_TABLE = {"xformOp:scale": (1.0, 1.0, 1.0), "visibleInPrimaryRay": True}

OPS_ATTR_PRECISION_TABLE = {
    UsdGeom.XformOp.TypeOrient: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateX: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateY: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateZ: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateXYZ: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateXZY: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateYXZ: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateYZX: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateZXY: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeRotateZYX: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeScale: UsdGeom.XformOp.PrecisionFloat,
    UsdGeom.XformOp.TypeTransform: UsdGeom.XformOp.PrecisionDouble,
    UsdGeom.XformOp.TypeTranslate: UsdGeom.XformOp.PrecisionFloat,
}

OPS_ATTR_ORDER_TABLE = {
    UsdGeom.XformOp.TypeInvalid: 0,
    UsdGeom.XformOp.TypeScale: 1,
    UsdGeom.XformOp.TypeRotateX: 2,
    UsdGeom.XformOp.TypeRotateY: 3,
    UsdGeom.XformOp.TypeRotateZ: 4,
    UsdGeom.XformOp.TypeRotateXYZ: 5,
    UsdGeom.XformOp.TypeRotateXZY: 6,
    UsdGeom.XformOp.TypeRotateYXZ: 7,
    UsdGeom.XformOp.TypeRotateYZX: 8,
    UsdGeom.XformOp.TypeRotateZXY: 9,
    UsdGeom.XformOp.TypeRotateZYX: 10,
    UsdGeom.XformOp.TypeTranslate: 11,
    UsdGeom.XformOp.TypeOrient: 12,
    UsdGeom.XformOp.TypeTransform: 13,
}


DEFAULT_PRECISION = UsdGeom.XformOp.PrecisionFloat
