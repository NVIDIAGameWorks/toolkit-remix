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

import pathlib
from unittest.mock import MagicMock, patch

from omni.flux.asset_importer.core.data_models import TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.kit.test import AsyncTestCase
from pxr import Sdf

from lightspeed.trex.comfyui.core.enums import IntroducingLayer, RemixType
from lightspeed.trex.comfyui.core.keys import type_key
from lightspeed.trex.comfyui.core.resolvers import (
    RESOLVER_PLUGINS,
    AllStageTexturesResolver,
    ConstantResolver,
    LayerIdentifierResolver,
    ResolverConfigurationError,
    ResolverFactory,
    ResolverRule,
    ResolverValueError,
    SelectedPrimPathResolver,
    SelectedTextureResolver,
    create_default_resolver,
    create_resolver,
    get_resolver_rule,
)


class TestValueResolver(AsyncTestCase):
    """Test resolver catalog ordering, defaults, and values."""

    async def test_resolver_rule_rejects_default_outside_options(self):
        """A resolver rule cannot select a class it does not offer."""
        # Arrange
        options = (ConstantResolver,)

        # Act
        with self.assertRaises(ValueError) as error_context:
            ResolverRule(options=options, default=SelectedTextureResolver)

        # Assert
        self.assertIn("default", str(error_context.exception))

    async def test_resolver_catalog_orders_remix_native_and_constant_options(self):
        """Resolver choices follow semantic, native, then constant precedence without duplicates."""
        # Arrange
        remix_type = RemixType.TEXTURE_FILE_PATH

        # Act
        rule = get_resolver_rule(remix_type, pathlib.Path)

        # Assert
        self.assertEqual(rule.options, (SelectedTextureResolver, AllStageTexturesResolver, ConstantResolver))
        self.assertIs(rule.default, SelectedTextureResolver)

    async def test_all_stage_textures_getter_is_offered_but_not_default(self):
        """The All Stage Textures getter is a non-default texture option that mirrors Selected Texture."""
        # Arrange / Act
        rule = get_resolver_rule(RemixType.TEXTURE_FILE_PATH, pathlib.Path)
        resolver = create_resolver(AllStageTexturesResolver, pathlib.Path, pathlib.Path(), context_name="texturecraft")

        # Assert
        self.assertIn(AllStageTexturesResolver, rule.options)
        self.assertIsNot(rule.default, AllStageTexturesResolver)
        self.assertIsInstance(resolver, AllStageTexturesResolver)
        self.assertEqual(AllStageTexturesResolver.label, "All Textures")
        self.assertEqual(
            tuple(parameter.name for parameter in resolver.parameters), ("texture_type", "introducing_layer")
        )

    async def test_all_stage_textures_source_filter_offers_capture_choices(self):
        """The All Textures getter adds an introducing layer parameter that defaults to the capture layer."""
        # Arrange
        resolver = AllStageTexturesResolver(context_name="texturecraft")

        # Act
        source_parameter = resolver.parameters[1]

        # Assert
        self.assertEqual(source_parameter.name, "introducing_layer")
        self.assertIs(source_parameter.value_type, IntroducingLayer)
        self.assertEqual(source_parameter.choices, tuple(IntroducingLayer))
        self.assertEqual(source_parameter.get_value(), IntroducingLayer.CAPTURE)
        self.assertEqual(source_parameter.label, "Introducing Layer")

    async def test_all_stage_textures_source_filter_selects_captured_replaced_or_all(self):
        """The source filter includes captured only, replaced only, or every texture."""
        # Arrange
        resolver = AllStageTexturesResolver(context_name="texturecraft")

        # Act / Assert
        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.all_stage.is_texture_from_capture",
            side_effect=lambda path: path.endswith("captured.png"),
        ):
            resolver.introducing_layer = IntroducingLayer.ANY
            self.assertTrue(resolver.accepts_introducing_layer("/mods/replaced.png"))
            self.assertTrue(resolver.accepts_introducing_layer("/game/captured.png"))
            resolver.introducing_layer = IntroducingLayer.CAPTURE
            self.assertTrue(resolver.accepts_introducing_layer("/game/captured.png"))
            self.assertFalse(resolver.accepts_introducing_layer("/mods/replaced.png"))
            resolver.introducing_layer = IntroducingLayer.MOD
            self.assertFalse(resolver.accepts_introducing_layer("/game/captured.png"))
            self.assertTrue(resolver.accepts_introducing_layer("/mods/replaced.png"))

    async def test_all_stage_textures_accepts_resolved_value_applies_source_filter(self):
        """A resolved texture is accepted only when it matches the source filter."""
        # Arrange
        resolver = AllStageTexturesResolver(context_name="texturecraft", introducing_layer=IntroducingLayer.CAPTURE)

        # Act
        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.all_stage.is_texture_from_capture",
            side_effect=(True, False),
        ):
            captured = resolver.accepts_resolved_value(pathlib.Path("/game/captured.png"))
            replaced = resolver.accepts_resolved_value(pathlib.Path("/mods/replaced.png"))

        # Assert
        self.assertTrue(captured)
        self.assertFalse(replaced)

    async def test_resolver_keys_are_derived_from_class_names(self):
        """Every resolver factory key is derived from its class name, never a hand-written string."""
        # Arrange / Act / Assert
        for resolver_class in RESOLVER_PLUGINS:
            with self.subTest(resolver_class=resolver_class.__name__):
                self.assertEqual(resolver_class.name, type_key(resolver_class))

    async def test_all_stage_textures_resolver_resolves_like_selected_texture(self):
        """The All Stage Textures getter resolves one texture per material exactly like Selected Texture."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = AllStageTexturesResolver(context_name="texturecraft")

        # Act
        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.base.iter_texture_paths_for_prim",
            return_value=iter(["/textures/diffuse.png"]),
        ) as iter_texture_paths:
            result = resolver(mock_prim)

        # Assert
        self.assertEqual(result, pathlib.Path("/textures/diffuse.png"))
        iter_texture_paths.assert_called_once_with(
            "/World/Mesh",
            context_name="texturecraft",
            texture_type=TEXTURE_TYPE_INPUT_MAP[TextureTypes.DIFFUSE],
        )

    async def test_resolver_catalog_uses_real_native_defaults_without_semantics(self):
        """Native getters are offered by exact return type while Constant uses USD defaults."""
        # Arrange
        expected_native_types = (bool, int, float, pathlib.Path)

        # Act
        rules = {native_type: get_resolver_rule(None, native_type) for native_type in expected_native_types}
        string_rule = get_resolver_rule(None, str)

        # Assert
        for native_type in expected_native_types:
            with self.subTest(native_type=native_type):
                rule = rules[native_type]
                self.assertEqual(rule.options, (ConstantResolver,))
                self.assertIs(rule.default, ConstantResolver)

        self.assertEqual(
            string_rule.options,
            (SelectedPrimPathResolver, LayerIdentifierResolver, ConstantResolver),
        )
        self.assertIs(string_rule.default, ConstantResolver)

    async def test_create_default_resolver_uses_usd_type_defaults(self):
        """A Constant starts from its USD type default instead of workflow-authored sample data."""
        # Arrange
        cases = (
            (bool, True, Sdf.ValueTypeNames.Bool.defaultValue),
            (int, 3, Sdf.ValueTypeNames.Int.defaultValue),
            (float, 0.5, Sdf.ValueTypeNames.Float.defaultValue),
            (str, "prompt", Sdf.ValueTypeNames.String.defaultValue),
            (
                pathlib.Path,
                pathlib.Path("fallback.png"),
                pathlib.Path(Sdf.ValueTypeNames.Asset.defaultValue.path),
            ),
        )
        # Act
        resolvers = [
            create_default_resolver(None, native_type, authored_value)
            for native_type, authored_value, _expected_value in cases
        ]

        # Assert
        for (native_type, _authored_value, expected_value), resolver in zip(cases, resolvers):
            with self.subTest(native_type=native_type):
                self.assertIs(type(resolver), ConstantResolver)
                self.assertIs(resolver.value_type, native_type)
                self.assertEqual(resolver.value, expected_value)

    async def test_create_constant_resolver_without_default_uses_empty_native_value(self):
        """A missing semantic path default becomes an empty typed file-path Constant."""
        # Arrange
        default_value = pathlib.Path("workflow-example.png")

        # Act
        resolver = create_resolver(ConstantResolver, pathlib.Path, default_value)

        # Assert
        self.assertIs(type(resolver), ConstantResolver)
        self.assertIs(resolver.value_type, pathlib.Path)
        self.assertEqual(resolver.value, pathlib.Path())

    async def test_resolver_catalog_always_offers_constant_fallback(self):
        """An unregistered constructible input type uses its native empty value."""
        # Arrange
        fallback = 3 + 4j

        # Act
        resolver = create_default_resolver(None, complex, fallback)

        # Assert
        self.assertIsInstance(resolver, ConstantResolver)
        self.assertEqual(resolver.value, complex())

    async def test_resolver_factory_registers_exact_catalog_plugins(self):
        """Resolver rules come only from explicitly registered exact plugin classes."""
        # Arrange
        factory = ResolverFactory()

        # Act
        factory.register_plugins(RESOLVER_PLUGINS)
        rule = factory.get_rule(RemixType.TEXTURE_FILE_PATH, pathlib.Path)

        # Assert
        self.assertEqual(rule.options, (SelectedTextureResolver, AllStageTexturesResolver, ConstantResolver))
        self.assertIs(rule.default, SelectedTextureResolver)
        self.assertEqual(tuple(factory.get_all_plugins().values()), tuple(RESOLVER_PLUGINS))

    async def test_constant_resolver_returns_fixed_value(self):
        """ConstantResolver returns the same value regardless of the prim argument."""
        # Arrange
        resolver = ConstantResolver(value=42)
        mock_prim = MagicMock()

        # Act
        result = resolver(mock_prim)

        # Assert
        self.assertEqual(result, 42)

    async def test_file_path_constant_requires_a_readable_file(self):
        """File-path Constants reject missing files and return readable files unchanged."""
        # Arrange
        invalid_paths = (pathlib.Path(), pathlib.Path(__file__).parent / "missing.png")
        valid_path = pathlib.Path(__file__)

        # Act
        errors = []
        for invalid_path in invalid_paths:
            with self.subTest(invalid_path=invalid_path):
                with self.assertRaises(ResolverConfigurationError) as error_context:
                    ConstantResolver(invalid_path, value_type=pathlib.Path)(MagicMock())
                errors.append(error_context.exception)
        result = ConstantResolver(valid_path, value_type=pathlib.Path)(MagicMock())

        # Assert
        self.assertTrue(all("Select a valid file" in str(error) for error in errors))
        self.assertEqual(result, valid_path)

    async def test_constant_resolver_parameter_updates_value(self):
        """The public parameter binding exposes and enforces the exact native type."""
        # Arrange
        resolver = ConstantResolver(value=42)
        parameter = resolver.parameters[0]

        # Act
        parameter.set_value(7)
        with self.assertRaises(TypeError) as error_context:
            parameter.set_value(True)

        # Assert
        self.assertIsInstance(error_context.exception, TypeError)
        self.assertIs(parameter.value_type, int)
        self.assertEqual(parameter.get_value(), 7)
        self.assertEqual(resolver.value, 7)

    async def test_selected_prim_path_resolver_returns_actual_material_path(self):
        """The selected-prim getter returns the material prim supplied by the generation flow."""
        # Arrange
        prim = MagicMock()
        prim.GetPath.return_value = "/World/Looks/Material"

        # Act
        result = SelectedPrimPathResolver()(prim)

        # Assert
        self.assertEqual(result, "/World/Looks/Material")

    async def test_layer_identifier_resolver_returns_material_stage_root_layer(self):
        """The layer getter returns the root layer for the material prim's stage."""
        # Arrange
        prim = MagicMock()
        prim.GetStage.return_value.GetRootLayer.return_value.identifier = "C:/project/mod.usda"

        # Act
        result = LayerIdentifierResolver()(prim)

        # Assert
        self.assertEqual(result, "C:/project/mod.usda")

    async def test_selected_texture_resolver_returns_path(self):
        """SelectedTextureResolver returns a pathlib.Path from prim texture data."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver(context_name="texturecraft")

        # Act
        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.base.iter_texture_paths_for_prim",
            return_value=iter(["/textures/diffuse.png"]),
        ) as iter_texture_paths:
            result = resolver(mock_prim)

        # Assert
        self.assertEqual(result, pathlib.Path("/textures/diffuse.png"))
        self.assertIsInstance(result, pathlib.Path)
        iter_texture_paths.assert_called_once_with(
            "/World/Mesh",
            context_name="texturecraft",
            texture_type=TEXTURE_TYPE_INPUT_MAP[TextureTypes.DIFFUSE],
        )

    async def test_selected_texture_resolver_uses_requested_texture_type(self):
        """SelectedTextureResolver forwards its texture type to USD extraction."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver(texture_type=TextureTypes.NORMAL_DX, context_name="texturecraft")

        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.base.iter_texture_paths_for_prim",
            return_value=iter(["/textures/normal.png"]),
        ) as iter_texture_paths:
            # Act
            result = resolver(mock_prim)

        # Assert
        self.assertEqual(result, pathlib.Path("/textures/normal.png"))
        iter_texture_paths.assert_called_once_with(
            "/World/Mesh",
            context_name="texturecraft",
            texture_type=TEXTURE_TYPE_INPUT_MAP[TextureTypes.NORMAL_DX],
        )

    async def test_selected_texture_resolver_rejects_unsupported_texture_type(self):
        """An inconsistent texture map produces an actionable resolver error instead of a raw mapping failure."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver(context_name="texturecraft")

        # Act
        with patch.dict(
            "lightspeed.trex.comfyui.core.resolvers.textures.base.TEXTURE_TYPE_INPUT_MAP",
            {},
            clear=True,
        ):
            with self.assertRaisesRegex(ResolverValueError, "selected texture type is not supported"):
                resolver(mock_prim)

    async def test_selected_texture_resolver_exposes_all_texture_type_choices(self):
        """The selected-texture parameter is typed and offers every supported texture type."""
        # Arrange
        resolver = SelectedTextureResolver()

        # Act
        parameter = resolver.parameters[0]

        # Assert
        self.assertIs(parameter.value_type, TextureTypes)
        self.assertEqual(parameter.get_value(), TextureTypes.DIFFUSE)
        self.assertEqual(parameter.choices, tuple(t for t in TextureTypes if t is not TextureTypes.OTHER))
        self.assertNotIn(TextureTypes.OTHER, parameter.choices)
        self.assertEqual(parameter.label, "Texture Type")

    async def test_selected_texture_parameter_updates_texture_type(self):
        """The public parameter binding controls subsequent texture resolution."""
        # Arrange
        resolver = SelectedTextureResolver()
        parameter = resolver.parameters[0]

        # Act
        parameter.set_value(TextureTypes.NORMAL_DX)

        # Assert
        self.assertEqual(parameter.get_value(), TextureTypes.NORMAL_DX)
        self.assertEqual(resolver.texture_type, TextureTypes.NORMAL_DX)

    async def test_selected_texture_resolver_explains_missing_and_ambiguous_paths(self):
        """Skip reasons explain the texture problem and the available recovery action."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver(context_name="texturecraft")

        cases = (
            (TextureTypes.DIFFUSE, (), "This material has no albedo texture."),
            (
                TextureTypes.DIFFUSE,
                ("/textures/a.png", "/textures/b.png"),
                "This material has 2 albedo textures. Choose a getter that returns one texture file.",
            ),
            (TextureTypes.NORMAL_OGL, (), "This material has no normal (OpenGL) texture."),
        )

        for texture_type, paths, expected in cases:
            with self.subTest(texture_type=texture_type, paths=paths):
                resolver.texture_type = texture_type
                # Act
                with (
                    patch(
                        "lightspeed.trex.comfyui.core.resolvers.textures.base.iter_texture_paths_for_prim",
                        return_value=iter(paths),
                    ),
                    self.assertRaises(ValueError) as error_context,
                ):
                    resolver(mock_prim)

                # Assert
                self.assertEqual(str(error_context.exception), expected)

    async def test_selected_texture_resolver_deduplicates_identical_paths(self):
        """Repeated emission of one texture path is not ambiguous."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver(context_name="texturecraft")

        # Act
        with patch(
            "lightspeed.trex.comfyui.core.resolvers.textures.base.iter_texture_paths_for_prim",
            return_value=iter(["/textures/a.png", "/textures/a.png"]),
        ):
            result = resolver(mock_prim)

        # Assert
        self.assertEqual(result, pathlib.Path("/textures/a.png"))

    async def test_selected_texture_resolver_rejects_missing_context(self):
        """Texture resolution cannot silently use the default USD context."""
        # Arrange
        mock_prim = MagicMock()
        mock_prim.GetPath.return_value = MagicMock(__str__=MagicMock(return_value="/World/Mesh"))
        resolver = SelectedTextureResolver()

        # Act
        with self.assertRaises(ValueError) as error:
            resolver(mock_prim)

        # Assert
        self.assertEqual(
            str(error.exception),
            "The selected texture could not be read. Reopen the project and try again.",
        )
