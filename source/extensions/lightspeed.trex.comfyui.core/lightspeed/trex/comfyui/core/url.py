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

__all__ = [
    "Endpoint",
    "build_url",
    "canonical_endpoint",
    "is_valid_host",
    "is_valid_local_leaf",
    "is_valid_port",
    "parse_url",
]

import ipaddress
from urllib.parse import urlparse

from .constants import (
    HOSTNAME_REGEX,
    INVALID_LOCAL_LEAF_CHARACTERS,
    SUPPORTED_COMFYUI_SCHEMES,
    WINDOWS_RESERVED_LOCAL_LEAVES,
)

Endpoint = tuple[str, str, int]


def canonical_endpoint(scheme: str, host: str, port: int) -> Endpoint:
    """Return a normalized endpoint address without resolving DNS names.

    Args:
        scheme: HTTP scheme.
        host: Server hostname or IP address.
        port: Server TCP port.

    Returns:
        Normalized ``(scheme, host, port)`` endpoint address.

    Raises:
        ValueError: If any endpoint component is invalid.
    """
    if not isinstance(scheme, str):
        raise ValueError(f"Unsupported URL scheme: {scheme}")
    normalized_scheme = scheme.lower()
    if normalized_scheme not in SUPPORTED_COMFYUI_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {scheme}")
    if not is_valid_host(host):
        raise ValueError(f"Invalid host: {host}")
    if not is_valid_port(port):
        raise ValueError(f"Invalid port: {port}")
    try:
        normalized_host = ipaddress.ip_address(host).compressed
    except ValueError:
        normalized_host = host.casefold()
    return normalized_scheme, normalized_host, int(port)


def parse_url(value: str) -> tuple[bool, str | None, str | None, int | None]:
    """Parse a URL string into validated endpoint components.

    Args:
        value: URL with an optional HTTP scheme and TCP port.

    Returns:
        Validation flag followed by the parsed scheme, host, and port; omitted
        components are ``None``, and invalid URLs return no components.
    """
    if not isinstance(value, str) or not value.strip() or any(ord(character) < 32 for character in value):
        return (False, None, None, None)

    value = value.strip()
    has_scheme = "://" in value
    try:
        parsed = urlparse(value if has_scheme else f"http://{value}")
    except ValueError:
        return (False, None, None, None)

    scheme = None
    if has_scheme and parsed.scheme:
        scheme = parsed.scheme.lower()
        if scheme not in SUPPORTED_COMFYUI_SCHEMES:
            return (False, None, None, None)

    if (
        parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return (False, None, None, None)

    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return (False, None, None, None)

    if not host or not is_valid_host(host) or (port is not None and not is_valid_port(port)):
        return (False, None, None, None)

    return (True, scheme, host, port)


def build_url(scheme: str, host: str, port: int) -> str:
    """Build URL from components.

    Args:
        scheme: Protocol scheme (e.g. ``http`` or ``https``).
        host: Hostname or IP address.
        port: TCP port number.

    Returns:
        Absolute endpoint URL with IPv6 hosts enclosed in brackets.

    Raises:
        ValueError: If any endpoint component is invalid.
    """
    scheme, host, port = canonical_endpoint(scheme, host, port)
    try:
        is_ipv6 = isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
    except ValueError:
        is_ipv6 = False
    rendered_host = f"[{host}]" if is_ipv6 else host
    return f"{scheme}://{rendered_host}:{port}"


def is_valid_host(host: str) -> bool:
    """Check if the host is a valid IP address or RFC 1123 hostname.

    Args:
        host: Candidate hostname or unbracketed IP address.

    Returns:
        Whether the host is valid for a ComfyUI endpoint.
    """
    if not isinstance(host, str) or not host or host != host.strip() or "[" in host or "]" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        if all(character.isdigit() or character == "." for character in host) and "." in host:
            return False
    if host.lower() == "localhost":
        return True
    if len(host) > 253:
        return False
    return bool(HOSTNAME_REGEX.match(host))


def is_valid_local_leaf(value: str) -> bool:
    """Check if a value is a portable local filename or directory leaf.

    Args:
        value: Candidate filename or single directory component.

    Returns:
        Whether the value is portable and avoids Windows-reserved names.
    """
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 255
        or len(value.encode("utf-16-le")) // 2 > 255
        or value != value.strip()
        or value.endswith(".")
        or any(ord(character) < 32 or character in INVALID_LOCAL_LEAF_CHARACTERS for character in value)
    ):
        return False
    return value.split(".", maxsplit=1)[0].upper() not in WINDOWS_RESERVED_LOCAL_LEAVES


def is_valid_port(port: int) -> bool:
    """Check if the port is within the valid TCP/IP range.

    Args:
        port: Candidate TCP port number.

    Returns:
        Whether the value is an integer from 1 through 65535, excluding booleans.
    """
    return isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535
