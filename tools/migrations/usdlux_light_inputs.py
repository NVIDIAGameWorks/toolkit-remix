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

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:
    from .constants import USD_FILE_SUFFIXES, USD_FILE_SUFFIXES_DISPLAY
except ImportError:
    from constants import USD_FILE_SUFFIXES, USD_FILE_SUFFIXES_DISPLAY

LIGHT_PRIM_TYPES = {
    "CylinderLight",
    "DiskLight",
    "DistantLight",
    "DomeLight",
    "GeometryLight",
    "PluginLight",
    "PortalLight",
    "RectLight",
    "SphereLight",
}

LEGACY_LIGHT_ATTRIBUTES_TO_INPUTS = {
    "angle": "inputs:angle",
    "color": "inputs:color",
    "colorTemperature": "inputs:colorTemperature",
    "diffuse": "inputs:diffuse",
    "enableColorTemperature": "inputs:enableColorTemperature",
    "exposure": "inputs:exposure",
    "height": "inputs:height",
    "intensity": "inputs:intensity",
    "length": "inputs:length",
    "normalize": "inputs:normalize",
    "radius": "inputs:radius",
    "shaping:cone:angle": "inputs:shaping:cone:angle",
    "shaping:cone:softness": "inputs:shaping:cone:softness",
    "shaping:focus": "inputs:shaping:focus",
    "shaping:focusTint": "inputs:shaping:focusTint",
    "shaping:ies:angleScale": "inputs:shaping:ies:angleScale",
    "shaping:ies:file": "inputs:shaping:ies:file",
    "shaping:ies:normalize": "inputs:shaping:ies:normalize",
    "specular": "inputs:specular",
    "texture:file": "inputs:texture:file",
    "texture:format": "inputs:texture:format",
    "width": "inputs:width",
}

_PRIM_SPEC_RE = re.compile(r"^\s*(?:def|over|class)\s+(?:(?P<type>[A-Za-z_][A-Za-z0-9_]*)\s+)?\"[^\"]+\"")
_LEGACY_LIGHT_ATTRIBUTE_RE = re.compile(
    r"^(?P<prefix>\s*(?:(?:custom|uniform|varying)\s+)*[A-Za-z_][A-Za-z0-9_:<>]*(?:\[\])?\s+)"
    r"(?P<name>"
    + "|".join(re.escape(name) for name in sorted(LEGACY_LIGHT_ATTRIBUTES_TO_INPUTS, key=len, reverse=True))
    + r")(?P<suffix>\.timeSamples\b|\s*(?:=|\(|$))"
)


@dataclass(frozen=True)
class MigrationResult:
    path: Path
    changed: bool
    skipped: bool
    replacement_count: int
    message: str


def migrate_usdlux_light_inputs_text(source: str) -> tuple[str, int]:
    """Update legacy UsdLux light attributes to their USD 25.11 inputs names."""
    light_scope_stack: list[bool] = []
    pending_prim_scope: bool | None = None
    replacement_count = 0
    migrated_lines = []
    string_delimiter = None

    for line in source.splitlines(keepends=True):
        current_light_scope = light_scope_stack[-1] if light_scope_stack else False
        line_starts_in_string = string_delimiter is not None
        structural_line, string_delimiter = _strip_usda_strings_and_comments(line, string_delimiter)
        prim_spec = None if line_starts_in_string else _PRIM_SPEC_RE.match(line)
        if prim_spec:
            prim_type = prim_spec.group("type")
            pending_prim_scope = prim_type in LIGHT_PRIM_TYPES

        if current_light_scope:
            migrated_line, line_replacement_count = _migrate_light_line(line, structural_line)
            replacement_count += line_replacement_count
        else:
            migrated_line = line

        migrated_lines.append(migrated_line)

        for character in structural_line:
            if character == "{":
                light_scope_stack.append(current_light_scope if pending_prim_scope is None else pending_prim_scope)
                pending_prim_scope = None
                current_light_scope = light_scope_stack[-1]
            elif character == "}":
                if light_scope_stack:
                    light_scope_stack.pop()
                current_light_scope = light_scope_stack[-1] if light_scope_stack else False

    return "".join(migrated_lines), replacement_count


