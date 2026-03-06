"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

Update .idea/lightspeed-kit.iml with source roots for PyCharm import resolution.

Reads ``.idea/lightspeed-kit.iml.template`` (committed) and fills two marker
comments with generated content, writing the result to ``.idea/lightspeed-kit.iml``
(git-ignored).

Generated content:

1. **Extension source roots** — every directory under ``source/extensions/`` so that
   cross-extension imports (``omni.flux.*``, ``lightspeed.*``) resolve.
2. **Build extra-paths** — ``python.analysis.extraPaths`` from ``.vscode/settings.json``
   (Kit kernel, extscache, pip_prebundle, etc.) so that SDK imports (``carb``, ``pxr``,
   ``omni.usd``, ``py7zr``, …) resolve without manual interpreter-path configuration.

Build paths that live under ``_build/`` are grouped by their container directory
(``exts``, ``extscache``, ``extscore``) and added as **separate content roots** so they
are not blocked by the ``_build`` exclude in the main content root.

Run via the build system (automatic) or manually::

    _build/windows-x86_64/release/kit/python/python.exe tools/utils/update_pycharm_sources.py
"""

import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TEMPLATE_PATH = REPO_ROOT / ".idea" / "lightspeed-kit.iml.template"
IML_PATH = REPO_ROOT / ".idea" / "lightspeed-kit.iml"
EXTENSIONS_DIR = REPO_ROOT / "source" / "extensions"
VSCODE_SETTINGS_PATH = REPO_ROOT / ".vscode" / "settings.json"

_SOURCE_FOLDERS_MARKER = "<!-- GENERATED:SOURCE_FOLDERS -->"
_BUILD_CONTENT_ROOTS_MARKER = "<!-- GENERATED:BUILD_CONTENT_ROOTS -->"


def _get_extension_dirs() -> list[str]:
    if not EXTENSIONS_DIR.is_dir():
        return []
    return sorted(d.name for d in EXTENSIONS_DIR.iterdir() if d.is_dir())


def _load_json_safe(text: str) -> dict:
    """Parse JSON that may contain comments and trailing commas."""
    # NOTE: This naively strips // comments and will corrupt URLs inside string values.
    # Acceptable here because the only consumer is _read_vscode_extra_paths (file paths, no URLs).
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*([\s\S]*?)\*/", "", text, flags=re.MULTILINE)
    text = re.sub(r",(?=\s*[}\]])", "", text)
    return json.loads(text)


def _read_vscode_extra_paths() -> list[str]:
    """Read python.analysis.extraPaths from .vscode/settings.json."""
    if not VSCODE_SETTINGS_PATH.exists():
        return []
    text = VSCODE_SETTINGS_PATH.read_text(encoding="utf-8")
    try:
        settings = json.loads(text)
    except json.JSONDecodeError:
        settings = _load_json_safe(text)
    return settings.get("python.analysis.extraPaths", [])


_KNOWN_EXT_DIRS = frozenset(("exts", "extscache", "extscore"))
# "exts" directories are symlinks to source/extensions/ — already in the main content root.
_SKIPPED_EXT_DIRS = frozenset(("exts",))


def _compute_content_root(build_path: str) -> str:
    """Find the content root for a build path by detecting extension container dirs.

    Paths under known extension directories (exts, extscache, extscore) are grouped
    under the container directory.  Other paths use themselves as the content root.
    """
    parts = build_path.split("/")
    for i, part in enumerate(parts):
        if part in _KNOWN_EXT_DIRS:
            return "/".join(parts[: i + 1])
    return build_path


def _group_build_paths(raw_paths: list[str]) -> dict[str, list[str]]:
    """Group existing ``_build/`` paths by their content root directory."""
    groups: dict[str, list[str]] = {}
    seen: set[str] = set()
    for raw in raw_paths:
        if not isinstance(raw, str) or not raw:
            continue
        posix = raw.replace("\\", "/")
        if not posix.startswith("_build/"):
            continue
        candidate = REPO_ROOT / posix
        if not candidate.is_dir() or posix in seen:
            continue
        seen.add(posix)
        root = _compute_content_root(posix)
        # Skip paths under "exts" — they mirror source/extensions/ already in the main content root.
        if root.rsplit("/", 1)[-1] in _SKIPPED_EXT_DIRS:
            continue
        groups.setdefault(root, []).append(posix)
    for _root, paths in groups.items():
        paths.sort()
    return dict(sorted(groups.items()))


DEPS_DIR = REPO_ROOT / "deps"


def _read_pip_target_names() -> list[str]:
    """Read ``target`` basenames from ``deps/*.toml`` files that define pip ``[[dependency]]`` sections."""
    if not DEPS_DIR.is_dir():
        return []
    names: list[str] = []
    for toml_path in sorted(DEPS_DIR.glob("*.toml")):
        text = toml_path.read_text(encoding="utf-8")
        if "[[dependency]]" not in text:
            continue
        for match in re.finditer(r'^\s*target\s*=\s*"([^"]+)"', text, re.MULTILINE):
            resolved = (DEPS_DIR / match.group(1)).resolve()
            names.append(resolved.name)
    return names


def _discover_pip_prebundle_paths() -> dict[str, list[str]]:
    """Discover pip prebundle directories by reading ``deps/*.toml`` dependency targets.

    Parses ``target`` fields from ``[[dependency]]`` sections in deps config files,
    then searches for matching directories in the build extension directories.

    Returns groups keyed by the parent extension directory (posix, relative to
    REPO_ROOT), with values being lists of matching subdirectories.
    """
    target_names = _read_pip_target_names()
    if not target_names:
        return {}

    build_dir = REPO_ROOT / "_build"
    if not build_dir.is_dir():
        return {}

    groups: dict[str, list[str]] = {}
    for ext_container in sorted(build_dir.glob("*/*/exts")):
        if not ext_container.is_dir():
            continue
        for ext_dir in sorted(ext_container.iterdir()):
            if not ext_dir.is_dir():
                continue
            found = []
            for name in target_names:
                candidate = ext_dir / name
                if candidate.is_dir():
                    found.append(candidate.relative_to(REPO_ROOT).as_posix())
            if found:
                root_posix = ext_dir.relative_to(REPO_ROOT).as_posix()
                groups[root_posix] = sorted(found)
    return dict(sorted(groups.items()))


