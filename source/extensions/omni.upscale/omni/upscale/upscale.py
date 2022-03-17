"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""

import omni.ext

from .upscale_core import UpscalerCore


class UpscalerExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        pass

    def on_shutdown(self):
        pass

    def upscale(self, source_path, dest_path):
        UpscalerCore.perform_upscale(source_path, dest_path)
