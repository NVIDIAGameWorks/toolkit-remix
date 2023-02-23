# Copyright (c) 2021-2022, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#
import typing

if typing.TYPE_CHECKING:
    from pxr import Gf


def flatten_matrix(matrix: "Gf.Matrix4d"):
    m0, m1, m2, m3 = matrix[0], matrix[1], matrix[2], matrix[3]
    return [
        m0[0],
        m0[1],
        m0[2],
        m0[3],
        m1[0],
        m1[1],
        m1[2],
        m1[3],
        m2[0],
        m2[1],
        m2[2],
        m2[3],
        m3[0],
        m3[1],
        m3[2],
        m3[3],
    ]


def flatten_rot_matrix(matrix: "Gf.Matrix3d"):
    m0, m1, m2 = matrix[0], matrix[1], matrix[2]
    return [m0[0], m0[1], m0[2], 0, m1[0], m1[1], m1[2], 0, m2[0], m2[1], m2[2], 0, 0, 0, 0, 1]
