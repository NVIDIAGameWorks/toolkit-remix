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

import dataclasses
import pathlib

import omni.kit.test
from lightspeed.trex.asset_pipeline.core.jobs.models import (
    MeshOptimizationRequest,
    MeshOptimizationResult,
    PrepareOptimizationResult,
    ProcessedTexture,
    TextureLedgerEntry,
    TextureProcessingItem,
    TextureProcessingRequest,
    TextureProcessingResult,
    resolve_processed_textures,
)
from lightspeed.trex.asset_pipeline.core.pipeline.item import TextureAsset
from omni.flux.asset_importer.core.data_models import TextureTypes

_TEXTURE_FIELD_CASES = (
    ("key type", "key", None, TypeError, "key must be a str"),
    ("blank key", "key", " ", ValueError, "key must not be blank"),
    ("path type", "path", "a.png", TypeError, "path must be a pathlib.Path"),
    ("texture type", "texture_type", "diffuse", TypeError, "texture_type must be a TextureTypes value"),
)
_LINEAGE_CASES = (
    ("lineage tuple type", "lineage", [], TypeError, "lineage must be a tuple"),
    ("lineage item type", "lineage", (("source",),), TypeError, "lineage[0] must be a 3-tuple of str"),
    (
        "blank lineage item",
        "lineage",
        (("source", "output", " "),),
        ValueError,
        "lineage[0] elements must not be blank",
    ),
)


def _texture_item(key="texture_0"):
    return TextureProcessingItem(key, pathlib.Path(f"textures/{key}.png"), TextureTypes.DIFFUSE)


def _processed_texture(key="texture_0"):
    return ProcessedTexture(
        key, pathlib.Path(f"textures/{key}.png"), f"processed/{key}.dds", TextureTypes.DIFFUSE, (f"{key}.1001.dds",)
    )


def _prepared_result(texture_items=(), texture_ledger=(), referenced_layers=()):
    return PrepareOptimizationResult(
        pathlib.Path("processed/model.usd"),
        texture_items,
        pathlib.Path("model.usda"),
        pathlib.Path("."),
        referenced_layers,
        texture_ledger,
        output_url="omniverse://server/project/assets/ingested",
        replace_udim_textures_by_empty=False,
    )


def _assert_invalid(test, valid_model, *cases):
    for title, field, value, error_type, message in cases:
        with test.subTest(title=title):
            # Arrange
            kwargs = {field: value}
            # Act
            with test.assertRaises(error_type) as error:
                dataclasses.replace(valid_model, **kwargs)
            # Assert
            test.assertIn(message, str(error.exception))


