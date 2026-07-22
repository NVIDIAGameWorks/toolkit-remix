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

import argparse
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


DXVK_REMIX_REPO_URL = os.environ.get("TOOLKIT_GITLAB_DXVK_REPO_URL")
DXVK_REMIX_BRANCH = "main"
PACKAGE_BASE_URL = "https://omnipackages.nvidia.com/packages/cloudfront"
TARGET_DEPS_PATH = Path("deps/target-deps.packman.xml")
CHANGELOG_PATH = Path("CHANGELOG.md")
TARGET_PACKAGES = frozenset({"rtx-remix-hdremix", "rtx-remix-omni_core_materials"})
REMIX_RUNTIME_PACKAGE = "rtx-remix-remix_runtime"
ALL_REMIX_TARGET_PACKAGES = TARGET_PACKAGES | {REMIX_RUNTIME_PACKAGE}
CHANGELOG_ENTRY_PREFIX = "- Update Remix target dependencies:"

_MAIN_EXT_VERSION_PATTERN = re.compile(r"^ext-[0-9a-f]{7}-main$")
_RUNTIME_RELEASE_PATTERN = re.compile(r"^remix-(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class PinUpdate:
    old: str
    new: str


@dataclass(frozen=True)
class TargetUpdate:
    pins: dict[str, PinUpdate]
    dxvk_source_sha: str | None
    paired_version: str | None
    runtime_version: str
    probe_log: tuple[str, ...]

    @property
    def is_noop(self) -> bool:
        """Return whether the current pins already match the selected target."""
        return not self.pins


class HttpPackageProbe:
    def __init__(self, base_url: str = PACKAGE_BASE_URL, timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def artifact_exists(self, package: str, version: str) -> bool:
        """Return whether the remote Packman artifact exists."""
        parsed_url = urllib.parse.urlsplit(self._base_url)
        remote = parsed_url.path.rstrip("/").rsplit("/", 1)[-1] or "cloudfront"
        api_root = urllib.parse.urlunsplit((parsed_url.scheme, parsed_url.netloc, "", "", ""))
        url = (
            f"{api_root}/api/v3/packages/{urllib.parse.quote(package, safe='')}/"
            f"{urllib.parse.quote(version, safe='')}/{urllib.parse.quote(remote, safe='')}"
        )
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

        return payload.get("name") == version and payload.get("extension") == ".7z" and bool(payload.get("url"))

    def list_runtime_versions(self) -> list[str]:
        """Return runtime versions from the remote Packman package index."""
        return list_package_versions(self._base_url, REMIX_RUNTIME_PACKAGE, self._timeout)


def list_package_versions(base_url: str, package: str, timeout: int = 30) -> list[str]:
    """Return package versions from the Omnipackages package API."""
    parsed_url = urllib.parse.urlsplit(base_url.rstrip("/"))
    remote = parsed_url.path.rstrip("/").rsplit("/", 1)[-1] or "cloudfront"
    api_root = urllib.parse.urlunsplit((parsed_url.scheme, parsed_url.netloc, "", "", ""))

    page = 1
    page_count = 1
    versions = set()
    while page <= page_count:
        query = urllib.parse.urlencode({"version": "", "remote": remote, "page": page, "pageSize": 100})
        url = f"{api_root}/api/v3/packages/{urllib.parse.quote(package, safe='')}/?{query}"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        for item in payload.get("items", []):
            if item.get("extension") == ".7z" and isinstance(item.get("name"), str):
                versions.add(item["name"])
        page_count = int(payload.get("pageCount", page))
        page += 1

    return sorted(versions)


def collect_dxvk_commits(repo_url: str | None, branch: str, max_commits: int) -> Iterator[str]:
    """Yield newest-to-oldest commit SHAs from a dxvk-remix branch."""
    if not repo_url:
        raise RuntimeError("TOOLKIT_GITLAB_DXVK_REPO_URL is not set.")

    parsed_url = urllib.parse.urlsplit(repo_url)
    project_path = parsed_url.path.strip("/").removesuffix(".git")
    if not parsed_url.hostname or not project_path:
        raise ValueError(f"Invalid GitLab repository URL: {repo_url}")

    project = urllib.parse.quote(project_path, safe="")
    page = 1
    yielded = 0
    while yielded < max_commits:
        page_size = min(max_commits - yielded, 100)
        query = urllib.parse.urlencode({"ref_name": branch, "page": page, "per_page": page_size})
        result = subprocess.run(
            [
                "glab",
                "api",
                "--hostname",
                parsed_url.hostname,
                f"projects/{project}/repository/commits?{query}",
            ],
            check=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
        )
        commits = json.loads(result.stdout)
        if not isinstance(commits, list):
            raise RuntimeError("GitLab commits API returned an invalid response.")

        for commit in commits:
            if not isinstance(commit, dict) or not isinstance(commit.get("id"), str):
                raise RuntimeError("GitLab commits API returned a commit without an ID.")
            yield commit["id"]
            yielded += 1

        if len(commits) < page_size:
            return
        page += 1


def read_packman_versions(path: Path, package_names: set[str] | frozenset[str]) -> dict[str, str]:
    """Read package versions from a Packman XML dependency file."""
    root = ET.parse(path).getroot()
    versions = {}
    for package in root.iter("package"):
        name = package.attrib.get("name")
        if name in package_names:
            versions[name] = package.attrib["version"]

    missing = package_names - versions.keys()
    if missing:
        raise RuntimeError(f"Missing package pins in {path}: {', '.join(sorted(missing))}")
    return versions


def update_packman_versions(path: Path, package_versions: dict[str, str]) -> None:
    """Update selected package versions in a Packman XML dependency file."""
    tree = ET.parse(path)
    root = tree.getroot()
    remaining = set(package_versions)

    for package in root.iter("package"):
        name = package.attrib.get("name")
        if name in package_versions:
            package.set("version", package_versions[name])
            remaining.remove(name)

    if remaining:
        raise RuntimeError(f"Missing package pins in {path}: {', '.join(sorted(remaining))}")

    ET.indent(tree, space="  ")
    path.write_text(ET.tostring(root, encoding="unicode", short_empty_elements=True) + "\n", encoding="utf-8")


def select_latest_runtime_release(versions: list[str]) -> str:
    """Return the newest remix_runtime release version, excluding prereleases."""
    release_versions = []
    for version in versions:
        match = _RUNTIME_RELEASE_PATTERN.fullmatch(version)
        if match:
            release_versions.append((tuple(int(part) for part in match.groups()), version))

    if not release_versions:
        raise RuntimeError("No remix_runtime release versions found.")

    return max(release_versions)[1]


def select_target_update(
    current_versions: dict[str, str],
    dxvk_commits: Iterable[str],
    package_probe,
) -> TargetUpdate:
    """Select target package pins for the Remix dependency bot."""
    probe_log = []
    paired_sha = None
    paired_version = None

    for sha in dxvk_commits:
        candidate = f"ext-{sha[:7]}-main"
        available = {package: package_probe.artifact_exists(package, candidate) for package in sorted(TARGET_PACKAGES)}
        probe_log.append(
            f"{candidate}: "
            + ", ".join(f"{package}={'found' if exists else 'missing'}" for package, exists in available.items())
        )
        if all(available.values()):
            paired_sha = sha
            paired_version = candidate
            break

    if paired_sha is None or paired_version is None:
        raise RuntimeError("Unable to find a dxvk-remix commit with both hdremix and omni_core_materials artifacts.")

    runtime_version = select_latest_runtime_release(package_probe.list_runtime_versions())
    selected = {
        "rtx-remix-hdremix": paired_version,
        "rtx-remix-omni_core_materials": paired_version,
        REMIX_RUNTIME_PACKAGE: runtime_version,
    }
    pins = {
        package: PinUpdate(current_versions[package], version)
        for package, version in selected.items()
        if current_versions[package] != version
    }
    return TargetUpdate(
        pins=pins,
        dxvk_source_sha=paired_sha,
        paired_version=paired_version,
        runtime_version=runtime_version,
        probe_log=tuple(probe_log),
    )


def update_changelog(path: Path, entry: str) -> None:
    """Replace the root changelog's Remix target dependency entry."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    unreleased_start = _find_line(lines, "## [Unreleased]")
    next_release = _find_next_heading(lines, unreleased_start + 1, "## ")
    changed_start = _find_line(lines, "### Changed", unreleased_start + 1, next_release)

    if changed_start is None:
        insert_at = _find_next_heading(lines, unreleased_start + 1, "### ")
        insert_at = min(insert_at, next_release)
        lines[insert_at:insert_at] = ["### Changed", entry, ""]
    else:
        changed_end = min(_find_next_heading(lines, changed_start + 1, "### "), next_release)
        lines[changed_start + 1 : changed_end] = [
            line for line in lines[changed_start + 1 : changed_end] if not line.startswith(CHANGELOG_ENTRY_PREFIX)
        ]
        next_release = _find_next_heading(lines, unreleased_start + 1, "## ")
        insert_at = _find_next_heading(lines, changed_start + 1, "### ")
        insert_at = min(insert_at, next_release)
        while insert_at > changed_start + 1 and lines[insert_at - 1] == "":
            insert_at -= 1
        lines.insert(insert_at, entry)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def format_changelog_entry(update: TargetUpdate) -> str:
    """Return the root changelog entry for a target dependency update."""
    parts = []
    paired_updates = [package for package in sorted(TARGET_PACKAGES) if package in update.pins]
    if len(paired_updates) == len(TARGET_PACKAGES) and update.paired_version:
        parts.append(f"hdremix and omni_core_materials to `{update.paired_version}`")
    else:
        for package in paired_updates:
            parts.append(f"{_changelog_package_name(package)} to `{update.pins[package].new}`")

    if REMIX_RUNTIME_PACKAGE in update.pins:
        parts.append(f"remix_runtime to `{update.pins[REMIX_RUNTIME_PACKAGE].new}`")

    return f"{CHANGELOG_ENTRY_PREFIX} {', '.join(parts)}"


def current_pins_track_main(current_versions: dict[str, str]) -> bool:
    """Return whether the paired Remix target pins look like normal dxvk-remix main artifacts."""
    return all(_MAIN_EXT_VERSION_PATTERN.fullmatch(current_versions[package]) for package in TARGET_PACKAGES)


def format_summary(update: TargetUpdate) -> str:
    """Return a Markdown summary for CI logs and commit bodies."""
    if update.is_noop:
        return "Remix target dependencies are already current."

    lines = [
        "Remix target dependency update",
        "",
        f"- dxvk-remix source SHA: `{update.dxvk_source_sha}`",
        f"- paired hdremix/omni_core_materials version: `{update.paired_version}`",
        f"- remix_runtime release version: `{update.runtime_version}`",
        "",
        "Changed pins:",
    ]
    for package, pin in sorted(update.pins.items()):
        lines.append(f"- `{package}`: `{pin.old}` -> `{pin.new}`")

    lines.extend(["", "Artifact probe:", *[f"- {line}" for line in update.probe_log]])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the Remix target dependency bot."""
    args = _parse_args(argv)
    current_versions = read_packman_versions(args.target_deps, ALL_REMIX_TARGET_PACKAGES)

    if not args.force_main_selection and not current_pins_track_main(current_versions):
        print(
            "Current paired Remix target pins do not track dxvk-remix main artifacts. Leaving compatibility pins alone."
        )
        return 0

    commits = collect_dxvk_commits(args.dxvk_repo, args.dxvk_branch, args.max_commits)
    update = select_target_update(current_versions, commits, HttpPackageProbe(args.package_base_url, args.timeout))
    summary = format_summary(update)
    print(summary)

    if args.summary_file:
        args.summary_file.write_text(summary + "\n", encoding="utf-8")

    if update.is_noop or not args.apply:
        return 0

    update_packman_versions(args.target_deps, {package: pin.new for package, pin in update.pins.items()})
    update_changelog(args.changelog, format_changelog_entry(update))
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update pinned RTX Remix target dependencies.")
    parser.add_argument("--apply", action="store_true", help="Write target dependency and changelog updates.")
    parser.add_argument("--target-deps", type=Path, default=TARGET_DEPS_PATH)
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_PATH)
    parser.add_argument("--summary-file", type=Path)
    parser.add_argument("--dxvk-repo", default=DXVK_REMIX_REPO_URL)
    parser.add_argument("--dxvk-branch", default=DXVK_REMIX_BRANCH)
    parser.add_argument("--max-commits", type=int, default=200)
    parser.add_argument("--package-base-url", default=PACKAGE_BASE_URL)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--force-main-selection",
        action="store_true",
        help="Update even when current hdremix pins look like compatibility overrides.",
    )
    return parser.parse_args(argv)


def _find_line(lines: list[str], target: str, start: int = 0, end: int | None = None) -> int | None:
    if end is None:
        end = len(lines)
    for index in range(start, end):
        if lines[index] == target:
            return index
    return None


def _find_next_heading(lines: list[str], start: int, prefix: str) -> int:
    for index in range(start, len(lines)):
        if lines[index].startswith(prefix):
            return index
    return len(lines)


def _changelog_package_name(package: str) -> str:
    return package.removeprefix("rtx-remix-")


if __name__ == "__main__":
    raise SystemExit(main())
