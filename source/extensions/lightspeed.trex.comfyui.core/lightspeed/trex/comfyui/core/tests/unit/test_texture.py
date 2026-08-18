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

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import lightspeed.trex.comfyui.core.texture as texture
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS, TEXTURE_TYPE_INPUT_MAP, TextureTypes
from omni.kit.test import AsyncTestCase

__all__ = ("TestTexture",)


class _AssetPathDouble:
    """Represent the two AssetPath fields consumed by texture extraction."""

    def __init__(self, path: str, resolved_path: str = "") -> None:
        """Store authored and resolved paths.

        Args:
            path: Authored asset path.
            resolved_path: Resolved asset path, or an empty string when unresolved.
        """
        self.path = path
        self.resolvedPath = resolved_path


class _USDPrimDouble:
    """Mark real-prim checks without importing the USD prim type."""


def _make_prim(path: str, *, valid: bool = True) -> MagicMock:
    """Create a mock USD prim with a stable path and validity.

    Args:
        path: USD path returned by the mock prim.
        valid: Whether the mock prim reports itself as valid.

    Returns:
        A mock prim configured with the requested path and validity.
    """
    prim = MagicMock()
    prim.GetPath.return_value = path
    prim.IsValid.return_value = valid
    prim.HasRelationship.return_value = False
    return prim


def _make_prim_graph() -> tuple[MagicMock, dict[str, MagicMock]]:
    """Create a mock stage containing a bound material and shader.

    Returns:
        The mock stage and its prims indexed by USD path.
    """
    stage = MagicMock()
    root = _make_prim("/World/Root")
    material = _make_prim("/World/Looks/Material")
    shader = _make_prim("/World/Looks/Material/Shader")
    invalid = _make_prim("/Missing", valid=False)
    root.HasRelationship.side_effect = lambda name: name == "material:binding"
    root.GetRelationship.return_value.GetTargets.return_value = [material.GetPath()]
    prims = {
        "/World/Root": root,
        "/World/Looks/Material": material,
        "/World/Looks/Material/Shader": shader,
    }
    stage.GetPrimAtPath.side_effect = lambda path: prims.get(str(path), invalid)
    for prim in (*prims.values(), invalid):
        prim.GetStage.return_value = stage
    return stage, prims


def _make_context(stage: MagicMock | None) -> MagicMock:
    """Create a mock USD context for a stage.

    Args:
        stage: Stage returned by the mock context, or None when no stage is open.

    Returns:
        A mock USD context configured with the requested stage.
    """
    context = MagicMock()
    context.get_stage.return_value = stage
    return context


def _patch_usdshade(get_shader, get_material):
    """Patch every USD wrapper used by extraction without loading real USD values.

    Args:
        get_shader: Callback that resolves mock shader wrappers from prims.
        get_material: Callback that resolves mock material wrappers from prims.

    Returns:
        A context manager that applies the mock USD wrappers.
    """
    time_code = MagicMock()
    time_code.Default.return_value = None
    usd_shade = MagicMock()
    usd_shade.Shader.side_effect = get_shader
    usd_shade.Material.side_effect = get_material
    return patch.multiple(
        texture,
        Sdf=SimpleNamespace(AssetPath=_AssetPathDouble),
        Usd=SimpleNamespace(Prim=_USDPrimDouble, TimeCode=time_code),
        UsdShade=usd_shade,
    )