def _generate_source_folder_lines(ext_dirs: list[str]) -> str:
    """Generate ``<sourceFolder …/>`` XML lines for extension directories."""
    lines = []
    for ext_dir in ext_dirs:
        lines.append(
            f'      <sourceFolder url="file://$MODULE_DIR$/source/extensions/{ext_dir}" isTestSource="false" />'
        )
    return "\n".join(lines)


def _generate_build_content_roots(groups: dict[str, list[str]]) -> str:
    """Generate ``<content>`` XML elements for grouped build paths."""
    elements = []
    for content_root, source_paths in groups.items():
        lines = [f'    <content url="file://$MODULE_DIR$/{content_root}">']
        for sp in source_paths:
            lines.append(f'      <sourceFolder url="file://$MODULE_DIR$/{sp}" isTestSource="false" />')
        lines.append("    </content>")
        elements.append("\n".join(lines))
    return "\n".join(elements)


def update_iml() -> None:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    ext_dirs = _get_extension_dirs()
    source_folder_xml = _generate_source_folder_lines(ext_dirs)

    raw_paths = _read_vscode_extra_paths()
    groups = _group_build_paths(raw_paths)

    # Merge dynamically discovered pip prebundle paths (from pip archive extensions).
    for root, paths in _discover_pip_prebundle_paths().items():
        existing = groups.get(root, [])
        existing_set = set(existing)
        for p in paths:
            if p not in existing_set:
                existing.append(p)
        if existing:
            groups[root] = existing
    groups = dict(sorted(groups.items()))

    build_content_xml = _generate_build_content_roots(groups)

    total_sources = sum(len(paths) for paths in groups.values())

    if _SOURCE_FOLDERS_MARKER not in template or _BUILD_CONTENT_ROOTS_MARKER not in template:
        print(f"Warning: Template {TEMPLATE_PATH} is missing expected marker comments, skipping generation.")
        return

    output = template.replace(_SOURCE_FOLDERS_MARKER, source_folder_xml)
    output = output.replace(_BUILD_CONTENT_ROOTS_MARKER, build_content_xml)

    IML_PATH.write_text(output, encoding="utf-8")

    print(
        f"Updated {IML_PATH.relative_to(REPO_ROOT)} with "
        f"{len(ext_dirs)} extension source roots, "
        f"{len(groups)} build content roots, and "
        f"{total_sources} build source folders."
    )


if __name__ == "__main__":
    update_iml()
