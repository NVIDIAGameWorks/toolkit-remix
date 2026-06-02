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

Bundle RTX Remix Toolkit crash evidence into a per-run handoff folder.
"""

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


MINIDUMP_NAME_RE = re.compile(
    r"(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.dmp\.zip$"
)
DUMP_ID_RE = re.compile(
    r"DumpId\s*=?\s*['\"]?(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)
AFTERMATH_SUFFIXES = (".nv-gpudmp", ".gpudmp", ".nv-gpudmp.zip", ".gpudmp.zip")


def _existing_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.exists():
        raise argparse.ArgumentTypeError(f"path does not exist: {value}")
    return path


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "untitled"


def _create_run_dir(case_root: Path, run_id: str, title: str | None) -> Path:
    case_root.mkdir(parents=True, exist_ok=True)

    existing = sorted(path for path in case_root.iterdir() if path.is_dir() and path.name.startswith(f"{run_id}_"))
    if existing:
        raise FileExistsError(f"run folder already exists for {run_id}: {existing[0]}")

    suffix = _slugify(title or "crash-handoff")
    run_dir = case_root / f"{run_id}_{datetime.now().strftime('%Y%m%d')}-{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _split_name_for_suffix(source: Path) -> tuple[str, str]:
    suffix = "".join(source.suffixes) if source.is_file() else ""
    if suffix and source.name.endswith(suffix):
        return source.name[: -len(suffix)], suffix
    return source.name, ""


def _unique_target(destination: Path, source: Path) -> Path:
    target = destination / source.name
    if not target.exists():
        return target

    stem, suffix = _split_name_for_suffix(source)
    parent_slug = _slugify(source.parent.name)
    index = 1
    while True:
        qualifier = parent_slug if index == 1 else f"{parent_slug}-{index}"
        target = destination / f"{stem}-{qualifier}{suffix}"
        if not target.exists():
            return target
        index += 1


def _copy_paths(paths: list[Path], destination: Path) -> list[tuple[Path, Path]]:
    copied = []
    if not paths:
        return copied

    destination.mkdir(parents=True, exist_ok=True)
    for source in paths:
        target = _unique_target(destination, source)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        copied.append((source, target))
    return copied


def _iter_files(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(child for child in path.rglob("*") if child.is_file()))
    return files


def _collect_minidump_ids(files: list[Path]) -> list[tuple[str, Path]]:
    ids_by_uuid = {}
    for path in files:
        name_match = MINIDUMP_NAME_RE.search(path.name)
        if name_match:
            ids_by_uuid.setdefault(name_match.group("uuid").lower(), path)
            continue

        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for match in DUMP_ID_RE.finditer(text):
            ids_by_uuid.setdefault(match.group("uuid").lower(), path)

    return sorted(ids_by_uuid.items())


def _is_aftermath_dump(path: Path) -> bool:
    lowered = path.name.lower()
    return any(lowered.endswith(suffix) for suffix in AFTERMATH_SUFFIXES)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _write_manifest(
    args,
    run_dir: Path,
    copied_files: list[tuple[Path, Path]],
    minidump_ids: list[tuple[str, Path]],
    aftermath_dumps: list[Path],
) -> None:
    lines = [
        f"# {args.run_id} Manifest",
        "",
        f"Title: {args.title or ''}",
        f"Outcome: `{args.outcome or 'unknown'}`",
        f"Trigger: {args.trigger or 'unknown'}",
        f"Recorded: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
    ]

    if minidump_ids:
        lines.append("Minidump UUIDs:")
        lines.extend(f"- `{uuid}` from `{_relative(path, run_dir)}`" for uuid, path in minidump_ids)
        lines.append("")

    if aftermath_dumps:
        lines.append("Aftermath GPU dumps:")
        lines.extend(
            f"- `{_relative(path, run_dir)}` ({path.stat().st_size} bytes)" for path in sorted(aftermath_dumps)
        )
        lines.append("")

    if args.note:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in args.note)
        lines.append("")

    lines.append("Artifacts:")
    if copied_files:
        for source, target in sorted(copied_files, key=lambda item: str(item[1])):
            lines.append(f"- `{_relative(target, run_dir)}` copied from `{source}`")
    else:
        lines.append("- No files were copied.")

    (run_dir / "RUN_MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bundle RTX Remix Toolkit crash evidence into a handoff folder.")
    parser.add_argument("--case-root", type=Path, required=True, help="Root folder for the crash case.")
    parser.add_argument("--run-id", required=True, help="Stable, unused run id, such as RUN-036.")
    parser.add_argument("--title", help="Short run title used when creating a new run folder.")
    parser.add_argument("--outcome", help="Short outcome, such as crash, hang, no-crash-control, or invalid.")
    parser.add_argument("--trigger", help="Short repro trigger description.")
    parser.add_argument("--note", action="append", default=[], help="Additional manifest note. May be repeated.")

    parser.add_argument("--kit-log", action="append", type=_existing_path, default=[], help="Kit log path.")
    parser.add_argument("--dxvk-log", action="append", type=_existing_path, default=[], help="DXVK/remix log path.")
    parser.add_argument("--dump", action="append", type=_existing_path, default=[], help="Kit dump/crash text path.")
    parser.add_argument("--aftermath-dump", action="append", type=_existing_path, default=[], help="AF GPU dump path.")
    parser.add_argument("--repro", action="append", type=_existing_path, default=[], help="Repro script/log path.")
    parser.add_argument("--config", action="append", type=_existing_path, default=[], help="Runtime config path.")
    parser.add_argument("--provenance", action="append", type=_existing_path, default=[], help="Provenance file path.")
    parser.add_argument("--extra", action="append", type=_existing_path, default=[], help="Extra evidence path.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        run_dir = _create_run_dir(args.case_root, args.run_id, args.title)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    copied_files = []
    copied_files.extend(_copy_paths(args.kit_log, run_dir / "kit-logs"))
    copied_files.extend(_copy_paths(args.dxvk_log, run_dir / "dxvk-logs"))
    copied_files.extend(_copy_paths(args.dump, run_dir / "dumps"))
    copied_files.extend(_copy_paths(args.aftermath_dump, run_dir / "aftermath-dumps"))
    copied_files.extend(_copy_paths(args.repro, run_dir / "repro"))
    copied_files.extend(_copy_paths(args.config + args.provenance, run_dir / "provenance"))
    copied_files.extend(_copy_paths(args.extra, run_dir / "extra"))

    copied_targets = [target for _source, target in copied_files]
    copied_target_files = _iter_files(copied_targets)
    minidump_ids = _collect_minidump_ids(copied_target_files)
    aftermath_dumps = [path for path in copied_target_files if _is_aftermath_dump(path)]
    _write_manifest(args, run_dir, copied_files, minidump_ids, aftermath_dumps)

    print(f"RunRoot={run_dir}")
    if minidump_ids:
        print("MinidumpIds=" + ",".join(uuid for uuid, _path in minidump_ids))
    print(f"AftermathDumpCount={len(aftermath_dumps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
