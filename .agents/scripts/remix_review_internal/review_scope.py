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

import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from .process_pool import ProbeTimeout, clean_environment, resolve_executable, run_git, run_probe
from .providers.base import ProviderSetupRequired, SetupIssue


__all__ = [
    "ChangeEntry",
    "ForgeCheck",
    "ForgeEvidence",
    "ReviewTarget",
    "RevisionSnapshot",
    "add_detached_checkout",
    "build_change_manifest",
    "build_delta_index",
    "check_forge_cli",
    "count_changes",
    "remove_review_checkout",
    "resolve_review",
    "resolve_revision_snapshot",
    "verify_review_checkout",
]


_SUPPORTED_CHANGE_STATUSES = frozenset({"A", "C", "D", "M", "R", "T"})
_REGULAR_FILE_MODES = frozenset({"100644", "100755"})
_HUNK_HEADER = re.compile(rb"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@")


@dataclass(frozen=True)
class ForgeCheck:
    """Describe one exact-head forge check without provider-specific fields."""

    name: str
    status: str
    required: bool
    allow_failure: bool
    sha: str
    url: str


@dataclass(frozen=True)
class ForgeEvidence:
    """Distinguish observed, unavailable, and local-only forge evidence."""

    description_state: str
    description: str
    checks_state: str
    checks: tuple[ForgeCheck, ...]
    checks_reason: str = ""


@dataclass(frozen=True)
class ReviewTarget:
    """Describe one exact remote review revision range."""

    kind: str
    review: str
    url: str
    number: int
    source_branch: str
    target_branch: str
    base: str
    head: str
    fetch_ref: str
    forge_evidence: ForgeEvidence


@dataclass(frozen=True)
class RevisionSnapshot:
    """Describe one immutable Git revision range."""

    base_ref: str
    head_ref: str
    base_sha: str
    head_sha: str
    head_tree_sha: str


@dataclass(frozen=True)
class ChangeEntry:
    """Describe one changed Git path and its readable review artifact."""

    status: str
    old_path: str | None
    new_path: str | None
    old_oid: str
    new_oid: str
    old_mode: str
    new_mode: str
    artifact_path: str


def resolve_revision_snapshot(repository: Path, base_ref: str, head_ref: str) -> RevisionSnapshot:
    """Resolve two Git references and the head tree to immutable object IDs."""
    base_sha = _resolve_object(repository, f"{base_ref}^{{commit}}", "review base")
    head_sha = _resolve_object(repository, f"{head_ref}^{{commit}}", "review head")
    head_tree_sha = _resolve_object(repository, f"{head_sha}^{{tree}}", "review head tree")
    return RevisionSnapshot(base_ref, head_ref, base_sha, head_sha, head_tree_sha)