class TestTextureProcessingItem(omni.kit.test.AsyncTestCase):
    def test_texture_models_invalid_fields_raise(self):
        _assert_invalid(self, _texture_item(), *_TEXTURE_FIELD_CASES)
        cases = tuple(
            (title, "source_path" if field == "path" else field, value, error, message)
            for title, field, value, error, message in _TEXTURE_FIELD_CASES
        )
        cases += (
            ("asset URL type", "asset_url", pathlib.Path("a.dds"), TypeError, "asset_url must be a str"),
            ("UDIM tuple type", "udim_tiles", [], TypeError, "udim_tiles must be a tuple of str values"),
            ("blank asset URL", "asset_url", " ", ValueError, "asset_url must not be blank"),
        )
        _assert_invalid(self, _processed_texture(), *cases)

    def test_immutable_models_keep_exact_values(self):
        # Arrange
        item, processed = _texture_item(), _processed_texture()
        request = TextureProcessingRequest((item,), pathlib.Path("models"), "/out")
        texture_result = TextureProcessingResult((processed,), (("source", "output", "hash"),), False)
        ledger = TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "texture_0")
        mesh_request = MeshOptimizationRequest(
            pathlib.Path("model.fbx"),
            pathlib.Path("models"),
            output_url="omniverse://server/project/assets/ingested",
            replace_udim_textures_by_empty=False,
        )
        mesh_result = MeshOptimizationResult(
            "processed/model.usd", texture_result, (("source", "output", "hash"),), pathlib.Path("model.fbx"), False
        )
        prepared = _prepared_result((item,), (ledger,), ("layer.usd", "sublayer.usd"))
        models = (item, processed, request, texture_result, ledger, mesh_request, mesh_result, prepared)
        fields = (
            "key",
            "asset_url",
            "output_url",
            "items",
            "texture_key",
            "source_path",
            "asset_url",
            "model_work_path",
        )

        for model, field in zip(models, fields):
            with self.subTest(title=type(model).__name__), self.assertRaises(dataclasses.FrozenInstanceError):
                # Act
                setattr(model, field, None)

        # Assert
        self.assertEqual(
            (
                item.path,
                item.texture_type,
                processed.asset_url,
                processed.udim_tiles,
                request.items,
                request.source_root,
                request.output_url,
                texture_result.items,
                texture_result.lineage,
            ),
            (
                pathlib.Path("textures/texture_0.png"),
                TextureTypes.DIFFUSE,
                "processed/texture_0.dds",
                ("texture_0.1001.dds",),
                (item,),
                pathlib.Path("models"),
                "/out",
                (processed,),
                (("source", "output", "hash"),),
            ),
        )
        self.assertEqual(
            (
                ledger.material_path,
                ledger.texture_type,
                ledger.texture_key,
                mesh_request.source_path,
                mesh_request.output_url,
                mesh_request.source_root,
                mesh_result.asset_url,
                mesh_result.texture_result,
                mesh_result.lineage,
                mesh_result.source_path,
                prepared.model_work_path,
                prepared.texture_items,
                prepared.source_path,
                prepared.source_root,
                prepared.output_url,
                prepared.referenced_layers,
                prepared.texture_ledger,
            ),
            (
                "/Root/Material",
                TextureTypes.DIFFUSE,
                "texture_0",
                pathlib.Path("model.fbx"),
                "omniverse://server/project/assets/ingested",
                pathlib.Path("models"),
                "processed/model.usd",
                texture_result,
                (("source", "output", "hash"),),
                pathlib.Path("model.fbx"),
                pathlib.Path("processed/model.usd"),
                (item,),
                pathlib.Path("model.usda"),
                pathlib.Path("."),
                "omniverse://server/project/assets/ingested",
                ("layer.usd", "sublayer.usd"),
                (ledger,),
            ),
        )
        for value in (
            texture_result.validation_passed,
            mesh_request.replace_udim_textures_by_empty,
            mesh_result.validation_passed,
            prepared.replace_udim_textures_by_empty,
        ):
            self.assertIs(value, False)
        empty_request = TextureProcessingRequest((), pathlib.Path("."), None)
        empty_result = TextureProcessingResult(())
        self.assertEqual((empty_request.items, empty_result.items), ((), ()))
        self.assertIs(empty_result.validation_passed, True)


class TestTextureProcessingRequest(omni.kit.test.AsyncTestCase):
    def test_texture_processing_request_invalid_fields_raise(self):
        item = _texture_item()
        _assert_invalid(
            self,
            TextureProcessingRequest((item,), pathlib.Path("."), None),
            ("items tuple type", "items", [item], TypeError, "items must be a tuple of TextureProcessingItem values"),
            ("duplicate keys", "items", (item, item), ValueError, "item keys must be unique within one request"),
            ("source root type", "source_root", ".", TypeError, "source_root must be a pathlib.Path"),
            ("output URL type", "output_url", pathlib.Path("."), TypeError, "output_url must be a str or None"),
            ("blank output URL", "output_url", " ", ValueError, "output_url must not be blank"),
        )


class TestTextureProcessingResult(omni.kit.test.AsyncTestCase):
    def test_texture_processing_result_invalid_fields_raise(self):
        processed = _processed_texture()
        _assert_invalid(
            self,
            TextureProcessingResult((processed,)),
            ("items tuple type", "items", [processed], TypeError, "items must be a tuple of ProcessedTexture values"),
            (
                "duplicate keys",
                "items",
                (processed, processed),
                ValueError,
                "item keys must be unique within one result",
            ),
            *_LINEAGE_CASES,
        )

    def test_rebased_onto_points_matched_items_and_lineage_at_published_copies(self):
        # Arrange
        result = TextureProcessingResult(
            (_processed_texture("albedo"), _processed_texture("unused")),
            lineage=(
                ("textures/albedo.png", "processed/albedo.dds", "hash-a"),
                ("textures/unused.png", "processed/unused.dds", "hash-u"),
            ),
            validation_passed=False,
        )
        published = TextureAsset(
            path=pathlib.Path("model/textures/albedo.a.rtex.dds"),
            texture_type=TextureTypes.DIFFUSE,
            key="albedo",
            udim_tiles=(pathlib.Path("model/textures/albedo.1001.a.rtex.dds"),),
        )

        # Act
        rebased = result.rebased_onto([published])

        # Assert
        self.assertEqual(rebased.items[0].asset_url, str(published.path))
        self.assertEqual(rebased.items[0].udim_tiles, (str(published.udim_tiles[0]),))
        self.assertEqual(rebased.items[0].source_path, result.items[0].source_path)
        self.assertEqual(rebased.items[1], result.items[1])
        self.assertEqual(rebased.lineage[0], ("textures/albedo.png", str(published.path), "hash-a"))
        self.assertEqual(rebased.lineage[1], result.lineage[1])
        self.assertIs(rebased.validation_passed, False)

    def test_rebased_onto_without_published_copies_returns_equal_result(self):
        # Arrange
        result = TextureProcessingResult((_processed_texture(),))

        # Act
        rebased = result.rebased_onto([])

        # Assert
        self.assertEqual(rebased, result)