class TestTexture(AsyncTestCase):
    """Tests for ComfyUI USD texture discovery."""

    async def test_texture_path_detection_accepts_supported_extensions(self):
        """Texture detection accepts supported extensions case-insensitively."""
        # Arrange
        paths = [f"texture{extension.upper()}" for extension in SUPPORTED_TEXTURE_EXTENSIONS]

        # Act
        results = [texture._is_texture_path(path) for path in paths]

        # Assert
        for extension, result in zip(SUPPORTED_TEXTURE_EXTENSIONS, results):
            with self.subTest(extension=extension):
                self.assertTrue(result)

    async def test_texture_path_detection_rejects_unrelated_values(self):
        """Texture detection rejects empty or unrelated values."""
        # Arrange
        values = ("", "a.txt", "texture.png.tmp", "texture.exr")

        # Act
        results = [texture._is_texture_path(value) for value in values]

        # Assert
        self.assertEqual(results, [False] * len(values))

    async def test_iter_texture_paths_for_prim_returns_empty_without_a_stage(self):
        """Texture path extraction is a no-op while the USD context has no open stage."""
        # Arrange
        context = _make_context(None)

        with patch.object(texture, "get_context", return_value=context):
            # Act
            paths = list(texture.iter_texture_paths_for_prim("/World/Root", context_name="texturecraft"))

        # Assert
        self.assertEqual(paths, [])

    async def test_iter_texture_paths_reads_asset_and_string_shader_inputs(self):
        """Shader extraction resolves both USD asset and string texture inputs."""
        # Arrange
        stage, prims = _make_prim_graph()
        shader_prim = prims["/World/Looks/Material/Shader"]
        asset_input = MagicMock()
        asset_input.Get.return_value = _AssetPathDouble(
            "textures/albedo.PNG",
            "C:/project/textures/albedo.PNG",
        )
        string_input = MagicMock()
        string_input.Get.return_value = "C:/project/textures/string.jpg"
        string_input.GetAttr.return_value.GetPropertyStack.return_value = []
        label_input = MagicMock()
        label_input.Get.return_value = "not-a-texture"
        shader = MagicMock()
        shader.GetInputs.return_value = [asset_input, string_input, label_input]

        with _patch_usdshade(lambda prim: shader if prim is shader_prim else None, lambda _prim: None):
            # Act
            paths = list(texture._iter_texture_paths(shader_prim))

        # Assert
        self.assertEqual(paths, ["C:/project/textures/albedo.PNG", "C:/project/textures/string.jpg"])

    async def test_iter_texture_paths_anchors_unresolved_asset_path_to_authoring_layer(self):
        """Relative unresolved assets are anchored to the layer that authored them."""
        # Arrange
        authored_path = "textures/pending.png"
        expected_path = "C:/project/textures/pending.png"
        prim = _make_prim("/Shader")
        prop_spec = MagicMock(default=_AssetPathDouble(authored_path))
        prop_spec.layer.ComputeAbsolutePath.return_value = expected_path
        unresolved_input = MagicMock()
        unresolved_input.Get.return_value = _AssetPathDouble(authored_path)
        unresolved_input.GetAttr.return_value.GetPropertyStack.return_value = [prop_spec]
        unresolved_shader = MagicMock()
        unresolved_shader.GetInputs.return_value = [unresolved_input]

        with _patch_usdshade(lambda _prim: unresolved_shader, lambda _prim: None):
            # Act
            paths = list(texture._iter_texture_paths(prim))

        # Assert
        self.assertEqual(paths, [expected_path])

    async def test_iter_texture_paths_anchors_string_path_to_authoring_layer(self):
        """Relative string texture values are anchored to the layer that authored them."""
        # Arrange
        authored_path = "textures/string.png"
        expected_path = "C:/project/textures/string.png"
        prim = _make_prim("/Shader")
        prop_spec = MagicMock(default=authored_path)
        prop_spec.layer.ComputeAbsolutePath.return_value = expected_path
        string_input = MagicMock()
        string_input.Get.return_value = authored_path
        string_input.GetAttr.return_value.GetPropertyStack.return_value = [prop_spec]
        shader = MagicMock()
        shader.GetInputs.return_value = [string_input]

        with _patch_usdshade(lambda _prim: shader, lambda _prim: None):
            # Act
            paths = list(texture._iter_texture_paths(prim))

        # Assert
        self.assertEqual(paths, [expected_path])

    async def test_iter_texture_paths_selects_diffuse_instead_of_first_shader_input(self):
        """Texture extraction selects the exact full shader-input name."""
        # Arrange
        _, prims = _make_prim_graph()
        shader_prim = prims["/World/Looks/Material/Shader"]
        diffuse_input = MagicMock()
        diffuse_input.GetFullName.return_value = "inputs:diffuse_texture"
        diffuse_input.Get.return_value = _AssetPathDouble("textures/albedo.png")
        preview_input = MagicMock()
        preview_input.GetFullName.return_value = "inputs:diffuse_texture_preview"
        preview_input.Get.return_value = _AssetPathDouble("textures/preview.png")
        shader = MagicMock()
        shader.GetInputs.return_value = [preview_input, diffuse_input]

        with _patch_usdshade(lambda prim: shader if prim is shader_prim else None, lambda _prim: None):
            # Act
            paths = list(
                texture._iter_texture_paths(
                    shader_prim,
                    texture_type=TEXTURE_TYPE_INPUT_MAP[TextureTypes.DIFFUSE],
                )
            )

        # Assert
        self.assertEqual(paths, ["textures/albedo.png"])

    async def test_iter_texture_paths_rejects_invalid_prim(self):
        """Shader extraction returns no paths for invalid prims."""
        # Arrange
        stage, _ = _make_prim_graph()

        # Act
        invalid = list(texture._iter_texture_paths(stage.GetPrimAtPath("/Missing")))

        # Assert
        self.assertEqual(invalid, [])

    async def test_iter_texture_paths_skips_seen_prim(self):
        """Shader extraction returns no paths for already-seen prims."""
        # Arrange
        _, prims = _make_prim_graph()
        shader_prim = prims["/World/Looks/Material/Shader"]

        # Act
        seen = list(texture._iter_texture_paths(shader_prim, seen_prims={str(shader_prim.GetPath())}))

        # Assert
        self.assertEqual(seen, [])

    def _patch_usdshade_for_material_graph(self, prims: dict[str, MagicMock]):
        """Patch UsdShade wrappers for the mock material graph.

        Args:
            prims: Mock material graph indexed by USD path.

        Returns:
            The empty material prim and a context manager for the mock wrappers.
        """
        shader_prim = prims["/World/Looks/Material/Shader"]
        material_prim = prims["/World/Looks/Material"]
        empty_material_prim = _make_prim("/World/Looks/Empty")

        texture_input = MagicMock()
        texture_input.Get.return_value = _AssetPathDouble(
            "textures/albedo.PNG",
            "C:/project/textures/albedo.PNG",
        )
        shader = MagicMock()
        shader.GetInputs.return_value = [texture_input]
        source_info = MagicMock()
        source_info.source.GetPrim.return_value = shader_prim
        surface_output = MagicMock()
        surface_output.GetConnectedSources.return_value = ([source_info], [])
        material = MagicMock()
        material.GetSurfaceOutput.return_value = surface_output
        empty_material = MagicMock()
        empty_material.GetSurfaceOutput.return_value = None

        def get_shader(prim):
            """Return the shader wrapper for the graph's shader prim.

            Args:
                prim: Prim to resolve as a shader.

            Returns:
                The mock shader for the shader prim, otherwise None.
            """
            return shader if prim is shader_prim else None

        def get_material(prim):
            """Return the matching material wrapper for a graph prim.

            Args:
                prim: Prim to resolve as a material.

            Returns:
                The matching mock material, otherwise None.
            """
            if prim is material_prim:
                return material
            if prim is empty_material_prim:
                return empty_material
            return None

        return empty_material_prim, _patch_usdshade(get_shader, get_material)

    async def test_iter_texture_paths_follows_material_connections(self):
        """Material extraction consumes the real GetConnectedSources return shape."""
        # Arrange
        stage, prims = _make_prim_graph()
        material_prim = prims["/World/Looks/Material"]
        _, usd_shade_patch = self._patch_usdshade_for_material_graph(prims)

        with usd_shade_patch:
            # Act
            paths = list(texture._iter_texture_paths(material_prim))

        # Assert
        self.assertEqual(paths, ["C:/project/textures/albedo.PNG"])

    async def test_iter_texture_paths_follows_mdl_surface_output_without_universal_output(self):
        """Material extraction follows authored MDL surface outputs."""
        # Arrange
        _, prims = _make_prim_graph()
        material_prim = prims["/World/Looks/Material"]
        shader_prim = prims["/World/Looks/Material/Shader"]
        texture_input = MagicMock()
        texture_input.Get.return_value = _AssetPathDouble("textures/albedo.png")
        shader = MagicMock()
        shader.GetInputs.return_value = [texture_input]
        source_info = MagicMock()
        source_info.source.GetPrim.return_value = shader_prim
        mdl_output = MagicMock()
        mdl_output.GetConnectedSources.return_value = ([source_info], [])
        material = MagicMock()
        material.GetSurfaceOutputs.return_value = [mdl_output]
        material.GetSurfaceOutput.return_value = None

        with _patch_usdshade(
            lambda prim: shader if prim is shader_prim else None,
            lambda prim: material if prim is material_prim else None,
        ):
            # Act
            paths = list(texture._iter_texture_paths(material_prim))

        # Assert
        self.assertEqual(paths, ["textures/albedo.png"])

    async def test_iter_texture_paths_returns_empty_for_material_without_surface_output(self):
        """Material extraction returns no paths when the surface output is missing."""
        # Arrange
        _, prims = _make_prim_graph()
        empty_material_prim, usd_shade_patch = self._patch_usdshade_for_material_graph(prims)

        with usd_shade_patch:
            # Act
            paths = list(texture._iter_texture_paths(empty_material_prim))

        # Assert
        self.assertEqual(paths, [])

    async def test_iter_texture_paths_for_prim_deduplicates_and_rejects_invalid_prim(self):
        """Public extraction preserves order while suppressing duplicate file paths."""
        # Arrange
        prim = SimpleNamespace(IsValid=lambda: True)
        stage = SimpleNamespace(GetPrimAtPath=lambda _path: prim)
        context = SimpleNamespace(get_stage=lambda: stage)

        with (
            patch.object(texture, "get_context", return_value=context),
            patch.object(
                texture,
                "_iter_texture_paths",
                return_value=iter(["textures/a.png", "textures/a.png", "textures/b.dds"]),
            ),
        ):
            # Act
            paths = list(texture.iter_texture_paths_for_prim("/World/Root", context_name="texturecraft"))

        # Assert
        self.assertEqual(paths, ["textures/a.png", "textures/b.dds"])

    async def test_iter_texture_paths_for_prim_rejects_invalid_prim(self):
        """Public extraction returns no paths for invalid prims."""
        # Arrange
        prim = SimpleNamespace(IsValid=lambda: False)
        stage = SimpleNamespace(GetPrimAtPath=lambda _path: prim)
        context = SimpleNamespace(get_stage=lambda: stage)

        with patch.object(texture, "get_context", return_value=context):
            # Act
            invalid = list(texture.iter_texture_paths_for_prim("/Missing", context_name="texturecraft"))

        # Assert
        self.assertEqual(invalid, [])
