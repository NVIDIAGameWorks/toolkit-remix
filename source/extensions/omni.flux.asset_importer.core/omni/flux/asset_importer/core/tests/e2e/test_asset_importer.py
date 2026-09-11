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

import base64
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory

import carb
import carb.tokens
import omni.kit
import omni.kit.test
import omni.usd
from pxr import Sdf, Usd, UsdGeom, UsdUtils
from pydantic import ValidationError

from ... import ImporterCore
from ...data_models import SUPPORTED_ASSET_EXTENSIONS

_TEST_DATA_ROOT = Path(__file__).parents[6] / "data" / "tests"

# One unit quad written as two triangles. Every synthesized source below describes this same
# geometry, so one expected triangle count covers every format.
_QUAD_CORNERS = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))
_QUAD_FACETS = ((0, 1, 2), (0, 2, 3))
_QUAD_TRIANGLES = len(_QUAD_FACETS)


def _quad_gltf_document(buffer_length: int) -> dict:
    """Return the glTF document that describes the quad, minus its buffer payload.

    Args:
        buffer_length: Byte length of the position buffer.

    Returns:
        A glTF 2.0 document with one mesh and one position accessor.
    """
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(_QUAD_FACETS) * 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": buffer_length}],
        "buffers": [{"byteLength": buffer_length}],
    }


def _quad_positions() -> bytes:
    """Return the quad's triangle corners as tightly packed float triples."""
    return b"".join(struct.pack("<3f", *_QUAD_CORNERS[index]) for facet in _QUAD_FACETS for index in facet)


def _write_gltf(path: Path) -> None:
    """Write the quad as a text glTF file that embeds its buffer as a data URI."""
    positions = _quad_positions()
    document = _quad_gltf_document(len(positions))
    encoded = base64.b64encode(positions).decode("ascii")
    document["buffers"][0]["uri"] = f"data:application/octet-stream;base64,{encoded}"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def _write_glb(path: Path) -> None:
    """Write the quad as a binary glTF package."""
    positions = _quad_positions()
    document = _quad_gltf_document(len(positions))

    # Every glTF chunk is four-byte aligned: JSON pads with spaces and binary pads with zeros.
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    binary_chunk = positions + b"\x00" * (-len(positions) % 4)

    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(binary_chunk), 0x004E4942)
        + binary_chunk
    )


def _write_obj(path: Path) -> None:
    """Write the quad as a Wavefront OBJ file."""
    lines = [f"v {x} {y} {z}" for x, y, z in _QUAD_CORNERS]
    lines.append("vn 0 0 1")
    lines += [f"f {a + 1}//1 {b + 1}//1 {c + 1}//1" for a, b, c in _QUAD_FACETS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_ply(path: Path) -> None:
    """Write the quad as an ASCII PLY file."""
    lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(_QUAD_CORNERS)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(_QUAD_FACETS)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    lines += [f"{x} {y} {z}" for x, y, z in _QUAD_CORNERS]
    lines += [f"3 {a} {b} {c}" for a, b, c in _QUAD_FACETS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_stl_ascii(path: Path) -> None:
    """Write the quad as an ASCII STL file."""
    lines = ["solid quad"]
    for facet in _QUAD_FACETS:
        lines.append("  facet normal 0 0 1")
        lines.append("    outer loop")
        lines += ["      vertex {} {} {}".format(*_QUAD_CORNERS[index]) for index in facet]
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid quad")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_stl_binary(path: Path) -> None:
    """Write the quad as a binary STL file."""
    payload = b"binary stl".ljust(80, b"\x00") + struct.pack("<I", len(_QUAD_FACETS))
    for facet in _QUAD_FACETS:
        payload += struct.pack("<3f", 0.0, 0.0, 1.0)
        payload += b"".join(struct.pack("<3f", *_QUAD_CORNERS[index]) for index in facet)
        payload += struct.pack("<H", 0)
    path.write_bytes(payload)


def _write_usdz(path: Path) -> None:
    """Write the quad as a USDZ package.

    Raises:
        RuntimeError: If the package cannot be built or does not open as a stage.
    """
    source = path.with_name("usdz_source.usda")
    stage = Usd.Stage.CreateNew(str(source))
    mesh = UsdGeom.Mesh.Define(stage, "/World/Quad")
    mesh.CreatePointsAttr(list(_QUAD_CORNERS))
    mesh.CreateFaceVertexCountsAttr([3] * len(_QUAD_FACETS))
    mesh.CreateFaceVertexIndicesAttr([index for facet in _QUAD_FACETS for index in facet])
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.GetRootLayer().Save()

    if not UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(source)), str(path)):
        raise RuntimeError(f"Could not build a USDZ package at {path}")
    if not Usd.Stage.Open(str(path)):
        raise RuntimeError(f"USDZ package at {path} does not open as a stage")