def iter_usd_files(directory: Path, recursive: bool = False) -> list[Path]:
    paths = directory.rglob("*") if recursive else directory.iterdir()
    return sorted(path for path in paths if path.is_file() and path.suffix.lower() in USD_FILE_SUFFIXES)


def migrate_usdlux_light_inputs_file(path: Path) -> MigrationResult:
    if path.suffix.lower() not in USD_FILE_SUFFIXES:
        raise ValueError(f"The selected file is not a USD file. Valid file types are: {USD_FILE_SUFFIXES_DISPLAY}")

    raw_content = path.read_bytes()
    if raw_content.startswith(b"PXR-USDC") or b"\0" in raw_content[:4096]:
        return MigrationResult(path, False, True, 0, "Skipped binary USD crate; only ASCII USD can be migrated.")

    try:
        source = raw_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return MigrationResult(path, False, True, 0, "Skipped non UTF-8 USD text file.")

    if not source.lstrip().startswith("#usda"):
        return MigrationResult(path, False, True, 0, "Skipped non-USDA text file.")

    migrated, replacement_count = migrate_usdlux_light_inputs_text(source)
    if replacement_count == 0:
        return MigrationResult(path, False, False, 0, "No legacy UsdLux light attributes found.")

    path.write_text(migrated, encoding="utf-8", newline="")
    return MigrationResult(
        path, True, False, replacement_count, f"Updated {replacement_count} light attribute name(s)."
    )


def migrate_usdlux_light_inputs_paths(paths: list[Path]) -> list[MigrationResult]:
    return [migrate_usdlux_light_inputs_file(path) for path in paths]


def _migrate_light_line(line: str, structural_line: str) -> tuple[str, int]:
    """Update a legacy light attribute declaration without touching values or comments."""
    match = _LEGACY_LIGHT_ATTRIBUTE_RE.match(structural_line)
    if not match:
        return line, 0

    inputs_name = LEGACY_LIGHT_ATTRIBUTES_TO_INPUTS[match.group("name")]
    start, end = match.span("name")
    return f"{line[:start]}{inputs_name}{line[end:]}", 1


def _strip_usda_strings_and_comments(line: str, string_delimiter: str | None) -> tuple[str, str | None]:
    """Blank USDA string and comment contents so structural parsing ignores them."""
    structural_line = list(line)
    index = 0
    while index < len(line):
        if string_delimiter:
            if string_delimiter in {"'''", '"""'} and line.startswith(string_delimiter, index):
                _blank_span(structural_line, index, index + len(string_delimiter))
                index += len(string_delimiter)
                string_delimiter = None
                continue
            char = line[index]
            _blank_span(structural_line, index, index + 1)
            index += 1
            if string_delimiter not in {"'''", '"""'}:
                if char == "\\" and index < len(line):
                    _blank_span(structural_line, index, index + 1)
                    index += 1
                elif char == string_delimiter:
                    string_delimiter = None
            continue

        if line.startswith('"""', index) or line.startswith("'''", index):
            string_delimiter = line[index : index + 3]
            _blank_span(structural_line, index, index + 3)
            index += 3
            continue
        if line[index] in {"'", '"'}:
            string_delimiter = line[index]
            _blank_span(structural_line, index, index + 1)
            index += 1
            continue
        if line[index] == "#":
            _blank_span(structural_line, index, len(line))
            break
        index += 1
    return "".join(structural_line), string_delimiter


def _blank_span(characters: list[str], start: int, end: int) -> None:
    """Replace non-newline characters with spaces in the given span."""
    for index in range(start, min(end, len(characters))):
        if characters[index] not in {"\r", "\n"}:
            characters[index] = " "
