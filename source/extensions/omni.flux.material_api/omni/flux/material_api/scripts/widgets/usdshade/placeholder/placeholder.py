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

__doc__ = """This module defines the UsdShadePropertyPlaceholder class, which acts as a stand-in for Usd.Attribute
for use in UsdShade widgets without serializing default properties and metadata to USD files."""

__all__ = ["UsdShadePropertyPlaceholder"]

from typing import Any

import omni.UsdMdl
from pxr import Sdf, Sdr, Usd, UsdShade


class UsdShadePropertyPlaceholder:
    """This class serves as a stand-in for Usd.Attribute within the context of various UsdShade widgets.

    By default, the UsdPropertiesWidget widget is driven by Usd.Attributes, and if we want to display properties for
    a prim, then those properties need to exist on the stage. This is problematic for UsdShade properties as we don't
    want to serialize properties whose values have not been changed from their default. We also don't want to
    serialize all of the corresponding metadata these properties may contain, doing so results in unnecessarily
    bloated USD files. Therefore, this class can serve as a stand-in. It contains all of the necessary functions
    required by the UI widgets and allows us to display all of the parameters for a UsdShade.Shader that are defined
    via an Sdr.ShaderNode definition without having to store them on the stage and/or session layer first. These
    objects also provide a convenient means for overwriting metadata used to drive the display without having to
    serialize.

    Args:
        name (str): The name of the property.
        metadata (dict | None): The metadata associated with the property.
        from_sdr (bool): Indicates whether the property is from SDR."""

    MATERIAL_INPUT_SUFFIX = "__material_input__"

    def __init__(self, name: str, metadata: dict | None, from_sdr: bool = False):
        """Initializer for the UsdShadePropertyPlaceholder class."""
        self._name = name
        self._metadata = metadata if metadata else {}
        self._from_sdr = from_sdr

    @classmethod
    def PlaceholderFromAttribute(cls, usd_attribute: Usd.Attribute):  # noqa: N802  # pragma: no cover
        """
        Create a UsdShadePropertyPlaceholder from a Usd.Attribute.

        Args:
            usd_attribute (Usd.Attribute)

        Returns:
            UsdShadePropertyPlaceholder"""
        return cls(usd_attribute.GetPath().name, usd_attribute.GetAllMetadata())

    def GetPropertyType(self):  # noqa: N802
        """Gets the type of the property represented by the placeholder.

        Returns:
            :obj:`Usd.Attribute`: The type of property."""
        return Usd.Attribute

    def IsHidden(self) -> bool:  # noqa: N802
        """Checks if the property is hidden.

        Returns:
            bool: True if the property is hidden, False otherwise."""
        return self._metadata.get(Sdf.AttributeSpec.HiddenKey, False)

    def GetName(self) -> str:  # noqa: N802
        """Retrieves the name of the property.

        Returns:
            str: The name of the property."""
        return self._name

    def SetName(self, name: str) -> None:  # noqa: N802
        """Sets the name of the property.

        Args:
            name (str): The new name for the property."""
        self._name = name

    def GetColorSpace(self) -> str | None:  # noqa: N802  # pragma: no cover
        """Gets the color space of the property.

        Returns:
            str | None: The color space of the property, or None if not set."""
        return self._metadata.get("colorSpace", None)

    def GetDisplayGroup(self) -> str:  # noqa: N802
        """Gets the display group of the property.

        Returns:
            str: The display group of the property."""
        return self._metadata.get(Sdf.AttributeSpec.DisplayGroupKey, "")

    def GetDisplayName(self) -> str:  # noqa: N802
        """Gets the display name of the property.

        Returns:
            str: The display name of the property."""
        return self._metadata.get(Sdf.AttributeSpec.DisplayNameKey, "")

    def GetMetadata(self, key: str) -> Any | None:  # noqa: N802  # pragma: no cover
        """Retrieves the metadata value for the given key.

        Args:
            key (str): The metadata key to query.

        Returns:
            Any | None: The value of the given metadata key, or None if not set."""
        return self._metadata.get(key, None)

    def GetAllMetadata(self) -> dict:  # noqa: N802
        """Retrieves all metadata associated with the property.

        Returns:
            dict: A dictionary of all metadata."""
        return self._metadata

    def GetTypeName(self) -> str | None:  # noqa: N802
        """Gets the type name of the property.

        Returns:
            str | None: The type name of the property, or None if not set."""
        return self._metadata.get(Sdf.PrimSpec.TypeNameKey, None)

    def SetMetadata(self, key: str, value: Any) -> None:  # noqa: N802
        """Sets the metadata key to the given value.

        Args:
            key (str): The metadata key.
            value (Any): The value to associate with the key."""
        self._metadata[key] = value

    def SetDisplayName(self, value: str) -> None:  # noqa: N802
        """Sets the display name of the property.

        Args:
            value (str): The new display name for the property."""
        self._metadata[Sdf.AttributeSpec.DisplayNameKey] = value

    def SetDisplayGroup(self, value: str) -> None:  # noqa: N802
        """Sets the display group of the property.

        Args:
            value (str): The new display group for the property."""
        self._metadata[Sdf.AttributeSpec.DisplayGroupKey] = value

    def SetHidden(self, value: bool) -> None:  # noqa: N802
        """Sets the hidden state of the property.

        Args:
            value (bool): The new hidden state for the property."""
        self._metadata[Sdf.AttributeSpec.HiddenKey] = value

    def SetColorSpace(self, value: str) -> None:  # noqa: N802  # pragma: no cover
        """Sets the color space of the property.

        Args:
            value (str): The new color space for the property."""
        self._metadata["colorSpace"] = value

    def GetDefaultValue(self) -> Any | None:  # noqa: N802  # pragma: no cover
        """Gets the default value of the property.

        Returns:
            Any | None: The default value of the property, or None if not set."""
        custom_data = self._metadata.get(Sdf.AttributeSpec.CustomDataKey, {})
        return custom_data.get(Sdf.AttributeSpec.DefaultValueKey, None)

    def GetEnableIfCondition(self) -> str | None:  # noqa: N802  # pragma: no cover
        """Gets the enable-if condition for the property.

        Returns:
            str | None: The enable-if condition, or None if not set."""
        custom_data = self._metadata.get(Sdf.AttributeSpec.CustomDataKey, {})
        enable_if = custom_data.get("enable_if", {})
        return enable_if.get("condition", None)

    def HasMetadata(self, key) -> bool:  # noqa: N802  # pragma: no cover
        """Checks if the specified metadata key is present.

        Args:
            key (str): The metadata key to check.

        Returns:
            bool: True if the key is present, False otherwise."""
        return key in self._metadata

    def FromSdr(self) -> bool:  # noqa: N802
        """Indicates if the property placeholder was created from an Sdr node.

        Returns:
            bool: True if created from Sdr, False otherwise."""
        return self._from_sdr

    def GetAllSdrMetadata(self) -> dict:  # noqa: N802  # pragma: no cover
        return self._metadata.get(UsdShade.Tokens.sdrMetadata, {})

    def GetSdrMetadata(self, key, default_value=None) -> Any | None:  # noqa: N802  # pragma: no cover
        return self.GetAllSdrMetadata().get(key, default_value)

    def GetRenderType(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetMetadata(Sdr.PropertyMetadata.RenderType)

    def GetMdlStructType(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetSdrMetadata(omni.UsdMdl.Metadata.StructType)

    def GetMdlSymbol(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetSdrMetadata(omni.UsdMdl.Metadata.Symbol)

    def GetMdlArrayElementType(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetSdrMetadata(omni.UsdMdl.Metadata.ArrayElementType)

    def GetMdlModifier(self) -> str:  # noqa: N802  # pragma: no cover
        return self.GetSdrMetadata(omni.UsdMdl.Metadata.Modifier, omni.UsdMdl.TypeModifiers.Varying)

    def GetDocumentation(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetMetadata("documentation")

    def GetConnectability(self) -> str | None:  # noqa: N802  # pragma: no cover
        return self.GetMetadata("connectability")

    def GetHidden(self) -> bool:  # noqa: N802  # pragma: no cover
        return bool(self.GetMetadata(Sdf.AttributeSpec.HiddenKey))
