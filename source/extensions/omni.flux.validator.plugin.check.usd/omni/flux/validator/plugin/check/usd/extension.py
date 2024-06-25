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

import carb
import carb.settings
import omni.ext
from omni.flux.validator.factory import get_instance as _get_factory_instance

from .ai.generate_pbr_material import GeneratePBRMaterial as _GeneratePBRMaterial
from .example.print_prims import PrintPrims as _PrintPrims
from .generic.value_mapping import ValueMapping as _ValueMapping
from .material.clear_unassigned_materials import ClearUnassignedMaterial as _ClearUnassignedMaterial
from .material.default_material import DefaultMaterial as _DefaultMaterial
from .material.material_shaders import MaterialShaders as _MaterialShaders
from .mesh.add_inverted_uv_attr import AddInvertedUVAttr as _AddInvertedUVAttr
from .mesh.add_vertex_indices_to_geom_subsets import AddVertexIndicesToGeomSubsets as _AddVertexIndicesToGeomSubsets
from .mesh.force_primvar_to_vertex_interpolation import (
    ForcePrimvarToVertexInterpolation as _ForcePrimvarToVertexInterpolation,
)
from .mesh.strip_extra_attributes import StripExtraAttributes as _StripExtraAttributes
from .mesh.triangulate import Triangulate as _Triangulate
from .meta.default_prim import DefaultPrim as _DefaultPrim
from .meta.wrap_root_prims import WrapRootPrims as _WrapRootPrims
from .paths.relative_asset_paths import RelativeAssetPaths as _RelativeAssetPaths
from .paths.relative_references import RelativeReferences as _RelativeReferences
from .render.generate_thumbnail import GenerateThumbnail as _GenerateThumbnail
from .texture.convert_to_dds import ConvertToDDS as _ConvertToDDS
from .texture.convert_to_octahedral import ConvertToOctahedral as _ConvertToOctahedral
from .texture.mass_texture_preview import MassTexturePreview as _MassTexturePreview
from .xform.apply_unit_scale import ApplyUnitScale as _ApplyUnitScale
from .xform.reset_pivot import ResetPivot as _ResetPivot


class FluxValidatorPluginCheckUSDExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[omni.flux.validator.plugin.check.usd] Startup")
        _get_factory_instance().register_plugins(
            [
                _GeneratePBRMaterial,
                _PrintPrims,
                _ClearUnassignedMaterial,
                _DefaultMaterial,
                _ValueMapping,
                _MaterialShaders,
                _AddInvertedUVAttr,
                _AddVertexIndicesToGeomSubsets,
                _ForcePrimvarToVertexInterpolation,
                _StripExtraAttributes,
                _Triangulate,
                _DefaultPrim,
                _WrapRootPrims,
                _RelativeReferences,
                _RelativeAssetPaths,
                _ConvertToDDS,
                _ConvertToOctahedral,
                _ApplyUnitScale,
                _ResetPivot,
                _MassTexturePreview,
                _GenerateThumbnail,
            ]
        )

    def on_shutdown(self):
        carb.log_info("[omni.flux.validator.plugin.check.usd] Shutdown")
        _get_factory_instance().unregister_plugins(
            [
                _GeneratePBRMaterial,
                _PrintPrims,
                _ClearUnassignedMaterial,
                _DefaultMaterial,
                _ValueMapping,
                _MaterialShaders,
                _AddInvertedUVAttr,
                _AddVertexIndicesToGeomSubsets,
                _ForcePrimvarToVertexInterpolation,
                _StripExtraAttributes,
                _Triangulate,
                _DefaultPrim,
                _WrapRootPrims,
                _RelativeReferences,
                _RelativeAssetPaths,
                _ConvertToDDS,
                _ConvertToOctahedral,
                _ApplyUnitScale,
                _ResetPivot,
                _MassTexturePreview,
                _GenerateThumbnail,
            ]
        )