class TestMeshOptimizationRequest(omni.kit.test.AsyncTestCase):
    def test_mesh_optimization_request_invalid_fields_raise(self):
        _assert_invalid(
            self,
            MeshOptimizationRequest(pathlib.Path("mesh.fbx"), pathlib.Path(".")),
            ("source path type", "source_path", "mesh.fbx", TypeError, "source_path must be a pathlib.Path"),
            ("output URL type", "output_url", pathlib.Path("processed"), TypeError, "output_url must be a str or None"),
            ("blank output URL", "output_url", " ", ValueError, "output_url must not be blank"),
            ("source root type", "source_root", ".", TypeError, "source_root must be a pathlib.Path"),
        )


class TestMeshOptimizationResult(omni.kit.test.AsyncTestCase):
    def test_mesh_optimization_result_invalid_fields_raise(self):
        _assert_invalid(
            self,
            MeshOptimizationResult("processed/model.usd", TextureProcessingResult(())),
            ("asset URL type", "asset_url", pathlib.Path("model.usd"), TypeError, "asset_url must be a str"),
            ("blank asset URL", "asset_url", " ", ValueError, "asset_url must not be blank"),
            (
                "texture result type",
                "texture_result",
                None,
                TypeError,
                "texture_result must be a TextureProcessingResult",
            ),
            *_LINEAGE_CASES,
        )


class TestPrepareOptimizationResult(omni.kit.test.AsyncTestCase):
    def test_ledger_and_prepared_result_invalid_fields_raise(self):
        _assert_invalid(
            self,
            TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "texture_0"),
            ("material path type", "material_path", None, TypeError, "material_path must be a str"),
            ("blank material path", "material_path", " ", ValueError, "material_path must not be blank"),
            ("texture type", "texture_type", "diffuse", TypeError, "texture_type must be a TextureTypes value"),
            ("texture key type", "texture_key", None, TypeError, "texture_key must be a str"),
            ("blank texture key", "texture_key", " ", ValueError, "texture_key must not be blank"),
        )
        item = _texture_item()
        ledger = TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "texture_0")
        _assert_invalid(
            self,
            _prepared_result(),
            ("model path type", "model_work_path", "model.usd", TypeError, "model_work_path must be a pathlib.Path"),
            (
                "items tuple type",
                "texture_items",
                [item],
                TypeError,
                "texture_items must be a tuple of TextureProcessingItem values",
            ),
            (
                "duplicate keys",
                "texture_items",
                (item, item),
                ValueError,
                "texture item keys must be unique within one result",
            ),
            (
                "layer item type",
                "referenced_layers",
                (pathlib.Path("layer.usd"),),
                TypeError,
                "referenced_layers must be a tuple of str values",
            ),
            ("source path type", "source_path", "model.usda", TypeError, "source_path must be a pathlib.Path"),
            ("source root type", "source_root", ".", TypeError, "source_root must be a pathlib.Path"),
            (
                "ledger tuple type",
                "texture_ledger",
                [ledger],
                TypeError,
                "texture_ledger must be a tuple of TextureLedgerEntry values",
            ),
            ("output URL type", "output_url", pathlib.Path("processed"), TypeError, "output_url must be a str or None"),
            ("blank output URL", "output_url", " ", ValueError, "output_url must not be blank"),
        )


class TestResolveProcessedTextures(omni.kit.test.AsyncTestCase):
    def test_resolve_processed_textures_raises_when_ledger_key_has_no_match(self):
        # Arrange
        ledger = TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "missing_key")
        # Act / Assert
        with self.assertRaisesRegex(
            ValueError, r"/Root/Material.*DIFFUSE.*missing_key.*has no matching processed texture"
        ):
            resolve_processed_textures((ledger,), TextureProcessingResult(()))

    def test_resolve_processed_textures_raises_on_conflicting_keys(self):
        # Arrange
        processed = (_processed_texture("key_a"), _processed_texture("key_b"))
        ledger = (
            TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "key_a"),
            TextureLedgerEntry("/Root/Material", TextureTypes.DIFFUSE, "key_b"),
        )
        # Act / Assert
        with self.assertRaisesRegex(ValueError, r"Conflicting ledger entries.*key_a.*key_b"):
            resolve_processed_textures(ledger, TextureProcessingResult(processed))
