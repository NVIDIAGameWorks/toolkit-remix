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

from typing import TYPE_CHECKING, Optional, Tuple

import carb
import omni.kit
import omni.usd
from pxr import Sdf, Usd, UsdShade

from .mapping import Converters as _ConvertersEnum

if TYPE_CHECKING:
    from .base.converter_base import ConverterBase
    from .utils import SupportedShaderInputs as _SupportedShaderInputs


class MaterialConverterCore:
    @staticmethod
    async def convert(context_name: str, converter: "ConverterBase") -> Tuple[bool, Optional[str], bool]:
        """
        Convert the material

        Args:
            context_name: the context to use
            converter: the converter to use

        Returns:
            Success, message, skipped or not
        """
        context = omni.usd.get_context(context_name)
        if not context:
            return False, f"Unable to get the context with name {context_name}", False
        stage = context.get_stage()
        if not stage:
            return False, f"Unable to get the stage in context with name {context_name}", False

        root_layer = stage.GetRootLayer()

        # If the input prim is not defined on this layer, we don't need to convert anything
        prim_spec = root_layer.GetPrimAtPath(converter.input_material_prim.GetPath())
        if not prim_spec:
            return True, f"Input material prim was not defined on layer: '{root_layer.identifier}'", True

        # Get a valid prim path for a temporary output prim
        output_material_path = Sdf.Path(
            omni.usd.get_stage_next_free_path(
                stage,
                str(converter.input_material_prim.GetPath()),
                False,
            )
        )

        has_source_prop_spec = True

        input_shader_prim = None
        input_shader = omni.usd.get_shader_from_material(converter.input_material_prim, get_prim=False)
        if input_shader:
            has_source_prop_spec = bool(
                root_layer.GetPropertyAtPath(input_shader.GetImplementationSourceAttr().GetPath())
            ) or bool(root_layer.GetPropertyAtPath(input_shader.GetIdAttr().GetPath()))

            input_shader_prim = input_shader.GetPrim()
            if not input_shader_prim:
                return False, "Unable to fetch input material shader prim", False

        output_shader_prim = None
        if has_source_prop_spec:
            # If the material was defined on this layer, create a definition prim
            output_shader_prim = MaterialConverterCore._create_material_definition_prim(
                context_name, converter, str(output_material_path)
            )
        elif input_shader_prim:
            # If the material was defined on another layer, create a temporary overrides prim
            output_shader_prim = MaterialConverterCore._create_material_override_prim(
                context_name,
                str(output_material_path),
                str(output_material_path.AppendChild(input_shader_prim.GetPath().name)),
            )

        if not output_shader_prim:
            return False, "Unable to fetch output material shader prim", False

        if input_shader:
            # TODO Bug OM-90672: `load_mdl_parameters_for_prim_async` will not work with non-default contexts
            # In the meantime, we create attributes on the temporary material and then set them
            # When the bug is resolved, cleanup all the material creation & alt translation functions
            await MaterialConverterCore._create_material_attributes(
                context_name, converter, input_shader_prim, output_shader_prim
            )
            # await MaterialConverterCore._convert_material_attributes(
            #     context_name, converter, input_shader_prim, output_shader_prim
            # )

        input_material_path = converter.input_material_prim.GetPath()

        # Delete the original material
        omni.kit.commands.execute(
            "RemovePrimSpecCommand",
            layer_identifier=root_layer.identifier,
            prim_spec_path=input_material_path,
            usd_context=context_name,
        )

        # Rename the temporary prim to the original name.
        # Using commands here will increment the name and cause the replacement to fail
        root_layer.GetPrimAtPath(output_material_path).name = input_material_path.name

        if has_source_prop_spec:
            # Make sure we fix the connections to point to the newly renamed prim
            final_material_prim = stage.GetPrimAtPath(input_material_path)
            for attr in final_material_prim.GetAttributes():
                connections = attr.GetConnections()
                if not attr.GetName().startswith("output") or not connections:
                    continue
                for conn in connections:
                    parent_path = conn.GetPrimPath().GetParentPath()
                    prim_name = conn.GetPrimPath().name
                    valid_path = (
                        parent_path.ReplaceName(input_material_path.name)
                        .AppendChild(prim_name)
                        .AppendProperty(conn.name)
                    )
                    attr.RemoveConnection(conn)
                    attr.AddConnection(valid_path)
        else:
            # If the layer did not contain a definition, make sure we set it as an override now that it's ready
            final_material_prim_spec = root_layer.GetPrimAtPath(input_material_path)
            if not final_material_prim_spec:
                return False, "Unable to find the converted material prim", False
            final_material_prim = stage.GetPrimAtPath(input_material_path)
            shader_prim = omni.usd.get_shader_from_material(final_material_prim, get_prim=True)

            if not shader_prim:
                return False, "Unable to find the converted shader prim", False
            final_shader_prim_spec = root_layer.GetPrimAtPath(input_material_path.AppendChild(shader_prim.GetName()))
            if not final_shader_prim_spec:
                return False, "Unable to find the converted shader prim", False

            final_material_prim_spec.specifier = Sdf.SpecifierOver
            final_shader_prim_spec.specifier = Sdf.SpecifierOver

        return (
            True,
            f"Completed prim '{final_material_prim.GetPath()}' conversion on layer {root_layer.identifier}",
            False,
        )

    @staticmethod
    def _create_material_definition_prim(context_name: str, converter: "ConverterBase", output_material_path: str):
        stage = omni.usd.get_context(context_name).get_stage()

        omni.kit.commands.execute(
            "CreateMdlMaterialPrim",
            mtl_url=converter.output_mdl_subidentifier + ".mdl",
            mtl_name=converter.output_mdl_subidentifier,
            mtl_path=output_material_path,
            stage=stage,
            context_name=context_name,
        )

        output_material_prim = stage.GetPrimAtPath(output_material_path)
        return omni.usd.get_shader_from_material(output_material_prim, get_prim=True)

    @staticmethod
    def _create_material_override_prim(context_name: str, output_material_path: str, output_shader_path: str):
        stage = omni.usd.get_context(context_name).get_stage()

        omni.kit.commands.execute(
            "CreatePrimCommand",
            prim_path=output_material_path,
            prim_type="Material",
            select_new_prim=False,
            context_name=context_name,
        )
        omni.kit.commands.execute(
            "CreatePrimCommand",
            prim_path=output_shader_path,
            prim_type="Shader",
            select_new_prim=False,
            context_name=context_name,
        )

        return stage.GetPrimAtPath(output_shader_path)

    @staticmethod
    async def _convert_material_attributes(
        context_name: str, converter: "ConverterBase", input_shader_prim: "Usd.Prim", output_shader_prim: "Usd.Prim"
    ):
        context = omni.usd.get_context(context_name)
        root_layer = context.get_stage().GetRootLayer()

        if not output_shader_prim.IsValid() or not output_shader_prim.IsA(UsdShade.Shader):
            carb.log_warn(
                f'Could not convert "{input_shader_prim.GetName()}" to "{output_shader_prim.GetName()}" '
                f"as it doesn't appear to be a valid shader prim."
            )
            return

        output_material_prim = output_shader_prim.GetParent()

        if not output_material_prim.IsValid() or not output_material_prim.IsA(UsdShade.Material):
            carb.log_warn(
                f'Could not convert "{input_shader_prim.GetName()}" to "{output_shader_prim.GetName()}" '
                f"as it doesn't appear to have a valid material prim."
            )
            return

        # Populate the material with all the shader attributes
        await context.load_mdl_parameters_for_prim_async(output_shader_prim)

        # Set the attribute values for the temporary output material
        for attr in converter.attributes:
            output_attr = output_shader_prim.GetAttribute(attr.output_attr_name)
            if not output_attr.IsValid():
                carb.log_warn(
                    f'Could not translate "{attr.input_attr_name}" to "{attr.output_attr_name}" '
                    f"as it doesn't exist on the output material"
                )
                continue

            # If the input doesn't have the value, there's nothing to translate
            if not input_shader_prim.HasAttribute(attr.input_attr_name):
                # If a default output value was set, add it to the output shader
                if attr.output_default_value is not None:
                    omni.kit.commands.execute(
                        "ChangePropertyCommand",
                        prop_path=output_attr.GetPath(),
                        value=attr.output_default_value,
                        prev=None,
                        target_layer=root_layer,
                        usd_context_name=context_name,
                    )
                continue

            input_attr = input_shader_prim.GetAttribute(attr.input_attr_name)
            input_attr_spec = root_layer.GetAttributeAtPath(input_attr.GetPath())

            # If the input attr was not defined on this layer, there's nothing to translate
            if not input_attr_spec:
                continue

            input_attr_value = input_attr.Get()
            if input_attr_value is None:
                has_default_value, value = MaterialConverterCore._get_default_value(input_attr)
                if has_default_value:
                    input_attr_value = value

            translated_value = attr.translate_fn(input_attr_value, input_attr)

            omni.kit.commands.execute(
                "ChangePropertyCommand",
                prop_path=output_attr.GetPath(),
                value=translated_value,
                prev=None,
                target_layer=root_layer,
                usd_context_name=context_name,
            )

    @staticmethod
    async def find_matching_supported_material(
        input_shader_prim: "Usd.Prim",
    ) -> Tuple[Optional["ConverterBase"], Optional["_SupportedShaderInputs"]]:
        """
        Find the matching supported material from all inputs.
        It can happen that inside a MDL, a supported MDL is imported and some attributes are set.
        But the MDL is not supported. So to check if this is really supported, we check if the attributes are matching
        with a supported MDL
        """
        for converter in _ConvertersEnum:
            all_valid = []
            if converter.value[1].value is None:
                continue
            converter_instance = converter.value[0]().build(input_shader_prim, converter.value[1].value)
            for attr in converter_instance.attributes:
                if attr.fake_attribute:
                    continue
                if not input_shader_prim.HasAttribute(attr.input_attr_name):
                    all_valid.append(False)
                    break
                all_valid.append(True)
            if all(all_valid):
                return converter.value[0], converter.value[1]
        return None, None

    @staticmethod
    async def _create_material_attributes(
        context_name: str, converter: "ConverterBase", input_shader_prim: "Usd.Prim", output_shader_prim: "Usd.Prim"
    ):
        stage = omni.usd.get_context(context_name).get_stage()
        root_layer = stage.GetRootLayer()
        session_layer = stage.GetSessionLayer()

        for attr in converter.attributes:
            output_attr_path = str(output_shader_prim.GetPath().AppendProperty(attr.output_attr_name))

            # If the input doesn't have the value, there's nothing to translate
            if not input_shader_prim.HasAttribute(attr.input_attr_name):
                # If a default output value was set, add it to the output shader if it doesn't exist already
                if attr.output_default_value is not None and not input_shader_prim.HasAttribute(attr.output_attr_name):
                    translated_type, _ = attr.translate_alt_fn(None, None, None)
                    omni.kit.commands.execute(
                        "ChangePropertyCommand",
                        prop_path=output_attr_path,
                        value=attr.output_default_value,
                        prev=None,
                        target_layer=root_layer,
                        type_to_create_if_not_exist=translated_type,
                        usd_context_name=context_name,
                    )
                continue

            input_attr = input_shader_prim.GetAttribute(attr.input_attr_name)
            input_attr_spec_root = root_layer.GetAttributeAtPath(input_attr.GetPath())
            input_attr_spec_session = session_layer.GetAttributeAtPath(input_attr.GetPath())

            # If the input attr was not defined on this layer, there's nothing to translate
            # It can happen that some attributes are defined in the MDL directly. So they will end up in the session
            # layer
            if not input_attr_spec_root and not input_attr_spec_session:
                continue

            input_attr_type = input_attr.GetTypeName()
            input_attr_value = input_attr.Get()
            if input_attr_value is None:
                has_default_value, value = MaterialConverterCore._get_default_value(input_attr)
                if has_default_value:
                    input_attr_value = value

            translated_type, translated_value = attr.translate_alt_fn(input_attr_type, input_attr_value, input_attr)

            omni.kit.commands.execute(
                "ChangePropertyCommand",
                prop_path=output_attr_path,
                value=translated_value,
                prev=None,
                target_layer=root_layer,
                type_to_create_if_not_exist=translated_type,
                usd_context_name=context_name,
            )

    @staticmethod
    def _get_default_value(usd_property):
        default_values = {"xformOp:scale": (1.0, 1.0, 1.0), "visibleInPrimaryRay": True, "primvars:multimatte_id": -1}
        metadata = usd_property.GetAllMetadata()
        if isinstance(usd_property, Usd.Attribute):
            prim = usd_property.GetPrim()
            if prim:
                custom = usd_property.GetCustomData()
                if "default" in custom:
                    # This is not the standard USD way to get default.
                    return True, custom["default"]
                if "customData" in metadata:
                    # This is to fetch default value for custom property.
                    default_value = metadata["customData"].get("default", None)
                    if default_value:
                        return True, default_value
                else:
                    prim_definition = prim.GetPrimDefinition()
                    prop_spec = prim_definition.GetSchemaPropertySpec(usd_property.GetPath().name)
                    if prop_spec and prop_spec.default is not None:
                        return True, prop_spec.default

                if usd_property.GetName() in default_values:
                    return True, default_values[usd_property.GetName()]

                # If we still don't find default value, use type's default value
                value_type = usd_property.GetTypeName()
                default_value = value_type.defaultValue
                return True, default_value
        return False, None
