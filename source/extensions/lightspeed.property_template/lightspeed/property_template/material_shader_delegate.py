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

from omni.kit.window.property.property_scheme_delegate import PropertySchemeDelegate
from pxr import UsdShade


# noinspection PyMethodMayBeStatic
class MaterialShaderDelegate(PropertySchemeDelegate):
    def get_widgets(self, payload):
        widgets_to_build = []
        if self._should_enable_delegate(payload):
            widgets_to_build.append("references")
            widgets_to_build.append("lss_shader")
            widgets_to_build.append("lss_material")
            widgets_to_build.append("attribute")
        return widgets_to_build

    def get_unwanted_widgets(self, payload):
        unwanted_widgets_to_build = []
        if self._should_enable_delegate(payload):
            unwanted_widgets_to_build = [
                "audio_listener",
                "audio_settings",
                "audio_sound",
                "backdrop",
                "camera",
                "compute_node",
                "geometry",
                "geometry_imageable",
                "kind",
                "light",
                "material",
                "material_binding",
                "media",
                "metadata",
                "nodegraph",
                "path",
                "payloads",
                "physx_custom_properties",
                "physx_invisible",
                "physx_main_frame_widget",
                "physx_rigid_body_cameras",
                "physx_update_all_drone_camera",
                "physx_update_all_follow_camera",
                "physx_update_all_velocity_camera",
                "physx_xform_cameras",
                "renderproduct_base",
                "rendersettings_base",
                "rendervar_base",
                "shader",
                "Shader",
                "skel",
                "tagging",
                "transform",
                "variants",
            ]
        return unwanted_widgets_to_build  # noqa R504

    def _should_enable_delegate(self, payload):
        stage = payload.get_stage()
        if stage:
            for prim_path in payload:
                prim = stage.GetPrimAtPath(prim_path)
                if prim and not (prim.IsA(UsdShade.Shader) or prim.IsA(UsdShade.Material)):
                    return False
            return True
        return False
