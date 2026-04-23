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

from pathlib import Path
from unittest.mock import Mock, patch

import omni.kit.test
from omni.flux.utils.common import omni_url as _omni_url
from omni.flux.utils.common.omni_url import OmniUrl
from omni.kit.test_suite.helpers import get_test_data_path


class TestOmniUrl(omni.kit.test.AsyncTestCase):
    async def test_iterdir(self):
        local_path_str = get_test_data_path(__name__)
        local_path = Path(local_path_str)
        files = {Path(str(file)) for file in OmniUrl(local_path).iterdir()}
        expected_files = {local_path / Path("file.txt"), local_path / Path("my_file.usd")}
        self.assertSetEqual(files, expected_files)

    async def test_exists(self):
        # Assert
        local_path_str = get_test_data_path(__name__)
        local_path = Path(local_path_str)
        self.assertTrue((OmniUrl(local_path) / Path("file.txt")).exists)
        self.assertFalse((OmniUrl(local_path) / Path("nofile.txt")).exists)
        self.assertTrue(OmniUrl(local_path / "file.txt").exists)
        self.assertFalse(OmniUrl(local_path / "nofile.txt").exists)
        self.assertTrue((OmniUrl(local_path) / "file.txt").exists)
        self.assertFalse((OmniUrl(local_path) / "nofile.txt").exists)

        self.assertTrue(OmniUrl(f"file:{local_path_str}/file.txt").exists)
        self.assertFalse(OmniUrl(f"file:{local_path_str}/nofile.txt").exists)

        self.assertTrue((OmniUrl(f"file:{local_path_str}") / "file.txt").exists)
        self.assertFalse((OmniUrl(f"file:{local_path_str}") / "nofile.txt").exists)

    async def test_iterdir_returns_no_children_when_omni_client_list_fails(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path")

        with patch.object(
            _omni_url.omni.client, "list", return_value=(_omni_url.omni.client.Result.ERROR_NOT_FOUND, [])
        ):
            # Act
            result = list(url.iterdir())

        # Assert
        self.assertEqual([], result)

    async def test_is_directory_returns_true_for_directory_entries(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path")
        entry = Mock(flags=_omni_url.omni.client.ItemFlags.CAN_HAVE_CHILDREN)

        with patch.object(_omni_url.omni.client, "stat", return_value=(_omni_url.omni.client.Result.OK, entry)):
            # Act
            result = url.is_directory

        # Assert
        self.assertTrue(result)

    async def test_is_file_returns_true_for_file_entries(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path/file.usd")
        entry = Mock(flags=0)

        with patch.object(_omni_url.omni.client, "stat", return_value=(_omni_url.omni.client.Result.OK, entry)):
            # Act
            result = url.is_file

        # Assert
        self.assertTrue(result)

    async def test_entry_returns_none_when_stat_fails(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path/file.usd")

        with patch.object(
            _omni_url.omni.client, "stat", return_value=(_omni_url.omni.client.Result.ERROR_NOT_FOUND, None)
        ):
            # Act
            result = url.entry

        # Assert
        self.assertIsNone(result)

    async def test_exists_returns_true_without_stat_when_list_entry_is_cached(self):
        # Arrange
        cached_entry = Mock()
        url = OmniUrl("omniverse://host.com/path/file.usd", list_entry=cached_entry)

        with patch.object(_omni_url.omni.client, "stat") as stat_mock:
            # Act
            result = url.exists

        # Assert
        self.assertTrue(result)
        stat_mock.assert_not_called()

    async def test_delete_delegates_to_omni_client_delete_with_the_original_url(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path/file.usd")

        with patch.object(_omni_url.omni.client, "delete", return_value="deleted") as delete_mock:
            # Act
            result = url.delete()

        # Assert
        self.assertEqual("deleted", result)
        delete_mock.assert_called_once_with("omniverse://host.com/path/file.usd")

    async def test_validate_omni_url_for_pydantic_returns_existing_instance(self):
        # Arrange
        url = OmniUrl("omniverse://host.com/path/to/file.usd")

        # Act
        result = OmniUrl._validate_omni_url_for_pydantic(url)

        # Assert
        self.assertIs(url, result)

    async def test_validate_omni_url_for_pydantic_converts_path_instances(self):
        # Arrange
        path = Path("relative/path.usd")

        # Act
        result = OmniUrl._validate_omni_url_for_pydantic(path)

        # Assert
        self.assertEqual(OmniUrl("relative/path.usd"), result)

    async def test_validate_omni_url_for_pydantic_raises_type_error_for_invalid_types(self):
        # Arrange

        # Act
        with self.assertRaisesRegex(TypeError, "Expected OmniUrl, Path, or str") as error:
            OmniUrl._validate_omni_url_for_pydantic(123)

        # Assert
        self.assertIsInstance(error.exception, TypeError)

    async def test_is_hashable(self):
        # Assert
        local_path_str = get_test_data_path(__name__)
        local_path = Path(local_path_str)
        self.assertTrue({OmniUrl(local_path) / Path("file.txt")})
        self.assertTrue(hash(OmniUrl(local_path) / Path("file.txt")))

    async def test_path(self):
        # Assert
        self.assertEqual(str(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"omni://host.com/path/to/my_file.usd").path), "/path/to/my_file.usd")
        # NOTE: Omni client is incorrectly returning "/Z:/..." as the path on Windows, so file:C:/ tests fail.
        # When omni client fixes https://nvidia-omniverse.atlassian.net/browse/HUB-646, these tests should be enabled.
        # self.assertEquals(str(OmniUrl(r"file:Z:/path/to/my_file.usd").path), "Z:/path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"file:/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"C:\path\to\my_file.usd").path), "C:/path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"./path/to/my_file.usd").path), "path/to/my_file.usd")
        self.assertEqual(str(OmniUrl(r"../path/to/my_file.usd").path), "../path/to/my_file.usd")

        self.assertEqual(str(OmniUrl(r"omniverse://host.com/path/to").path), "/path/to")
        self.assertEqual(str(OmniUrl(r"omni://host.com/path/to").path), "/path/to")
        # self.assertEquals(str(OmniUrl(r"file:Z:/path/to").path), "Z:/path/to")
        self.assertEqual(str(OmniUrl(r"file:/path/to").path), "/path/to")
        self.assertEqual(str(OmniUrl(r"C:\path\to").path), "C:/path/to")
        self.assertEqual(str(OmniUrl(r"/path/to").path), "/path/to")
        self.assertEqual(str(OmniUrl(r"./path/to").path), "path/to")
        self.assertEqual(str(OmniUrl(r"../path/to").path), "../path/to")
        self.assertEqual(str(OmniUrl(r"path").path), "path")

    async def test_parent_url(self):
        # Assert
        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").parent_url, r"omniverse://host.com/path/to"
        )
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.usd").parent_url, r"omniverse://host.com/path/to")
        # self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").parent_url, r"file:Z:/path/to")
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").parent_url, r"file:/path/to")
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").parent_url, r"C:/path/to")
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").parent_url, r"/path/to")
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").parent_url, r"path/to")
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").parent_url, r"../path/to")

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to").parent_url, r"omniverse://host.com/path")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to").parent_url, r"omniverse://host.com/path")
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").parent_url, r"file:Z:/path")
        self.assertEqual(OmniUrl(r"file:/path/to").parent_url, r"file:/path")
        self.assertEqual(OmniUrl(r"C:\path\to").parent_url, r"C:/path")
        self.assertEqual(OmniUrl(r"/path/to").parent_url, r"/path")
        self.assertEqual(OmniUrl(r"./path/to").parent_url, r"path")
        self.assertEqual(OmniUrl(r"../path/to").parent_url, r"../path")
        self.assertEqual(OmniUrl(r"path").parent_url, r".")

    async def test_name(self):
        # Assert
        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").name, r"my_file.usd")
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").name, r"my_file.usd")

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to").name, r"to")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to").name, r"to")
        self.assertEqual(OmniUrl(r"file:Z:/path/to").name, r"to")
        self.assertEqual(OmniUrl(r"file:/path/to").name, r"to")
        self.assertEqual(OmniUrl(r"C:\path\to").name, r"to")
        self.assertEqual(OmniUrl(r"/path/to").name, r"to")
        self.assertEqual(OmniUrl(r"./path/to").name, r"to")
        self.assertEqual(OmniUrl(r"path/to").name, r"to")
        self.assertEqual(OmniUrl(r"../path/to").name, r"to")
        self.assertEqual(OmniUrl(r"path").name, r"path")

    async def test_stem(self):
        # Assert
        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").stem, r"my_file")
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").stem, r"my_file")

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"file:Z:/path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"file:/path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"C:\path\to").stem, r"to")
        self.assertEqual(OmniUrl(r"/path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"./path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"../path/to").stem, r"to")
        self.assertEqual(OmniUrl(r"path").stem, r"path")

    async def test_suffix(self):
        # Assert
        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").suffix, r".usd")
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").suffix, r".usd")

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"./path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEqual(OmniUrl(r"../path/to/my_file.tar.gz").suffix, r".gz")

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to").suffix, "")
        self.assertEqual(OmniUrl(r"omni://host.com/path/to").suffix, "")
        self.assertEqual(OmniUrl(r"file:Z:/path/to").suffix, "")
        self.assertEqual(OmniUrl(r"file:/path/to").suffix, "")
        self.assertEqual(OmniUrl(r"C:\path\to").suffix, "")
        self.assertEqual(OmniUrl(r"/path/to").suffix, "")
        self.assertEqual(OmniUrl(r"./path/to").suffix, "")
        self.assertEqual(OmniUrl(r"path/to").suffix, "")
        self.assertEqual(OmniUrl(r"../path/to").suffix, "")
        self.assertEqual(OmniUrl(r"path").suffix, "")

    async def test_suffixes(self):
        # Assert
        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").suffixes, [".usd"])
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").suffixes, [".usd"])

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"omni://host.com/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"file:Z:/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"./path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEqual(OmniUrl(r"../path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])

        self.assertEqual(OmniUrl(r"omniverse://host.com/path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"omni://host.com/path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"file:Z:/path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"file:/path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"C:\path\to").suffixes, [])
        self.assertEqual(OmniUrl(r"/path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"./path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"../path/to").suffixes, [])
        self.assertEqual(OmniUrl(r"path").suffixes, [])

    async def test_with_path(self):
        # Assert
        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"omniverse://host.com/other_path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"omniverse://host.com/other_path/to/my_other_file.txt"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_path(Path("C:/other_path/to/my_other_file.txt")),
        #     OmniUrl(r"file:C:/other_path/to/my_other_file.txt"),
        # )
        self.assertEqual(
            OmniUrl(r"file:/path/to/my_file.usd").with_path(Path("/other_path/to/my_other_file.txt")),
            OmniUrl(r"file:/other_path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"C:\path\to\my_file.usd").with_path(Path(r"Z:\other_path\to\my_other_file.txt")),
            OmniUrl(r"Z:/other_path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"/path/to/my_file.usd").with_path(Path("/other_path/to/my_other_file.txt")),
            OmniUrl(r"/other_path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"./path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"other_path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"../path/to/my_file.usd").with_path(Path("../other_path/to/my_other_file.txt")),
            OmniUrl(r"../other_path/to/my_other_file.txt"),
        )

        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to").with_path(Path("other_path/to")),
            OmniUrl(r"omniverse://host.com/other_path/to"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to").with_path(Path("other_path/to")),
            OmniUrl(r"omniverse://host.com/other_path/to"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to").with_path(Path("C:/other_path/to")), OmniUrl(r"file:C:/other_path/to")
        # )
        self.assertEqual(OmniUrl(r"file:/path/to").with_path(Path("/other_path/to")), OmniUrl(r"file:/other_path/to"))
        self.assertEqual(OmniUrl(r"C:\path\to").with_path(Path(r"Z:\other_path\to")), OmniUrl(r"Z:/other_path/to"))
        self.assertEqual(OmniUrl(r"/path/to").with_path(Path("/other_path/to")), OmniUrl(r"/other_path/to"))
        self.assertEqual(OmniUrl(r"./path/to").with_path(Path("other_path/to")), OmniUrl(r"other_path/to"))
        self.assertEqual(OmniUrl(r"../path/to").with_path(Path("../other_path/to")), OmniUrl(r"../other_path/to"))
        self.assertEqual(OmniUrl(r"path").with_path(Path("other_path")), OmniUrl(r"other_path"))

    async def test_with_name(self):
        # Assert
        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"omniverse://host.com/path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"omniverse://host.com/path/to/my_other_file.txt"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_name("my_other_file.txt"),
        #     OmniUrl(r"file:Z:/path/to/my_other_file.txt"),
        # )
        self.assertEqual(
            OmniUrl(r"file:/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"file:/path/to/my_other_file.txt"),
        )
        self.assertEqual(
            OmniUrl(r"C:\path\to\my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"C:/path/to/my_other_file.txt")
        )
        self.assertEqual(
            OmniUrl(r"/path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"/path/to/my_other_file.txt")
        )
        self.assertEqual(
            OmniUrl(r"./path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"path/to/my_other_file.txt")
        )
        self.assertEqual(
            OmniUrl(r"../path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"../path/to/my_other_file.txt")
        )

        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to").with_name("other_to"),
            OmniUrl(r"omniverse://host.com/path/other_to"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to").with_name("other_to"), OmniUrl(r"omniverse://host.com/path/other_to")
        )
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").with_name("other_to"), OmniUrl(r"file:Z:/path/other_to"))
        self.assertEqual(OmniUrl(r"file:/path/to").with_name("other_to"), OmniUrl(r"file:/path/other_to"))
        self.assertEqual(OmniUrl(r"C:\path\to").with_name("other_to"), OmniUrl(r"C:/path/other_to"))
        self.assertEqual(OmniUrl(r"/path/to").with_name("other_to"), OmniUrl(r"/path/other_to"))
        self.assertEqual(OmniUrl(r"./path/to").with_name("other_to"), OmniUrl(r"path/other_to"))
        self.assertEqual(OmniUrl(r"../path/to").with_name("other_to"), OmniUrl(r"../path/other_to"))
        self.assertEqual(OmniUrl(r"path").with_name("other_to"), OmniUrl(r"other_to"))

    async def test_with_suffix(self):
        # Assert
        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_suffix(".usda"),
            OmniUrl(r"omniverse://host.com/path/to/my_file.usda"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_suffix(".usda"),
            OmniUrl(r"omniverse://host.com/path/to/my_file.usda"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"file:Z:/path/to/my_file.usda")
        # )
        self.assertEqual(
            OmniUrl(r"file:/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"file:/path/to/my_file.usda")
        )
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").with_suffix(".usda"), OmniUrl(r"C:/path/to/my_file.usda"))
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"/path/to/my_file.usda"))
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"path/to/my_file.usda"))
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"../path/to/my_file.usda"))

        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to").with_suffix(".usda"), OmniUrl(r"omniverse://host.com/path/to.usda")
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to").with_suffix(".usda"), OmniUrl(r"omniverse://host.com/path/to.usda")
        )
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").with_suffix(".usda"), OmniUrl(r"file:Z:/path/to.usda"))
        self.assertEqual(OmniUrl(r"file:/path/to").with_suffix(".usda"), OmniUrl(r"file:/path/to.usda"))
        self.assertEqual(OmniUrl(r"C:\path\to").with_suffix(".usda"), OmniUrl(r"C:/path/to.usda"))
        self.assertEqual(OmniUrl(r"/path/to").with_suffix(".usda"), OmniUrl(r"/path/to.usda"))
        self.assertEqual(OmniUrl(r"./path/to").with_suffix(".usda"), OmniUrl(r"path/to.usda"))
        self.assertEqual(OmniUrl(r"../path/to").with_suffix(".usda"), OmniUrl(r"../path/to.usda"))
        self.assertEqual(OmniUrl(r"path").with_suffix(".usda"), OmniUrl(r"path.usda"))

        self.assertEqual(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_suffix(""),
            OmniUrl(r"omniverse://host.com/path/to/my_file"),
        )
        self.assertEqual(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_suffix(""),
            OmniUrl(r"omniverse://host.com/path/to/my_file"),
        )
        # self.assertEquals(
        #    OmniUrl(r"file:Z:/path/to/my_file.usd").with_suffix(""), OmniUrl(r"file:Z:/path/to/my_file")
        # )
        self.assertEqual(OmniUrl(r"file:/path/to/my_file.usd").with_suffix(""), OmniUrl(r"file:/path/to/my_file"))
        self.assertEqual(OmniUrl(r"C:\path\to\my_file.usd").with_suffix(""), OmniUrl(r"C:/path/to/my_file"))
        self.assertEqual(OmniUrl(r"/path/to/my_file.usd").with_suffix(""), OmniUrl(r"/path/to/my_file"))
        self.assertEqual(OmniUrl(r"./path/to/my_file.usd").with_suffix(""), OmniUrl(r"path/to/my_file"))
        self.assertEqual(OmniUrl(r"../path/to/my_file.usd").with_suffix(""), OmniUrl(r"../path/to/my_file"))
