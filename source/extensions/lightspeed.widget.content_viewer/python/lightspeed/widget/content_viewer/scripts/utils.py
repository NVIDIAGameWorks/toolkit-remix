"""
* Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
import omni.client


def is_path_readable(path: str):
    """Check is a path is readable"""
    _, entry = omni.client.stat(path)
    if entry.flags & omni.client.ItemFlags.READABLE_FILE:
        return True
    return False
