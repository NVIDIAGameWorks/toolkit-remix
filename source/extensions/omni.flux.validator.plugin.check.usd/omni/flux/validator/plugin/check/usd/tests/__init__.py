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

from .e2e.generic.test_value_mapping import *
from .e2e.meta.test_default_prim_ui import *
from .unit.ai.test_generate_pbr_material import *
from .unit.generic.test_value_mapping import *
from .unit.material.test_default_material import *
from .unit.material.test_material_shaders import *
from .unit.mesh.test_add_inverted_uv_attr import *
from .unit.mesh.test_add_vertex_indices_to_geom_subsets import *
from .unit.mesh.test_force_primvar_to_vertex_interpolation import *
from .unit.mesh.test_strip_extra_attributes import *
from .unit.mesh.test_triangulate import *
from .unit.meta.test_default_prim import *
from .unit.meta.test_wrap_root_prims import *
from .unit.paths.test_relative_asset_paths import *
from .unit.paths.test_relative_references import *
from .unit.test_print_prims import *
from .unit.texture.test_convert_to_dds import *
from .unit.texture.test_convert_to_octahedral import *
from .unit.xform.test_apply_unit_scale import *
from .unit.xform.test_reset_pivot import *
