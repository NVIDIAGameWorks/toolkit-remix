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

import omni.kit.test
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

    async def test_is_hashable(self):
        # Assert
        local_path_str = get_test_data_path(__name__)
        local_path = Path(local_path_str)
        self.assertTrue({OmniUrl(local_path) / Path("file.txt")})
        self.assertTrue(hash(OmniUrl(local_path) / Path("file.txt")))

    async def test_path(self):
        # Assert
        self.assertEquals(str(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"omni://host.com/path/to/my_file.usd").path), "/path/to/my_file.usd")
        # NOTE: Omni client is incorrectly returning "/Z:/..." as the path on Windows, so file:C:/ tests fail.
        # When omni client fixes https://nvidia-omniverse.atlassian.net/browse/HUB-646, these tests should be enabled.
        # self.assertEquals(str(OmniUrl(r"file:Z:/path/to/my_file.usd").path), "Z:/path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"file:/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"C:\path\to\my_file.usd").path), "C:/path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"/path/to/my_file.usd").path), "/path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"./path/to/my_file.usd").path), "path/to/my_file.usd")
        self.assertEquals(str(OmniUrl(r"../path/to/my_file.usd").path), "../path/to/my_file.usd")

        self.assertEquals(str(OmniUrl(r"omniverse://host.com/path/to").path), "/path/to")
        self.assertEquals(str(OmniUrl(r"omni://host.com/path/to").path), "/path/to")
        # self.assertEquals(str(OmniUrl(r"file:Z:/path/to").path), "Z:/path/to")
        self.assertEquals(str(OmniUrl(r"file:/path/to").path), "/path/to")
        self.assertEquals(str(OmniUrl(r"C:\path\to").path), "C:/path/to")
        self.assertEquals(str(OmniUrl(r"/path/to").path), "/path/to")
        self.assertEquals(str(OmniUrl(r"./path/to").path), "path/to")
        self.assertEquals(str(OmniUrl(r"../path/to").path), "../path/to")
        self.assertEquals(str(OmniUrl(r"path").path), "path")

    async def test_parent_url(self):
        # Assert
        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").parent_url, r"omniverse://host.com/path/to"
        )
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.usd").parent_url, r"omniverse://host.com/path/to")
        # self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").parent_url, r"file:Z:/path/to")
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").parent_url, r"file:/path/to")
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").parent_url, r"C:/path/to")
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").parent_url, r"/path/to")
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").parent_url, r"path/to")
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").parent_url, r"../path/to")

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to").parent_url, r"omniverse://host.com/path")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to").parent_url, r"omniverse://host.com/path")
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").parent_url, r"file:Z:/path")
        self.assertEquals(OmniUrl(r"file:/path/to").parent_url, r"file:/path")
        self.assertEquals(OmniUrl(r"C:\path\to").parent_url, r"C:/path")
        self.assertEquals(OmniUrl(r"/path/to").parent_url, r"/path")
        self.assertEquals(OmniUrl(r"./path/to").parent_url, r"path")
        self.assertEquals(OmniUrl(r"../path/to").parent_url, r"../path")
        self.assertEquals(OmniUrl(r"path").parent_url, r".")

    async def test_name(self):
        # Assert
        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").name, r"my_file.usd")
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").name, r"my_file.usd")

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to").name, r"to")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to").name, r"to")
        self.assertEquals(OmniUrl(r"file:Z:/path/to").name, r"to")
        self.assertEquals(OmniUrl(r"file:/path/to").name, r"to")
        self.assertEquals(OmniUrl(r"C:\path\to").name, r"to")
        self.assertEquals(OmniUrl(r"/path/to").name, r"to")
        self.assertEquals(OmniUrl(r"./path/to").name, r"to")
        self.assertEquals(OmniUrl(r"path/to").name, r"to")
        self.assertEquals(OmniUrl(r"../path/to").name, r"to")
        self.assertEquals(OmniUrl(r"path").name, r"path")

    async def test_stem(self):
        # Assert
        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").stem, r"my_file")
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").stem, r"my_file")

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"file:Z:/path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"file:/path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"C:\path\to").stem, r"to")
        self.assertEquals(OmniUrl(r"/path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"./path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"../path/to").stem, r"to")
        self.assertEquals(OmniUrl(r"path").stem, r"path")

    async def test_suffix(self):
        # Assert
        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").suffix, r".usd")
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").suffix, r".usd")

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"/path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"./path/to/my_file.tar.gz").suffix, r".gz")
        self.assertEquals(OmniUrl(r"../path/to/my_file.tar.gz").suffix, r".gz")

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to").suffix, "")
        self.assertEquals(OmniUrl(r"omni://host.com/path/to").suffix, "")
        self.assertEquals(OmniUrl(r"file:Z:/path/to").suffix, "")
        self.assertEquals(OmniUrl(r"file:/path/to").suffix, "")
        self.assertEquals(OmniUrl(r"C:\path\to").suffix, "")
        self.assertEquals(OmniUrl(r"/path/to").suffix, "")
        self.assertEquals(OmniUrl(r"./path/to").suffix, "")
        self.assertEquals(OmniUrl(r"path/to").suffix, "")
        self.assertEquals(OmniUrl(r"../path/to").suffix, "")
        self.assertEquals(OmniUrl(r"path").suffix, "")

    async def test_suffixes(self):
        # Assert
        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").suffixes, [".usd"])
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").suffixes, [".usd"])

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"omni://host.com/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"file:Z:/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"/path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"./path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])
        self.assertEquals(OmniUrl(r"../path/to/my_file.tar.gz").suffixes, [".tar", ".gz"])

        self.assertEquals(OmniUrl(r"omniverse://host.com/path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"omni://host.com/path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"file:Z:/path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"file:/path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"C:\path\to").suffixes, [])
        self.assertEquals(OmniUrl(r"/path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"./path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"../path/to").suffixes, [])
        self.assertEquals(OmniUrl(r"path").suffixes, [])

    async def test_with_path(self):
        # Assert
        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"omniverse://host.com/other_path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"omniverse://host.com/other_path/to/my_other_file.txt"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_path(Path("C:/other_path/to/my_other_file.txt")),
        #     OmniUrl(r"file:C:/other_path/to/my_other_file.txt"),
        # )
        self.assertEquals(
            OmniUrl(r"file:/path/to/my_file.usd").with_path(Path("/other_path/to/my_other_file.txt")),
            OmniUrl(r"file:/other_path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"C:\path\to\my_file.usd").with_path(Path(r"Z:\other_path\to\my_other_file.txt")),
            OmniUrl(r"Z:/other_path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"/path/to/my_file.usd").with_path(Path("/other_path/to/my_other_file.txt")),
            OmniUrl(r"/other_path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"./path/to/my_file.usd").with_path(Path("other_path/to/my_other_file.txt")),
            OmniUrl(r"other_path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"../path/to/my_file.usd").with_path(Path("../other_path/to/my_other_file.txt")),
            OmniUrl(r"../other_path/to/my_other_file.txt"),
        )

        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to").with_path(Path("other_path/to")),
            OmniUrl(r"omniverse://host.com/other_path/to"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to").with_path(Path("other_path/to")),
            OmniUrl(r"omniverse://host.com/other_path/to"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to").with_path(Path("C:/other_path/to")), OmniUrl(r"file:C:/other_path/to")
        # )
        self.assertEquals(OmniUrl(r"file:/path/to").with_path(Path("/other_path/to")), OmniUrl(r"file:/other_path/to"))
        self.assertEquals(OmniUrl(r"C:\path\to").with_path(Path(r"Z:\other_path\to")), OmniUrl(r"Z:/other_path/to"))
        self.assertEquals(OmniUrl(r"/path/to").with_path(Path("/other_path/to")), OmniUrl(r"/other_path/to"))
        self.assertEquals(OmniUrl(r"./path/to").with_path(Path("other_path/to")), OmniUrl(r"other_path/to"))
        self.assertEquals(OmniUrl(r"../path/to").with_path(Path("../other_path/to")), OmniUrl(r"../other_path/to"))
        self.assertEquals(OmniUrl(r"path").with_path(Path("other_path")), OmniUrl(r"other_path"))

    async def test_with_name(self):
        # Assert
        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"omniverse://host.com/path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"omniverse://host.com/path/to/my_other_file.txt"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_name("my_other_file.txt"),
        #     OmniUrl(r"file:Z:/path/to/my_other_file.txt"),
        # )
        self.assertEquals(
            OmniUrl(r"file:/path/to/my_file.usd").with_name("my_other_file.txt"),
            OmniUrl(r"file:/path/to/my_other_file.txt"),
        )
        self.assertEquals(
            OmniUrl(r"C:\path\to\my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"C:/path/to/my_other_file.txt")
        )
        self.assertEquals(
            OmniUrl(r"/path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"/path/to/my_other_file.txt")
        )
        self.assertEquals(
            OmniUrl(r"./path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"path/to/my_other_file.txt")
        )
        self.assertEquals(
            OmniUrl(r"../path/to/my_file.usd").with_name("my_other_file.txt"), OmniUrl(r"../path/to/my_other_file.txt")
        )

        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to").with_name("other_to"),
            OmniUrl(r"omniverse://host.com/path/other_to"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to").with_name("other_to"), OmniUrl(r"omniverse://host.com/path/other_to")
        )
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").with_name("other_to"), OmniUrl(r"file:Z:/path/other_to"))
        self.assertEquals(OmniUrl(r"file:/path/to").with_name("other_to"), OmniUrl(r"file:/path/other_to"))
        self.assertEquals(OmniUrl(r"C:\path\to").with_name("other_to"), OmniUrl(r"C:/path/other_to"))
        self.assertEquals(OmniUrl(r"/path/to").with_name("other_to"), OmniUrl(r"/path/other_to"))
        self.assertEquals(OmniUrl(r"./path/to").with_name("other_to"), OmniUrl(r"path/other_to"))
        self.assertEquals(OmniUrl(r"../path/to").with_name("other_to"), OmniUrl(r"../path/other_to"))
        self.assertEquals(OmniUrl(r"path").with_name("other_to"), OmniUrl(r"other_to"))

    async def test_with_suffix(self):
        # Assert
        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_suffix(".usda"),
            OmniUrl(r"omniverse://host.com/path/to/my_file.usda"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_suffix(".usda"),
            OmniUrl(r"omniverse://host.com/path/to/my_file.usda"),
        )
        # self.assertEquals(
        #     OmniUrl(r"file:Z:/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"file:Z:/path/to/my_file.usda")
        # )
        self.assertEquals(
            OmniUrl(r"file:/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"file:/path/to/my_file.usda")
        )
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").with_suffix(".usda"), OmniUrl(r"C:/path/to/my_file.usda"))
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"/path/to/my_file.usda"))
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"path/to/my_file.usda"))
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").with_suffix(".usda"), OmniUrl(r"../path/to/my_file.usda"))

        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to").with_suffix(".usda"), OmniUrl(r"omniverse://host.com/path/to.usda")
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to").with_suffix(".usda"), OmniUrl(r"omniverse://host.com/path/to.usda")
        )
        # self.assertEquals(OmniUrl(r"file:Z:/path/to").with_suffix(".usda"), OmniUrl(r"file:Z:/path/to.usda"))
        self.assertEquals(OmniUrl(r"file:/path/to").with_suffix(".usda"), OmniUrl(r"file:/path/to.usda"))
        self.assertEquals(OmniUrl(r"C:\path\to").with_suffix(".usda"), OmniUrl(r"C:/path/to.usda"))
        self.assertEquals(OmniUrl(r"/path/to").with_suffix(".usda"), OmniUrl(r"/path/to.usda"))
        self.assertEquals(OmniUrl(r"./path/to").with_suffix(".usda"), OmniUrl(r"path/to.usda"))
        self.assertEquals(OmniUrl(r"../path/to").with_suffix(".usda"), OmniUrl(r"../path/to.usda"))
        self.assertEquals(OmniUrl(r"path").with_suffix(".usda"), OmniUrl(r"path.usda"))

        self.assertEquals(
            OmniUrl(r"omniverse://host.com/path/to/my_file.usd").with_suffix(""),
            OmniUrl(r"omniverse://host.com/path/to/my_file"),
        )
        self.assertEquals(
            OmniUrl(r"omni://host.com/path/to/my_file.usd").with_suffix(""),
            OmniUrl(r"omniverse://host.com/path/to/my_file"),
        )
        # self.assertEquals(
        #    OmniUrl(r"file:Z:/path/to/my_file.usd").with_suffix(""), OmniUrl(r"file:Z:/path/to/my_file")
        # )
        self.assertEquals(OmniUrl(r"file:/path/to/my_file.usd").with_suffix(""), OmniUrl(r"file:/path/to/my_file"))
        self.assertEquals(OmniUrl(r"C:\path\to\my_file.usd").with_suffix(""), OmniUrl(r"C:/path/to/my_file"))
        self.assertEquals(OmniUrl(r"/path/to/my_file.usd").with_suffix(""), OmniUrl(r"/path/to/my_file"))
        self.assertEquals(OmniUrl(r"./path/to/my_file.usd").with_suffix(""), OmniUrl(r"path/to/my_file"))
        self.assertEquals(OmniUrl(r"../path/to/my_file.usd").with_suffix(""), OmniUrl(r"../path/to/my_file"))
