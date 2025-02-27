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

# Original module is omni.kit.property.usd/placeholder_attribute.py

__all__ = ["PlaceholderAttribute"]

import carb
from pxr import Sdf, UsdGeom, UsdShade


class PlaceholderAttribute:
    """This is a placeholder for Usd.Attribute object as those objects have to be attached to a Usd.Prim object.
    This conforms to enough of the Usd.Attribute API to be used by omni.kit.property.usd widgets.

    The purpose of this is so custom Usd.Attributes can be created and displayed by widgets but don't actually effect
    the Usd.Prim until user modifies a value, then the `CreateAttribute` function will be called and a real
    Usd.Attribute will be created using values from this class.
    """

    # these functions simulate Usd.Prim so need to use uppercase
    def __init__(self, name, prim=None, metadata=None):
        """Initializes the PlaceholderAttribute.

        Args:
            name (str): Name of the mock Usd.Prim.
            prim: (Usd.Prim): Prim attribute is attached to.
            metadata: (dict): metadata of mock attribute."""
        self._name = name
        self._prim = prim
        self._metadata = metadata if metadata else {}

    def Get(self, time_code=0):  # noqa: N802
        """Mock Usd.Attribute function"""
        if self._metadata:
            custom_data = self._metadata.get("customData")
            if custom_data is not None and "default" in custom_data:
                return custom_data["default"]

            default = self._metadata.get("default")
            if default is not None:
                return default

        carb.log_warn("PlaceholderAttribute.Get() customData.default or default not found in metadata")
        return None

    def GetPath(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        if self._prim:
            return self._prim.GetPath()
        return None

    def ValueMightBeTimeVarying(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        return False

    def GetMetadata(self, token):  # noqa: N802
        """Mock Usd.Attribute function"""
        if token in self._metadata:
            return self._metadata[token]
        return False

    def GetAllMetadata(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        return self._metadata

    def GetPrim(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        return self._prim

    def CreateAttribute(self):  # noqa: N802
        """Create the Usd.Attribute in the Usd.Prim"""
        try:
            if not self._name:
                carb.log_warn("PlaceholderAttribute.CreateAttribute() error no attribute name")
                return None

            if not self._prim:
                carb.log_warn("PlaceholderAttribute.CreateAttribute() error no target prim")
                return None

            type_name_key = self._metadata.get(Sdf.PrimSpec.TypeNameKey)
            if not type_name_key:
                carb.log_warn("PlaceholderAttribute.CreateAttribute() error TypeNameKey")
                return None

            type_name = Sdf.ValueTypeNames.Find(type_name_key)

            metadata = {}
            # By default don't add metadata to attributes on shader prims
            if not self._prim.IsA(UsdShade.Shader):
                metadata = self._metadata.copy()

            if self._name.startswith("primvars:"):
                attribute = UsdGeom.PrimvarsAPI(self._prim).CreatePrimvar(self._name[9:], type_name).GetAttr()
            elif self._name.startswith("inputs:"):
                shader = UsdShade.Shader(self._prim)
                attribute = shader.CreateInput(self._name[7:], type_name).GetAttr()

                # add colorSpace metadata to shader input parameters, if it exists.
                if "colorSpace" in self._metadata:
                    metadata["colorSpace"] = self._metadata["colorSpace"]
            else:
                attribute = self._prim.CreateAttribute(self._name, type_name, custom=False)

            filters = {"customData", "displayName", "displayGroup", "documentation"}
            if attribute:
                for key, item in metadata.items():
                    if key not in filters:
                        attribute.SetMetadata(key, item)
                attribute.Set(self.Get())

            return attribute
        except Exception as exc:  # pylint: disable=broad-exception-caught  # pragma: no cover
            carb.log_warn(f"PlaceholderAttribute.CreateAttribute() error {exc}")
        return None  # pragma: no cover

    def HasAuthoredConnections(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        return False

    def IsHidden(self):  # noqa: N802
        """Mock Usd.Attribute function"""
        return False

    def GetPropertyStack(self, *args, **kwargs):  # noqa: N802
        return []