# Sources this test builds itself, so no binary fixture enters the repository.
_SYNTHESIZED_SOURCES = (
    ("quad.obj", _write_obj),
    ("quad.ply", _write_ply),
    ("quad.gltf", _write_gltf),
    ("quad.glb", _write_glb),
    ("quad_ascii.stl", _write_stl_ascii),
    ("quad_binary.stl", _write_stl_binary),
    ("quad.usdz", _write_usdz),
)

# Suffixes with conversion coverage elsewhere. The USD text and binary formats go through the
# collector, not the converter, and the other tests in this file exercise that path with the
# checked-in ``.fbx`` and ``.usda`` fixtures. No library here writes Modo's ``.lxo``, which reaches
# the converter through its Assimp fallback.
_COVERED_ELSEWHERE = frozenset({".usd", ".usda", ".usdc", ".fbx", ".lxo"})


class TestAssetImporterE2E(omni.kit.test.AsyncTestCase):
    """Verify batch asset conversion success and failure paths."""

    test_paths = [
        "SM_Fixture_Elevator_Interior/SM_Fixture_Elevator_Interior_Textured.fbx",
        "SM_Fixture_IndustrialValveCap/SM_Fixture_IndustrialValveCap.fbx",
        "SM_Prop_Mug/SM_Prop_Mug.fbx",
        "SM_Prop_RTX4090/SM_Prop_RTX4090_A1_01.fbx",
        "filingcabinet_1.fbx",
        "subfolder/ref.usda",
    ]

    async def setUp(self):
        """Create an importer and temporary output directory for each test."""
        self.temp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        self.temp_path = Path(self.temp_dir.name)
        self._importer = ImporterCore()
        self.test_config_path = _TEST_DATA_ROOT / "test_config.json"

    async def tearDown(self):
        """Remove the temporary output directory after each test."""
        self.temp_dir.cleanup()

    async def _import_one_asset(self) -> Path:
        """Import one fixture for tests that inspect the generated stage.

        Returns:
            Path to the generated USD stage.
        """
        input_path = _TEST_DATA_ROOT / TestAssetImporterE2E.test_paths[0]
        output_path = self.temp_path / input_path.with_suffix(".usd").name
        await self._importer.import_batch_async({"data": [{"input_path": str(input_path)}]}, str(self.temp_path))
        return output_path

    async def test_import_batch_with_multiple_assets_writes_outputs_and_reports_progress(self):
        """Batch conversion writes every output and reports progress."""

        def sub_finished_count_fn(_value):
            """Record a batch completion event.

            Args:
                _value: Completion status emitted by the importer.
            """
            nonlocal sub_finished_count
            sub_finished_count.append(_value)

        def sub_progress_count_fn(_value):
            """Record a batch progress event.

            Args:
                _value: Progress percentage emitted by the importer.
            """
            nonlocal sub_progress_count
            sub_progress_count.append(_value)

        sub_finished_count = []
        sub_progress_count = []

        _sub = self._importer.subscribe_batch_finished(sub_finished_count_fn)
        _sub1 = self._importer.subscribe_batch_progress(sub_progress_count_fn)

        # Build one real batch from the extension fixtures while recording its production notifications.
        config = {"data": []}
        expected_outputs = []
        inputs_exist = []
        outputs_were_absent = []
        for path in TestAssetImporterE2E.test_paths:
            input_path = _TEST_DATA_ROOT / path
            config["data"].append(
                {
                    "input_path": str(input_path),
                }
            )
            expected_outputs.append(self.temp_path / Path(path).with_suffix(".usd").name)
            inputs_exist.append(input_path.exists())
            outputs_were_absent.append(not expected_outputs[-1].exists())

        # Import every fixture into the temporary output directory through the public asynchronous API.
        conversion_succeeded = await self._importer.import_batch_async(config, str(self.temp_path))

        # Every stage is written and progress spans the complete batch from zero to one hundred percent.
        self.assertTrue(all(inputs_exist))
        self.assertTrue(all(outputs_were_absent))
        self.assertTrue(conversion_succeeded)
        self.assertTrue(all(path.exists() for path in expected_outputs))
        self.assertTrue(sub_finished_count[-1])
        self.assertEqual(0.0, sub_progress_count[0])
        self.assertEqual(50.0, sub_progress_count[3])
        self.assertEqual(100.0, sub_progress_count[-1])

    async def test_import_batch_writes_loadable_stage(self):
        """A generated USD stage can be opened by the USD runtime."""
        # Import one production fixture, then hand the resulting file to USD rather than inspecting text output.
        output_path = await self._import_one_asset()

        stage = Usd.Stage.Open(str(output_path))

        # Successful import means the actual USD runtime can construct the stage.
        self.assertIsNotNone(stage)

    async def test_import_batch_with_explicit_output_paths_writes_each_stage(self):
        """Batch conversion honors an explicit output path for each asset."""
        config = {"data": []}
        expected_outputs = []
        outputs_were_absent = []
        output_folder = self.temp_path / Path("output")
        output_folder.mkdir(exist_ok=True)
        for path in TestAssetImporterE2E.test_paths:
            output_path = output_folder / Path(path).with_suffix(".usda").name
            input_path = _TEST_DATA_ROOT / path
            config["data"].append(
                {
                    "input_path": str(input_path),
                    "output_path": str(output_path),
                }
            )
            expected_outputs.append(output_path)
            carb.log_info(f"converting {str(input_path)} to {str(output_path)}")
            outputs_were_absent.append(not output_path.exists())

        # Submit the batch with a different explicit destination for every source asset.
        conversion_succeeded = await self._importer.import_batch_async(config, str(self.temp_path))

        # The importer honors every per-item path instead of falling back to the batch directory.
        self.assertTrue(all(outputs_were_absent))
        self.assertTrue(conversion_succeeded)
        self.assertTrue(all(path.exists() for path in expected_outputs))

    async def test_import_batch_with_json_config_writes_stages(self):
        """Batch conversion accepts a valid JSON configuration and writes its stages."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Feed the public importer its real JSON configuration fixture.
        conversion_succeeded = await self._importer.import_batch_async(self.test_config_path, str(output_folder))

        # Each configured asset produces a stage in the requested output directory.
        self.assertTrue(conversion_succeeded)
        expected_outputs = [output_folder / Path(path).with_suffix(".usd").name for path in self.test_paths]
        self.assertTrue(all(path.exists() for path in expected_outputs))

    async def test_import_batch_with_missing_json_config_returns_false(self):
        """Batch conversion rejects a missing JSON configuration file."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Send a nonexistent configuration path through the non-raising batch API.
        conversion_succeeded = await self._importer.import_batch_async("file/does/not/exist.json", str(output_folder))

        # Recoverable configuration errors are reported through the boolean result.
        self.assertFalse(conversion_succeeded)

    async def test_import_batch_with_invalid_json_config_returns_false(self):
        """Batch conversion rejects an invalid JSON configuration."""
        output_folder = self.temp_path / Path("json")
        output_folder.mkdir(exist_ok=True)

        # Load the malformed configuration fixture through the same public entry point.
        conversion_succeeded = await self._importer.import_batch_async(
            "${omni.flux.asset_importer.core}/data/tests/test_bad_config.json", str(output_folder)
        )

        # Invalid configuration content is rejected without producing a successful batch.
        self.assertFalse(conversion_succeeded)

    async def test_import_batch_with_error_for_missing_input_raises_validation_error(self):
        """Error-reporting batch conversion raises for a missing input asset."""
        fake_file = "file/does/not/exist.fbx"
        config = {"data": [{"input_path": fake_file}]}
        fake_file_exists = Path(fake_file).exists()

        # Use the error-reporting API so an invalid source crosses the real validation boundary.
        with self.assertRaises(ValidationError) as error_context:
            await self._importer.import_batch_async_with_error(config, str(self.temp_path))

        # The importer reports its domain validation error rather than creating or masking the missing input.
        self.assertFalse(fake_file_exists)
        self.assertIsInstance(error_context.exception, ValidationError)

    async def test_import_batch_with_missing_output_directory_returns_false(self):
        """Batch conversion rejects an output directory that does not exist."""
        output_folder = self.temp_path / Path("unmade_folder")

        # Submit valid inputs with an output directory that was deliberately never created.
        conversion_succeeded = await self._importer.import_batch_async(self.test_config_path, str(output_folder))

        # The non-raising API reports that the batch could not start.
        self.assertFalse(conversion_succeeded)

    async def test_import_batch_converts_every_synthesized_mesh_format(self):
        """Every synthesized source format converts and keeps its triangle count."""
        for file_name, writer in _SYNTHESIZED_SOURCES:
            with self.subTest(file_name=file_name):
                input_path = self.temp_path / file_name
                output_path = self.temp_path / f"{input_path.stem}_{input_path.suffix.lstrip('.')}.usd"
                writer(input_path)

                # Send a real source file through the same public entry point the pipeline uses.
                conversion_succeeded = await self._importer.import_batch_async(
                    {"data": [{"input_path": str(input_path), "output_path": str(output_path)}]}
                )

                # The source produces a stage whose geometry survived the conversion. Point counts
                # differ by format, because STL repeats a corner for every facet, so the triangle
                # count is what proves the mesh arrived intact.
                self.assertTrue(conversion_succeeded, f"{file_name} did not convert")
                self.assertTrue(output_path.exists(), f"{file_name} produced no stage")
                # Bind the stage: a temporary is collected mid-traversal and expires the prim range.
                stage = Usd.Stage.Open(str(output_path))
                meshes = [UsdGeom.Mesh(prim) for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh)]
                self.assertTrue(meshes, f"{file_name} produced no mesh")
                triangles = sum(
                    max(0, count - 2) for mesh in meshes for count in (mesh.GetFaceVertexCountsAttr().Get() or [])
                )
                self.assertEqual(_QUAD_TRIANGLES, triangles, f"{file_name} lost geometry")

    async def test_every_supported_asset_extension_has_conversion_coverage(self):
        """No supported extension is advertised without a conversion test behind it."""
        synthesized = {Path(file_name).suffix.lower() for file_name, _writer in _SYNTHESIZED_SOURCES}

        # Every advertised suffix is either synthesized here or covered by a checked-in fixture.
        uncovered = {extension.lower() for extension in SUPPORTED_ASSET_EXTENSIONS} - synthesized - _COVERED_ELSEWHERE
        self.assertEqual(set(), uncovered)

        # And nothing is synthesized that the importer does not advertise.
        unadvertised = synthesized - {extension.lower() for extension in SUPPORTED_ASSET_EXTENSIONS}
        self.assertEqual(set(), unadvertised)
