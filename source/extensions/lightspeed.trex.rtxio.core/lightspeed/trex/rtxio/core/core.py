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

import asyncio
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import carb
import carb.tokens
import omni.kit.app
from omni.flux.asset_importer.core.data_models import SUPPORTED_TEXTURE_EXTENSIONS as _SUPPORTED_TEXTURE_EXTENSIONS
from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from omni.flux.utils.common.omni_url import OmniUrl as _OmniUrl
from pxr import Sdf, Usd, UsdUtils

_PACKAGING_TEXTURE_SUFFIXES = frozenset(suffix.lower() for suffix in _SUPPORTED_TEXTURE_EXTENSIONS)
_RTXIO_PACKAGER_EXE_RELATIVE = Path("deps") / "rtxio" / "bin" / "RtxIoResourcePackager.exe"
_RTXIO_EXTRACTOR_EXE_RELATIVE = Path("deps") / "rtxio" / "bin" / "RtxIoResourceExtractor.exe"
_RTXIO_PACKAGE_MAGIC = b"\x0d\xd0\xad\xba"


@dataclass(frozen=True)
class RtxIoProbeResult:
    package_files: list[Path]
    broken_references: list[tuple[str, str, str]]
    was_cancelled: bool = False


class RtxIoCore:
    def __init__(self):
        self.default_attr = {
            "_cancel_token": None,
            "_current_count": None,
            "_total_count": None,
            "_status": None,
            "_rtxio_proc": None,
        }
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._cancel_token = False
        self._current_count = 0
        self._total_count = 0
        self._status = "Initializing..."
        self._rtxio_proc = None

        self.__progress = _Event()

    def cancel(self):
        """Cancel the current RTX IO operation."""
        self._cancel_token = True
        proc = self._rtxio_proc
        if proc is not None:
            proc.terminate()

    @property
    def current_count(self) -> int:
        return self._current_count

    @current_count.setter
    def current_count(self, value):
        self._current_count = min(value, self.total_count)
        self._progress()

    @property
    def total_count(self) -> int:
        return self._total_count

    @total_count.setter
    def total_count(self, value):
        self._total_count = value
        self._progress()

    @property
    def status(self) -> str:
        return self._status

    @property
    def was_cancelled(self) -> bool:
        return self._cancel_token

    def subscribe_progress(self, function: Callable[[int, int, str], Any]):
        """Return the object that will automatically unsubscribe when destroyed."""
        return _EventSubscription(self.__progress, function)

    @staticmethod
    def _resolve_extension_path(relative_path: Path) -> Path | None:
        ext_root_str = carb.tokens.get_tokens_interface().resolve("${lightspeed.trex.rtxio.core}")
        if not ext_root_str:
            return None
        resolved_path = Path(ext_root_str) / relative_path
        return resolved_path if resolved_path.is_file() else None

    def _find_packager_exe(self) -> Path | None:
        return self._resolve_extension_path(_RTXIO_PACKAGER_EXE_RELATIVE)

    def _find_extractor_exe(self) -> Path | None:
        return self._resolve_extension_path(_RTXIO_EXTRACTOR_EXE_RELATIVE)

    @staticmethod
    def is_rtxio_package_file(path: Path) -> bool:
        """Return True when ``path`` looks like a root RTX IO package file."""
        if not path.is_file() or path.suffix.lower() != ".pkg":
            return False

        try:
            with path.open("rb") as stream:
                return stream.read(len(_RTXIO_PACKAGE_MAGIC)) == _RTXIO_PACKAGE_MAGIC
        except OSError:
            return False

    @classmethod
    def find_rtxio_package_files(cls, directory: Path) -> list[Path]:
        """Return extractable RTX IO package files below ``directory``.

        Args:
            directory: Directory to scan recursively. When the path does not exist or
                is not a directory, an empty list is returned.

        Returns:
            list[Path]: Every root RTX IO package below ``directory``. Split
                fragments such as ``mod.pkg.000`` and non-RTX IO `.pkg` files are
                excluded intentionally.
        """
        path = Path(directory)
        if not path.exists() or not path.is_dir():
            return []
        return [pkg for pkg in path.rglob("*.pkg") if cls.is_rtxio_package_file(pkg)]

    @staticmethod
    def _normalize_packaging_absolute_path(absolute_path: str) -> str:
        return Path(absolute_path).as_posix()

    @staticmethod
    def _is_missing_packaging_texture_path(absolute_path: str) -> bool:
        absolute_url = _OmniUrl(absolute_path)
        if absolute_url.suffix.lower() not in _PACKAGING_TEXTURE_SUFFIXES:
            return False
        return not absolute_url.exists

    def collect_invalid_stage_assets(
        self,
        stage_prims: list[Usd.Prim],
        unresolved_paths: list[str],
        *,
        include_missing_authored_textures: bool = True,
        is_cancelled: Callable[[], bool] | None = None,
        on_prim_processed: Callable[[], None] | None = None,
    ) -> set[tuple[str, str, str]]:
        """Collect invalid authored asset references from stage prims."""
        unresolved_set = (
            {self._normalize_packaging_absolute_path(path) for path in unresolved_paths} if unresolved_paths else None
        )
        result: set[tuple[str, str, str]] = set()

        for prim in stage_prims:
            if is_cancelled and is_cancelled():
                return result

            if unresolved_set:
                prim_stack = prim.GetPrimStack()
                for prim_spec in prim_stack:
                    for ref in prim_spec.referenceList.GetAddedOrExplicitItems():
                        resolved_path = self._normalize_packaging_absolute_path(
                            prim_spec.layer.ComputeAbsolutePath(ref.assetPath)
                        )
                        if resolved_path in unresolved_set:
                            result.add((prim_spec.layer.identifier, str(prim_spec.path), resolved_path))

            for prop in prim.GetAttributes():
                if not isinstance(prop.Get(), Sdf.AssetPath):
                    continue
                property_stack = prop.GetPropertyStack(Usd.TimeCode.Default())
                for prop_spec in property_stack:
                    prop_layer = prop_spec.layer
                    authored_value = prop_spec.default
                    if not isinstance(authored_value, Sdf.AssetPath) or not authored_value.path:
                        continue
                    abs_path = self._normalize_packaging_absolute_path(
                        prop_layer.ComputeAbsolutePath(authored_value.path)
                    )
                    if include_missing_authored_textures and self._is_missing_packaging_texture_path(abs_path):
                        result.add((prop_layer.identifier, str(prop.GetPath()), abs_path))
                    if unresolved_set and abs_path in unresolved_set:
                        result.add((prop_layer.identifier, str(prop.GetPath()), abs_path))

            if on_prim_processed:
                on_prim_processed()

        return result

    async def scan_invalid_stage_asset_references(self, root_layer_path: Path) -> list[tuple[str, str, str]]:
        """Return broken asset references authored anywhere in the given stage stack.

        Args:
            root_layer_path: Root USD layer path for the stage that should be scanned.

        Returns:
            list[tuple[str, str, str]]: One tuple per broken reference, containing the
                authoring layer identifier, the USD property path, and the resolved
                absolute asset path that could not be found.
        """
        self._cancel_token = False
        root_layer = Sdf.Layer.FindOrOpen(str(root_layer_path))
        if not root_layer:
            carb.log_warn(f"[rtxio] Could not open stage layer for invalid-reference scan: {root_layer_path}")
            return []

        self._new_stage("Opening project stage for RTX IO validation...", 1)
        self.current_count = 1
        await omni.kit.app.get_app().next_update_async()

        stage = Usd.Stage.Open(root_layer)
        if not stage:
            carb.log_warn(f"[rtxio] Could not open stage for invalid-reference scan: {root_layer_path}")
            return []

        _, _, unresolved_paths = UsdUtils.ComputeAllDependencies(root_layer.identifier)
        stage_prims = list(stage.TraverseAll())
        total_prims = max(len(stage_prims), 1)
        self._new_stage("Scanning project texture references...", total_prims)

        result: set[tuple[str, str, str]] = set()
        for start_index in range(0, len(stage_prims), 32):
            if self._cancel_token:
                break
            prim_chunk = stage_prims[start_index : start_index + 32]
            result.update(
                self.collect_invalid_stage_assets(
                    prim_chunk,
                    unresolved_paths,
                    include_missing_authored_textures=True,
                    is_cancelled=lambda: self._cancel_token,
                    on_prim_processed=lambda: setattr(self, "current_count", self.current_count + 1),
                )
            )
            await omni.kit.app.get_app().next_update_async()

        stage = None
        return list(result)

    async def probe_directory(self, directory: Path, root_layer_path: Path | None = None) -> RtxIoProbeResult:
        """Probe a directory and optional stage file for RTX IO packages and broken references."""
        self._cancel_token = False
        self._new_stage("Scanning for RTX IO packages...", 1)
        package_files = self.find_rtxio_package_files(directory)
        self.current_count = 1
        await omni.kit.app.get_app().next_update_async()

        if not package_files or not root_layer_path or self._cancel_token:
            return RtxIoProbeResult(package_files=package_files, broken_references=[], was_cancelled=self._cancel_token)

        broken_references = await self.scan_invalid_stage_asset_references(root_layer_path)
        return RtxIoProbeResult(
            package_files=package_files,
            broken_references=broken_references,
            was_cancelled=self._cancel_token,
        )

    async def compress_directory(self, output_directory: Path, split_size_mb: int | None = None) -> list[str]:
        """Compress all `.dds` files in ``output_directory`` into an RTX IO `mod.pkg`.

        Returns:
            list[str]: An empty list on success, or one error message per failure.
        """
        self._cancel_token = False
        exe = self._find_packager_exe()
        if not exe:
            return ["RtxIoResourcePackager.exe was not found in the RTX IO extension directory."]

        dds_files = list(Path(output_directory).rglob("*.dds"))
        if not dds_files:
            carb.log_info("[rtxio] No .dds files found to compress, skipping RTX IO step.")
            return []

        self._new_stage("Compressing textures to RTX IO format...", len(dds_files))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as list_file:
            for dds in dds_files:
                list_file.write(str(dds) + "\n")
            list_path = list_file.name

        output_pkg = Path(output_directory) / "mod.pkg"
        lines_seen = [0]
        returncode = [None]
        stderr_lines: list[str] = []

        def _run_packager():
            split_args = ["--split", str(split_size_mb)] if split_size_mb is not None else []
            try:
                proc = subprocess.Popen(
                    [
                        str(exe),
                        "-l",
                        list_path,
                        "-o",
                        str(output_pkg),
                        "-b",
                        str(output_directory),
                        "-c",
                        "12",
                        "-v",
                        "-m",
                        "8",
                    ]
                    + split_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except Exception as exc:  # noqa: BLE001
                stderr_lines.append(str(exc))
                returncode[0] = -1
                return

            self._rtxio_proc = proc

            def _drain_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line.decode(errors="replace").rstrip())

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            try:
                for _ in proc.stdout:
                    if self._cancel_token:
                        proc.terminate()
                        break
                    lines_seen[0] += 1
            finally:
                proc.wait()
                stderr_thread.join(timeout=5.0)
                returncode[0] = proc.returncode
                self._rtxio_proc = None

        try:
            future = asyncio.get_event_loop().run_in_executor(None, _run_packager)

            while not future.done():
                proc = self._rtxio_proc
                if self._cancel_token and proc is not None:
                    proc.terminate()
                self.current_count = min(lines_seen[0], len(dds_files))
                await omni.kit.app.get_app().next_update_async()

            await future

            if self._cancel_token:
                return []

            self.current_count = len(dds_files)

            if returncode[0] != 0:
                err_text = "\n".join(stderr_lines).strip() or "unknown error"
                return [f"RtxIoResourcePackager failed (exit {returncode[0]}): {err_text}"]

            carb.log_info(f"[rtxio] Compressed {len(dds_files)} DDS file(s) -> {output_pkg}")
            return []
        finally:
            Path(list_path).unlink(missing_ok=True)

    async def extract_packages(self, mod_directory: Path, force_overwrite: bool = False) -> list[str]:
        """Extract all RTX IO packages in ``mod_directory`` back to raw files.

        Returns:
            list[str]: An empty list on success, or one error message per failure.
        """
        self._cancel_token = False
        exe = self._find_extractor_exe()
        if not exe:
            return ["RtxIoResourceExtractor.exe was not found in the RTX IO extension directory."]

        pkg_files = self.find_rtxio_package_files(Path(mod_directory))
        if not pkg_files:
            return [f"No .pkg files found in: {mod_directory}"]

        self._new_stage("Extracting RTX IO packages...", len(pkg_files))

        errors = []
        loop = asyncio.get_event_loop()
        for pkg in pkg_files:
            if self._cancel_token:
                break
            command = [str(exe), str(pkg), "-o", str(mod_directory)]
            if force_overwrite:
                command.append("--force")
            returncode = [None]
            stderr_lines: list[str] = []

            def _run_extractor(cmd=command, stderr_buffer=stderr_lines, return_code=returncode):
                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                except Exception as exc:  # noqa: BLE001
                    stderr_buffer.append(str(exc))
                    return_code[0] = -1
                    return

                self._rtxio_proc = proc

                def _drain_stderr(stderr_stream=proc.stderr, buffer=stderr_buffer):
                    for line in stderr_stream:
                        buffer.append(line.decode(errors="replace").rstrip())

                stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
                stderr_thread.start()

                try:
                    proc.wait()
                finally:
                    stderr_thread.join(timeout=5.0)
                    return_code[0] = proc.returncode
                    self._rtxio_proc = None

            future = loop.run_in_executor(None, _run_extractor)

            while not future.done():
                proc = self._rtxio_proc
                if self._cancel_token and proc is not None:
                    proc.terminate()
                await omni.kit.app.get_app().next_update_async()

            await future

            if self._cancel_token:
                break

            if returncode[0] != 0:
                err_text = "\n".join(stderr_lines).strip() or "unknown error"
                errors.append(f"Failed to extract {pkg.name} (exit {returncode[0]}): {err_text}")
            else:
                carb.log_info(f"[rtxio] Extracted: {pkg}")

            self.current_count += 1

        return errors

    async def delete_dds_files(self, directory: Path) -> None:
        """Delete all `.dds` files under ``directory`` recursively."""
        dds_files = list(Path(directory).rglob("*.dds"))
        self._new_stage("Deleting packaged DDS files...", len(dds_files))
        for index, dds in enumerate(dds_files, start=1):
            if self._cancel_token:
                break
            try:
                dds.unlink()
                carb.log_info(f"[rtxio] Deleted: {dds}")
            except OSError as exc:
                carb.log_warn(f"[rtxio] Could not delete {dds}: {exc}")
            self.current_count += 1
            if index % 32 == 0:
                await omni.kit.app.get_app().next_update_async()

    def _new_stage(self, status: str, total_count: int):
        self._status = status
        self._current_count = 0
        self._total_count = total_count
        self._progress()

    def _progress(self):
        self.__progress(self.current_count, self.total_count, self.status)

    def destroy(self):
        self.cancel()
        _reset_default_attrs(self)
