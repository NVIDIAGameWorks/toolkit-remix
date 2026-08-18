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

from omni.kit.test import AsyncTestCase
from lightspeed.trex.comfyui.core.url import (
    build_url,
    canonical_endpoint,
    is_valid_host,
    is_valid_local_leaf,
    is_valid_port,
    parse_url,
)


class TestURL(AsyncTestCase):
    """Test ComfyUI endpoint parsing, validation, and normalization."""

    async def test_canonical_endpoint_normalizes_address_without_dns_resolution(self):
        """Endpoint addresses normalize case and IP text while keeping distinct host spellings distinct."""
        # Arrange
        cases = (
            (("HTTP", "Comfy.Example.COM", 8188), ("http", "comfy.example.com", 8188)),
            (("http", "2001:0DB8:0:0::1", 8188), ("http", "2001:db8::1", 8188)),
            (("http", "localhost", 8188), ("http", "localhost", 8188)),
            (("http", "127.0.0.1", 8188), ("http", "127.0.0.1", 8188)),
        )

        for endpoint, expected in cases:
            with self.subTest(endpoint=endpoint):
                # Act
                result = canonical_endpoint(*endpoint)

                # Assert
                self.assertEqual(result, expected)

    async def test_parse_url_accepts_server_addresses_and_rejects_other_url_shapes(self):
        """Parsing accepts HTTP server addresses and rejects unsafe or malformed components."""
        # Arrange
        invalid = (False, None, None, None)
        cases = (
            ("https://example.com:8188", (True, "https", "example.com", 8188)),
            ("127.0.0.1:8188", (True, None, "127.0.0.1", 8188)),
            ("https://[2001:db8::1]:8188", (True, "https", "2001:db8::1", 8188)),
            ("http://", invalid),
            ("localhost:not-a-port", invalid),
            ("localhost:65536", invalid),
            ("ftp://comfy.example.com:8188", invalid),
            ("http://comfy:8188/api", invalid),
            ("http://comfy:8188/;parameter", invalid),
            ("http://comfy:8188?query=value", invalid),
            ("http://comfy:8188#fragment", invalid),
            ("http://user@comfy:8188", invalid),
            ("http://user:password@comfy:8188", invalid),
            ("http://exa\nmple.com:8188", invalid),
            ("http://exa\tmple.com:8188", invalid),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                # Act
                result = parse_url(value)

                # Assert
                self.assertEqual(result, expected)

    async def test_build_url_normalizes_hostnames_and_brackets_ipv6(self):
        """URL construction reuses canonical endpoint normalization before rendering."""
        # Arrange
        cases = (
            (("http", "localhost", 8188), "http://localhost:8188"),
            (("HTTP", "Comfy.Example.COM", 8188), "http://comfy.example.com:8188"),
            (("http", "2001:0DB8:0:0::1", 8188), "http://[2001:db8::1]:8188"),
        )

        for parts, expected in cases:
            with self.subTest(parts=parts):
                # Act
                result = build_url(*parts)

                # Assert
                self.assertEqual(result, expected)

    async def test_is_valid_host_accepts_network_hosts_and_rejects_url_syntax(self):
        """Host validation accepts IP and DNS names but not brackets or invalid DNS labels."""
        # Arrange
        cases = (
            ("127.0.0.1", True),
            ("localhost", True),
            ("comfy.example.com", True),
            ("comfy", True),
            ("[localhost]", False),
            ("[2001:db8::1]", False),
            ("[2001:db8::1", False),
            ("2001:db8::1]", False),
            ("-bad.example.com", False),
            ("bad-.example.com", False),
            ("010.0.0.1", False),
            ("999.999.999.999", False),
        )

        for host, expected in cases:
            with self.subTest(host=host):
                # Act
                result = is_valid_host(host)

                # Assert
                self.assertEqual(result, expected)

    async def test_is_valid_port_enforces_tcp_port_bounds(self):
        """Port validation accepts only integers in the inclusive TCP range."""
        # Arrange
        cases = ((1, True), (65535, True), (0, False), (65536, False))

        for port, expected in cases:
            with self.subTest(port=port):
                # Act
                result = is_valid_port(port)

                # Assert
                self.assertEqual(result, expected)

    async def test_endpoint_builders_reject_non_string_schemes_with_value_error(self):
        """The public endpoint helpers preserve their documented failure type."""
        # Arrange
        invalid_scheme = 7

        for builder in (canonical_endpoint, build_url):
            with self.subTest(builder=builder.__name__):
                # Act
                with self.assertRaises(ValueError) as error_context:
                    builder(invalid_scheme, "localhost", 8188)

                # Assert
                self.assertIsInstance(error_context.exception, ValueError)

    async def test_local_leaf_enforces_portable_filesystem_unit_limits(self):
        """A portable leaf fits both UTF-8 bytes and UTF-16 code units."""
        # Arrange
        cases = (("a" * 255, True), ("a" * 256, False), ("😀" * 63, True), ("😀" * 64, False))

        for value, expected in cases:
            with self.subTest(length=len(value), expected=expected):
                # Act
                result = is_valid_local_leaf(value)

                # Assert
                self.assertEqual(result, expected)
