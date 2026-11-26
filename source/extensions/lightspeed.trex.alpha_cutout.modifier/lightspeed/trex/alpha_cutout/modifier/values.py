"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["MATERIAL_KEY", "MATERIAL_PRIM_KEY", "MESHES_KEY", "PRIM_PATH_KEY", "TEXTURE_KEY"]

# Keys of the serializable mesh entries that build_graph stores under job.values for the job to consume.
MESHES_KEY = "meshes"
PRIM_PATH_KEY = "prim_path"
TEXTURE_KEY = "texture"
MATERIAL_KEY = "material"
MATERIAL_PRIM_KEY = "material_prim"
