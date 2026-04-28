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

import asyncio
import io
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import omni.kit.test
from lightspeed.trex.rtxio.core import RtxIoCore
from pxr import Sdf, Usd

_RTXIO_PACKAGE_MAGIC = b"\x0d\xd0\xad\xba"


class TestRtxIoCoreE2E(omni.kit.test.AsyncTestCase):
    @staticmethod
    def _write_fake_rtxio_package(path: Path):
        path.write_bytes(_RTXIO_PACKAGE_MAGIC + b"\x00" * 8)

    async def test_find_invalid_stage_asset_references_detects_missing_textures(self):
        rtxio_core = RtxIoCore()
        with tempfile.TemporaryDirectory() as tmp_dir:
            layer_path = Path(tmp_dir) / "layer.usda"
            layer = Sdf.Layer.CreateNew(str(layer_path))
            with Sdf.ChangeBlock():
                shader_spec = Sdf.CreatePrimInLayer(layer, "/RootNode/Looks/mat_001/Shader")
                shader_spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(shader_spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./not_created.a.rtex.dds")
            layer.Save()
            missing_posix = (layer_path.parent / "not_created.a.rtex.dds").as_posix()

            result = await rtxio_core.scan_invalid_stage_asset_references(layer_path)
            self.assertEqual(1, len(result))
            layer_id, prop_path, abs_path = result[0]
            self.assertEqual(layer_path.as_posix(), layer_id)
            self.assertEqual("/RootNode/Looks/mat_001/Shader.inputs:diffuse_texture", prop_path)
            self.assertEqual(missing_posix, abs_path)

    async def test_collect_invalid_stage_assets_detects_missing_texture_masked_by_valid_stronger_sublayer(self):
        rtxio_core = RtxIoCore()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            (tmp / "valid_texture.a.rtex.dds").touch()
            missing_texture_posix = (tmp / "missing_texture.a.rtex.dds").as_posix()

            weaker_layer = Sdf.Layer.CreateNew(str(tmp / "weaker.usda"))
            with Sdf.ChangeBlock():
                shader_spec = Sdf.CreatePrimInLayer(weaker_layer, "/RootNode/Looks/mat_001/Shader")
                shader_spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(shader_spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./missing_texture.a.rtex.dds")
            weaker_layer.Save()

            stronger_layer = Sdf.Layer.CreateNew(str(tmp / "stronger.usda"))
            with Sdf.ChangeBlock():
                shader_spec = Sdf.CreatePrimInLayer(stronger_layer, "/RootNode/Looks/mat_001/Shader")
                shader_spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(shader_spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./valid_texture.a.rtex.dds")
                stronger_layer.subLayerPaths.append("./weaker.usda")
            stronger_layer.Save()

            stage = Sdf.Layer.FindOrOpen(stronger_layer.identifier)
            usd_stage = Usd.Stage.Open(stage.identifier) if stage else None

            result = list(
                rtxio_core.collect_invalid_stage_assets(
                    list(usd_stage.TraverseAll()),
                    [missing_texture_posix],
                    include_missing_authored_textures=False,
                )
            )
            usd_stage = None

            self.assertEqual(1, len(result), msg=f"Expected 1 result but got: {result}")
            layer_id, prim_path, resolved_path = result[0]
            self.assertEqual(weaker_layer.identifier, layer_id)
            self.assertEqual("/RootNode/Looks/mat_001/Shader.inputs:diffuse_texture", prim_path)
            self.assertEqual(missing_texture_posix, resolved_path)

    async def test_collect_invalid_stage_assets_detects_missing_textures_in_both_sublayers(self):
        rtxio_core = RtxIoCore()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            missing_a_posix = (tmp / "missing_a.a.rtex.dds").as_posix()
            missing_b_posix = (tmp / "missing_b.a.rtex.dds").as_posix()

            weaker_layer = Sdf.Layer.CreateNew(str(tmp / "weaker.usda"))
            with Sdf.ChangeBlock():
                spec = Sdf.CreatePrimInLayer(weaker_layer, "/RootNode/Looks/mat_001/Shader")
                spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./missing_b.a.rtex.dds")
            weaker_layer.Save()

            stronger_layer = Sdf.Layer.CreateNew(str(tmp / "stronger.usda"))
            with Sdf.ChangeBlock():
                spec = Sdf.CreatePrimInLayer(stronger_layer, "/RootNode/Looks/mat_001/Shader")
                spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./missing_a.a.rtex.dds")
                stronger_layer.subLayerPaths.append("./weaker.usda")
            stronger_layer.Save()

            usd_stage = Usd.Stage.Open(stronger_layer.identifier)
            result = list(
                rtxio_core.collect_invalid_stage_assets(
                    list(usd_stage.TraverseAll()),
                    [missing_a_posix, missing_b_posix],
                    include_missing_authored_textures=False,
                )
            )
            usd_stage = None

            attr_path = "/RootNode/Looks/mat_001/Shader.inputs:diffuse_texture"
            self.assertEqual(2, len(result), msg=f"Expected 2 results but got: {result}")
            layer_ids = {entry[0] for entry in result}
            self.assertIn(stronger_layer.identifier, layer_ids)
            self.assertIn(weaker_layer.identifier, layer_ids)
            for _, prim_path, _ in result:
                self.assertEqual(attr_path, prim_path)

    async def test_collect_invalid_stage_assets_detects_missing_file_without_dependency_scan(self):
        rtxio_core = RtxIoCore()
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            layer = Sdf.Layer.CreateNew(str(tmp / "layer.usda"))
            with Sdf.ChangeBlock():
                shader_spec = Sdf.CreatePrimInLayer(layer, "/RootNode/Looks/mat_001/Shader")
                shader_spec.specifier = Sdf.SpecifierOver
                attr_spec = Sdf.AttributeSpec(shader_spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
                attr_spec.default = Sdf.AssetPath("./not_created.a.rtex.dds")
            layer.Save()

            usd_stage = Usd.Stage.Open(layer.identifier)
            result = rtxio_core.collect_invalid_stage_assets(
                list(usd_stage.TraverseAll()),
                [],
                include_missing_authored_textures=True,
            )
            usd_stage = None

            missing_posix = (tmp / "not_created.a.rtex.dds").as_posix()
            self.assertEqual(1, len(result))
            layer_id, prop_path, abs_path = next(iter(result))
            self.assertEqual(layer.identifier, layer_id)
            self.assertEqual("/RootNode/Looks/mat_001/Shader.inputs:diffuse_texture", prop_path)
            self.assertEqual(missing_posix, abs_path)

    async def test_compress_directory_with_split_size_should_pass_split_argument(self):
        rtxio_core = RtxIoCore()
        popen_calls = []

        class _FakeProc:
            def __init__(self, command):
                popen_calls.append(command)
                self.stdout = io.BytesIO(b"dds_0\n")
                self.stderr = io.BytesIO()
                self.returncode = 0

            def wait(self):
                return self.returncode

            def terminate(self):
                self.returncode = -1

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_directory = Path(tmp_dir)
            (output_directory / "texture.dds").touch()
            exe = output_directory / "RtxIoResourcePackager.exe"
            exe.touch()
            loop_mock = Mock()

            with (
                patch.object(RtxIoCore, "_find_packager_exe", return_value=exe),
                patch(
                    "lightspeed.trex.rtxio.core.core.subprocess.Popen",
                    side_effect=lambda *args, **kwargs: _FakeProc(args[0]),
                ),
                patch("lightspeed.trex.rtxio.core.core.asyncio.get_event_loop", return_value=loop_mock),
            ):

                def _run_in_executor(_executor, function):
                    function()
                    future = asyncio.Future()
                    future.set_result(None)
                    return future

                loop_mock.run_in_executor.side_effect = _run_in_executor

                errors = await rtxio_core.compress_directory(output_directory, split_size_mb=2048)

        self.assertEqual([], errors)
        self.assertEqual(1, len(popen_calls))
        self.assertEqual(["--split", "2048"], popen_calls[0][-2:])

    async def test_extract_packages_with_force_overwrite_should_pass_force_argument(self):
        rtxio_core = RtxIoCore()
        popen_calls = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            mod_directory = Path(tmp_dir)
            self._write_fake_rtxio_package(mod_directory / "mod.pkg")
            exe = mod_directory / "RtxIoResourceExtractor.exe"
            exe.touch()
            loop_mock = Mock()

            class _FakeProc:
                def __init__(self, command):
                    popen_calls.append(command)
                    self.stderr = io.BytesIO()
                    self.returncode = 0

                def wait(self):
                    return self.returncode

                def terminate(self):
                    self.returncode = -1

            def _run_in_executor(_executor, function):
                function()
                future = asyncio.Future()
                future.set_result(None)
                return future

            with (
                patch.object(RtxIoCore, "_find_extractor_exe", return_value=exe),
                patch(
                    "lightspeed.trex.rtxio.core.core.subprocess.Popen",
                    side_effect=lambda *args, **kwargs: _FakeProc(args[0]),
                ),
                patch("lightspeed.trex.rtxio.core.core.asyncio.get_event_loop", return_value=loop_mock),
            ):
                loop_mock.run_in_executor.side_effect = _run_in_executor

                errors = await rtxio_core.extract_packages(mod_directory, force_overwrite=True)

        self.assertEqual([], errors)
        self.assertEqual(1, len(popen_calls))
        self.assertEqual("--force", popen_calls[0][-1])

    async def test_delete_dds_files_cancelled_should_leave_remaining_files(self):
        rtxio_core = RtxIoCore()
        rtxio_core._cancel_token = True

        with tempfile.TemporaryDirectory() as tmp_dir:
            dds_file = Path(tmp_dir) / "texture.dds"
            dds_file.touch()

            await rtxio_core.delete_dds_files(Path(tmp_dir))

            self.assertTrue(dds_file.exists())

    async def test_find_rtxio_package_files_should_ignore_split_fragments(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            mod_directory = Path(tmp_dir)
            root_pkg = mod_directory / "mod.pkg"
            split_pkg = mod_directory / "mod.pkg.000"
            nested_pkg = mod_directory / "nested" / "submod.pkg"
            fake_pkg = mod_directory / "fake.pkg"
            nested_pkg.parent.mkdir()

            self._write_fake_rtxio_package(root_pkg)
            self._write_fake_rtxio_package(split_pkg)
            self._write_fake_rtxio_package(nested_pkg)
            fake_pkg.write_text("not rtxio", encoding="utf-8")

            result = RtxIoCore.find_rtxio_package_files(mod_directory)

        self.assertEqual(sorted([nested_pkg, root_pkg]), sorted(result))
