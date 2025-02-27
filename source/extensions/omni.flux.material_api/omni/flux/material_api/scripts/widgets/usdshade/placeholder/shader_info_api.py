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

__all__ = ["ShaderInfoAPI"]

import ast
import math
from typing import Any, List, Optional

import carb
from omni.kit.window.preferences import PERSISTENT_SETTINGS_PREFIX
from pxr import Sdf, Sdr, Usd, UsdShade

from ..input_placeholder_attribute import UsdShadeInputPlaceholderAttribute
from ..utils import deep_dict_update, get_sdr_shader_node_for_prim, get_sdr_shader_property_default_value
from .placeholder import UsdShadePropertyPlaceholder


class ShaderInfoAPI:
    """
    An API for querying the properties for a UsdShade prim.

    If the prim is of type UsdShade.Nodegraph, the input/output properties of the prim are returned.

    If the prim is of type UsdShade.Shader
        1. Properties are first gathered from the Sdr registry from the underlying Sdr.ShaderNode
        2. In the case where the property exists on the UsdShade.Shader prim it's metadata is over'd
            with the metadata returned from the SDR.

    The returned properties are UsdShadePropertyPlaceholder objects.  This allows consumers of this API
    to iterate over a UsdShade prims properties without having to make a distinction between whether
    the property is one that exists on the stage (UsdAttribute) vs a Sdr.ShaderProperty.

    ToDo: it might make sense to put this into UsdMdl or even AoUsd to provide a means for a user to query
        information about all of the parmeters on a shader
      right now someone would need to do this in two parts:
      1. Using the UsdShade API's - this would return only those parameters that have an underlying property
          on the stage.
      2. Using the SDR API's - this returns information on all of the available parameters.
    """

    RENDER_CONTEXTS_SETTING_PATH = PERSISTENT_SETTINGS_PREFIX + "/app/hydra/material/renderContexts"

    def __init__(self, prim: Usd.Prim, overlay_property_metadata: Optional[bool] = True):
        self._prim = prim
        self._overlay_property_metadata = overlay_property_metadata
        self._prim_path = prim.GetPath()
        self._prim_properties_metadata = {p.GetName(): p.GetAllMetadata() for p in prim.GetProperties()}
        self._sdr_node = None
        self._usdshade_prim = None

        if self._prim.IsA(UsdShade.Shader):
            self._usdshade_prim = UsdShade.Shader(prim)
            self._sdr_node = get_sdr_shader_node_for_prim(prim, warn_on_substitution=True)

            if not self._sdr_node:  # pragma: no cover
                carb.log_warn(f"Cannot get Sdr.ShaderNode for prim at: '{self._prim_path}'")

        elif self._prim.IsA(UsdShade.NodeGraph):
            self._usdshade_prim = UsdShade.NodeGraph(prim)

        else:  # pragma: no cover
            carb.log_error(f"Expected UsdShade.Shader or UsdShade.NodeGraph prim at: '{self._prim_path}'")

    def get_node_properties(self) -> List[UsdShadePropertyPlaceholder]:
        """
        Create and return an UsdShadePropertyPlaceholder's for this nodes node level properties.
            e.g. description
        """

        if not self._sdr_node:  # pragma: no cover
            return []

        node_help = self._sdr_node.GetHelp()
        if not node_help:
            return []

        metadata = {Sdf.AttributeSpec.DefaultValueKey: node_help, Sdf.AttributeSpec.DisplayGroupKey: "Description"}

        return [UsdShadePropertyPlaceholder("Description", metadata, True)]

    def get_input_properties(
        self, property_name_filter: Optional[List[str]] = None
    ) -> List[UsdShadePropertyPlaceholder]:
        """
        Create and return UsdShadePropertyPlaceholder's for this nodes input properties
        """

        if self._sdr_node:
            sdr_shader_properties = [self._sdr_node.GetInput(name) for name in self._sdr_node.GetInputNames()]
            return self._get_placeholders(sdr_shader_properties, UsdShade.Tokens.inputs, property_name_filter)

        # If we are here that means we weren't able to retrive an SdrShaderNode from the SDR registry, which might be
        # the case if we are loading a scene file that contains shaders from a render context we don't support,
        # e.g. Arnold or Renderman In this case we will create placeholders from the input attributes on the
        # UsdShade.shader
        input_attributes = [usdshade_input.GetAttr() for usdshade_input in self._usdshade_prim.GetInputs()]
        return self._get_placeholders_for_attrs(input_attributes)

    def get_output_properties(
        self, property_name_filter: Optional[List[str]] = None
    ) -> List[UsdShadePropertyPlaceholder]:
        """
        Create and return  UsdShadePropertyPlaceholder's for this nodes output properties
        """
        if self._prim.IsA(UsdShade.Material):
            return self._get_material_output_properties(property_name_filter)

        if self._sdr_node:
            sdr_shader_properties = [self._sdr_node.GetOutput(name) for name in self._sdr_node.GetOutputNames()]
            return self._get_placeholders(sdr_shader_properties, UsdShade.Tokens.outputs, property_name_filter)

        # If we are here that means we weren't able to retrive an SdrShaderNode from the SDR registry, which might be
        # the case if we are loading a scene file that contains shaders from a render context we don't support,
        # e.g. Arnold or Renderman In this case we will create placeholders from the output attributes on the
        # UsdShade.shader
        output_attributes = [
            usdshade_output.GetAttr() for usdshade_output in self._usdshade_prim.GetOutputs()
        ]  # pragma: no cover
        return self._get_placeholders_for_attrs(output_attributes)  # pragma: no cover

    def _get_material_output_properties(
        self, property_name_filter: Optional[List[str]] = None
    ) -> List[UsdShadePropertyPlaceholder]:
        """
        Special handling for UsdShade.Material prim outputs.
        """
        import omni.UsdMdl

        placeholder_properties = []

        settings = carb.settings.get_settings()
        render_contexts = settings.get(self.RENDER_CONTEXTS_SETTING_PATH)

        for render_context in render_contexts:
            context_name = render_context
            if context_name != UsdShade.Tokens.universalRenderContext:
                context_name += Sdf.Path.namespaceDelimiter

            for suffix in [UsdShade.Tokens.displacement, UsdShade.Tokens.surface, UsdShade.Tokens.volume]:
                full_name = f"{UsdShade.Tokens.outputs}{context_name}{suffix}"
                if property_name_filter and full_name not in property_name_filter:
                    continue

                metadata = {
                    Sdf.PrimSpec.TypeNameKey: Sdf.ValueTypeNames.Token,
                    Sdr.PropertyMetadata.RenderType: omni.UsdMdl.Types.Struct,
                    UsdShade.Tokens.sdrMetadata: {
                        omni.UsdMdl.Metadata.StructType: omni.UsdMdl.StructTypes.Material,
                        omni.UsdMdl.Metadata.Symbol: "::material",
                    },
                }

                placeholder_properties.append(UsdShadePropertyPlaceholder(full_name, metadata, False))

        return placeholder_properties

    def _get_placeholders_for_attrs(self, attributes: List[Usd.Attribute]) -> List[UsdShadePropertyPlaceholder]:
        placeholder_properties = []

        for attribute in attributes:
            name = attribute.GetName()
            property_metadata = self._prim_properties_metadata.get(name, {})
            property_metadata["readonly"] = True
            placeholder = UsdShadePropertyPlaceholder(name, property_metadata, True)

            if not placeholder.GetDisplayName():
                placeholder.SetDisplayName(attribute.GetBaseName())

            display_group = placeholder.GetDisplayGroup()

            if name.startswith(UsdShade.Tokens.outputs):
                if not display_group.startswith("Outputs:"):
                    display_group = f"Outputs:{display_group}"

            elif name.startswith(UsdShade.Tokens.inputs) and not display_group.startswith("Inputs:"):
                display_group = f"Inputs:{display_group}" if display_group else "Inputs"

            placeholder.SetDisplayGroup(display_group)

            placeholder_properties.append(placeholder)

        return placeholder_properties

    def _get_placeholders(
        self,
        sdr_shader_properties: List[Sdr.ShaderProperty],
        property_name_prefix: str,
        property_name_filter: Optional[List[str]] = None,
    ) -> List[UsdShadePropertyPlaceholder]:
        """
        Create and return a list of UsdShadePropertyPlaceholder's from the input list of Sdr.ShaderProperty's.

        If the underlying prim has a property of the same name, we optionally overlay it's metadata on top of the
        metadata we gathered from the SDR, if we have conflicting values, the metadata on the prim "wins"/takes
        precedence
        """

        # filter properties
        filtered = [
            prop for prop in sdr_shader_properties if not property_name_filter or prop.GetName() in property_name_filter
        ]

        placeholder_properties = []
        for sdr_shader_property in filtered:
            metadata = self._get_property_metadata(sdr_shader_property)

            full_name = f"{property_name_prefix}{sdr_shader_property.GetName()}"

            # overlay the metadata from property on the underlying prim if requested
            if self._overlay_property_metadata:
                metadata = deep_dict_update(metadata, self._prim_properties_metadata.get(full_name, {}))

            placeholder_properties.append(UsdShadePropertyPlaceholder(full_name, metadata, True))

        return placeholder_properties

    def _get_property_metadata(self, sdr_shader_property: Sdr.ShaderProperty) -> dict:
        """
        Convert Sdr.ShaderProperty metadata into property metadata.
        """

        def set_display_group(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            page = sdr_shader_property.GetPage()
            display_group = ""
            if page:
                display_group = page
                del metadata[Sdr.PropertyMetadata.Page]

            if sdr_shader_property.IsOutput():
                if not display_group.startswith("Outputs"):
                    display_group = f"Outputs:{display_group}" if display_group else "Outputs"

            elif not display_group.startswith("Inputs"):
                display_group = f"Inputs:{display_group}" if display_group else "Inputs"

            metadata[Sdf.AttributeSpec.DisplayGroupKey] = display_group

        def set_display_name(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            display_name = sdr_shader_property.GetName()

            label = sdr_shader_property.GetLabel()
            if label:
                display_name = label
                del metadata[Sdr.PropertyMetadata.Label]

            metadata[Sdf.AttributeSpec.DisplayNameKey] = display_name

        def set_type_name(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            ndr_type_indicator = sdr_shader_property.GetTypeAsSdfType()
            type_name = ndr_type_indicator[1]
            if not type_name:
                type_name = str(ndr_type_indicator[0])

            metadata[Sdf.PrimSpec.TypeNameKey] = type_name

        def set_default_value(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            default_value = get_sdr_shader_property_default_value(sdr_shader_property, metadata)
            metadata[Sdf.AttributeSpec.CustomDataKey][Sdf.AttributeSpec.DefaultValueKey] = default_value

        def set_allowed_tokens(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            options = sdr_shader_property.GetOptions()
            if not options:
                return

            metadata["allowedTokens"] = [kv[0] for kv in options]

            if metadata[Sdf.PrimSpec.TypeNameKey] == Sdf.ValueTypeNames.Int:
                metadata[UsdShade.Tokens.sdrMetadata][Sdr.PropertyMetadata.Options] = [
                    (kv[0], int(kv[1])) for kv in options
                ]

        def literal_eval(sdr_shader_property: Sdr.ShaderProperty, expr: str) -> Any:
            """
            Evaulate the input expression if possible returning a Python object.
            Return original expression on failure.
            """
            if not isinstance(expr, str):  # pragma: no cover
                carb.log_warn(
                    f"Unable to evaluate '{expr}' for Sdr.ShaderProperty: '{sdr_shader_property.GetName()}' "
                    f"for prim: '{self._prim_path}'. Excepted string, received: '{type(expr)}'."
                )
                return expr

            if expr.startswith(("[", "{")) or expr.isnumeric():
                try:
                    value = ast.literal_eval(expr)

                except Exception as e:  # pylint: disable=broad-exception-caught  # pragma: no cover
                    carb.log_warn(
                        f"Unable to evaluate '{expr}' for Sdr.ShaderProperty: '{sdr_shader_property.GetName()}' "
                        f"for prim: '{self._prim_path}'. Error: '{e}'"
                    )
                    return expr

            else:
                value = expr

            if isinstance(value, (dict, list, tuple, str, int, float, bool, type(None))):
                return value

            carb.log_warn(
                f"Unable to evaluate '{expr}' for Sdr.ShaderProperty: '{sdr_shader_property.GetName()}' "
                f"for prim: '{self._prim_path}'. Evaluated data is of unexpected type: '{type(value)}'."
            )  # pragma: no cover
            return value

        def set_sdr_metadata(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            """
            Sdr metadata will contain objects that can be evaled to Python objects, e.g.
                hard_range -> {'max':1,'min':0}
            """
            import omni.UsdMdl

            for token in omni.UsdMdl.GetAllMetadataTokens():
                if token in metadata:
                    metadata[UsdShade.Tokens.sdrMetadata][token] = literal_eval(sdr_shader_property, metadata[token])
                    del metadata[token]

        def promote_hints(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            """
            Hints will contain objects that can be evaled to Python objects, e.g.
                hard_range -> {'max':1,'min':0}
            """

            def materialx_uiminmax(range_type: str, min_key: str, max_key: str, hints: dict) -> dict:
                """
                Set range hints for Material-X.
                Note we only set the hint if both values exist, I have noticed cases where only one value is present
                e.g.
                ND_UsdPreviewSurface_surfaceShader ior parameter has the following so only soft_range would be set.
                uimin --> 0.0
                uisoftmax --> 3.0
                uisoftmin --> 1.0
                """
                if (min_key in hints) and (max_key in hints):
                    min_val = tuple(float(v) for v in hints[min_key].split(","))
                    min_val = min_val if len(min_val) > 1 else min_val[0]

                    max_val = tuple(float(v) for v in hints[max_key].split(","))
                    max_val = max_val if len(max_val) > 1 else max_val[0]

                    hints[range_type] = {"min": min_val, "max": max_val}

                return hints

            hints = sdr_shader_property.GetHints()
            if not hints:
                return

            if self._sdr_node.GetSourceType() == "mtlx":
                hints = materialx_uiminmax("hard_range", "uimin", "uimax", hints)
                hints = materialx_uiminmax("soft_range", "uisoftmin", "uisoftmax", hints)

            for k, v in hints.items():
                value = v
                if isinstance(value, str):
                    value = literal_eval(sdr_shader_property, value)

                key = k
                if k == "hard_range":
                    key = "range"

                    # for int values with hard_range of [0, 1] set the widget type to checkbox and skip setting
                    # the custom data.
                    if (
                        (metadata[Sdf.PrimSpec.TypeNameKey] == Sdf.ValueTypeNames.Int)
                        and isinstance(value, dict)
                        and (value.get("min", None) == 0)
                        and (value.get("max", None) == 1)
                    ):
                        metadata[Sdr.PropertyMetadata.Widget] = "checkBox"
                        continue

                metadata[Sdf.AttributeSpec.CustomDataKey][key] = value

        def set_color_space(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            """
            Convert the MDL tex::gamma_mode value to a color space string.
            """
            import omni.UsdMdl

            add_color_space = Sdr.PropertyMetadata.IsAssetIdentifier in metadata

            render_type = metadata.get(Sdr.PropertyMetadata.RenderType, None)
            if render_type and (render_type != omni.UsdMdl.Types.Texture2d):
                add_color_space = False

            if not add_color_space:
                return

            gamma = metadata[UsdShade.Tokens.sdrMetadata].get(omni.UsdMdl.Metadata.TextureGamma, 0)
            if gamma is None:
                return

            converter = [(0, "auto"), (1, "raw"), (2.2, "sRGB")]
            color_space = next(
                (item[1] for item in converter if math.isclose(item[0], float(gamma), rel_tol=1e-05)), None
            )

            if not color_space:  # pragma: no cover
                color_space = "auto"
                message = (
                    f"The default 'gamma' value for Sdr.ShaderProperty: '{sdr_shader_property.GetName()}' "
                    f"on prim: '{self._prim_path}' contains an unknown value: '{gamma}' and cannot be mapped to a "
                    f"color space name, setting to 'auto'."
                )
                carb.log_warn(message)

            metadata["colorSpace"] = color_space

            # store the default value as metadata so the MetadataObjectModel is aware of what the default value is.
            metadata[Sdf.AttributeSpec.CustomDataKey][f"colorSpace_{Sdf.AttributeSpec.DefaultValueKey}"] = color_space

        def set_hidden(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            metadata[Sdf.AttributeSpec.HiddenKey] = (
                ("hidden" in metadata)
                or ("unused" in metadata)
                or ("hidden" in metadata[Sdf.AttributeSpec.CustomDataKey])
                or ("unused" in metadata[Sdf.AttributeSpec.CustomDataKey])
            )

        def set_documentation(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            help_text = sdr_shader_property.GetHelp()
            if help_text:
                metadata[Sdf.AttributeSpec.DocumentationKey] = help_text
                del metadata[Sdr.PropertyMetadata.Help]

        def set_placeholder_class(sdr_shader_property: Sdr.ShaderProperty, metadata: dict) -> None:
            """
            By default 'omni.kit.property.usd.UsdBase' constructs placeholder objects of type:
                'omni.kit.property.usd.PlaceholderAttribute'.
            However it's possible that for this property no information has been serialzed to the stage.
            This will result in widget errors due to not being able to retrieve property information: value,
            metadata etc.

            Setting the placeholder_class metadata will cause 'omni.kit.property.usd.UsdBase' to construct
            placeholder objects of type: 'UsdShadeInputPlaceholderAttribute' which is what allows us to display
            properties in the UI that do not exist on the stage. See the 'UsdShadeInputPlaceholderAttribute' class
            documentation for further information/explanation.
            """
            metadata["placeholder_class"] = UsdShadeInputPlaceholderAttribute

        property_metadata = sdr_shader_property.GetMetadata()
        metadata = property_metadata

        # Is this a custom property
        metadata[Sdf.AttributeSpec.CustomKey] = False

        metadata["variability"] = Sdf.VariabilityVarying

        metadata[UsdShade.Tokens.sdrMetadata] = {}
        metadata[Sdf.AttributeSpec.CustomDataKey] = {}

        set_display_group(sdr_shader_property, metadata)
        set_display_name(sdr_shader_property, metadata)
        set_type_name(sdr_shader_property, metadata)
        set_sdr_metadata(sdr_shader_property, metadata)
        set_documentation(sdr_shader_property, metadata)
        set_default_value(sdr_shader_property, metadata)

        if not sdr_shader_property.IsOutput():
            set_allowed_tokens(sdr_shader_property, metadata)
            promote_hints(sdr_shader_property, metadata)
            set_hidden(sdr_shader_property, metadata)
            set_color_space(sdr_shader_property, metadata)
            set_placeholder_class(sdr_shader_property, metadata)

        return metadata