def add_detached_checkout(repository: Path, head_sha: str, path: Path) -> Path:
    """Materialize one detached exact-head checkout without changing caller Git state."""
    disabled_hooks = path.parent / "disabled-hooks"
    result = run_git(
        repository,
        "-c",
        f"core.hooksPath={disabled_hooks.resolve().as_posix()}",
        "-c",
        "core.longpaths=true",
        "worktree",
        "add",
        "--detach",
        str(path),
        head_sha,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Git could not create the private review checkout.")
    return path.resolve()


def build_change_manifest(
    repository: Path,
    snapshot: RevisionSnapshot,
    checkout: Path,
    artifacts_dir: Path,
) -> tuple[ChangeEntry, ...]:
    """Build a complete NUL-safe manifest for one immutable revision range."""
    verify_review_checkout(checkout, snapshot)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for index, change in enumerate(_read_change_entries(repository, snapshot.base_sha, snapshot.head_sha)):
        artifact_path = _materialize_change_artifact(
            repository,
            checkout,
            artifacts_dir,
            index,
            change.status,
            change.old_path,
            change.new_path,
            change.old_oid,
            change.new_oid,
            change.old_mode,
            change.new_mode,
        )
        entries.append(replace(change, artifact_path=str(artifact_path)))
    return tuple(entries)


def build_delta_index(
    repository: Path,
    base_sha: str,
    head_sha: str,
) -> dict[str, dict[str, object]]:
    """Index changed base and head lines for one immutable Git delta.

    Args:
        repository: Repository containing both immutable revisions.
        base_sha: Exact base commit object ID.
        head_sha: Exact head commit object ID.

    Returns:
        A mapping from each logical changed path to inclusive base and head line
        intervals plus a file-level change flag.

    Raises:
        RuntimeError: When Git cannot enumerate or render the immutable delta.
    """
    index: dict[str, dict[str, object]] = {}
    for change in _read_change_entries(repository, base_sha, head_sha):
        logical_path = change.new_path or change.old_path
        if logical_path is None or logical_path in index:
            raise RuntimeError("Git returned an ambiguous logical path for the immutable delta index.")
        paths = tuple(
            dict.fromkeys(f":(literal){path}" for path in (change.old_path, change.new_path) if path is not None)
        )
        diff = run_git(
            repository,
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            base_sha,
            head_sha,
            "--",
            *paths,
            check=False,
        )
        if diff.returncode:
            raise RuntimeError(f"Git could not render immutable delta evidence for {logical_path!r}.")
        base_intervals, head_intervals = _parse_hunk_intervals(diff.stdout)
        index[logical_path] = {
            "base": base_intervals,
            "head": head_intervals,
            "base_path": change.old_path,
            "head_path": change.new_path,
            "file": change.status in {"A", "C", "D", "R", "T"}
            or change.old_mode != change.new_mode
            or "160000" in {change.old_mode, change.new_mode}
            or (not base_intervals and not head_intervals),
        }
    return index


def _read_change_entries(
    repository: Path,
    base_sha: str,
    head_sha: str,
) -> tuple[ChangeEntry, ...]:
    """Return raw immutable changes as entries without materialized artifacts."""
    raw = run_git(
        repository,
        "diff",
        "--raw",
        "-z",
        "--no-abbrev",
        "--find-renames",
        "--find-copies",
        "--find-copies-harder",
        base_sha,
        head_sha,
        "--",
        check=False,
    )
    if raw.returncode:
        raise RuntimeError("Git could not enumerate immutable change entries.")
    return tuple(ChangeEntry(*change, "") for change in _parse_raw_changes(raw.stdout))


def count_changes(repository: Path, snapshot: RevisionSnapshot) -> int:
    """Count the logical changed paths of one immutable range, exactly as the manifest enumerates them."""
    return len(_read_change_entries(repository, snapshot.base_sha, snapshot.head_sha))


def check_forge_cli(repository: Path, review: str) -> None:
    """Stop before any provider starts when the forge CLI is missing or logged out.

    A named merge request must be reviewed at its exact forge diff. When `glab` or `gh` cannot
    serve that diff, the run must stop with the exact repair, so a caller never substitutes the
    local branch for the merge request.
    """
    forge = _forge(repository, review)
    command = "glab" if forge == "gitlab" else "gh"
    host = _forge_host(repository, review)
    login = f"{command} auth login --hostname {host}" if host else f"{command} auth login"
    executable = resolve_executable(command)
    if executable is None:
        _fail_forge_setup(
            command,
            "FORGE_CLI_NOT_FOUND",
            f"{command} was not found on PATH, so the exact merge request diff cannot be read. Install {command}, "
            f"open a new terminal so PATH includes it, run `{login}` there, and retry.",
        )
    argv = (str(executable), "auth", "status", *(("--hostname", host) if host else ()))
    try:
        result = run_probe(argv, cwd=repository, environment=clean_environment(), deadline=time.monotonic() + 15.0)
    except (OSError, ProbeTimeout):
        _fail_forge_setup(command, "FORGE_CLI_UNEXECUTABLE", f"{command} auth status did not run. Reinstall {command}.")
    if result.returncode:
        _fail_forge_setup(
            command,
            "FORGE_AUTH_REQUIRED",
            f"{command} is not logged in to {host or 'the forge'}. Run `{login}` in your own terminal, then retry. "
            f"{_probe_tail(result)}".rstrip(),
        )


def resolve_review(repository: Path, review: str, *, deadline_mono: float | None = None) -> ReviewTarget:
    """Resolve and fetch one GitLab merge request or GitHub pull request within a deadline."""
    forge = _forge(repository, review)
    executable = resolve_executable("glab" if forge == "gitlab" else "gh")
    if executable is None:
        command = "glab" if forge == "gitlab" else "gh"
        raise RuntimeError(f"{command} is required for --review. Install it, authenticate it, and retry.")
    reference = review[1:] if review[:1] in {"!", "#"} else review
    if forge == "gitlab":
        argv = (str(executable), "mr", "view", reference, "--output", "json")
    else:
        argv = (
            str(executable),
            "pr",
            "view",
            reference,
            "--json",
            "number,url,baseRefName,baseRefOid,headRefName,headRefOid,body,statusCheckRollup",
        )
    deadline = _bounded_deadline(deadline_mono, 30.0)
    result = run_probe(
        argv,
        cwd=repository,
        environment=clean_environment(),
        deadline=deadline,
    )
    if result.returncode:
        raise RuntimeError(
            f"{executable.name} could not read {review!r}. Verify authentication and access. {_probe_tail(result)}".rstrip()
        )
    try:
        payload = json.loads(result.stdout)
        if forge == "gitlab":
            target = _gitlab_target(payload, review, _gitlab_evidence(executable, repository, payload, deadline))
        else:
            target = _github_target(payload, review)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{executable.name} returned incomplete review metadata for {review!r}.") from error
    return _fetch_review(repository, target, deadline_mono=deadline_mono)


def remove_review_checkout(repository: Path, path: Path) -> None:
    """Remove one detached review checkout owned by the current run."""
    if not _review_checkout_registered(repository, path):
        if path.exists():
            raise RuntimeError(f"An unregistered private review checkout remains at {path}.")
        return
    result = run_git(
        repository,
        "-c",
        "core.longpaths=true",
        "worktree",
        "remove",
        "--force",
        str(path),
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Git could not remove the private review checkout at {path}.")
    if _review_checkout_registered(repository, path) or path.exists():
        raise RuntimeError(f"The private review checkout remains after Git removed it at {path}.")


def _review_checkout_registered(repository: Path, path: Path) -> bool:
    """Tell whether Git still owns the exact private worktree path."""
    result = run_git(repository, "worktree", "list", "--porcelain", "-z", check=False)
    if result.returncode:
        raise RuntimeError("Git could not inspect registered worktrees during cleanup.")
    expected = path.resolve()
    for field in result.stdout.split(b"\0"):
        if not field.startswith(b"worktree "):
            continue
        try:
            registered = Path(field[len(b"worktree ") :].decode("utf-8")).resolve()
        except UnicodeDecodeError as error:
            raise RuntimeError("Git returned a non-UTF-8 worktree path during cleanup.") from error
        if registered == expected:
            return True
    return False


def _resolve_object(repository: Path, revision: str, description: str) -> str:
    """Resolve one Git revision to an exact object ID."""
    result = run_git(repository, "rev-parse", "--verify", "--end-of-options", revision, check=False)
    value = result.stdout.decode("ascii", errors="strict").strip() if not result.returncode else ""
    if not value:
        raise RuntimeError(f"Git could not resolve the exact {description}.")
    return value


def verify_review_checkout(checkout: Path, snapshot: RevisionSnapshot) -> None:
    """Verify that an artifact source matches the immutable head snapshot."""
    head_sha = _resolve_object(checkout, "HEAD^{commit}", "review checkout head")
    head_tree_sha = _resolve_object(checkout, "HEAD^{tree}", "review checkout tree")
    if head_sha != snapshot.head_sha or head_tree_sha != snapshot.head_tree_sha:
        raise RuntimeError("The private review checkout does not match the immutable review head.")
    index = run_git(checkout, "diff-index", "--cached", "--quiet", "HEAD", "--", check=False)
    worktree = run_git(checkout, "diff-files", "--quiet", "--", check=False)
    if index.returncode == 1 or worktree.returncode == 1:
        raise RuntimeError("The private review checkout contains tracked changes outside the immutable review head.")
    if index.returncode or worktree.returncode:
        raise RuntimeError("Git could not verify the private review checkout state.")
    untracked = run_git(checkout, "ls-files", "--others", "--exclude-standard", "-z", check=False)
    ignored = run_git(checkout, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", check=False)
    if untracked.returncode or ignored.returncode:
        raise RuntimeError("Git could not inspect untracked files in the private review checkout.")
    if untracked.stdout or ignored.stdout:
        raise RuntimeError("The private review checkout contains untracked files outside the immutable review head.")


def _decode_path(value: bytes) -> str:
    """Decode one Git path or fail with a bounded error before JSON serialization."""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("The review scope contains a path that is not valid UTF-8.") from error


def _parse_raw_changes(
    payload: bytes,
) -> tuple[tuple[str, str | None, str | None, str, str, str, str], ...]:
    """Parse Git's NUL-delimited raw diff without path quoting or line splitting."""
    fields = payload.split(b"\0")
    if fields and not fields[-1]:
        fields.pop()
    changes = []
    cursor = 0
    while cursor < len(fields):
        header = fields[cursor]
        cursor += 1
        parts = header.split()
        if len(parts) != 5 or not parts[0].startswith(b":"):
            raise RuntimeError("Git returned a malformed raw change record.")
        try:
            old_mode = parts[0][1:].decode("ascii")
            new_mode = parts[1].decode("ascii")
            old_oid = parts[2].decode("ascii")
            new_oid = parts[3].decode("ascii")
            status = parts[4][:1].decode("ascii")
        except UnicodeDecodeError as error:
            raise RuntimeError("Git returned non-ASCII raw change metadata.") from error
        if status not in _SUPPORTED_CHANGE_STATUSES:
            raise RuntimeError(f"Git returned unsupported change status {status!r}.")
        if cursor >= len(fields):
            raise RuntimeError("Git returned a raw change record without a path.")
        first_path = _decode_path(fields[cursor])
        cursor += 1
        if status in {"C", "R"}:
            if cursor >= len(fields):
                raise RuntimeError("Git returned a copied or renamed change without its destination path.")
            second_path = _decode_path(fields[cursor])
            cursor += 1
            old_path, new_path = first_path, second_path
        elif status == "A":
            old_path, new_path = None, first_path
        elif status == "D":
            old_path, new_path = first_path, None
        else:
            old_path = new_path = first_path
        changes.append((status, old_path, new_path, old_oid, new_oid, old_mode, new_mode))
    return tuple(changes)


def _parse_hunk_intervals(payload: bytes) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    """Parse inclusive base and head intervals from a zero-context Git diff."""
    base_intervals = []
    head_intervals = []
    for base_start, base_count, head_start, head_count in _hunk_ranges(payload):
        if base_count:
            base_intervals.append((base_start, base_start + base_count - 1))
        if head_count:
            head_intervals.append((head_start, head_start + head_count - 1))
    return tuple(base_intervals), tuple(head_intervals)


def _hunk_ranges(payload: bytes) -> tuple[tuple[int, int, int, int], ...]:
    """Return zero-context Git hunk starts and counts in source order."""
    ranges = []
    for line in payload.splitlines():
        match = _HUNK_HEADER.match(line)
        if match is not None:
            ranges.append(
                (
                    int(match.group(1)),
                    int(match.group(2) or b"1"),
                    int(match.group(3)),
                    int(match.group(4) or b"1"),
                )
            )
    return tuple(ranges)


def _materialize_change_artifact(
    repository: Path,
    checkout: Path,
    artifacts_dir: Path,
    index: int,
    status: str,
    old_path: str | None,
    new_path: str | None,
    old_oid: str,
    new_oid: str,
    old_mode: str,
    new_mode: str,
) -> Path:
    """Return readable exact-revision evidence for one changed Git path."""
    if new_path is not None and new_mode in _REGULAR_FILE_MODES:
        artifact_path = checkout.resolve() / new_path
        if not artifact_path.is_file():
            raise RuntimeError(f"The private review checkout is missing changed file {new_path!r}.")
        observed = run_git(
            checkout,
            "hash-object",
            f"--path={new_path}",
            "--",
            str(artifact_path),
            check=False,
        )
        observed_oid = observed.stdout.decode("ascii", errors="strict").strip() if not observed.returncode else ""
        if observed_oid != new_oid:
            raise RuntimeError(f"Changed file {new_path!r} does not match its immutable Git object.")
        return artifact_path
    if "160000" in {old_mode, new_mode}:
        artifact_path = artifacts_dir / f"{index:06d}.gitlink.json"
        artifact_path.write_text(
            json.dumps(
                {
                    "new_mode": new_mode,
                    "new_oid": new_oid,
                    "new_path": new_path,
                    "old_mode": old_mode,
                    "old_oid": old_oid,
                    "old_path": old_path,
                    "status": status,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return artifact_path.resolve()
    object_id = new_oid if new_path is not None and new_mode != "000000" else old_oid
    blob = run_git(repository, "cat-file", "blob", object_id, check=False)
    if blob.returncode:
        raise RuntimeError("Git could not materialize a changed non-regular file.")
    artifact_path = artifacts_dir / f"{index:06d}.blob"
    artifact_path.write_bytes(blob.stdout)
    return artifact_path.resolve()


def _forge(repository: Path, review: str) -> str:
    """Identify the review forge from its reference or origin URL."""
    lowered = review.lower()
    if "/pull/" in lowered or "github" in lowered or review.startswith("#"):
        return "github"
    if "/merge_requests/" in lowered or "gitlab" in lowered or review.startswith("!"):
        return "gitlab"
    remote = run_git(repository, "remote", "get-url", "origin", check=False)
    remote_url = remote.stdout.decode("utf-8", errors="replace").lower()
    if "github" in remote_url:
        return "github"
    if "gitlab" in remote_url:
        return "gitlab"
    raise RuntimeError("--review must identify a GitLab merge request or GitHub pull request.")


def _forge_host(repository: Path, review: str) -> str:
    """Return the forge host from the review URL, else from the origin remote."""
    for candidate in (
        review,
        run_git(repository, "remote", "get-url", "origin", check=False)
        .stdout.decode("utf-8", errors="replace")
        .strip(),
    ):
        if "://" in candidate:
            host = urlsplit(candidate).hostname
            if host:
                return host
        elif "@" in candidate and ":" in candidate:
            # scp-like remote: git@host:group/project.git
            return candidate.split("@", 1)[1].split(":", 1)[0]
    return ""


def _fail_forge_setup(command: str, code: str, message: str) -> None:
    """Raise one forge CLI setup failure in the shared setup_required shape."""
    raise ProviderSetupRequired((SetupIssue(provider=command, affected_lanes=("scope",), code=code, message=message),))


def _probe_tail(result) -> str:
    """Return what the CLI printed as one bounded line, so the error names the real cause."""
    text = (result.stderr or result.stdout).decode("utf-8", errors="replace")
    # glab wraps one sentence over several lines and prefixes a banner, so join the lines.
    words = " ".join(line.strip() for line in text.splitlines() if line.strip() and line.strip() != "ERROR")
    return words.lstrip("X ").strip()[-300:]


def _gitlab_target(payload: dict, requested: str, evidence: ForgeEvidence) -> ReviewTarget:
    """Normalize GitLab merge-request metadata."""
    diff_refs = payload["diff_refs"]
    number = int(payload["iid"])
    return ReviewTarget(
        kind="gitlab_mr",
        review=requested,
        url=str(payload["web_url"]),
        number=number,
        source_branch=str(payload["source_branch"]),
        target_branch=str(payload["target_branch"]),
        base=str(diff_refs["base_sha"]),
        head=str(diff_refs["head_sha"]),
        fetch_ref=f"refs/merge-requests/{number}/head",
        forge_evidence=evidence,
    )


def _github_target(payload: dict, requested: str) -> ReviewTarget:
    """Normalize GitHub pull-request metadata."""
    number = int(payload["number"])
    return ReviewTarget(
        kind="github_pr",
        review=requested,
        url=str(payload["url"]),
        number=number,
        source_branch=str(payload["headRefName"]),
        target_branch=str(payload["baseRefName"]),
        base=str(payload["baseRefOid"]),
        head=str(payload["headRefOid"]),
        fetch_ref=f"refs/pull/{number}/head",
        forge_evidence=_github_evidence(payload),
    )


def _gitlab_evidence(executable: Path, repository: Path, payload: dict, deadline: float) -> ForgeEvidence:
    """Capture one bounded GitLab description and exact-head jobs snapshot."""
    description_state = "available" if "description" in payload else "unavailable"
    description = str(payload.get("description") or "")

    def unavailable(reason: str) -> ForgeEvidence:
        """Return unavailable pipeline evidence with the captured description."""
        return ForgeEvidence(description_state, description, "unavailable", (), reason)

    pipeline = payload.get("head_pipeline") or payload.get("pipeline")
    head = str(payload.get("diff_refs", {}).get("head_sha", ""))
    if not isinstance(pipeline, dict):
        return unavailable("No pipeline was reported.")
    if str(pipeline.get("sha", "")) != head:
        return unavailable("Pipeline SHA did not match the reviewed head.")
    project_id, pipeline_id = payload.get("project_id"), pipeline.get("id")
    if not project_id or not pipeline_id:
        return unavailable("Pipeline identity was incomplete.")
    try:
        result = run_probe(
            (str(executable), "api", f"projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=100"),
            cwd=repository,
            environment=clean_environment(),
            deadline=deadline,
        )
    except (OSError, ProbeTimeout):
        return unavailable("Pipeline jobs were unavailable.")
    if result.returncode:
        return unavailable("Pipeline jobs were unavailable.")
    try:
        jobs = json.loads(result.stdout)
        checks = tuple(
            ForgeCheck(
                name=str(job["name"]),
                status=str(job["status"]),
                required=not bool(job.get("allow_failure")),
                allow_failure=bool(job.get("allow_failure")),
                sha=head,
                url=str(job.get("web_url") or ""),
            )
            for job in jobs
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return unavailable("Pipeline jobs were malformed.")
    if not checks:
        return unavailable("No jobs were reported.")
    return ForgeEvidence(description_state, description, "available", checks)


def _github_evidence(payload: dict) -> ForgeEvidence:
    """Normalize GitHub's description and check rollup from the metadata read."""
    description_state = "available" if "body" in payload else "unavailable"
    description = str(payload.get("body") or "")
    rollup = payload.get("statusCheckRollup")
    if not isinstance(rollup, list):
        return ForgeEvidence(description_state, description, "unavailable", (), "Check rollup was unavailable.")
    head = str(payload.get("headRefOid") or "")
    checks = tuple(
        ForgeCheck(
            name=str(check.get("name") or check.get("context") or "check"),
            status=str(check.get("conclusion") or check.get("status") or "unknown").lower(),
            # GitHub's statusCheckRollup does not prove branch-protection requiredness. Keep
            # the check as review evidence, but never let it authorize the required-check-only
            # exemption from Git delta ownership.
            required=False,
            allow_failure=False,
            sha=head,
            url=str(check.get("detailsUrl") or ""),
        )
        for check in rollup
        if isinstance(check, dict)
    )
    if not checks:
        return ForgeEvidence(description_state, description, "unavailable", (), "No checks were reported.")
    return ForgeEvidence(description_state, description, "available", checks)


def _bounded_deadline(deadline_mono: float | None, limit_seconds: float) -> float:
    """Return the earlier operation or whole-run deadline, rejecting exhausted budgets."""
    now = time.monotonic()
    deadline = now + limit_seconds if deadline_mono is None else min(now + limit_seconds, deadline_mono)
    if deadline <= now:
        raise TimeoutError("The review deadline expired during scope preparation.")
    return deadline


def _remaining_timeout(deadline_mono: float | None, limit_seconds: float) -> float:
    """Return a positive subprocess timeout bounded by the whole-run deadline."""
    return _bounded_deadline(deadline_mono, limit_seconds) - time.monotonic()


def _fetch_review(
    repository: Path,
    target: ReviewTarget,
    *,
    deadline_mono: float | None = None,
) -> ReviewTarget:
    """Fetch and verify one exact remote review range within a deadline."""
    environment = clean_environment()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    fetch = run_git(
        repository,
        "fetch",
        "--no-tags",
        "origin",
        target.fetch_ref,
        check=False,
        environment=environment,
        timeout=_remaining_timeout(deadline_mono, 60.0),
    )
    if fetch.returncode:
        raise RuntimeError("Git could not fetch the exact review head from origin. Verify repository access.")
    fetched_head = run_git(repository, "rev-parse", "FETCH_HEAD").stdout.decode("utf-8").strip()
    if fetched_head != target.head:
        raise RuntimeError("The fetched review head does not match the forge metadata. Retry the review.")
    if run_git(repository, "cat-file", "-e", f"{target.base}^{{commit}}", check=False).returncode:
        base_fetch = run_git(
            repository,
            "fetch",
            "--no-tags",
            "origin",
            target.target_branch,
            check=False,
            environment=environment,
            timeout=_remaining_timeout(deadline_mono, 60.0),
        )
        if (
            base_fetch.returncode
            or run_git(repository, "cat-file", "-e", f"{target.base}^{{commit}}", check=False).returncode
        ):
            raise RuntimeError("Git could not resolve the exact review base from origin.")
    if target.kind == "github_pr":
        merge_base = run_git(repository, "merge-base", target.base, target.head, check=False)
        base = merge_base.stdout.decode("utf-8", errors="replace").strip()
        if merge_base.returncode or not base:
            raise RuntimeError("Git could not resolve the pull request merge base.")
        return replace(target, base=base)
    return target
