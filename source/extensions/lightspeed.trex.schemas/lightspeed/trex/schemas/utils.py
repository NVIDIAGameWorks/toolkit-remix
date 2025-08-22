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

__all__ = ["get_schema_prim"]

from pxr import Sdf, Usd

from .extension import get_schema_registry


def _get_schema_prim(schema_usd_path: str, prim_path: str) -> tuple[Sdf.Layer, Sdf.PrimSpec]:
    """
    Returns the schema prim provided the source schema path and prim path for its definition.
    """
    layer = Sdf.Layer.FindOrOpen(schema_usd_path)
    if not layer:
        raise ValueError(f"Schema layer could not be loaded.Layer '{schema_usd_path}' not found.")
    prim_spec = layer.GetPrimAtPath(prim_path)
    if not prim_spec:
        raise ValueError(f"Prim '{prim_path}' not found in schema file.")

    # must return the layer obj as well in order to keep the prim_spec valid
    return layer, prim_spec


def get_schema_prim(schema_name: str) -> tuple[Sdf.Layer, Usd.Prim]:
    """
    Returns the prim for the given schema name.
    """
    source_path, prim_path = get_schema_registry().lookup_schema(schema_name)
    return _get_schema_prim(source_path, prim_path)
