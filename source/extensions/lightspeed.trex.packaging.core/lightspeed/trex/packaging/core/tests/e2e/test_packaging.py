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

import asyncio
import filecmp
import tempfile
from os import walk
from pathlib import Path
from unittest.mock import Mock, call

import carb
import omni.client
import omni.kit.app
import omni.kit.test
import omni.usd
from lightspeed.trex.packaging.core.enum import ModPackagingMode
from lightspeed.trex.packaging.core.packaging import INDETERMINATE_PROGRESS_TOTAL
from lightspeed.trex.packaging.core.packaging import PackagingCore
from omni.flux.asset_importer.core.data_models import UsdExtensions as _UsdExtensions
from omni.kit.test_suite.helpers import get_test_data_path
from pxr import Sdf


def compare_files(fn1, fn2):
    try:  # try to compare the content to ignore CRLF/LF stuffs
        with (
            open(fn1, newline=None, encoding="utf8") as file1,
            open(fn2, newline=None, encoding="utf8") as file2,
        ):
            return file1.read() == file2.read()
    except UnicodeDecodeError:  # not a text file
        return filecmp.cmp(fn1, fn2)


class TestPackagingCoreE2E(omni.kit.test.AsyncTestCase):
    # Before running each test
    async def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    # After running each test
    async def tearDown(self):
        default_context = omni.usd.get_context()
        if default_context and default_context.get_stage():
            await default_context.close_stage_async()
        self.temp_dir.cleanup()
        self.temp_dir = None

    async def test_package_valid_arguments_should_create_expected_file_structure(self):
        packaging_core = PackagingCore()

        progress_mock = Mock()
        completed_mock = Mock()

        progress_mock.side_effect = lambda *args: print(f"Progress: {args}")
        completed_mock.side_effect = lambda *args: print(f"Completed: {args}")

        _progress_sub = packaging_core.subscribe_packaging_progress(progress_mock)
        _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)

        # TEST LOGGING
        mdl_search_paths = carb.tokens.get_tokens_interface().resolve(
            carb.settings.get_settings().get("/renderer/mdl/searchPaths/templates")
        )
        print("MDL Search Paths:\n -", "\n - ".join(mdl_search_paths.split(";")))
        mdl_files = [
            str(Path(root) / file)
            for mdl_path in mdl_search_paths.split(";")
            for root, _, files in walk(mdl_path)
            for file in files
            if file.lower().endswith(".mdl")
        ]
        print("MDL Files:\n -", "\n - ".join(mdl_files))
        print("Resolved MDL Files:\n -", "\n - ".join([str(Path(f).resolve()) for f in mdl_files]))
        # END TEST LOGGING

        output_dir = Path(self.temp_dir.name) / "package"

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"

            await packaging_core.package_async_with_exceptions(
                {
                    "context_name": "PackagingE2E",
                    "mod_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_subproject_mod),
                    ],
                    "selected_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_mod_capture_baker),
                        str(temp_sublayer),
                    ],
                    "output_directory": output_dir,
                    "packaging_mode": ModPackagingMode.REDIRECT,
                    "output_format": None,
                    "mod_name": "Main Project",
                    "mod_version": "1.0.0",
                    "mod_details": "Main Test Notes",
                }
            )

        self.__assert_packaging_progress(
            progress_mock.call_args_list,
            [
                (
                    "Filtering the selected layers...",
                    [(0, 1), (1, 1), (1, 3), (2, 3), (2, 3), (3, 3), (3, 3), (3, 3)],
                ),
                ("Listing references...", [(0, INDETERMINATE_PROGRESS_TOTAL)]),
                ("Looking for invalid references...", [(0, 0), (18, 18)]),
                ("Redirecting dependencies...", self.__expected_progress_range(13)),
                ("Creating temporary layers...", self.__expected_progress_range(10)),
                ("Listing assets to collect...", self.__expected_progress_range(13)),
                ("Updating asset paths...", self.__expected_progress_range(10)),
                ("Collecting assets...", self.__expected_progress_range(9)),
                ("Cleaning up temporary layers...", self.__expected_progress_range(10)),
            ],
        )

        self.assertEqual(1, completed_mock.call_count)
        self.assertEqual(call([], [], False), completed_mock.call_args)

        # Make sure the actual package matches the expected package
        await self.__asset_directories_equal(get_test_data_path(__name__, "package"), output_dir)

    async def test_package_cancel_during_reference_checks_should_complete_cancelled_without_export(self):
        for cancel_status in ("Listing references...", "Looking for invalid references..."):
            with self.subTest(cancel_status=cancel_status):
                # Set up a real packaging run and cancel from the requested reference-check progress stage.
                packaging_core = PackagingCore()
                progress_calls = []
                completed_mock = Mock()
                cancel_on_status, was_cancel_requested = self.__make_cancel_on_status(
                    packaging_core, progress_calls, cancel_status
                )

                _progress_sub = packaging_core.subscribe_packaging_progress(cancel_on_status)
                _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)

                output_dir = Path(self.temp_dir.name) / f"package_cancel_{cancel_status.split()[0].lower()}"

                with tempfile.TemporaryDirectory() as temp_input:
                    # Copy the fixture project so the test can verify that cancellation leaves no package behind.
                    input_project_path = get_test_data_path(__name__, "projects")
                    temp_project_path = Path(temp_input) / "projects"

                    result = await omni.client.copy_async(input_project_path, str(temp_project_path))
                    self.assertEqual(
                        result,
                        omni.client.Result.OK,
                        "Can't copy the project to the temporary directory",
                    )

                    temp_project_root = temp_project_path / "MainProject"
                    temp_mod_usda = temp_project_root / "mod.usda"
                    temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
                    temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
                    temp_sublayer = temp_project_root / "sublayer.usda"

                    # Run packaging through the real pipeline and let the progress callback request cancellation.
                    await asyncio.wait_for(
                        packaging_core.package_async_with_exceptions(
                            {
                                "context_name": f"PackagingE2E_Cancel_{cancel_status.split()[0]}",
                                "mod_layer_paths": [
                                    str(temp_mod_usda),
                                    str(temp_subproject_mod),
                                ],
                                "selected_layer_paths": [
                                    str(temp_mod_usda),
                                    str(temp_mod_capture_baker),
                                    str(temp_sublayer),
                                ],
                                "output_directory": output_dir,
                                "packaging_mode": ModPackagingMode.REDIRECT,
                                "output_format": None,
                                "mod_name": "Main Project",
                                "mod_version": "1.0.0",
                                "mod_details": "Main Test Notes",
                            }
                        ),
                        timeout=30,
                    )

                # Confirm the cancellation completed cleanly, skipped export, and still reported cleanup progress.
                self.assertTrue(was_cancel_requested())
                self.assertEqual(1, completed_mock.call_count)
                errors, failed_assets, was_cancelled = completed_mock.call_args.args
                self.assertEqual([], errors)
                self.assertEqual([], failed_assets)
                self.assertTrue(was_cancelled)
                self.assertFalse(output_dir.exists())
                self.assertIn("Cleaning up temporary layers...", [status for _, _, status in progress_calls])

    async def test_packaging_all_modes_should_not_modify_source_project_files(self):
        for packaging_mode in (
            ModPackagingMode.REDIRECT,
            ModPackagingMode.IMPORT,
            ModPackagingMode.FLATTEN,
        ):
            with self.subTest(packaging_mode=packaging_mode.value):
                packaging_core = PackagingCore()
                output_dir = Path(self.temp_dir.name) / f"package_{packaging_mode.value}"

                with tempfile.TemporaryDirectory() as temp_input:
                    input_project_path = get_test_data_path(__name__, "projects")
                    temp_project_path = Path(temp_input) / "projects"

                    result = await omni.client.copy_async(input_project_path, str(temp_project_path))
                    self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

                    temp_project_root = temp_project_path / "MainProject"
                    before_snapshot = self.__snapshot_directory_contents(temp_project_root)

                    temp_mod_usda = temp_project_root / "mod.usda"
                    temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
                    temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
                    temp_sublayer = temp_project_root / "sublayer.usda"

                    await packaging_core.package_async_with_exceptions(
                        {
                            "context_name": f"PackagingE2E_{packaging_mode.value}",
                            "mod_layer_paths": [
                                str(temp_mod_usda),
                                str(temp_subproject_mod),
                            ],
                            "selected_layer_paths": [
                                str(temp_mod_usda),
                                str(temp_mod_capture_baker),
                                str(temp_sublayer),
                            ],
                            "output_directory": output_dir,
                            "packaging_mode": packaging_mode,
                            "mod_name": "Main Project",
                            "mod_version": "1.0.0",
                            "mod_details": "Main Test Notes",
                        }
                    )

                    after_snapshot = self.__snapshot_directory_contents(temp_project_root)

                self.assertDictEqual(before_snapshot, after_snapshot)

    async def test_package_missing_authored_texture_should_report_failed_asset_and_skip_package(self):
        packaging_core = PackagingCore()

        completed_mock = Mock()
        _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)

        output_dir = Path(self.temp_dir.name) / "package_missing_texture"

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"
            material_layer_path = temp_project_root / "materials" / "AperturePBR_Translucent.usda"
            missing_texture_path = temp_project_root / "materials" / "not_created.a.rtex.dds"

            self.__author_missing_texture(material_layer_path)

            await packaging_core.package_async_with_exceptions(
                {
                    "context_name": "PackagingE2EMissingTexture",
                    "mod_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_subproject_mod),
                    ],
                    "selected_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_mod_capture_baker),
                        str(temp_sublayer),
                    ],
                    "output_directory": output_dir,
                    "mod_name": "Main Project",
                    "mod_version": "1.0.0",
                    "mod_details": "Main Test Notes",
                }
            )

            self.assertEqual(1, completed_mock.call_count)
            errors, failed_assets, was_cancelled = completed_mock.call_args.args
            self.assertEqual([], errors)
            self.assertFalse(was_cancelled)
            self.assertEqual(1, len(failed_assets))

            _, prop_path, missing_path = failed_assets[0]
            self.assertEqual("/RootNode/Looks/mat_CC76669780A210D2/Shader.inputs:diffuse_texture", prop_path)
            self.assertEqual(missing_texture_path.as_posix(), missing_path)
            self.assertFalse(output_dir.exists())

    async def test_package_all_modes_missing_reference_should_report_failed_asset_and_skip_package(self):
        for packaging_mode in (
            ModPackagingMode.REDIRECT,
            ModPackagingMode.IMPORT,
            ModPackagingMode.FLATTEN,
        ):
            with self.subTest(packaging_mode=packaging_mode.value):
                packaging_core = PackagingCore()
                completed_mock = Mock()
                _completed_sub = packaging_core.subscribe_packaging_completed(completed_mock)

                output_dir = Path(self.temp_dir.name) / f"package_missing_ref_{packaging_mode.value}"

                with tempfile.TemporaryDirectory() as temp_input:
                    input_project_path = get_test_data_path(__name__, "projects")
                    temp_project_path = Path(temp_input) / "projects"

                    result = await omni.client.copy_async(input_project_path, str(temp_project_path))
                    self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

                    temp_project_root = temp_project_path / "MainProject"
                    temp_mod_usda = temp_project_root / "mod.usda"
                    temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
                    temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
                    temp_sublayer = temp_project_root / "sublayer.usda"

                    missing_prim_path, missing_reference_path = self.__author_missing_reference(temp_sublayer)

                    await packaging_core.package_async_with_exceptions(
                        {
                            "context_name": f"PackagingE2EMissingReference_{packaging_mode.value}",
                            "mod_layer_paths": [
                                str(temp_mod_usda),
                                str(temp_subproject_mod),
                            ],
                            "selected_layer_paths": [
                                str(temp_mod_usda),
                                str(temp_mod_capture_baker),
                                str(temp_sublayer),
                            ],
                            "output_directory": output_dir,
                            "packaging_mode": packaging_mode,
                            "mod_name": "Main Project",
                            "mod_version": "1.0.0",
                            "mod_details": "Main Test Notes",
                        }
                    )

                    self.assertEqual(1, completed_mock.call_count)
                    errors, failed_assets, was_cancelled = completed_mock.call_args.args
                    self.assertEqual([], errors)
                    self.assertFalse(was_cancelled)
                    self.assertTrue(
                        any(
                            prim_path == missing_prim_path and asset_path.replace("\\", "/") == missing_reference_path
                            for _, prim_path, asset_path in failed_assets
                        ),
                        msg=f"Missing reference was not reported. Failed assets: {failed_assets}",
                    )
                    self.assertFalse(output_dir.exists())

    async def test_package_flatten_mode_should_export_single_root_layer_and_prune_packaged_sublayers(self):
        packaging_core = PackagingCore()
        output_dir = Path(self.temp_dir.name) / "package_flatten"

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"

            await packaging_core.package_async_with_exceptions(
                {
                    "context_name": "PackagingE2E_Flatten",
                    "mod_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_subproject_mod),
                    ],
                    "selected_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_mod_capture_baker),
                        str(temp_sublayer),
                    ],
                    "output_directory": output_dir,
                    "packaging_mode": ModPackagingMode.FLATTEN,
                    "output_format": None,
                    "mod_name": "Main Project",
                    "mod_version": "1.0.0",
                    "mod_details": "Main Test Notes",
                }
            )

        flattened_root = output_dir / "mod.usda"
        self.assertTrue(flattened_root.exists())
        self.assertFalse((output_dir / "sublayer.usda").exists())
        self.assertFalse((output_dir / "mod_capture_baker.usda").exists())
        self.assertFalse((output_dir / "SubUSDs").exists())
        self.assertFalse((output_dir / "deps" / "mods").exists())

        flattened_text = flattened_root.read_text(encoding="utf8")
        self.assertNotIn("sublayer.usda", flattened_text)
        self.assertNotIn("mod_capture_baker.usda", flattened_text)
        self.assertNotIn("../../mods/SubProject", flattened_text)
        self.assertNotIn('string SubProject = "0.0.1"', flattened_text)

    async def test_package_usdc_output_format_should_export_root_layer_as_usdc(self):
        packaging_core = PackagingCore()
        output_dir = Path(self.temp_dir.name) / "package_usdc_root"

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"

            await packaging_core.package_async_with_exceptions(
                {
                    "context_name": "PackagingE2E_BinaryRoot",
                    "mod_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_subproject_mod),
                    ],
                    "selected_layer_paths": [
                        str(temp_mod_usda),
                        str(temp_mod_capture_baker),
                        str(temp_sublayer),
                    ],
                    "output_directory": output_dir,
                    "packaging_mode": ModPackagingMode.REDIRECT,
                    "output_format": _UsdExtensions.USDC,
                    "mod_name": "Main Project",
                    "mod_version": "1.0.0",
                    "mod_details": "Main Test Notes",
                }
            )

        binary_root = output_dir / "mod.usdc"
        self.assertTrue(binary_root.exists())
        self.assertFalse((output_dir / "mod.usda").exists())
        self.assertTrue((output_dir / "sublayer.usda").exists())
        self.assertEqual(b"PXR-USDC", binary_root.read_bytes()[:8])

    async def test_packaging_twice_should_not_dirty_open_stage_and_should_recreate_package(self):
        packaging_core = PackagingCore()
        output_dir = Path(self.temp_dir.name) / "package_sequential"
        packaging_context_name = "PackagingE2E_Sequential"
        source_context = omni.usd.get_context()

        with tempfile.TemporaryDirectory() as temp_input:
            input_project_path = get_test_data_path(__name__, "projects")
            temp_project_path = Path(temp_input) / "projects"

            result = await omni.client.copy_async(input_project_path, str(temp_project_path))
            self.assertEqual(result, omni.client.Result.OK, "Can't copy the project to the temporary directory")

            temp_project_root = temp_project_path / "MainProject"
            temp_main_project = temp_project_root / "main_project.usda"
            temp_mod_usda = temp_project_root / "mod.usda"
            temp_subproject_mod = temp_project_root / "deps" / "mods" / "SubProject" / "mod.usda"
            temp_mod_capture_baker = temp_project_root / "mod_capture_baker.usda"
            temp_sublayer = temp_project_root / "sublayer.usda"

            await source_context.open_stage_async(str(temp_main_project))
            await omni.kit.app.get_app().next_update_async()
            self.__assert_context_is_clean(source_context, "before first packaging")

            schema = {
                "context_name": packaging_context_name,
                "mod_layer_paths": [
                    str(temp_mod_usda),
                    str(temp_subproject_mod),
                ],
                "selected_layer_paths": [
                    str(temp_mod_usda),
                    str(temp_mod_capture_baker),
                    str(temp_sublayer),
                ],
                "output_directory": output_dir,
                "packaging_mode": ModPackagingMode.FLATTEN,
                "output_format": _UsdExtensions.USD,
                "mod_name": "Main Project",
                "mod_version": "1.0.0",
                "mod_details": "Main Test Notes",
            }

            await packaging_core.package_async_with_exceptions(schema)
            await omni.kit.app.get_app().next_update_async()
            self.__assert_context_is_clean(source_context, "after first packaging")
            self.assertTrue((output_dir / "mod.usd").exists(), "First packaging did not create the packaged root file")

            await packaging_core.package_async_with_exceptions(schema)
            await omni.kit.app.get_app().next_update_async()
            self.__assert_context_is_clean(source_context, "after second packaging")
            self.assertTrue(
                (output_dir / "mod.usd").exists(), "Second packaging did not recreate the packaged root file"
            )

        packaging_context = omni.usd.get_context(packaging_context_name)
        if packaging_context and packaging_context.get_stage():
            await packaging_context.close_stage_async()

    def __author_missing_texture(self, material_layer_path: Path) -> str:
        material_layer = Sdf.Layer.FindOrOpen(str(material_layer_path))
        self.assertIsNotNone(material_layer)

        shader_spec = material_layer.GetPrimAtPath("/Looks/mat_AperturePBR_Translucent/Shader")
        self.assertIsNotNone(shader_spec)

        attr_spec = Sdf.AttributeSpec(shader_spec, "inputs:diffuse_texture", Sdf.ValueTypeNames.Asset)
        attr_spec.default = Sdf.AssetPath("./not_created.a.rtex.dds")
        material_layer.Save()
        material_layer_identifier = material_layer.identifier
        material_layer = None
        return material_layer_identifier

    def __author_missing_reference(self, layer_path: Path) -> tuple[str, str]:
        missing_reference_path = layer_path.parent / "not_created_ref.usda"
        layer = Sdf.Layer.FindOrOpen(str(layer_path))
        self.assertIsNotNone(layer)

        prim_path = "/RootNode/BadReference"
        prim_spec = Sdf.CreatePrimInLayer(layer, prim_path)
        self.assertIsNotNone(prim_spec)
        prim_spec.specifier = Sdf.SpecifierDef
        prim_spec.typeName = "Xform"
        prim_spec.referenceList.Append(Sdf.Reference("./not_created_ref.usda"))
        layer.Save()
        layer = None
        return prim_path, missing_reference_path.as_posix()

    @staticmethod
    def __expected_progress_range(total: int) -> list[tuple[int, int]]:
        return [(current, total) for current in range(total + 1)]

    @staticmethod
    def __make_cancel_on_status(packaging_core: PackagingCore, progress_calls: list, cancel_status: str):
        cancel_requested = False

        def cancel_on_status(current, total, status):
            nonlocal cancel_requested
            progress_calls.append((current, total, status))
            if status == cancel_status and not cancel_requested:
                cancel_requested = True
                packaging_core.cancel()

        return cancel_on_status, lambda: cancel_requested

    def __assert_packaging_progress(
        self,
        progress_calls,
        expected_progress_by_stage: list[tuple[str, list[tuple[int, int]]]],
    ):
        actual_progress_by_stage = []
        current_status = None
        current_progress = []

        for progress_call in progress_calls:
            current, total, status = progress_call.args
            if status != current_status:
                if current_status is not None:
                    actual_progress_by_stage.append((current_status, current_progress))
                current_status = status
                current_progress = []
            current_progress.append((current, total))

        if current_status is not None:
            actual_progress_by_stage.append((current_status, current_progress))

        self.assertEqual(expected_progress_by_stage, actual_progress_by_stage)

    async def __asset_directories_equal(self, expected: Path, actual: Path):
        # Make sure all the files in the expected directory are identical in the actual directory
        for dirpath, _, filenames in walk(expected):
            for filename in filenames:
                expected_path = Path(dirpath) / filename
                actual_path = actual / expected_path.relative_to(expected)
                self.assertTrue(
                    actual_path.exists(), msg=f"The file was not found in the actual package: {expected_path}"
                )
                self.assertTrue(
                    compare_files(expected_path, actual_path),
                    msg=f"The contents of the expected and actual files don't match: {expected_path}",
                )

        # Make sure no extra files exist in the actual directory
        for dirpath, _, filenames in walk(actual):
            for filename in filenames:
                actual_path = Path(dirpath) / filename
                expected_path = expected / actual_path.relative_to(actual)
                self.assertTrue(
                    expected_path.exists(), msg=f"An extra file was found in the actual package: {actual_path}"
                )

    def __snapshot_directory_contents(self, root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)).replace("\\", "/"): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def __assert_context_is_clean(self, context, label: str):
        stage = context.get_stage()
        self.assertIsNotNone(stage, msg=f"Expected an open stage for {label}")
        dirty_layers = [layer.identifier for layer in stage.GetLayerStack() if getattr(layer, "dirty", False)]
        self.assertFalse(
            context.has_pending_edit(),
            msg=f"Context had pending edits {label}. Dirty layers: {dirty_layers}",
        )
        self.assertListEqual([], dirty_layers, msg=f"Unexpected dirty layers {label}: {dirty_layers}")
