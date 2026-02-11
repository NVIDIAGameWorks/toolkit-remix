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

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import call, patch

import carb
import omni.kit.test
from omni.flux.utils.common import path_utils as _path_utils
from omni.flux.utils.common.omni_url import OmniUrl


class TestPathUtils(omni.kit.test.AsyncTestCase):
    async def test_is_absolute_path(self):
        # Assert
        self.assertTrue(_path_utils.is_absolute_path(r"C:\path"))
        self.assertTrue(_path_utils.is_absolute_path(r"C:/path"))
        self.assertTrue(_path_utils.is_absolute_path(r"/path"))
        self.assertTrue(_path_utils.is_absolute_path(r"file:Z:/path"))
        self.assertTrue(_path_utils.is_absolute_path(r"file:/path"))
        self.assertTrue(_path_utils.is_absolute_path(r"omniverse://server/my_dir/my_path/my_file.usd"))
        self.assertTrue(_path_utils.is_absolute_path(r"omni://server/my_dir/my_path/my_file.usd"))
        self.assertFalse(_path_utils.is_absolute_path(r"file:path/to"))
        self.assertFalse(_path_utils.is_absolute_path(r"./path"))
        self.assertFalse(_path_utils.is_absolute_path(r"path/to"))
        self.assertFalse(_path_utils.is_absolute_path(r"path"))

    async def test_is_file_path_valid(self):
        # Assert
        with tempfile.NamedTemporaryFile("w") as tmpfile:
            self.assertTrue(_path_utils.is_file_path_valid(tmpfile.name))

        with patch.object(carb, "log_error"):
            self.assertFalse(_path_utils.is_file_path_valid(""))
            self.assertFalse(_path_utils.is_file_path_valid(" "))

    async def test_get_new_hash_equal_default_key(self):
        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = "12345"
            with tempfile.NamedTemporaryFile("w") as jsonfile, tempfile.NamedTemporaryFile("w") as tmpfile:
                data = {
                    "src_hash": hash_str,
                }
                json.dump(data, jsonfile, indent=4)
                jsonfile.flush()
                self.assertEqual(_path_utils.get_new_hash(tmpfile.name, jsonfile.name), hash_str)

    async def test_get_new_hash_equal_custom_key(self):
        # test with a custom key
        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = "12345"
            with tempfile.NamedTemporaryFile("w") as jsonfile, tempfile.NamedTemporaryFile("w") as tmpfile:
                data = {
                    "blabla": hash_str,
                }
                json.dump(data, jsonfile, indent=4)
                jsonfile.flush()
                self.assertEqual(_path_utils.get_new_hash(tmpfile.name, jsonfile.name, key="blabla"), hash_str)
                self.assertEqual(mock2.call_args, call(jsonfile.name, "blabla"))

    async def test_get_new_hash_none_different_hash(self):
        with patch.object(_path_utils, "hash_file") as mock:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = None
            with tempfile.NamedTemporaryFile("w") as jsonfile, tempfile.NamedTemporaryFile("w") as tmpfile:
                data = {
                    "src_hash": hash_str,
                }
                json.dump(data, jsonfile, indent=4)
                jsonfile.flush()
                self.assertIsNone(_path_utils.get_new_hash(tmpfile.name, jsonfile.name))

    async def test_get_new_hash_none_same_hash(self):
        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = hash_str
            with tempfile.NamedTemporaryFile("w") as jsonfile, tempfile.NamedTemporaryFile("w") as tmpfile:
                data = {
                    "src_hash": hash_str,
                }
                json.dump(data, jsonfile, indent=4)
                jsonfile.flush()
                self.assertIsNone(_path_utils.get_new_hash(tmpfile.name, jsonfile.name))

    async def test_hash_match_metadata_false(self):
        with patch.object(_path_utils, "hash_file") as mock:
            mock.return_value = None
            with tempfile.NamedTemporaryFile("w") as tmpfile:
                self.assertFalse(_path_utils.hash_match_metadata(tmpfile.name))

        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = None
            with tempfile.NamedTemporaryFile("w") as tmpfile:
                self.assertFalse(_path_utils.hash_match_metadata(tmpfile.name))

        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = "123456789"
            with tempfile.NamedTemporaryFile("w") as tmpfile:
                self.assertFalse(_path_utils.hash_match_metadata(tmpfile.name))

    async def test_hash_match_metadata_true(self):
        with patch.object(_path_utils, "hash_file") as mock, patch.object(_path_utils, "read_metadata") as mock2:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            mock2.return_value = hash_str
            with tempfile.NamedTemporaryFile("w") as tmpfile:
                self.assertTrue(_path_utils.hash_match_metadata(tmpfile.name))

    async def test_delete_metadata(self):
        with patch.object(_path_utils, "hash_file") as mock:
            hash_str = "fd32abf0d19be70ea063dd7e9b4706e5"
            mock.return_value = hash_str
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".meta") as jsonfile:
                jsonfile_name = jsonfile.name
                data = {
                    "src_hash": hash_str,
                    "blabla": "hello",
                }
                json.dump(data, jsonfile, indent=4)
                jsonfile.flush()

            try:
                data = _path_utils.read_json_file(jsonfile_name)
                self.assertTrue("blabla" in data)

                _path_utils.delete_metadata(str(Path(jsonfile_name).parent / Path(jsonfile_name).stem), "blabla")
                data = _path_utils.read_json_file(jsonfile_name)
                self.assertTrue("blabla" not in data)
            finally:
                os.unlink(jsonfile_name)

    async def test_write_read_metadata(self):
        with tempfile.NamedTemporaryFile("w") as tmpfile:
            key = "test_key"
            key2 = "test_key2"
            value = "123456789"
            value2 = "1111111111"
            _path_utils.write_metadata(str(tmpfile.name), key, value)

            self.assertTrue(Path(tmpfile.name).with_suffix(".meta").exists())
            self.assertEqual(_path_utils.read_metadata(str(tmpfile.name), key), value)

            _path_utils.write_metadata(str(tmpfile.name), key2, value2)
            self.assertEqual(_path_utils.read_metadata(str(tmpfile.name), key), value)
            self.assertEqual(_path_utils.read_metadata(str(tmpfile.name), key2), value2)

    async def test_hash_file_exist(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp_file:
            tmp_file_name = tmp_file.name
            tmp_file.write("123456789")

        try:
            result = _path_utils.hash_file(str(tmp_file_name))
            self.assertEqual(result, "25f9e794323b453885f5181f1b624d0b")
        finally:
            os.unlink(tmp_file_name)

    async def test_hash_file_dont_exit(self):
        with patch.object(carb, "log_error") as mock:
            result = _path_utils.hash_file("file/font/exist")
            self.assertTrue(mock.called)
            self.assertIsNone(result)

    async def test_is_texture_udim(self):
        for text in [
            "c:/toto.<UDIM>.png",
            "c:/toto<UDIM>.png",
            "c:/toto_<UDIM>.png",
            "toto_<UDIM>.png",
            "c:/toto.<UVTILE0>.png",
            "c:/toto<UVTILE0>.png",
            "c:/toto_<UVTILE0>.png",
            "toto_<UVTILE0>.png",
            "c:/toto.<UVTILE1>.png",
            "c:/toto<UVTILE1>.png",
            "c:/toto_<UVTILE1>.png",
            "toto_<UVTILE1>.png",
        ]:
            with self.subTest(name=f"is_udim_texture_{text}"):
                self.assertTrue(_path_utils.is_udim_texture(text))

    async def test_is_not_texture_udim(self):
        for text in [
            "c:/toto.<UDIM_>.png",
            "c:/toto<UDI_M>.png",
            "c:/toto.png",
            "c:/toto.<UVTI LE0>.png",
            "c:/toto<UVTI_LE0>.png",
            "c:/toto_<UVT_ILE1>.png",
            "toto_<UVTIL E1>.png",
        ]:
            with self.subTest(name=f"is_not_udim_texture_{text}"):
                self.assertFalse(_path_utils.is_udim_texture(text))

    async def test_get_udim_sequence(self):
        with patch.object(OmniUrl, "iterdir") as mock:
            mock.return_value = [
                "c:/toto.1001.png",
                "c:/toto.1010.png",
                "c:/toto.1100.png",
                "c:/toto.1101.png",
                "c:/toto.1000.png",
                "c:/toto.png",
                "c:/toto.bla.png",
                "c:/toto.60.png",
            ]
            self.assertEqual(
                _path_utils.get_udim_sequence("c:/toto.<UDIM>.png"),
                [
                    "c:/toto.1001.png",
                    "c:/toto.1010.png",
                    "c:/toto.1100.png",
                    "c:/toto.1101.png",
                ],
            )

    async def test_texture_to_udim(self):
        for text_in, text_out in {
            "c:/toto.1001.png": "c:/toto.<UDIM>.png",
            "c:/toto.1010.png": "c:/toto.<UDIM>.png",
            "c:/toto.1100.png": "c:/toto.<UDIM>.png",
            "c:/toto.1101.png": "c:/toto.<UDIM>.png",
            "c:/toto.1000.png": "c:/toto.1000.png",
            "c:/toto.png": "c:/toto.png",
            "c:/toto.bla.png": "c:/toto.bla.png",
            "c:/toto.60.png": "c:/toto.60.png",
        }.items():
            with self.subTest(name=f"texture_to_udim_{text_in}"):
                self.assertEqual(_path_utils.texture_to_udim(text_in), text_out)

    async def test_get_invalid_extensions(self):
        valid_extensions = [".dds", ".jpg", ".png"]
        for file_paths, invalid_extensions in {
            ("mat.png",): [],
            ("mat.PNG",): [],
            ("mat.gif",): [".gif"],
            ("mat.pngg",): [".pngg"],
            ("mat.PNGG",): [".pngg"],
            ("mat.PnG", "mat.png"): [],
            ("mat.PNGG", "mat.jpg"): [".pngg"],
            ("mat.png", "mat.JPG", "mat.dds"): [],
            ("mat.PNG", "mat.JpG", "mat.ds", "mat2.ds"): [".ds"],
            ("mat.png", "mat.jpg", "mat.dds", "mat.gif", "mat.raw", "mat2.raw"): [".gif", ".raw"],
            ("mat.mno", "mat.jkl", "mat.ghi", "mat.abc", "mat.def"): [".abc", ".def", ".ghi", ".jkl", ".mno"],
        }.items():
            with self.subTest(name=f"get_invalid_extensions_{file_paths}"):
                self.assertEqual(
                    _path_utils.get_invalid_extensions(list(file_paths), valid_extensions), invalid_extensions
                )
