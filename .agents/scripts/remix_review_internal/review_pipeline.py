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

import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

from .assessment import (
    SCORE_CATEGORIES,
    AssessmentError,
    _overall_score,
    _score_value,
    materialize_feedback_adjudication,
    materialize_findings as materialize_grouped_findings,
    materialize_scorecard,
    validate_candidate_ownership,
    validate_feedback,
    validate_feedback_dispositions,
    validate_final_receipt,
)
from .artifacts import canonical_hash, file_hash, write_bytes, write_json, write_json_atomic
from .process_pool import ProbeTimeout, ProviderPool, WorkerCompletion, WorkerSpec, run_git, run_probe
from .progress_format import format_header, format_progress, format_stage_done, format_summary
from .review_scope import (
    ChangeEntry,
    ReviewTarget,
    RevisionSnapshot,
    add_detached_checkout,
    build_delta_index,
    build_change_manifest,
    count_changes,
    remove_review_checkout,
    resolve_review,
    resolve_revision_snapshot,
    verify_review_checkout,
)
from .rules import (
    ASSESSMENT_POLICY_HASH,
    RUBRIC_HASH,
    SCORE_FORMULA_VERSION,
    WORKLOAD_METRIC_VERSION,
    Rule,
    load_rule_registry,
    receipt_contract,
)
from .providers import (
    Provider,
    ProviderReadiness,
    ProviderSelection,
    ProviderSetupRequired,
    SetupIssue,
    WorkerRequest,
)


__all__ = ["PreparedReview", "doctor", "prepare_review", "progress", "review", "scope"]


REPO_ROOT = Path(__file__).resolve().parents[3]

# One worker can lose its Windows logon session, or exhaust handles, when many run together.
# Such a failure is an environment limit, so the run lowers its own concurrency and retries.
RESOURCE_MARKERS = (
    "logon session does not exist",
    "error 1312",
    "resource temporarily unavailable",
    "insufficient system resources",
    "too many open files",
    "cannot allocate memory",
    "not enough memory",
)

MAX_ATTEMPTS = 3

# Failure code recorded when the caller's wall-clock deadline ends a stage early.
DEADLINE_FAILURE_CODE = "DEADLINE_EXCEEDED"


class PlanRefusedError(ValueError):
    """Report a plan that cannot fit the caller's deadline. The run never started."""


# Three runs measured the deduplicated candidate volume per scoped file: MR 1352's real MR at
# ~3.3KB/file, the 130-file defect fixture at ~7.3KB/file (953,849 bytes over 130 files), and the
# 13-file defect fixture at ~25.1KB/file (326KB over 13 files). The constant drives only
# predictions — the verification and synthesis reserve slices and the deadline-refusal gate — so
# it takes the dense end: a reserve must cover the worst measured case, and over-reserving a
# sparse run only makes its conservative estimate cautious. At 3.3KB the 13-file fixture planned
# a 900s synthesis slice for a final pass that needed more than 15 minutes.
_MEASURED_CANDIDATE_BYTES_PER_FILE = 25000
_FIXED_PROMPT_BYTES = 20 * 1024
# A 317KB monolithic synthesis pass finished in 1110s, about 3.5s per prompt KB.
_MEASURED_SECONDS_PER_PROMPT_KB = 3.5

# The work in a file packet is roughly rules x files, so a packet's size is bounded by a unit
# budget rather than predicted in seconds: a per-unit wall-clock model was measured not to fit
# (the 50-packet medium calibration spanned 108-303s at identical work), so the budget bounds the
# prompt and the timeout, and the run measures the wall. The budget keeps a planned packet near
# 250 rule-file units so its prompt stays far from its timeout wall.
_PACKET_WORK_BUDGET = 250

# Verification candidates shard at this size so the advisory pass stays bounded.
_TAIL_SHARD_MAX_BYTES = 75 * 1024

# The host stays below known provider input limits instead of treating a provider-specific
# maximum as a portable guarantee. Oversized final input gets one lossless, one-to-one digest
# wave; if that representation still does not fit, the review fails closed.
_SYNTHESIS_PROMPT_MAX_BYTES = 768 * 1024
_SYNTHESIS_COMPACTION_TARGET_BYTES = 256 * 1024
_SYNTHESIS_CAPACITY_FAILURE_CODE = "SYNTHESIS_CAPACITY"

# The three packet lanes. After the mode cut there is one review shape, so the review packets run on
# the `review` lane, the falsification packets run on the `verification` lane, and the verdict packet
# runs on the `synthesis` lane. `primary` is the provider selection's lane, a different axis: it names
# which CLI account runs the workers, not a packet kind.
REVIEW_LANE = "review"
VERIFICATION_LANE = "verification"
SYNTHESIS_LANE = "synthesis"


@dataclass
class ReviewPacket:
    """Hold only state unique to one review packet."""

    packet_id: str
    lane: str
    phase: str
    path: str | None
    rules: tuple[Rule, ...]
    paths: tuple[str, ...] = field(default_factory=tuple)
    attempt: int = 0
    repairs: int = 0
    prior_error: str | None = None
    before_hashes: dict[str, str | None] = field(default_factory=dict)
    # A verification packet owns one shard of the deduplicated candidates. Empty otherwise.
    candidates: tuple[dict, ...] = ()
    # A feedback packet owns one shard of exact-source findings. Empty otherwise.
    feedback_findings: tuple[dict, ...] = ()


@dataclass(frozen=True)
class PacketFailure:
    """Describe one terminal packet failure."""

    packet_id: str
    lane: str
    error: str
    provider: str | None = None
    code: str | None = None
    needs_user_action: bool = False
    action: str | None = None


@dataclass(frozen=True)
class WorkerTiming:
    """Record timing and outcome for one worker process execution."""

    packet_id: str
    lane: str
    phase: str
    attempt: int
    rule_count: int
    file_count: int
    started_at: str
    duration_seconds: float
    returncode: int
    outcome: str
    prompt_bytes: int = 0
    prompt_characters: int = 0
    tokens: dict[str, int] = field(default_factory=dict)
    # The reasoning effort this worker actually ran with, resolved at the CLI boundary. Recorded
    # per worker so a reader can audit which effort produced which measurement, now that these
    # timings are the evidence for a wall-clock requirement.
    reasoning: str | None = None


@dataclass(frozen=True)
class PreparedReview:
    """Hold one validated comparison or feedback source before provider setup."""

    source_repository: Path
    target: ReviewTarget | None
    snapshot: RevisionSnapshot
    review_identity: str
    previous_result: dict
    previous_result_sha256: str
    feedback_evidence: tuple[dict, ...] = ()
    mode: str = "comparison"


@dataclass
class RunContext:
    """Hold one lightweight scripted review run."""

    run_dir: Path
    repository: Path
    invoking_context: Path
    base_ref: str
    head_ref: str
    base_sha: str
    head_sha: str
    head_tree_sha: str
    scope: dict
    forge_evidence: dict
    files: tuple[str, ...]
    changes: tuple[ChangeEntry, ...]
    file_artifacts: dict[str, str]
    file_hashes: dict[str, str | None]
    scope_patch: Path
    scope_artifacts: Path
    rules: list[Rule]
    rules_hash: str
    review_identity: str
    rubric_hash: str
    assessment_policy_hash: str
    instructions: str
    providers: dict[str, Provider]
    readiness: dict[str, ProviderReadiness]
    selections: tuple[ProviderSelection, ...]
    jobs: int | None
    evidence_gaps: tuple[str, ...]
    previous_result: dict | None = None
    previous_result_sha256: str | None = None
    feedback_evidence: tuple[dict, ...] = ()
    review_mode: str = "snapshot"
    score_basis: dict = field(default_factory=dict)
    delta_index: dict[str, dict[str, object]] = field(default_factory=dict)
    scorecard: dict | None = None
    result_sha256: str | None = None
    canary_artifact_path: Path | None = None
    canary_challenge: str | None = None
    canary_read_attested: bool = False
    status: str = "active"
    pools: dict[str, ProviderPool] = field(default_factory=dict)
    active: dict[str, ReviewPacket] = field(default_factory=dict)
    worker_starts: dict[str, tuple[str, float, int, int]] = field(default_factory=dict)
    worker_timings: list[WorkerTiming] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)
    failures: list[PacketFailure] = field(default_factory=list)
    expected_receipts: dict[str, int] = field(default_factory=dict)
    receipt_gaps: list[str] = field(default_factory=list)
    # One bounded record per rejected receipt attempt: which packet, which check failed, and
    # enough specifics to act on. A rejection discards the worker's output, so without this the
    # reason a retried packet burned a pass would survive nowhere — run one's final pass was
    # rejected twice and the only record was the exit code.
    rejection_records: list[dict] = field(default_factory=list)
    # Final cause-partition bookkeeping: how many groups the model returned, how many omitted
    # inputs the host restored as ordered singletons, and how many grounded drops it returned.
    final_ranking_report: dict = field(default_factory=dict)
    # Packet ids whose accepted receipt reported at least one gap. Their rules count as
    # evaluated, but the reader must know they were not fully verified.
    gap_packet_ids: set[str] = field(default_factory=set)
    last_progress_at: float = 0.0
    deadline_seconds: float | None = None
    deadline_mono: float | None = None
    synthesis_reserve_seconds: float = 0.0
    # The active drain stage's stop time. `_start_ready` uses it to refuse work that cannot
    # finish inside the remaining budget.
    stage_stop_at: float | None = None
    # The verification stage between deduplication and synthesis: an optional model override on the
    # same provider, the falsification packets, and the reconciled dispositions keyed by candidate
    # identity with their accounting counts, computed once.
    verify_model: str | None = None
    verification_packets: list[ReviewPacket] = field(default_factory=list)
    verification_merged: dict[str, dict] | None = None
    feedback_merged: dict[str, dict] | None = None
    verification_accounting: dict = field(default_factory=dict)
    synthesis_context_path: Path | None = None
    synthesis_context_sha256: str | None = None
    synthesis_context_counts: dict[str, int] = field(default_factory=dict)
    final_candidates: list[dict] | None = None
    host_merged_candidate_count: int = 0
    synthesis_digests: dict[str, dict] = field(default_factory=dict)
    # Packets a timeout split into smaller parts, by parent packet id. A split parent never
    # produces a receipt; coverage reporting reads the leaf packets instead.
    packet_splits: dict[str, list[ReviewPacket]] = field(default_factory=dict)
    # Streaming tail state. As review receipts arrive, their candidates merge incrementally
    # into `tail_candidates` (the deduplicated universe, built with the same rule the batch
    # merge uses, in the same receipt order). Candidates not yet dispatched to verification
    # wait in `tail_unverified`. `tail_sealed_ids` freezes a candidate once its verification shard
    # has left: a late duplicate of a sealed candidate drops only when it is a byte-identical copy,
    # and otherwise rides forward as its own candidate for the final merge to choose between the
    # pair. `tail_closed` is set when the review stage has ended and the mop-up builders drain
    # the buffers, which arms the strict accounting.
    tail_candidates: list[dict] = field(default_factory=list)
    tail_unverified: list[dict] = field(default_factory=list)
    tail_sealed_ids: set[str] = field(default_factory=set)
    tail_closed: bool = False
    # The unsharded final merge recomputes on every read; the provenance coverage check runs
    # once, when the tail is closed. The sharded path's check runs inside the reconciler.
    tail_provenance_checked: bool = False
    # Progress bookkeeping. `started_mono` is the run's monotonic clock start. `stage_starts`
    # records when each drain starts, by lane, for the stage-completion lines.
    started_mono: float = field(default_factory=time.monotonic)
    stage_starts: dict[str, float] = field(default_factory=dict)
    # The planned review packet identifiers, stored once when the plan is made. The progress
    # fraction counts against this frozen set: mutable context state can never move it.
    planned_review_packet_ids: tuple[str, ...] = ()


def doctor(
    selections: tuple[ProviderSelection, ...],
    readiness: dict[str, ProviderReadiness],
    providers: dict[str, Provider],
) -> dict:
    """Validate local runtime and selected providers."""
    rules, rules_hash = load_rule_registry(REPO_ROOT / ".agents" / "reviews" / "rules")
    probes = {name: _sandbox_probes(providers[name], readiness[name]) for name in sorted(readiness)}
    issues = [
        SetupIssue(
            name,
            (),
            f"SANDBOX_{kind.upper()}_PROBE_FAILED",
            _doctor_issue_message(name, kind, result[kind].evidence),
        )
        for name, result in probes.items()
        for kind in ("read", "write", "discovery")
        if not result[kind].passed
    ]
    if issues:
        raise ProviderSetupRequired(tuple(issues))
    return {
        "schema_version": 1,
        "status": "ready",
        "providers": {provider: list(value.command) for provider, value in sorted(readiness.items())},
        "capabilities": {provider: asdict(value.capabilities) for provider, value in sorted(readiness.items())},
        "accounts": {provider: value.account for provider, value in sorted(readiness.items())},
        "selections": [asdict(selection) for selection in selections],
        "python": list(sys.version_info[:3]),
        "rule_counts": {
            "file": sum(rule.target == "file" for rule in rules),
            "global": sum(rule.target == "global" for rule in rules),
        },
        "rules_hash": rules_hash,
        # The payload shows the evidence sentence for each probe, so a reader sees which proof
        # applied (structural or runtime). The gate above reads only the typed boolean.
        "probes": {name: {kind: result[kind].evidence for kind in result} for name, result in probes.items()},
    }


def _doctor_issue_message(provider: str, kind: str, result: str) -> str:
    """Build one precise, actionable setup-issue message for a failed doctor probe."""
    if provider == "cursor" and kind == "discovery":
        return (
            f"The cursor discovery probe failed: {result}. "
            "Cursor is present but not usable for a review until cursor-agent can place its "
            "generated `.cursor/cli.json` outside the working directory (for example through a "
            "supported configuration-path option). Use Codex or Claude Code instead."
        )
    return f"The {provider} {kind} probe failed: {result}"


@dataclass(frozen=True)
class ProbeResult:
    """Carry one doctor probe outcome as a typed value, not a magic string.

    The gate reads `passed`. The `doctor` payload shows `evidence`, which names the proof that
    applied (structural or runtime). A string check such as startswith("pass") would accept a
    value like "passive", so the boolean is the only contract the gate trusts.
    """

    passed: bool
    evidence: str


_PROBE_MARKER = "## Code Style"

# Phrases used to prove automatic project-context discovery. Each provider inlines a different
# entry file at startup: Claude Code loads CLAUDE.md and then the body of .agents/instructions.md
# (via the @-import); Codex loads only the body of AGENTS.md. There is no single file whose body
# both providers inline, so each provider gets a phrase drawn from the body of the file it does
# load. Each phrase is distinctive and not repeated in any prompt or rule text, so a worker
# without discovery cannot produce it by chance and cannot read the file (tools are disabled).
# Keep the phrases in this one named map so they are easy to update. If a phrase's source line is
# edited, the doctor discovery check fails loudly, which is the correct behavior for a gate:
# discovery of the *current* file content is what a review depends on.
_DISCOVERY_PHRASES = {
    # Claude inlines .agents/instructions.md; this is its second body line.
    "claude": "Lean always-on shared context",
    # Codex inlines AGENTS.md; this is its auto-use rule line.
    "codex": "Auto-use `completion-gates` before done",
}

# Codex permissions value that grants no filesystem read at all. Codex loads its project document
# at startup, as part of building its own context, and that is not a sandboxed tool call. So a
# worker with this grant still auto-loads AGENTS.md (the discovery phrase comes back), while any
# explicit file read fails. Verified experimentally: with this value a no-tool recall probe
# returned the AGENTS.md phrase, and a forced read attempt produced no read tool call. This makes
# the Codex discovery check structural, like Claude's, instead of a heuristic string scan.
_CODEX_NO_READ_PERMISSIONS = (
    'permissions={remix_reviewer={workspace_roots={},filesystem={":minimal"="none"},network={enabled=false}}}'
)


def _sandbox_probes(provider: Provider, readiness: ProviderReadiness) -> dict[str, ProbeResult]:
    """Prove one provider worker can read the workspace, cannot write to it, and discovers project context."""
    probe_dir = REPO_ROOT / "_build" / "remix-review" / "doctor-probes" / f"{provider.name}-{uuid.uuid4().hex[:8]}"
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        return {
            "read": _read_probe(provider, readiness, probe_dir),
            "write": _write_probe(provider, readiness, probe_dir),
            "discovery": _discovery_probe(provider, readiness, probe_dir),
        }
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def _run_probe_worker(provider: Provider, readiness: ProviderReadiness, probe_dir: Path, prompt: str) -> dict:
    """Run one provider worker probe and return its decoded output."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = probe_dir / "prompt.txt"
    stdout_path = probe_dir / "stdout.json"
    stderr_path = probe_dir / "stderr.log"
    schema_path = probe_dir / "schema.json"
    write_json(schema_path, receipt_contract("provider-canary")["json_schema"])
    prompt_path.write_text(prompt, encoding="utf-8")
    request = WorkerRequest(
        worker_id="probe",
        schema_path=schema_path,
        worker_cwd=probe_dir,
        project_root=REPO_ROOT,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        read_paths=_worker_read_paths(REPO_ROOT, prompt_path),
        selection=ProviderSelection("primary", provider.name, None, None),
    )
    provider.prepare_workspace(request)
    spec = provider.build_worker(readiness, request)
    result = run_probe(
        spec.argv,
        cwd=spec.cwd,
        environment=spec.environment,
        deadline=time.monotonic() + 240.0,
        stdin=prompt_path.read_bytes(),
    )
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    # Check the return code before trusting any output. A nonzero exit means the worker failed,
    # and any parseable-looking stdout must not be read as a pass.
    if result.returncode != 0:
        raise ValueError(f"worker exited with return code {result.returncode}")
    return provider.decode(stdout_path)


def _probe_prompt(action: str) -> str:
    """Build one minimal receipt-shaped probe instruction."""
    return (
        f"{action} Then return only one JSON receipt object. Set status to ok, packet_id, lane, and phase to probe, "
        "use empty arrays for candidates, findings, rule_ids, gaps, and dependencies_read, and use null for verdict "
        "and verdict_basis."
    )


def _read_probe(provider: Provider, readiness: ProviderReadiness, probe_dir: Path) -> ProbeResult:
    """Prove the worker can read one workspace rule document."""
    target = REPO_ROOT / ".agents" / "rules" / "code-style.md"
    prompt = _probe_prompt(f"Read the file {target} and set notes to the exact first line of that file.")
    try:
        receipt = _run_probe_worker(provider, readiness, probe_dir / "read", prompt)
    except (OSError, ValueError, ProbeTimeout) as error:
        return ProbeResult(False, f"read probe could not run: {error}")
    if _PROBE_MARKER in str(receipt.get("notes") or ""):
        return ProbeResult(True, "pass [runtime]: worker read a workspace document")
    return ProbeResult(False, f"worker did not report the first line of {target.name}")


def _write_probe(provider: Provider, readiness: ProviderReadiness, probe_dir: Path) -> ProbeResult:
    """Prove a worker cannot write to the workspace, structurally, for every provider.

    Each provider's review worker is read-only by construction, so the gate is the structural
    assertion and no model runs. The Codex runtime router-denial probe lives in the probe file as
    a developer check, not in readiness: it matches an English stderr marker that a CLI update can
    change, and a brittle string must never gate readiness. See `_write_capability_assertions`.
    """
    del probe_dir  # The structural gate needs no probe directory.
    return _write_capability_assertions(provider, readiness)


# Write-capable Claude tools that must never appear in a review worker's tool set.
_CLAUDE_WRITE_TOOLS = ("Write", "Edit", "NotebookEdit", "Bash")


def _flag_value(argv: tuple[str, ...], flag: str) -> str | None:
    """Return the value that follows one flag, or None when the flag or its value is absent."""
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    return argv[index + 1] if index + 1 < len(argv) else None


def _write_capability_assertions(provider: Provider, readiness: ProviderReadiness) -> ProbeResult:
    """Assert the worker spec makes a write impossible by construction. No model runs.

    Every provider's review worker is read-only by construction, so this structural proof is the
    write gate for all three providers. Claude: the `--tools` list has no write-capable tool.
    Codex: the named permission profile grants no write root or network. Cursor: the generated
    `.cursor/cli.json` denies `Write(**)` and `Shell(*)`. A malformed spec is a gate failure, never
    an exception: a missing flag or value returns a failed result with the reason.
    """
    probe_dir = (
        REPO_ROOT / "_build" / "remix-review" / "doctor-probes" / f"{provider.name}-struct-{uuid.uuid4().hex[:8]}"
    )
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        request = WorkerRequest(
            worker_id="probe",
            schema_path=probe_dir / "schema.json",
            worker_cwd=probe_dir,
            project_root=REPO_ROOT,
            prompt_path=probe_dir / "prompt.txt",
            stdout_path=probe_dir / "stdout.json",
            stderr_path=probe_dir / "stderr.log",
            read_paths=(),
            selection=ProviderSelection("primary", provider.name, None, None),
        )
        write_json(request.schema_path, receipt_contract("provider-canary")["json_schema"])
        if provider.name == "claude":
            spec = provider.build_worker(readiness, request)
            tools_value = _flag_value(spec.argv, "--tools")
            if tools_value is None:
                return ProbeResult(False, "worker spec has no --tools flag to inspect")
            allowed = set(tools_value.split(","))
            present = [tool for tool in _CLAUDE_WRITE_TOOLS if tool in allowed]
            if present:
                return ProbeResult(False, f"worker spec grants write-capable tools {present}")
            return ProbeResult(True, "pass [structural]: no write capability in the worker specification")
        if provider.name == "cursor":
            # Cursor's write denial lives in the generated .cursor/cli.json, not the argv.
            try:
                provider.prepare_workspace(request)
                deny = json.loads((request.worker_cwd / ".cursor" / "cli.json").read_text(encoding="utf-8"))[
                    "permissions"
                ]["deny"]
            except (OSError, ValueError, KeyError, TypeError) as error:
                return ProbeResult(False, f"cursor cli.json is missing or malformed: {error}")
            if not isinstance(deny, list) or "Write(**)" not in deny or "Shell(*)" not in deny:
                return ProbeResult(False, f"cursor deny list does not block Write(**) and Shell(*): {deny}")
            return ProbeResult(True, "pass [structural]: no write capability in the worker specification")
        if provider.name == "codex":
            spec = provider.build_worker(readiness, request)
            if "--sandbox" in spec.argv:
                return ProbeResult(False, "codex worker spec overrides the named permission profile")
            default_permissions = next(
                (
                    spec.argv[i + 1]
                    for i, token in enumerate(spec.argv)
                    if token == "-c" and i + 1 < len(spec.argv) and spec.argv[i + 1].startswith("default_permissions=")
                ),
                None,
            )
            if default_permissions != 'default_permissions="remix_reviewer"':
                return ProbeResult(False, "codex worker spec does not select the remix_reviewer permission profile")
            permissions = next(
                (
                    spec.argv[i + 1]
                    for i, token in enumerate(spec.argv)
                    if token == "-c" and i + 1 < len(spec.argv) and spec.argv[i + 1].startswith("permissions=")
                ),
                None,
            )
            if permissions is None:
                return ProbeResult(False, "worker spec has no permissions configuration to inspect")
            if '"write"' in permissions:
                return ProbeResult(False, "codex permissions grant a write root")
            if "network={enabled=false}" not in permissions:
                return ProbeResult(False, "codex permissions do not disable the network")
            return ProbeResult(True, "pass [structural]: no write capability in the worker specification")
        return ProbeResult(False, f"no write-capability assertion configured for provider {provider.name}")
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def _strip_cwd(argv: tuple[str, ...], provider: str) -> tuple[str, ...]:
    """Remove every grant that lets the worker read a file, so discovery is proven structurally.

    The discovery probe must make a file read impossible, not merely tell the worker to avoid
    tools. The read probe already proves file access works, so a discovery probe that leaves any
    read grant in place would let the worker read the source document and pass for the wrong
    reason. Claude: drop `--add-dir` and set `--tools` to empty (dropping `--tools` would restore
    the default tool set, including Write). Codex: replace the `-c permissions=...` value with a
    grant that reads nothing, because startup loads the project document itself and does not need
    a filesystem read root (verified experimentally).
    """
    result = []
    skip_next = False
    for token in argv:
        if skip_next:
            skip_next = False
            continue
        if token == "--add-dir":
            skip_next = True
            continue
        if token == "--tools":
            result.extend((token, ""))
            skip_next = True
            continue
        if provider == "codex" and token.startswith("permissions="):
            result.append(_CODEX_NO_READ_PERMISSIONS)
            continue
        result.append(token)
    return tuple(result)


# Per-provider discovery prompts. Each asks for a phrase from the body of the entry file that
# provider actually inlines, without naming the phrase. A worker that loaded the file can answer;
# a worker that did not, and that has no tool to read it, cannot.
_DISCOVERY_PROMPTS = {
    # Claude inlines .agents/instructions.md; ask for the words right after its title line.
    "claude": (
        "Answer from your loaded project context only, and do not use any tool. "
        "The file .agents/instructions.md opens with the title '# Agent Instructions - lightspeed-kit'. "
        "Set notes to the exact sentence that immediately follows that title, before the first '##' heading."
    ),
    # Codex inlines AGENTS.md; ask for the auto-use rule about the completion-gates skill.
    "codex": (
        "Answer from your loaded project context only, and do not use any tool. "
        "The file AGENTS.md has a rule that names the `completion-gates` skill and says when to auto-use it. "
        "Set notes to the exact clause that begins 'Auto-use `completion-gates`'."
    ),
}


def _discovery_probe(provider: Provider, readiness: ProviderReadiness, probe_dir: Path) -> ProbeResult:
    """Prove the worker auto-loads project context from the invoking workspace, without any tool."""
    if provider.name == "cursor":
        # Cursor cannot place its generated `.cursor/cli.json` outside its working directory.
        # Giving it the workspace root as cwd would let it write into the repository (which has a
        # real `.cursor/`), so Cursor workers keep an isolated artifact cwd and can never load the
        # workspace project context. Report this limit instead of running the probe.
        return ProbeResult(
            False,
            "Cursor cannot isolate its generated configuration from the working directory, "
            "so the workspace project context cannot load without risking a write into the repository",
        )
    phrase = _DISCOVERY_PHRASES.get(provider.name)
    prompt_text = _DISCOVERY_PROMPTS.get(provider.name)
    if phrase is None or prompt_text is None:
        return ProbeResult(False, f"no discovery phrase configured for provider {provider.name}")
    prompt = _probe_prompt(prompt_text)
    probe_dir = probe_dir / "discovery"
    probe_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = probe_dir / "prompt.txt"
    stdout_path = probe_dir / "stdout.json"
    stderr_path = probe_dir / "stderr.log"
    schema_path = probe_dir / "schema.json"
    write_json(schema_path, receipt_contract("provider-canary")["json_schema"])
    prompt_path.write_text(prompt, encoding="utf-8")
    # Build a request with no readable paths, then strip every filesystem read grant from the
    # argv (per provider). The worker keeps project-root cwd (so startup discovery still fires)
    # but cannot open any file at runtime.
    request = WorkerRequest(
        worker_id="probe",
        schema_path=schema_path,
        worker_cwd=probe_dir,
        project_root=REPO_ROOT,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        read_paths=(),
        selection=ProviderSelection("primary", provider.name, None, None),
    )
    provider.prepare_workspace(request)
    spec = provider.build_worker(readiness, request)
    spec = WorkerSpec(
        worker_id=spec.worker_id,
        argv=_strip_cwd(spec.argv, provider.name),
        cwd=spec.cwd,
        environment=spec.environment,
        prompt_path=spec.prompt_path,
        stdout_path=spec.stdout_path,
        stderr_path=spec.stderr_path,
    )
    try:
        result = run_probe(
            spec.argv,
            cwd=spec.cwd,
            environment=spec.environment,
            deadline=time.monotonic() + 240.0,
            stdin=prompt_path.read_bytes(),
        )
        stdout_path.write_bytes(result.stdout)
        stderr_path.write_bytes(result.stderr)
        # Check the return code before trusting any output.
        if result.returncode != 0:
            return ProbeResult(False, f"worker exited with return code {result.returncode}")
        receipt = provider.decode(stdout_path)
    except (OSError, ValueError, ProbeTimeout) as error:
        return ProbeResult(False, f"discovery probe could not run: {error}")
    # Both providers run with file reads structurally disabled: Claude via --tools "" plus no
    # --add-dir, Codex via the no-read permissions grant. A correct answer is therefore reachable
    # only from project context the CLI auto-loaded from the working directory.
    if phrase in str(receipt.get("notes") or ""):
        return ProbeResult(True, "pass [structural]: project context loaded with file reads disabled")
    return ProbeResult(False, "worker did not auto-load project context from the invoking workspace")


def _early_progress(run_dir: Path, phase: str) -> None:
    """Write a heartbeat while the run prepares its scope, before any context exists.

    The drain loop heartbeats on the `_progress` cadence once packets run, but scope resolution,
    the detached checkout, the diff, and the registry load all happen first. Without these writes
    the manifest is silent while the process lives, and a slow forge would let `progress`
    mislabel a healthy run as stale.
    """
    write_json_atomic(
        run_dir / "progress.json",
        {
            "schema_version": 1,
            "run_id": run_dir.name,
            "status": "starting",
            "phase": phase,
            "updated_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Packman Python 3.10
            "completed": 0,
            "expected": 0,
            "remaining": 0,
            "active": 0,
            "lanes": {},
        },
    )
    print(f"[remix-review] {phase}", file=sys.stderr, flush=True)


_REVIEW_RUN_ID = re.compile(r"review-[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_GIT_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_FEEDBACK_BYTES = 64 * 1024


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    """Build one JSON object while rejecting duplicate keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Feedback JSON repeats duplicate field {key!r}.")
        result[key] = value
    return result


def _load_feedback(path: Path, previous_result: dict, previous_result_sha256: str) -> tuple[dict, ...]:
    """Load bounded feedback bound to findings in one exact source result."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(_FEEDBACK_BYTES + 1)
    except OSError as error:
        raise ValueError(f"Feedback file {path} could not be read.") from error
    if len(raw) > _FEEDBACK_BYTES:
        raise ValueError("Feedback file exceeds 64 KiB.")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Feedback file must contain valid UTF-8.") from error
    try:
        envelope = json.loads(text, object_pairs_hook=_strict_json_object)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Feedback file must contain valid JSON.") from error
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema_version",
        "previous_run_id",
        "previous_result_sha256",
        "responses",
    }:
        raise ValueError("Feedback envelope fields are not exact.")
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise ValueError("Feedback schema_version must be 1.")
    if envelope["previous_run_id"] != previous_result.get("run_id"):
        raise ValueError("Feedback previous_run_id does not match the source result.")
    if envelope["previous_result_sha256"] != previous_result_sha256:
        raise ValueError("Feedback previous_result_sha256 does not match the source result.")
    try:
        responses = validate_feedback(envelope["responses"])
    except AssessmentError as error:
        raise ValueError(f"Feedback responses are invalid: {error}") from error
    if not responses:
        raise ValueError("Feedback must contain at least one response.")
    public_findings = previous_result.get("findings")
    if not isinstance(public_findings, list):
        raise ValueError("Previous review findings cannot bind feedback.")
    public_finding_ids = [
        finding.get("finding_id")
        for finding in public_findings
        if isinstance(finding, dict) and isinstance(finding.get("finding_id"), str)
    ]
    if len(public_finding_ids) != len(public_findings) or len(set(public_finding_ids)) != len(public_finding_ids):
        raise ValueError("Previous review findings cannot bind feedback.")
    public_finding_ids = set(public_finding_ids)
    evidence = []
    for response in responses:
        if response["finding_id"] not in public_finding_ids:
            raise ValueError("Feedback responses must reference findings in the source result.")
        evidence.append(response)
    return tuple(evidence)


def _forge_evidence_sha256(evidence: dict) -> str:
    """Hash forge evidence with order-insensitive check records."""
    if not isinstance(evidence, dict):
        raise ValueError("Forge evidence must be an object.")
    normalized = copy.deepcopy(evidence)
    checks = normalized.get("checks")
    if not isinstance(checks, (list, tuple)):
        raise ValueError("Forge evidence checks must be an array.")
    normalized["checks"] = sorted(
        checks,
        key=lambda check: json.dumps(check, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )
    return canonical_hash(normalized)


def prepare_review(arguments, *, deadline_mono: float | None = None) -> PreparedReview:
    """Validate one comparison or feedback source before provider setup."""
    if deadline_mono is not None and time.monotonic() >= deadline_mono:
        raise TimeoutError("The review deadline expired during previous-result preparation.")
    source_repository = _git_root()
    previous_result, result_sha256 = _load_previous_result(source_repository, arguments.previous_run)
    target = (
        resolve_review(source_repository, arguments.review, deadline_mono=deadline_mono) if arguments.review else None
    )
    review_identity = _review_identity(source_repository, target)
    if previous_result["review_identity"] != review_identity:
        raise ValueError("Previous review identity does not match the current review target.")

    feedback_path = getattr(arguments, "feedback", None)
    if feedback_path is not None:
        _, current_rules_hash = load_rule_registry(REPO_ROOT / ".agents" / "reviews" / "rules")
        if (
            previous_result["validation_level"] != "default"
            or previous_result["rules_hash"] != current_rules_hash
            or previous_result["rubric_hash"] != RUBRIC_HASH
            or previous_result["assessment_policy_hash"] != ASSESSMENT_POLICY_HASH
        ):
            raise ValueError("Feedback requires the exact source assessment contract.")
        base_ref = previous_result["head"]["base_sha"]
        head_ref = target.head if target is not None else arguments.head
    else:
        base_ref, head_ref = (
            (target.base, target.head)
            if target is not None
            else (arguments.base or _default_base(source_repository), arguments.head)
        )
    snapshot = resolve_revision_snapshot(source_repository, base_ref, head_ref)

    feedback_evidence = ()
    if feedback_path is not None:
        prior_head = previous_result["head"]
        if snapshot.head_sha != prior_head["head_sha"] or snapshot.head_tree_sha != prior_head["head_tree_sha"]:
            raise ValueError("Feedback review requires the exact source head and tree.")
        feedback_evidence = _load_feedback(feedback_path, previous_result, result_sha256)
        if (
            not isinstance(previous_result.get("scope"), dict)
            or not isinstance(previous_result.get("rules"), dict)
            or not isinstance(previous_result.get("gaps"), list)
            or any(not isinstance(gap, str) for gap in previous_result["gaps"])
        ):
            raise ValueError("Feedback source result is missing retained review evidence.")
        selected_ids = [record["finding_id"] for record in feedback_evidence]
        try:
            materialize_feedback_adjudication(
                f"{previous_result['run_id']}-validation",
                previous_result,
                result_sha256,
                feedback_evidence,
                {
                    finding_id: {
                        "finding_id": finding_id,
                        "disposition": "cannot_verify",
                        "basis": "Preparation validates the source without deciding the submitted response.",
                        "evidence": [],
                    }
                    for finding_id in selected_ids
                },
                reviewed_locations=set(),
            )
        except AssessmentError as error:
            raise ValueError(f"Feedback source result is invalid: {error}") from error
        prior_forge_hash = previous_result.get("forge_evidence_sha256")
        current_forge_evidence = (
            asdict(target.forge_evidence)
            if target is not None
            else {"description_state": "not_applicable", "checks_state": "not_applicable", "checks": []}
        )
        if (
            not isinstance(prior_forge_hash, str)
            or _HEX_DIGEST.fullmatch(prior_forge_hash) is None
            or prior_forge_hash != _forge_evidence_sha256(current_forge_evidence)
        ):
            raise ValueError(
                "Feedback requires matching retained forge evidence; run a separately authorized full review instead."
            )
    retained_previous = previous_result
    if feedback_path is None:
        scorecard = previous_result["scorecard"]
        retained_previous = {
            "run_id": previous_result["run_id"],
            "review_identity": previous_result["review_identity"],
            "validation_level": previous_result["validation_level"],
            "rules_hash": previous_result["rules_hash"],
            "rubric_hash": previous_result["rubric_hash"],
            "assessment_policy_hash": previous_result["assessment_policy_hash"],
            "head": {
                "base_sha": previous_result["head"]["base_sha"],
                "head_sha": previous_result["head"]["head_sha"],
            },
            "scorecard": {
                "basis": {"point_pool": scorecard["basis"]["point_pool"]},
                "categories": {
                    name: {
                        "score": scorecard["categories"][name]["score"],
                        "penalty_points": scorecard["categories"][name]["penalty_points"],
                    }
                    for name in SCORE_CATEGORIES
                },
                "overall_branch": scorecard["overall_branch"],
            },
        }
    return PreparedReview(
        source_repository=source_repository,
        target=target,
        snapshot=snapshot,
        review_identity=review_identity,
        previous_result=retained_previous,
        previous_result_sha256=result_sha256,
        feedback_evidence=feedback_evidence,
        mode="feedback" if feedback_path is not None else "comparison",
    )


def _review_identity(repository: Path, target: ReviewTarget | None) -> str:
    """Return the opaque identity for one remote review or local workspace."""
    if target is not None:
        return canonical_hash([target.kind, target.url])
    origin = run_git(repository, "remote", "get-url", "origin", check=False)
    if not origin.returncode:
        url = origin.stdout.decode("utf-8", errors="strict").strip()
        if url:
            return canonical_hash(["workspace", url])
    common = run_git(repository, "rev-parse", "--git-common-dir", check=False)
    if common.returncode:
        raise RuntimeError("Git could not resolve the workspace common directory.")
    value = common.stdout.decode("utf-8", errors="strict").strip()
    common_directory = Path(value)
    if not common_directory.is_absolute():
        common_directory = repository / common_directory
    return canonical_hash(["workspace", str(common_directory.resolve())])


def _load_previous_result(repository: Path, run_id: str) -> tuple[dict, str]:
    """Read one contained schema-3 snapshot and validate its exact terminal hash."""
    if not isinstance(run_id, str) or _REVIEW_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("--previous-run must be a bare review run ID")
    seed_root = repository / "_build" / "remix-review"
    try:
        contained_root = seed_root.resolve(strict=True)
        run_dir = (seed_root / run_id).resolve(strict=True)
    except OSError as error:
        raise RuntimeError(f"Previous review run {run_id!r} is missing.") from error
    try:
        contained_root.relative_to(repository.resolve())
        run_dir.relative_to(contained_root)
    except ValueError as error:
        raise ValueError("Previous review run path escapes _build/remix-review.") from error
    if not run_dir.is_dir():
        raise RuntimeError(f"Previous review run {run_id!r} is not a directory.")
    paths = {}
    for name in ("run.json", "result.json"):
        try:
            path = (run_dir / name).resolve(strict=True)
            path.relative_to(run_dir)
        except OSError as error:
            raise RuntimeError(f"Previous review run is missing {name}.") from error
        except ValueError as error:
            raise ValueError(f"Previous review {name} escapes its run directory.") from error
        if not path.is_file():
            raise RuntimeError(f"Previous review run is missing {name}.")
        paths[name] = path
    try:
        run_manifest = json.loads(paths["run.json"].read_bytes())
        result_bytes = paths["result.json"].read_bytes()
        result = json.loads(result_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Previous review artifacts do not contain valid JSON.") from error
    result_sha256 = hashlib.sha256(result_bytes).hexdigest()
    _validate_previous_result(run_id, run_manifest, result, result_sha256)
    return result, result_sha256


def _validate_previous_result(
    run_id: str,
    run_manifest: object,
    result: object,
    result_sha256: str,
) -> None:
    """Validate the bounded snapshot fields used by comparison and feedback."""
    if not isinstance(run_manifest, dict) or not isinstance(result, dict):
        raise ValueError("Previous review run and result must be JSON objects.")
    if run_manifest.get("schema_version") != 3 or result.get("schema_version") != 3:
        raise ValueError("Previous review artifacts must use snapshot schema version 3.")
    if run_manifest.get("workflow") != "remix-review" or result.get("workflow") != "remix-review":
        raise ValueError("Previous review artifacts must use the remix-review workflow.")
    validation_level = result.get("validation_level")
    if (
        not isinstance(validation_level, str)
        or not validation_level
        or run_manifest.get("validation_level") != validation_level
    ):
        raise ValueError("Previous review validation level is missing or inconsistent.")
    if run_manifest.get("status") != "complete" or result.get("status") != "complete":
        raise ValueError("Previous review artifacts must both be complete.")
    if run_manifest.get("run_id") != run_id or result.get("run_id") != run_id:
        raise ValueError("Previous review run ID does not match the requested run.")
    review_identity = result.get("review_identity")
    if (
        not isinstance(review_identity, str)
        or _HEX_DIGEST.fullmatch(review_identity) is None
        or run_manifest.get("review_identity") != review_identity
    ):
        raise ValueError("Previous review identity is missing or inconsistent.")
    for name in ("assessment_policy_hash", "rules_hash", "rubric_hash"):
        value = result.get(name)
        if not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None:
            raise ValueError("Previous review policy hashes are missing or invalid.")
    head = result.get("head")
    if not isinstance(head, dict) or any(
        not isinstance(head.get(name), str) or _GIT_OBJECT_ID.fullmatch(head[name]) is None
        for name in ("base_sha", "head_sha", "head_tree_sha")
    ):
        raise ValueError("Previous review head object IDs are missing or invalid.")
    _validate_snapshot_scorecard(result.get("scorecard"))
    findings = result.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Previous review findings are missing or invalid.")
    finding_ids = [
        finding.get("finding_id")
        for finding in findings
        if isinstance(finding, dict) and isinstance(finding.get("finding_id"), str)
    ]
    if (
        len(finding_ids) != len(findings)
        or len(set(finding_ids)) != len(finding_ids)
        or any(re.fullmatch(r"F-(\d{4,})", finding_id) is None for finding_id in finding_ids)
    ):
        raise ValueError("Previous review finding IDs are missing or invalid.")
    adjudication = result.get("adjudication")
    if adjudication is not None:
        source_hash = adjudication.get("source_result_sha256") if isinstance(adjudication, dict) else None
        selected = adjudication.get("finding_ids") if isinstance(adjudication, dict) else None
        if (
            not isinstance(adjudication, dict)
            or set(adjudication) != {"source_run_id", "source_result_sha256", "finding_ids"}
            or not isinstance(adjudication.get("source_run_id"), str)
            or _REVIEW_RUN_ID.fullmatch(adjudication["source_run_id"]) is None
            or not isinstance(source_hash, str)
            or _HEX_DIGEST.fullmatch(source_hash) is None
            or not isinstance(selected, list)
            or not selected
            or any(
                not isinstance(finding_id, str) or re.fullmatch(r"F-(\d{4,})", finding_id) is None
                for finding_id in selected
            )
            or selected != sorted(set(selected), key=lambda finding_id: int(finding_id[2:]))
        ):
            raise ValueError("Previous review adjudication is invalid.")
    try:
        validate_feedback(result.get("feedback", []))
    except AssessmentError as error:
        raise ValueError(f"Previous review feedback is invalid: {error}") from error
    forge_hash = result.get("forge_evidence_sha256")
    if forge_hash is not None and (not isinstance(forge_hash, str) or _HEX_DIGEST.fullmatch(forge_hash) is None):
        raise ValueError("Previous review forge evidence hash is invalid.")
    stored_hash = run_manifest.get("result_sha256")
    if not isinstance(stored_hash, str) or _HEX_DIGEST.fullmatch(stored_hash) is None:
        raise ValueError("Previous review terminal result hash is empty or invalid.")
    if stored_hash != result_sha256:
        raise ValueError("Previous review result hash does not match its exact bytes.")


def _validate_snapshot_scorecard(scorecard: object) -> None:
    """Validate the current-score subset consumed by comparison and feedback."""
    if not isinstance(scorecard, dict):
        raise ValueError("Previous review scorecard is missing or invalid.")
    basis = scorecard.get("basis")
    if not isinstance(basis, dict) or set(basis) != {"formula", "point_pool", "workload"}:
        raise ValueError("Previous review score basis is missing or invalid.")
    point_pool = basis.get("point_pool")
    workload = basis.get("workload")
    if (
        basis.get("formula") != SCORE_FORMULA_VERSION
        or type(point_pool) is not int
        or point_pool < 1
        or not isinstance(workload, dict)
        or set(workload) != {"metric", "units", "sha256"}
        or workload.get("metric") != WORKLOAD_METRIC_VERSION
        or type(workload.get("units")) is not int
        or workload["units"] < 0
        or not isinstance(workload.get("sha256"), str)
        or _HEX_DIGEST.fullmatch(workload["sha256"]) is None
        or point_pool != max(5, workload["units"].bit_length())
    ):
        raise ValueError("Previous review workload basis is invalid.")
    categories = scorecard.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(SCORE_CATEGORIES):
        raise ValueError("Previous review scorecard categories are invalid.")
    scores = []
    penalties = {}
    expected_category_fields = {
        "score",
        "penalty_points",
        "finding_ids",
        "candidate_ids",
        "rule_ids",
        "locations",
        "rationale",
    }
    for name, category in categories.items():
        if (
            not isinstance(category, dict)
            or set(category) != expected_category_fields
            or type(category.get("score")) not in (int, float)
            or not math.isfinite(category["score"])
            or not 0 <= category["score"] <= 10
            or type(category.get("penalty_points")) is not int
            or category["penalty_points"] < 0
            or any(
                not isinstance(category.get(name), list)
                for name in ("finding_ids", "candidate_ids", "rule_ids", "locations")
            )
            or not isinstance(category.get("rationale"), str)
        ):
            raise ValueError("Previous review score category is invalid.")
        if category["score"] != _score_value(point_pool, category["penalty_points"]):
            raise ValueError("Previous review score category is not reproducible.")
        scores.append(category["score"])
        penalties[name] = category["penalty_points"]
    overall = scorecard.get("overall_branch")
    if (
        type(overall) not in (int, float)
        or not math.isfinite(overall)
        or not 0 <= overall <= 10
        or overall != _overall_score(point_pool, penalties)
    ):
        raise ValueError("Previous review overall score is invalid.")


def review(
    arguments,
    selections: tuple[ProviderSelection, ...],
    readiness: dict[str, ProviderReadiness],
    providers: dict[str, Provider],
    prepared: PreparedReview | None = None,
    *,
    started_mono: float | None = None,
    deadline_mono: float | None = None,
) -> dict:
    """Run one scripted review synchronously."""
    started_mono = time.monotonic() if started_mono is None else started_mono
    if deadline_mono is None and arguments.deadline_seconds is not None:
        deadline_mono = started_mono + arguments.deadline_seconds
    if deadline_mono is not None and time.monotonic() >= deadline_mono:
        raise TimeoutError("The review deadline expired during preparation.")
    if arguments.previous_run is not None and prepared is None:
        raise ValueError("A previous-run review must be prepared before provider setup.")
    if prepared is not None:
        source_repository = prepared.source_repository
        target = prepared.target
        snapshot = prepared.snapshot
        review_identity = prepared.review_identity
    else:
        source_repository = _git_root()
        target, snapshot = _resolve_scope(source_repository, arguments, deadline_mono=deadline_mono)
        review_identity = _review_identity(source_repository, target)
    print(f"[remix-review] scope {_scope_line(target, snapshot)}", file=sys.stderr, flush=True)
    run_id = f"review-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"  # noqa: UP017
    run_dir = source_repository / "_build" / "remix-review" / run_id
    accounts = " ".join(
        f"{name}:{readiness[name].account.get('organization') or readiness[name].account.get('auth_method') or 'unknown'}"
        for name in sorted(providers)
    )
    print(
        f"[remix-review] disclosure providers={','.join(sorted(providers))} "
        "read_scope=detached exact-head review checkout, complete change manifest, and patch "
        f"web_search=general-knowledge queries may leave the host "
        f"retained={run_dir / 'result.json'} accounts={accounts}",
        file=sys.stderr,
        flush=True,
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    # The first heartbeat lands before the checkout: prep measured ~5s for the 95-file MR 1352
    # run on this host, but a slow forge must never leave the manifest silent.
    _early_progress(run_dir, "preparing the review scope")
    root = REPO_ROOT
    external_run_root = None
    checkout = None
    checkout_attempted = False
    context = None
    result = None
    plan_refused = False
    try:
        external_run_root = _create_external_run_root(root)
        checkout = external_run_root / "review-root"
        checkout_attempted = True
        repository = add_detached_checkout(source_repository, snapshot.head_sha, checkout)
        _early_progress(run_dir, "checkout ready; computing the scope diff")
        rules, rules_hash = load_rule_registry(root / ".agents" / "reviews" / "rules")
        invoking_context = _stage_invoking_context(root, external_run_root / "project", rules)
        run_git(invoking_context, "init", "--quiet")
        patch = run_git(
            repository,
            "diff",
            "--binary",
            "--full-index",
            "--find-renames",
            "--find-copies",
            "--find-copies-harder",
            snapshot.base_sha,
            snapshot.head_sha,
            "--",
        ).stdout
        scope_artifacts_root = run_dir / "scope-artifacts"
        scope_artifacts = scope_artifacts_root / "current"
        scope_patch = scope_artifacts / "scope.patch"
        write_bytes(scope_patch, patch)
        _early_progress(run_dir, "scope patch written; loading rules and hashing files")
        changes = build_change_manifest(source_repository, snapshot, repository, scope_artifacts)
        delta_index = build_delta_index(repository, snapshot.base_sha, snapshot.head_sha)
        files = tuple(_change_path(change) for change in changes)
        file_artifacts = {_change_path(change): change.artifact_path for change in changes}
        file_hashes = _hashes(repository, files, file_artifacts)
        scope = (
            asdict(target)
            if target
            else {"kind": "workspace", "review": arguments.review, "base": snapshot.base_sha, "head": snapshot.head_sha}
        )
        scope.pop("fetch_ref", None)
        forge_evidence = scope.pop(
            "forge_evidence",
            {"description_state": "not_applicable", "checks_state": "not_applicable", "checks": []},
        )
        scope.update(
            {
                "base": snapshot.base_sha,
                "head": snapshot.head_sha,
                "base_ref": snapshot.base_ref,
                "head_ref": snapshot.head_ref,
                "base_sha": snapshot.base_sha,
                "head_sha": snapshot.head_sha,
                "head_tree_sha": snapshot.head_tree_sha,
                "changes": [
                    {key: value for key, value in asdict(change).items() if key != "artifact_path"}
                    for change in changes
                ],
            }
        )
        context = RunContext(
            run_dir=run_dir,
            repository=repository,
            invoking_context=invoking_context,
            base_ref=snapshot.base_ref,
            head_ref=snapshot.head_ref,
            base_sha=snapshot.base_sha,
            head_sha=snapshot.head_sha,
            head_tree_sha=snapshot.head_tree_sha,
            scope=scope,
            forge_evidence=forge_evidence,
            files=files,
            changes=changes,
            delta_index=delta_index,
            file_artifacts=file_artifacts,
            file_hashes=file_hashes,
            scope_patch=scope_patch,
            scope_artifacts=scope_artifacts,
            rules=rules,
            rules_hash=rules_hash,
            review_identity=review_identity,
            rubric_hash=RUBRIC_HASH,
            assessment_policy_hash=ASSESSMENT_POLICY_HASH,
            instructions=(root / ".agents" / "reviews" / "packet-worker.md").read_text(encoding="utf-8"),
            providers=providers,
            readiness=readiness,
            selections=selections,
            jobs=arguments.jobs,
            # Older callers build the namespace by hand, so tolerate its absence.
            verify_model=getattr(arguments, "verify_model", None),
            deadline_seconds=arguments.deadline_seconds,
            deadline_mono=deadline_mono,
            started_mono=started_mono,
            evidence_gaps=_evidence_gaps(forge_evidence),
            previous_result=prepared.previous_result if prepared is not None else None,
            previous_result_sha256=prepared.previous_result_sha256 if prepared is not None else None,
            feedback_evidence=prepared.feedback_evidence if prepared is not None else (),
            review_mode=prepared.mode if prepared is not None else "snapshot",
        )
        context.score_basis = _score_basis(context)
        _save_run(context)
        try:
            result = _run(context)
        except PlanRefusedError:
            # Remove the run only after Git unregisters its private worktree in `finally` below.
            # Deleting the directory first leaves stale worktree administration behind.
            plan_refused = True
            raise
    finally:
        active_error = sys.exc_info()[1]
        cleanup_errors = []
        checkout_cleanup_failed = False
        if checkout_attempted and checkout is not None:
            try:
                remove_review_checkout(source_repository, checkout)
            except RuntimeError as error:
                checkout_cleanup_failed = True
                cleanup_errors.append(f"Could not unregister the private review checkout at {checkout}: {error}")
        if external_run_root is not None and not checkout_cleanup_failed:
            try:
                shutil.rmtree(external_run_root)
            except OSError as error:
                cleanup_errors.append(
                    f"Could not remove the temporary review workspace at {external_run_root}: {error.strerror or error}"
                )
        if cleanup_errors and result is not None and context is not None:
            # A retained registered worktree is a material cleanup failure. Amend the already
            # written result in place so the foreground caller cannot mistake it for a complete,
            # publishable review.
            result["status"] = "incomplete"
            result["verdict"] = None
            result["findings"] = []
            result["scorecard"] = None
            if "adjudication" in result:
                result.pop("feedback", None)
            result.setdefault("gaps", []).extend(f"Cleanup failed: {error}" for error in cleanup_errors)
            context.status = "incomplete"
            _persist_terminal_result(context, result)
        elif cleanup_errors:
            cleanup_summary = "; ".join(cleanup_errors)
            if active_error is not None:
                raise RuntimeError(f"Review setup failed and cleanup also failed: {cleanup_summary}") from active_error
            raise RuntimeError(cleanup_summary)
        if plan_refused and not cleanup_errors:
            # A refused plan never started, so its directory holds only a false active manifest
            # and regenerable scope artifacts. Do not leave a zombie for `progress` to report.
            shutil.rmtree(run_dir, ignore_errors=True)
    return result


def scope(arguments) -> dict:
    """Resolve the exact review range and count its changes, without starting a review.

    The plan step of the skill calls this, so the plan and the run share one scope implementation:
    the same forge target, the same immutable snapshot, and the same diff flags as the manifest.
    """
    source_repository = _git_root()
    target, snapshot = _resolve_scope(source_repository, arguments)
    result = (
        asdict(target)
        if target
        else {"kind": "workspace", "review": arguments.review, "base": snapshot.base_sha, "head": snapshot.head_sha}
    )
    result.pop("fetch_ref", None)
    result.pop("forge_evidence", None)
    result.update(
        {
            "schema_version": 1,
            "base_ref": snapshot.base_ref,
            "head_ref": snapshot.head_ref,
            "changed_files": count_changes(source_repository, snapshot),
            "scope_line": _scope_line(target, snapshot),
        }
    )
    return result


def _resolve_scope(
    source_repository: Path, arguments, *, deadline_mono: float | None = None
) -> tuple[ReviewTarget | None, RevisionSnapshot]:
    """Resolve one named review or one local range to its immutable snapshot."""
    target = (
        resolve_review(source_repository, arguments.review, deadline_mono=deadline_mono) if arguments.review else None
    )
    base_ref, head_ref = (
        (target.base, target.head) if target else (arguments.base or _default_base(source_repository), arguments.head)
    )
    return target, resolve_revision_snapshot(source_repository, base_ref, head_ref)


def _scope_line(target: ReviewTarget | None, snapshot: RevisionSnapshot) -> str:
    """Name the exact scope in one line: the MR branch and commits, or the local range."""
    if target:
        return (
            f"{'merge request' if target.kind == 'gitlab_mr' else 'pull request'} {target.number}: "
            f"{target.source_branch} at {target.head[:12]} "
            f"against {target.target_branch} at {target.base[:12]}"
        )
    return (
        f"local range {snapshot.base_ref}..{snapshot.head_ref} "
        f"({snapshot.base_sha[:12]}..{snapshot.head_sha[:12]}), not a merge request"
    )


def progress(run_id: str | None, review_label: str | None) -> dict:
    """Read the latest matching progress snapshot without touching a review run."""
    root = _git_root() / "_build" / "remix-review"
    if run_id is not None:
        if not run_id.startswith("review-") or any(separator in run_id for separator in ("/", "\\")):
            raise ValueError("--run must be a run ID")
        candidates = [root / run_id]
    else:
        candidates = sorted(root.glob("review-*"), reverse=True) if root.is_dir() else []
    for run_dir in candidates:
        run_path = run_dir / "run.json"
        if not run_path.is_file():
            continue
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if review_label is not None and run.get("scope", {}).get("review") != review_label:
            continue
        progress_path = run_dir / "progress.json"
        if progress_path.is_file():
            snapshot = json.loads(progress_path.read_text(encoding="utf-8"))
            return _mark_stale(snapshot, progress_path)
        snapshot = {
            "schema_version": 1,
            "run_id": run["run_id"],
            "status": "starting",
            "phase": "initializing review packets",
            "lanes": {
                selection["lane"]: {
                    "provider": selection["provider"],
                    "status": "queued",
                    "completed": 0,
                    "expected": None,
                    "active": 0,
                }
                for selection in run.get("selections", [])
            },
        }
        return _mark_stale(snapshot, run_path)
    raise RuntimeError("No matching remix-review progress snapshot was found.")


# A live run rewrites its heartbeat at least every 15 seconds: the drain loop calls `_progress`
# continuously while any worker runs, `_progress` throttles its writes to that cadence, stage
# transitions force a write, and `_early_progress` covers the prep milestones. Four missed
# cadences (60 seconds) can only mean the process is gone. The worker-timeout ceiling is far
# larger and says nothing about liveness, so the measured write cadence is the basis, not a guess.
_HEARTBEAT_MAX_SECONDS = 60.0


def _mark_stale(snapshot: dict, heartbeat_path: Path) -> dict:
    """Mark a heartbeat-dead run as stale: a derived status, not a recorded one.

    Heartbeat age proves silence, and nothing more. `interrupted` stays the pipeline's own
    recorded status for the keyboard interrupt it caught itself. A derived status carries
    `status_basis: heartbeat` so a reader can tell it from a recorded one, and `last_alive_at`
    says when the run last proved itself alive. Never present the run as running, and never
    claim to know why it stopped.
    """
    if snapshot.get("status") not in {"active", "starting"}:
        return snapshot
    heartbeat_mtime = heartbeat_path.stat().st_mtime
    if time.time() - heartbeat_mtime <= _HEARTBEAT_MAX_SECONDS:
        return snapshot
    last_alive_at = snapshot.get("updated_at") or (
        datetime.fromtimestamp(heartbeat_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017
    )
    snapshot["status"] = "stale"
    snapshot["status_basis"] = "heartbeat"
    snapshot["phase"] = f"stale; last heartbeat {last_alive_at}"
    snapshot["last_alive_at"] = last_alive_at
    for lane in snapshot.get("lanes", {}).values():
        if lane.get("status") in {"queued", "running"}:
            lane["status"] = "stale"
    return snapshot


def _run(context: RunContext) -> dict:
    if context.review_mode == "feedback":
        return _run_feedback(context)
    packets = _initial_packets(context)
    _verify_rule_coverage(packets, _applicable_rules(context))
    # The plan is frozen here: the progress fraction counts against these identifiers. There is
    # no predicted wall clock — the model that produced one was falsified by measurement, so the
    # header prints the plan shape and never a number nobody should trust.
    context.planned_review_packet_ids = tuple(packet.packet_id for packet in packets)
    # Refuse only a physically impossible deadline here, before any worker starts.
    _plan_deadline(context)
    context.expected_receipts = {
        lane: sum(packet.lane == lane for packet in packets)
        for lane in dict.fromkeys(packet.lane for packet in packets)
    }
    context.pools = {
        name: ProviderPool(_worker_limit(context, name))
        for name in {selection.provider for selection in context.selections}
    }
    limit = _worker_limit(context, _selection(context, REVIEW_LANE).provider)
    _progress(
        context,
        format_header(len(context.files), len(packets), limit, None),
        force=True,
    )
    try:
        lanes = tuple(dict.fromkeys(packet.lane for packet in packets))
        # The provider must prove that its effective permission policy can read the external
        # exact-head checkout before any review work starts. The same existing canary runs alone;
        # its temporary challenge is removed and the checkout re-attested before fan-out.
        _progress(context, "running exact-head read canary", force=True)
        if not _run_canary_gate(context, lanes, _review_stop_at(context)):
            _progress(context, "canary failed, review stopped", force=True)
            return _finish(context)
        if any(failure.needs_user_action for failure in context.failures):
            return _finish(context)
        if _deadline_exceeded(context) and (not context.receipts or time.monotonic() >= context.deadline_mono):
            return _finish(context)

        # The tail streams inside this drain: every accepted review receipt feeds
        # `_tail_accumulate`, which seals a verification packet per full candidate shard. The last
        # review receipt triggers the verification remainder; the mop-up below is the stop-path
        # safety net. Review still stops early enough to protect the final synthesis reserve.
        _progress(context, "running review workers", force=True)
        context.stage_starts[REVIEW_LANE] = time.monotonic()
        _drain(context, list(packets), stop_at=_review_stop_at(context))
        if any(failure.needs_user_action for failure in context.failures):
            return _finish(context)
        if _deadline_exceeded(context) and (not context.receipts or time.monotonic() >= context.deadline_mono):
            return _finish(context)
        # One forced line per finished stage leaves a permanent mark in the scrollback; none of
        # them prints when the stage was cut short, because the count would lie.
        review_done, review_total = _review_progress_counts(context)
        if review_done == review_total and not _deadline_exceeded(context):
            _progress(
                context,
                format_stage_done(
                    "review",
                    review_done,
                    review_total,
                    time.monotonic() - context.stage_starts[REVIEW_LANE],
                    len(context.tail_candidates),
                ),
                force=True,
            )
        # Close the tail, then drain the buffers the stream left.
        # Verification is advisory: its failures become gaps, and its slice expiry carries the
        # unverified candidates forward, so it can lose evidence but never a candidate.
        context.tail_closed = True
        verification = _verification_packets(context)
        if verification:
            _progress(context, f"running {len(verification)} remaining verification passes", force=True)
            _drain(context, list(verification), stop_at=_verification_stop_at(context))
        if context.verification_packets:
            _verification_dispositions(context)
        (verify_done, verify_expected), _ = _tail_progress_counts(context)
        if verify_expected and verify_done == verify_expected and not _deadline_exceeded(context):
            _progress(
                context,
                format_stage_done(
                    "verify",
                    verify_done,
                    verify_expected,
                    time.monotonic() - context.stage_starts.get(VERIFICATION_LANE, context.started_mono),
                    len(context.tail_candidates),
                ),
                force=True,
            )
        if _prepare_synthesis_context(context) and not any(
            failure.lane == SYNTHESIS_LANE for failure in context.failures
        ):
            _run_synthesis(context)
    except KeyboardInterrupt as error:
        context.status = "interrupted"
        _cancel_in_flight(context, "interrupted")
        _progress(context, "review interrupted", force=True)
        _save_run(context)
        raise error
    finally:
        for pool in context.pools.values():
            pool.terminate_all()
        # The normal return path reaches `_finish` with nothing in flight, so this clears only the
        # state a stop path already reconciled. On a `finally` teardown after an exception it is a
        # no-op, because the matching stop path already cancelled the in-flight workers.
        _cancel_in_flight(context, "stopped")
    return _finish(context)


def _run_feedback(context: RunContext) -> dict:
    """Run the exact-source feedback path: canary, selected checks, host adjudication."""
    packets = _feedback_verification_packets(context)
    context.planned_review_packet_ids = ()
    context.verification_packets.extend(packets)
    context.tail_closed = True
    context.expected_receipts = {VERIFICATION_LANE: len(packets)}
    context.pools = {
        name: ProviderPool(_worker_limit(context, name))
        for name in {selection.provider for selection in context.selections}
    }
    verifier_reserve = _plan_feedback_deadline(context, packets)
    _progress(
        context,
        f"adjudicating {len(context.feedback_evidence)} findings with "
        f"{_worker_limit(context, _selection(context, VERIFICATION_LANE).provider)} workers",
        force=True,
    )
    try:
        _progress(context, "running exact-head read canary", force=True)
        canary_stop_at = context.deadline_mono - verifier_reserve if context.deadline_mono is not None else None
        if not _run_canary_gate(context, (VERIFICATION_LANE,), canary_stop_at):
            _progress(context, "canary failed, adjudication stopped", force=True)
            return _finish_feedback(context)
        if any(failure.needs_user_action for failure in context.failures):
            return _finish_feedback(context)
        context.stage_starts[VERIFICATION_LANE] = time.monotonic()
        _drain(context, list(packets), stop_at=context.deadline_mono)
    except KeyboardInterrupt as error:
        context.status = "interrupted"
        _cancel_in_flight(context, "interrupted")
        _progress(context, "feedback adjudication interrupted", force=True)
        _save_run(context)
        raise error
    finally:
        for pool in context.pools.values():
            pool.terminate_all()
        _cancel_in_flight(context, "stopped")
    return _finish_feedback(context)


# Verification-lane worker outcomes that end the packet without a receipt. Verification is
# advisory, so its terminal failures land here instead of in `failures`.
_TERMINAL_NO_RECEIPT_OUTCOMES = frozenset({"failed", "deadline", "cancelled", "stopped", "interrupted"})


def _review_progress_counts(context: RunContext) -> tuple[int, int]:
    """Return (done, planned) review packets, resolved against the frozen plan.

    The planned packet identifiers are stored once, when the plan is made: the denominator is
    frozen by construction, and a tick costs a set lookup per packet instead of rebuilding the
    plan. A planned packet counts as done when every leaf it owns produced a receipt or a
    terminal failure, so a packet split after a timeout counts once its parts finish, and the
    fraction never moves because the plan grew.
    """
    done_ids = {receipt.get("packet_id") for receipt in context.receipts}
    done_ids |= {failure.packet_id for failure in context.failures}
    done = 0
    for packet_id in context.planned_review_packet_ids:
        stack = [packet_id]
        leaves = []
        while stack:
            current = stack.pop()
            children = context.packet_splits.get(current)
            if children:
                stack.extend(child.packet_id for child in children)
            else:
                leaves.append(current)
        if all(leaf_id in done_ids for leaf_id in leaves):
            done += 1
    return done, len(context.planned_review_packet_ids)


def _tail_progress_counts(context: RunContext) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return ((verification done, expected), (synthesis done, expected)) for the tail."""
    verify_done = sum(receipt.get("lane") == VERIFICATION_LANE for receipt in context.receipts)
    verify_done += sum(
        timing.lane == VERIFICATION_LANE and timing.outcome in _TERMINAL_NO_RECEIPT_OUTCOMES
        for timing in context.worker_timings
    )
    synthesis_done = sum(receipt.get("lane") == SYNTHESIS_LANE for receipt in context.receipts)
    synthesis_done += sum(failure.lane == SYNTHESIS_LANE for failure in context.failures)
    return (
        (verify_done, context.expected_receipts.get(VERIFICATION_LANE, 0)),
        (synthesis_done, context.expected_receipts.get(SYNTHESIS_LANE, 0)),
    )


def _remaining_estimate(
    context: RunContext, review_done: int, review_total: int, elapsed: float
) -> tuple[float | None, str]:
    """Return the (seconds, source) remaining estimate for the status line, or (None, source).

    Until five review packets have finished there is no measured rate. After that it is the
    measured review completion rate plus the serial tail chain the review window cannot hide,
    and once the review stage is done it is the measured rate across every dispatched packet.
    """
    if review_done < 5 or elapsed <= 0:
        return None, "predicted"
    if review_done < review_total:
        remaining = (review_total - review_done) * (elapsed / review_done) + _tail_chain_seconds(len(context.files))
        return remaining, "measured"
    verify, synth = _tail_progress_counts(context)
    done_all = review_done + verify[0] + synth[0]
    total_all = review_total + verify[1] + synth[1]
    if done_all <= 0 or total_all <= done_all:
        return None, "measured"
    remaining = max(total_all - done_all, 0) * (elapsed / done_all)
    # A sub-second leftover would render as "~0s": omit it rather than print a zero estimate.
    return (remaining if remaining >= 1 else None), "measured"


def _progress_status(context: RunContext, now: float) -> dict:
    """Compute every value the status line and the progress snapshot need, once per write."""
    review_done, review_total = _review_progress_counts(context)
    (verify_done, verify_expected), (synth_done, synth_expected) = _tail_progress_counts(context)
    selection = _selection(context, REVIEW_LANE)
    pool = context.pools.get(selection.provider)
    elapsed = max(now - context.started_mono, 0.0)
    remaining, source = _remaining_estimate(context, review_done, review_total, elapsed)
    retries = sum(timing.outcome == "retried" for timing in context.worker_timings)
    line = format_progress(
        elapsed=elapsed,
        review_completed=review_done,
        review_expected=review_total,
        verification_completed=verify_done,
        verification_expected=verify_expected,
        synthesis_completed=synth_done,
        synthesis_expected=synth_expected,
        active_workers=len(context.active),
        worker_limit=pool.limit if pool is not None else _worker_limit(context, selection.provider),
        candidate_count=len(context.tail_candidates),
        retries=retries,
        splits=len(context.packet_splits),
        worker_limit_lowered=pool is not None and pool.limit < pool.ceiling,
        remaining_estimate=remaining,
        estimate_source=source,
    )
    return {
        "elapsed_seconds": round(elapsed, 1),
        "candidates": len(context.tail_candidates),
        "stage_counts": {
            "review": [review_done, review_total],
            "verification": [verify_done, verify_expected],
            "synthesis": [synth_done, synth_expected],
        },
        "retries": retries,
        "splits": len(context.packet_splits),
        "worker_limit": pool.limit if pool is not None else None,
        "worker_limit_lowered": pool is not None and pool.limit < pool.ceiling,
        "remaining_seconds": remaining,
        "estimate_source": source,
        "line": line,
    }


def _progress(context: RunContext, message: str, *, force: bool = False) -> None:
    """Persist and emit bounded progress without polluting stdout JSON."""
    now = time.monotonic()
    if not force and now - context.last_progress_at < 15:
        return
    context.last_progress_at = now
    completed_packets = len(context.receipts) + len(context.failures)
    total_packets = sum(context.expected_receipts.values())
    lanes = {}
    for lane in context.expected_receipts:
        if lane == SYNTHESIS_LANE:
            continue
        selection = _selection(context, lane)
        completed = sum(receipt.get("lane") == lane for receipt in context.receipts) + sum(
            failure.lane == lane for failure in context.failures
        )
        active = sum(packet.lane == lane for packet in context.active.values())
        expected = context.expected_receipts.get(lane, 0)
        status = "complete" if expected and completed >= expected else "running" if active else "queued"
        lanes[lane] = {
            "provider": selection.provider,
            "model": selection.model,
            "reasoning": selection.reasoning,
            "status": status,
            "completed": completed,
            "expected": expected,
            "active": active,
        }
    status = _progress_status(context, now)
    write_json_atomic(
        context.run_dir / "progress.json",
        {
            "schema_version": 1,
            "run_id": context.run_dir.name,
            "status": context.status,
            "phase": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Packman Python 3.10
            "completed": completed_packets,
            "expected": total_packets,
            "remaining": max(total_packets - completed_packets, 0),
            "active": len(context.active),
            "lanes": lanes,
            # The fields the status line needs, so the read-only `progress` command shows the
            # same truth as the console.
            **status,
        },
    )
    # Forced messages are rare events and stage markers: they print as-is (the format
    # functions already carry the prefix, so drop a duplicate). The cadence prints the line.
    if force:
        print(f"[remix-review] {message.removeprefix('[remix-review] ')}", file=sys.stderr, flush=True)
    else:
        print(status["line"], file=sys.stderr, flush=True)


def _drain(context: RunContext, pending: list[ReviewPacket], stop_at: float | None = None) -> None:
    context.stage_stop_at = stop_at
    try:
        while pending or context.active:
            if stop_at is not None and time.monotonic() >= stop_at:
                _stop_stage_at_deadline(context, pending)
                return
            _start_ready(context, pending)
            _collect(context, pending)
            # A canary failure or a failure that needs user action ends the run at once: no
            # queued worker can succeed, so terminate in-flight workers instead of starting more.
            if (
                _canary_failed(context)
                or any(failure.needs_user_action for failure in context.failures)
                or any(failure.lane == SYNTHESIS_LANE for failure in context.failures)
            ):
                for pool in context.pools.values():
                    pool.terminate_all()
                _cancel_in_flight(context, "cancelled")
                return
            _progress(
                context,
                (
                    f"completed={len(context.receipts) + len(context.failures)}/{sum(context.expected_receipts.values())} "
                    f"active={len(context.active)}"
                ),
            )
            if context.active or pending:
                time.sleep(0.2)
    finally:
        context.stage_stop_at = None


def _verify_checkout(context: RunContext) -> None:
    """Attest the run's immutable review checkout."""
    verify_review_checkout(
        context.repository,
        RevisionSnapshot(
            context.base_ref,
            context.head_ref,
            context.base_sha,
            context.head_sha,
            context.head_tree_sha,
        ),
    )


def _record_final_checkout_failure(context: RunContext) -> None:
    """Record a failed terminal checkout attestation."""
    try:
        _verify_checkout(context)
    except RuntimeError as error:
        context.failures.append(
            PacketFailure(
                "review-snapshot-final",
                REVIEW_LANE,
                str(error),
                None,
                "SNAPSHOT_CHANGED",
                False,
            )
        )


def _persist_finished_result(context: RunContext, result: dict) -> dict:
    """Persist shared terminal progress, timings, and result artifacts."""
    context.status = result["status"]
    _progress(
        context,
        format_summary(
            elapsed=max(time.monotonic() - context.started_mono, 0.0),
            status=result["status"],
            verdict=result["verdict"],
            findings=len(result["findings"]),
            gaps=len(result["gaps"]),
            failures=len(context.failures),
        ),
        force=True,
    )
    write_json(
        context.run_dir / "timings.json",
        {
            "schema_version": 1,
            "run_id": context.run_dir.name,
            "workers": [asdict(timing) for timing in context.worker_timings],
        },
    )
    _persist_terminal_result(context, result)
    return result


def _finish(context: RunContext) -> dict:
    """Persist and return the canonical review result."""
    _record_final_checkout_failure(context)
    candidates = [candidate for receipt in context.receipts for candidate in receipt.get("candidates", [])]
    synthesis = next(
        (receipt for receipt in reversed(context.receipts) if receipt.get("phase") == "final-synthesis"), {}
    )
    # The verification lane has no view: an unverified candidate is a gap, never an incomplete run.
    views = {
        lane: _view_summary(context, lane)
        for lane in context.expected_receipts
        if lane not in (SYNTHESIS_LANE, VERIFICATION_LANE)
    }
    if context.verification_packets:
        # Same for the verification dispositions: the section below reads the reconciled state.
        _verification_dispositions(context)
    assessment_error = None
    if synthesis:
        try:
            synthesis, _ = validate_final_receipt(
                _synthesis_candidates(context),
                synthesis,
                applicable_rule_ids=[rule.id for rule in _applicable_rules(context)],
                reviewed_files=list(context.files),
                verification_dispositions=_final_verification_dispositions(context, _synthesis_candidates(context)),
                delta_index=context.delta_index,
                forge_rule_ids=_forge_rule_ids(context),
            )
        except AssessmentError as error:
            # The packet boundary normally rejects this before a receipt is stored. Repeat the
            # structural gate at publication so no alternate caller or corrupt retained receipt
            # can turn malformed output into findings, a scorecard, or a verdict.
            assessment_error = str(error)
    if not context.verification_packets:
        verification_status = "skipped"
    elif any(failure.lane == VERIFICATION_LANE for failure in context.failures):
        verification_status = "failed"
    elif context.verification_accounting.get("unverified") or context.verification_accounting.get("rejected"):
        verification_status = "incomplete"
    else:
        verification_status = "complete"
    dispositions = context.verification_merged or {}
    # Materialize after the reconcilers above have run: one validated cause group becomes one
    # production-primary finding, with its other manifestations retained as supporting evidence.
    findings = _materialize_findings(context, synthesis) if assessment_error is None else None
    if findings is not None:
        try:
            context.scorecard = materialize_scorecard(
                synthesis,
                findings=findings,
                score_basis=context.score_basis,
                previous_scorecard=_previous_scorecard(context.previous_result),
                comparison_reason=(
                    "assessment_changed"
                    if context.previous_result is not None
                    and (
                        context.previous_result["assessment_policy_hash"] != context.assessment_policy_hash
                        or context.previous_result["rules_hash"] != context.rules_hash
                        or context.previous_result["rubric_hash"] != context.rubric_hash
                        or context.previous_result["validation_level"] != "default"
                    )
                    else None
                ),
            )
        except AssessmentError as error:
            assessment_error = str(error)
            findings = None
            context.scorecard = None
    synthesis_status = (
        "failed"
        if assessment_error is not None or any(failure.lane == SYNTHESIS_LANE for failure in context.failures)
        else ("complete" if synthesis else "incomplete")
    )
    # Disagreement is data: a candidate the verifier refuted but the verdict kept, or one the
    # verifier upheld but the verdict dropped, stays visible with both positions.
    open_disagreements = []
    if synthesis:
        # Kept means present in the verdict: the finding's own identifier, or — for a merged
        # finding — any identifier in its source list. Without the union, every upheld source
        # of a kept merge would report dropped, a false entry on the surface a reviewer reads
        # for what needs judgement.
        final_ids = {
            str(candidate_id)
            for group in synthesis.get("cause_groups") or ()
            for candidate_id in (
                group.get("primary_candidate_id"),
                *(group.get("supporting_candidate_ids") or ()),
            )
            if candidate_id is not None
        }
        for finding in findings or ():
            final_ids.update(str(source) for source in finding.get("source_candidate_ids") or ())
        for candidate_id, record in sorted(dispositions.items()):
            if record.get("ownership") == "pre_existing":
                continue
            kept = candidate_id in final_ids
            if record["disposition"] == "refuted" and kept:
                open_disagreements.append({"candidate_id": candidate_id, "verdict": "kept", **record})
            elif record["disposition"] == "upheld" and not kept:
                open_disagreements.append({"candidate_id": candidate_id, "verdict": "dropped", **record})
    reviewed = (
        not context.failures
        and synthesis_status == "complete"
        and all(view["status"] == "complete" for view in views.values())
    )
    # Pipeline-owned gaps always survive. Synthesis may summarize findings, never evidence.
    gaps = [
        *dict.fromkeys([*context.evidence_gaps, *context.receipt_gaps, *(synthesis.get("gaps") or ())]),
        *(f"{failure.error} ({failure.packet_id})" for failure in context.failures),
    ]
    if assessment_error is not None:
        gaps.append(f"Final assessment is invalid: {assessment_error}")
    cleanup_errors = _cleanup_transient(context.run_dir) if reviewed else ()
    gaps.extend(f"Cleanup failed: {error}" for error in cleanup_errors)
    complete = reviewed and not cleanup_errors
    total_prompt_bytes = sum(timing.prompt_bytes for timing in context.worker_timings)
    summed_tokens: dict[str, int] = {}
    for timing in context.worker_timings:
        for key, value in timing.tokens.items():
            if isinstance(value, int):
                summed_tokens[key] = summed_tokens.get(key, 0) + value
    applicable = _applicable_rules(context)
    registry_ids = [rule.id for rule in context.rules]
    applicable_ids = {rule.id for rule in applicable}
    excluded_ids = sorted(set(registry_ids) - applicable_ids)
    packets = _initial_packets(context)
    _verify_rule_coverage(packets, applicable)
    # Coverage is read from the leaf packets: a packet split after a timeout has no receipt of
    # its own; its parts carry its rules and files.
    leaves = _leaf_packets(context, packets)
    assigned_ids = {rule.id for packet in leaves for rule in packet.rules}
    successful_packet_ids = {receipt.get("packet_id") for receipt in context.receipts}
    unfinished = [packet for packet in leaves if packet.packet_id not in successful_packet_ids]
    unevaluated_ids = sorted({rule.id for packet in unfinished for rule in packet.rules})
    # Rule-level coverage is the wrong granularity for a failed file packet: every file packet
    # carries all file rules for its own file group, so a failure leaves those rules unchecked
    # for its files only. Report the unfinished packets with their files, and keep the flat rule
    # list beside it.
    unevaluated_groups = [
        {
            "packet_id": packet.packet_id,
            "phase": packet.phase,
            "files": sorted(_packet_files(context, packet)),
            "rules": sorted(rule.id for rule in packet.rules),
        }
        for packet in unfinished
    ]
    # Rules whose packet produced an accepted receipt that also reported a gap. They count as
    # evaluated, but they were not fully verified, so the reader must see them separately.
    verified_with_gaps_ids = sorted(
        {rule.id for packet in leaves for rule in packet.rules if packet.packet_id in context.gap_packet_ids}
    )
    if unevaluated_groups:
        unchecked = sorted({file for group in unevaluated_groups for file in group["files"]})
        gaps.append(
            f"Incomplete rule coverage: {len(unevaluated_ids)} rules were not evaluated on "
            f"{len(unchecked)} files from {len(unevaluated_groups)} unfinished packets; "
            "see rules.unevaluated_groups."
        )
    complete = complete and not unevaluated_ids
    retained = sorted({p.name for p in context.run_dir.iterdir()} | {"result.json", "timings.json"})
    result_payload = {
        "schema_version": 3,
        "workflow": "remix-review",
        "validation_level": "default",
        "run_id": context.run_dir.name,
        "status": "complete" if complete else "incomplete",
        "verdict": synthesis.get("verdict") if complete else None,
        "verdict_basis": "scoped_partition",
        "review_identity": context.review_identity,
        "forge_evidence_sha256": _forge_evidence_sha256(context.forge_evidence),
        "artifacts": {"retained": retained, "path": str(context.run_dir)},
        "scope": context.scope,
        "head": {
            "base_ref": context.base_ref,
            "head_ref": context.head_ref,
            "base_sha": context.base_sha,
            "head_sha": context.head_sha,
            "head_tree_sha": context.head_tree_sha,
        },
        "rules_hash": context.rules_hash,
        "rubric_hash": context.rubric_hash,
        "assessment_policy_hash": context.assessment_policy_hash,
        "views": views,
        "synthesis": {
            "provider": _selection(context, SYNTHESIS_LANE).provider,
            "status": synthesis_status,
            "accounting": {},
            # What the final pass excluded, with its concrete reason for each drop.
            "dropped": synthesis.get("dropped") or [],
            # What the deterministic host merge bought before the one final model pass.
            "merge_yield": {
                "candidates_in": len(context.tail_candidates),
                "candidates_out": context.host_merged_candidate_count,
                "final_input": len(_synthesis_candidates(context)),
                "final_grouped_by_model": context.final_ranking_report.get("model_grouped", 0),
                "final_placed_by_pipeline": context.final_ranking_report.get("pipeline_placed", 0),
                "final_dropped": context.final_ranking_report.get("dropped", 0),
            },
        },
        "verification": {
            "model": context.verify_model,
            "status": verification_status,
            # Disposition accounting: `in = verified + unverified`; `rejected` stands alone.
            # Empty when the stage did not run.
            "accounting": context.verification_accounting,
            "dispositions": [
                {"candidate_id": candidate_id, **record} for candidate_id, record in sorted(dispositions.items())
            ],
            "open_disagreements": open_disagreements,
        },
        # Only a structurally complete final assessment can publish actionable findings. Raw
        # candidates remain in receipts for diagnostics; they never masquerade as validated bugs.
        "findings": findings if complete and findings is not None else [],
        "scorecard": context.scorecard if complete else None,
        "gaps": gaps,
        "failures": [asdict(failure) for failure in context.failures],
        # Every rejected receipt attempt, with the check, the bounded reason, and the failure
        # class. A retried packet's history is visible here, including for a packet that later
        # succeeded, so a long deterministic failure can never quietly become another attempt.
        "rejection_records": context.rejection_records,
        "rules": {
            "registry": len(context.rules),
            "applicable": len(applicable),
            "assigned": len(assigned_ids),
            "excluded": excluded_ids,
            "unevaluated": unevaluated_ids,
            "unevaluated_groups": unevaluated_groups,
            "verified_with_gaps": verified_with_gaps_ids,
        },
        "coverage": {
            "files": len(context.files),
            "changes": len(context.changes),
            "receipts": len(context.receipts),
            "expected_receipts": sum(context.expected_receipts.values()),
            "candidates": len(candidates),
            "worker_seconds": round(sum(timing.duration_seconds for timing in context.worker_timings), 1),
            "prompt_bytes": total_prompt_bytes,
            "tokens": summed_tokens,
        },
        "provenance": {"result": str(context.run_dir / "result.json")},
    }
    return _persist_finished_result(context, result_payload)


def _finish_feedback(context: RunContext) -> dict:
    """Persist one host-only derivative result from selected feedback dispositions."""
    _record_final_checkout_failure(context)
    _verification_dispositions(context)
    submitted = context.feedback_evidence
    finding_ids = sorted((record["finding_id"] for record in submitted), key=lambda finding_id: int(finding_id[2:]))
    expected_ids = set(finding_ids)
    actual_ids = set(context.feedback_merged or {})
    assessment = None
    assessment_error = None
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids, key=lambda finding_id: int(finding_id[2:]))
        unexpected = sorted(actual_ids - expected_ids, key=lambda finding_id: int(finding_id[2:]))
        assessment_error = (
            "feedback verification did not account for the selected findings exactly once "
            f"(missing={missing}, unexpected={unexpected})"
        )
    elif context.failures:
        assessment_error = "feedback verification did not complete"
    else:
        try:
            assessment = materialize_feedback_adjudication(
                context.run_dir.name,
                context.previous_result,
                context.previous_result_sha256,
                submitted,
                context.feedback_merged or {},
                reviewed_locations=_reviewed_locations(context, context.feedback_merged or {}),
            )
        except AssessmentError as error:
            assessment_error = str(error)

    reviewed = assessment is not None and assessment_error is None and not context.failures
    cleanup_errors = _cleanup_transient(context.run_dir) if reviewed else ()
    complete = reviewed and not cleanup_errors
    prior = context.previous_result
    gaps = list(prior.get("gaps", ()))
    gaps.extend(context.receipt_gaps)
    if assessment is not None:
        gaps.extend(assessment["diagnostics"])
    gaps.extend(f"{failure.error} ({failure.packet_id})" for failure in context.failures)
    if assessment_error is not None:
        gaps.append(f"Feedback adjudication is invalid: {assessment_error}")
    gaps.extend(f"Cleanup failed: {error}" for error in cleanup_errors)

    total_prompt_bytes = sum(timing.prompt_bytes for timing in context.worker_timings)
    summed_tokens: dict[str, int] = {}
    for timing in context.worker_timings:
        for key, value in timing.tokens.items():
            if isinstance(value, int):
                summed_tokens[key] = summed_tokens.get(key, 0) + value
    verified_count = len(actual_ids) if actual_ids == expected_ids else 0
    retained = sorted({path.name for path in context.run_dir.iterdir()} | {"result.json", "timings.json"})
    result_payload = {
        "schema_version": 3,
        "workflow": "remix-review",
        "validation_level": "default",
        "run_id": context.run_dir.name,
        "status": "complete" if complete else "incomplete",
        "verdict": assessment["verdict"] if complete else None,
        "verdict_basis": "feedback_adjudication",
        "review_identity": context.review_identity,
        "forge_evidence_sha256": _forge_evidence_sha256(context.forge_evidence),
        "adjudication": (
            assessment["adjudication"]
            if complete
            else {
                "source_run_id": prior["run_id"],
                "source_result_sha256": context.previous_result_sha256,
                "finding_ids": finding_ids,
            }
        ),
        "artifacts": {"retained": retained, "path": str(context.run_dir)},
        "scope": copy.deepcopy(prior["scope"]),
        "head": copy.deepcopy(prior["head"]),
        "rules_hash": context.rules_hash,
        "rubric_hash": context.rubric_hash,
        "assessment_policy_hash": context.assessment_policy_hash,
        "views": {},
        "synthesis": {
            "provider": _selection(context, SYNTHESIS_LANE).provider,
            "status": "skipped",
            "accounting": {},
            "dropped": [],
            "merge_yield": {
                "candidates_in": 0,
                "candidates_out": 0,
                "final_input": 0,
                "final_grouped_by_model": 0,
                "final_placed_by_pipeline": 0,
                "final_dropped": 0,
            },
        },
        "verification": {
            "model": context.verify_model,
            "status": "complete" if complete else "incomplete",
            "accounting": {
                "in": len(expected_ids),
                "verified": verified_count,
                "unverified": len(expected_ids) - verified_count,
                "rejected": sum(record.get("lane") == VERIFICATION_LANE for record in context.rejection_records),
            },
            "dispositions": [],
            "open_disagreements": [],
        },
        "findings": assessment["findings"] if complete else [],
        "scorecard": assessment["scorecard"] if complete else None,
        "gaps": list(dict.fromkeys(gaps)),
        "failures": [asdict(failure) for failure in context.failures],
        "rejection_records": context.rejection_records,
        "rules": copy.deepcopy(prior["rules"]),
        "coverage": {
            "files": len(context.files),
            "changes": len(context.changes),
            "receipts": len(context.receipts),
            "expected_receipts": len(context.verification_packets),
            "candidates": 0,
            "worker_seconds": round(sum(timing.duration_seconds for timing in context.worker_timings), 1),
            "prompt_bytes": total_prompt_bytes,
            "tokens": summed_tokens,
        },
        "provenance": {"result": str(context.run_dir / "result.json")},
    }
    if complete and assessment["feedback"]:
        result_payload["feedback"] = assessment["feedback"]
    return _persist_finished_result(context, result_payload)


def _candidate_disposition(candidate: dict, dispositions: dict[str, dict]) -> dict | None:
    """Return the verifier's position for one candidate, following a merge's provenance.

    A kept candidate answers by its own identifier. A merged candidate carries a minted
    identifier no disposition can match — verification ran on the pre-merge stream — so its
    position comes from its sources only when every source was verified and reached the same
    disposition. Mixed or incomplete source evidence is uncertain. A candidate without
    `source_candidate_ids` — the unsharded stream, a recovered shard — answers by its own
    identifier exactly as before.
    """
    sources = candidate.get("source_candidate_ids")
    if not isinstance(sources, list) or not sources:
        return dispositions.get(str(candidate.get("candidate_id") or _candidate_id(candidate)))
    source_ids = list(dict.fromkeys(str(source) for source in sources))
    records = [record for source in source_ids if (record := dispositions.get(source)) is not None]
    positions = {record.get("disposition") for record in records}
    ownerships = {record.get("ownership") for record in records}
    if len(records) != len(source_ids) or len(positions) != 1 or len(ownerships) != 1:
        return {
            "disposition": "uncertain",
            "ownership": "uncertain",
            "evidence": "The merged candidate's source verifications are mixed or incomplete.",
        }
    combined = None
    for record in records:
        combined = _combine_verification_records(combined, record)
    return combined


def _combine_verification_records(left: dict | None, right: dict) -> dict:
    """Combine repeated logical-candidate verification without completion-order authority."""
    if left is None:
        return right
    positions = {left.get("disposition"), right.get("disposition")}
    ownerships = {left.get("ownership"), right.get("ownership")}
    evidence = " | ".join(
        sorted(
            {
                str(record.get("evidence") or "").strip()
                for record in (left, right)
                if str(record.get("evidence") or "").strip()
            }
        )
    )
    if len(positions) == 1 and len(ownerships) == 1:
        return {**left, "evidence": evidence}
    conflicts = []
    if len(positions) != 1:
        conflicts.append("outcomes")
    if len(ownerships) != 1:
        conflicts.append("ownership classifications")
    return {
        **left,
        "disposition": left.get("disposition") if len(positions) == 1 else "uncertain",
        "ownership": left.get("ownership") if len(ownerships) == 1 else "uncertain",
        "evidence": f"Conflicting verifier {' and '.join(conflicts)} for the same candidate: {evidence}",
    }


def _final_verification_dispositions(context: RunContext, candidates: list[dict]) -> dict[str, dict]:
    """Map reconciled verifier evidence to both original and compacted candidate identities."""
    dispositions = dict(context.verification_merged or {})
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or _candidate_id(candidate))
        resolved = _candidate_disposition(candidate, dispositions)
        if resolved is not None:
            dispositions[candidate_id] = resolved
    return dispositions


def _drop_evidence_refs(candidate: dict, dispositions: dict[str, dict]) -> list[dict]:
    """Return exact refs only when every source was independently verifier-refuted."""
    sources = candidate.get("source_candidate_ids")
    candidate_ids = (
        [str(candidate_id) for candidate_id in sources]
        if isinstance(sources, list) and sources
        else [str(candidate.get("candidate_id") or _candidate_id(candidate))]
    )
    records = [dispositions.get(candidate_id) for candidate_id in candidate_ids]
    if not all(
        isinstance(record, dict)
        and record.get("disposition") == "refuted"
        and isinstance(record.get("evidence"), str)
        and record["evidence"].strip()
        for record in records
    ):
        return []
    return [{"kind": "verification", "candidate_id": candidate_id} for candidate_id in candidate_ids]


def _materialize_findings(context: RunContext, synthesis: dict) -> list[dict] | None:
    """Build one finding per validated final cause group, or None without a final partition."""
    if not isinstance(synthesis.get("cause_groups"), list):
        return None
    candidates = _synthesis_candidates(context)
    dispositions = _final_verification_dispositions(context, candidates)
    source_candidates = [
        candidate
        for receipt in context.receipts
        if receipt.get("phase") in ("file-review", "scope-review")
        for candidate in receipt.get("candidates") or ()
        if isinstance(candidate, dict)
    ]
    return materialize_grouped_findings(
        candidates,
        synthesis,
        dispositions,
        source_candidates=source_candidates,
    )


def _reviewed_locations(context: RunContext, dispositions: object) -> set[tuple[str, int | None]]:
    """Return submitted evidence locations proven in tracked exact-head regular files."""
    records = dispositions.values() if isinstance(dispositions, dict) else dispositions
    requested: set[tuple[str, int | None]] = set()
    if isinstance(records, (list, tuple)) or hasattr(records, "__iter__"):
        for record in records:
            evidence = record.get("evidence") if isinstance(record, dict) else None
            if not isinstance(evidence, list):
                continue
            for location in evidence:
                if not isinstance(location, dict):
                    continue
                path, line = location.get("path"), location.get("line")
                if (
                    isinstance(path, str)
                    and path
                    and path.isprintable()
                    and "\\" not in path
                    and not path.startswith("/")
                    and all(part not in ("", ".", "..") for part in path.split("/"))
                    and (line is None or (type(line) is int and line > 0))
                ):
                    requested.add((path, line))
    if not requested:
        return set()

    paths = sorted({path for path, _ in requested})
    tracked = run_git(
        context.repository,
        "ls-files",
        "--stage",
        "-z",
        "--",
        *(f":(top,literal){path}" for path in paths),
        check=False,
    )
    if tracked.returncode != 0:
        return set()
    regular_paths = set()
    for row in tracked.stdout.split(b"\0"):
        if not row or b"\t" not in row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        fields = metadata.split()
        if len(fields) != 3 or fields[0] not in (b"100644", b"100755") or fields[2] != b"0":
            continue
        try:
            path = raw_path.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        if path in paths:
            regular_paths.add(path)

    root = context.repository.resolve()
    line_counts = {}
    for path in regular_paths:
        candidate = context.repository.joinpath(*path.split("/"))
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            if candidate.is_symlink() or not resolved.is_file():
                continue
            line_counts[path] = len(resolved.read_bytes().splitlines())
        except (OSError, ValueError):
            continue
    return {
        (path, line) for path, line in requested if path in line_counts and (line is None or line <= line_counts[path])
    }


def _previous_scorecard(previous_result: dict | None) -> dict | None:
    """Return the bounded prior score snapshot used only for display comparison."""
    if previous_result is None:
        return None
    scorecard = previous_result["scorecard"]
    return {
        "run_id": previous_result["run_id"],
        "base_sha": previous_result["head"]["base_sha"],
        "head_sha": previous_result["head"]["head_sha"],
        "point_pool": scorecard["basis"]["point_pool"],
        "categories": {
            name: {
                "score": scorecard["categories"][name]["score"],
                "penalty_points": scorecard["categories"][name]["penalty_points"],
            }
            for name in SCORE_CATEGORIES
        },
        "overall_branch": scorecard["overall_branch"],
    }


def _score_basis(context: RunContext) -> dict:
    """Return the current snapshot's deterministic scoring basis."""
    logical_changes = {
        json.dumps(
            [change.status, change.old_path, change.new_path, change.old_mode, change.new_mode],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for change in context.changes
    }
    change_records = [json.loads(value) for value in sorted(logical_changes)]
    applicable_rules = _applicable_rules(context)
    units = [
        ["file", rule.id, *change] for rule in applicable_rules if rule.target == "file" for change in change_records
    ]
    units.extend(["global", rule.id] for rule in applicable_rules if rule.target == "global")
    units.sort(key=lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    workload = {
        "metric": WORKLOAD_METRIC_VERSION,
        "units": len(units),
        "sha256": canonical_hash(
            {
                "metric": WORKLOAD_METRIC_VERSION,
                "rules_hash": context.rules_hash,
                "units": units,
            }
        ),
    }
    return {
        "formula": SCORE_FORMULA_VERSION,
        "point_pool": max(5, workload["units"].bit_length()),
        "workload": workload,
    }


def _synthesis_candidates(context: RunContext) -> list[dict]:
    """Return the host-merged candidates read by the one final synthesis pass."""
    if context.final_candidates is not None:
        return context.final_candidates
    merged = _merge_candidates(list(context.tail_candidates), context.receipts)
    if context.tail_closed and not context.tail_provenance_checked:
        context.tail_provenance_checked = True
        _check_provenance_coverage(context, list(context.tail_candidates), merged)
    return merged


def _admit_delta_owned_candidates(candidates: list[dict], dispositions: dict[str, dict]) -> tuple[list[dict], int]:
    """Return candidates eligible for synthesis and the upheld pre-existing count.

    Correctness refutations remain in the final partition so its existing grounded-drop
    contract can account for them. Delta ownership is stricter: every candidate needs an
    independent, definite classification, and an upheld pre-existing defect has no authority
    over the current delta.
    """
    admitted = []
    excluded = 0
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or _candidate_id(candidate))
        record = _candidate_disposition(candidate, dispositions)
        if not isinstance(record, dict):
            raise AssessmentError(f"candidate {candidate_id} has no verifier delta-ownership classification")
        disposition = record.get("disposition")
        if disposition not in ("upheld", "refuted"):
            raise AssessmentError(f"candidate {candidate_id} has an uncertain verifier outcome")
        if not isinstance(record.get("evidence"), str) or not record["evidence"].strip():
            raise AssessmentError(f"candidate {candidate_id} has malformed verifier evidence")
        # A refutation already proves the candidate is not an admissible defect; keep it on the
        # existing grounded-drop path even when causal ownership is moot or disputed. Ownership
        # must be definite only for an upheld candidate that could influence the assessment.
        if disposition == "refuted":
            admitted.append(candidate)
            continue
        ownership = record.get("ownership")
        if ownership not in ("introduced_or_worsened", "pre_existing"):
            raise AssessmentError(f"candidate {candidate_id} has uncertain delta ownership")
        if ownership == "pre_existing":
            excluded += 1
            continue
        admitted.append(candidate)
    return admitted, excluded


def _prepare_synthesis_context(context: RunContext) -> bool:
    """Write and attest the evidence displaced from bounded synthesis prompts."""
    dispositions = _verification_dispositions(context)
    raw_candidates = list(context.tail_candidates)
    host_merged = _synthesis_candidates(context)
    context.host_merged_candidate_count = len(host_merged)
    try:
        validate_candidate_ownership(
            raw_candidates,
            [rule.id for rule in _applicable_rules(context)],
            list(context.files),
            delta_index=context.delta_index,
            forge_rule_ids=_forge_rule_ids(context),
        )
        admitted, excluded = _admit_delta_owned_candidates(
            host_merged,
            _final_verification_dispositions(context, host_merged),
        )
    except AssessmentError as error:
        _fail_synthesis(context, "delta-ownership", str(error), "DELTA_OWNERSHIP")
        return False
    context.receipt_gaps.append(
        f"Reviewed {len(context.files)} changed files; admitted {len(admitted)} delta-owned candidates; "
        f"excluded {excluded} upheld pre-existing candidates."
    )
    context.final_candidates = admitted
    final_disposition_ids = {
        candidate_id
        for candidate in context.final_candidates
        for candidate_id in [
            _synthesis_candidate_id(candidate),
            *_candidate_sources(candidate),
        ]
    }
    context_dispositions = {
        candidate_id: record for candidate_id, record in dispositions.items() if candidate_id in final_disposition_ids
    }
    payload = {
        "reviewed_paths": list(context.files),
        "changes": [asdict(change) for change in context.changes],
        "forge_evidence": context.forge_evidence,
        "verification_dispositions": [
            {
                "candidate_id": candidate_id,
                "disposition": record.get("disposition"),
                "ownership": record.get("ownership"),
                "evidence": record.get("evidence"),
            }
            for candidate_id, record in sorted(context_dispositions.items())
        ],
    }
    path = context.scope_artifacts / "synthesis-context.json"
    try:
        write_json_atomic(path, payload)
        digest = file_hash(path)
    except OSError as error:
        _fail_synthesis(
            context,
            "synthesis-context",
            f"could not create the bounded synthesis context: {error.strerror or error}",
            "SYNTHESIS_CONTEXT",
        )
        return False
    context.synthesis_context_path = path
    context.synthesis_context_sha256 = digest
    context.synthesis_context_counts = {
        "files": len(context.files),
        "changes": len(context.changes),
        "verification_dispositions": len(context_dispositions),
    }
    error = _synthesis_context_error(context)
    if error is not None:
        _fail_synthesis(context, "synthesis-context", error, "SYNTHESIS_CONTEXT")
        return False
    return True


def _synthesis_context_error(context: RunContext) -> str | None:
    """Return why the run-owned synthesis context no longer matches its exact bytes."""
    if context.synthesis_context_path is None or context.synthesis_context_sha256 is None:
        return "the bounded synthesis context was not prepared"
    try:
        actual = file_hash(context.synthesis_context_path)
    except OSError as error:
        return f"the bounded synthesis context could not be read: {error.strerror or error}"
    if actual != context.synthesis_context_sha256:
        return "the bounded synthesis context changed after it was created"
    return None


def _fail_synthesis(
    context: RunContext,
    packet_id: str,
    error: str,
    code: str = _SYNTHESIS_CAPACITY_FAILURE_CODE,
) -> None:
    """Record one terminal synthesis failure without retrying an identical request."""
    context.failures.append(
        PacketFailure(packet_id, SYNTHESIS_LANE, error, _selection(context, SYNTHESIS_LANE).provider, code)
    )
    _progress(context, error, force=True)


def _packet_prompt_size(context: RunContext, packet: ReviewPacket) -> tuple[int, int]:
    """Return the exact rendered prompt's character and UTF-8 byte counts."""
    prompt, payload = _prompt_payload(context, packet, receipt_contract(packet.phase))
    return len(prompt), len(payload)


def _prompt_payload(context: RunContext, packet: ReviewPacket, contract: dict) -> tuple[str, bytes]:
    """Return one prompt and the exact bytes written to the worker request."""
    prompt = _render_prompt(context, _packet_payload(context, packet, contract))
    return prompt, prompt.encode("utf-8")


def _fixed_final_prompt_size(context: RunContext, packet: ReviewPacket) -> tuple[int, int]:
    """Return final-synthesis size with no candidates, exposing uncompactable overhead."""
    contract = receipt_contract(packet.phase)
    payload = _packet_payload(context, packet, contract)
    payload["validated_candidates"] = []
    prompt = _render_prompt(context, payload)
    return len(prompt), len(prompt.encode("utf-8"))


def _compaction_packets(context: RunContext) -> list[ReviewPacket] | None:
    """Greedily pack one canonical candidate stream by exact rendered prompt bytes."""
    packets = []
    current: list[dict] = []
    # ponytail: exact greedy rendering is O(n²); keep it until measured packing time, rather
    # than provider execution, becomes material for a real review.
    for candidate in _synthesis_candidates(context):
        trial = [*current, candidate]
        trial_packet = _shard_packet(context, SYNTHESIS_LANE, "synthesis-compaction", trial)
        _, trial_bytes = _packet_prompt_size(context, trial_packet)
        if trial_bytes <= _SYNTHESIS_COMPACTION_TARGET_BYTES:
            current = trial
            continue
        if current:
            packets.append(_shard_packet(context, SYNTHESIS_LANE, "synthesis-compaction", current))
        singleton = _shard_packet(context, SYNTHESIS_LANE, "synthesis-compaction", [candidate])
        singleton_characters, singleton_bytes = _packet_prompt_size(context, singleton)
        if singleton_bytes > _SYNTHESIS_PROMPT_MAX_BYTES:
            _fail_synthesis(
                context,
                singleton.packet_id,
                f"one synthesis candidate requires {singleton_bytes} prompt bytes "
                f"({singleton_characters} characters), above the "
                f"{_SYNTHESIS_PROMPT_MAX_BYTES}-byte host ceiling",
            )
            return None
        if singleton_bytes > _SYNTHESIS_COMPACTION_TARGET_BYTES:
            packets.append(singleton)
            current = []
        else:
            current = [candidate]
    if current:
        packets.append(_shard_packet(context, SYNTHESIS_LANE, "synthesis-compaction", current))
    return packets


def _compaction_accounting_error(context: RunContext) -> str | None:
    """Return why accepted compaction receipts do not cover the original IDs exactly once."""
    expected = [_synthesis_candidate_id(candidate) for candidate in _synthesis_candidates(context)]
    if len(expected) != len(set(expected)):
        return "the host-merged final candidate stream contains duplicate candidate IDs"
    actual = set(context.synthesis_digests)
    missing = sorted(set(expected) - actual)
    unknown = sorted(actual - set(expected))
    if missing or unknown:
        return f"compaction ID accounting is incomplete: missing={missing[:5]} unknown={unknown[:5]}"
    return None


def _validated_compaction_digests(context: RunContext, packet: ReviewPacket, receipt: dict) -> dict[str, dict]:
    """Validate one receipt as an exact one-to-one digest partition without repairing it."""
    expected = [_synthesis_candidate_id(candidate) for candidate in packet.candidates]
    if len(expected) != len(set(expected)):
        raise AssessmentError("a synthesis-compaction packet contains duplicate input candidate IDs")
    if receipt.get("verdict") is not None or receipt.get("verdict_basis") is not None:
        raise AssessmentError("synthesis-compaction cannot issue a verdict")
    entries = receipt.get("candidate_digests")
    if not isinstance(entries, list):
        raise AssessmentError("synthesis-compaction candidate_digests is not an array")
    digests = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != {
            "candidate_id",
            "claim_summary",
            "verification_summary",
        }:
            raise AssessmentError(f"synthesis-compaction digest {index} has an invalid shape")
        candidate_id = entry.get("candidate_id")
        claim = entry.get("claim_summary")
        verification = entry.get("verification_summary")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise AssessmentError(f"synthesis-compaction digest {index} has no candidate ID")
        if candidate_id in digests or candidate_id in context.synthesis_digests:
            raise AssessmentError(f"synthesis-compaction returned duplicate candidate ID {candidate_id}")
        if not isinstance(claim, str) or not claim.strip() or not 1 <= len(claim) <= 384:
            raise AssessmentError(f"synthesis-compaction digest {candidate_id} has an invalid claim summary")
        if not isinstance(verification, str) or len(verification) > 128:
            raise AssessmentError(f"synthesis-compaction digest {candidate_id} has an invalid verification summary")
        digests[candidate_id] = entry
    returned = [entry.get("candidate_id") for entry in entries if isinstance(entry, dict)]
    if returned != expected:
        raise AssessmentError("synthesis-compaction changed the canonical candidate-ID order")
    return {candidate_id: digests[candidate_id] for candidate_id in expected}


def _compaction_wave_seconds(context: RunContext, packets: list[ReviewPacket]) -> float:
    """Return the conservative timeout sum for every packet wave at the current pool limit."""
    provider = _selection(context, SYNTHESIS_LANE).provider
    limit = max(context.pools[provider].limit, 1)
    timeouts = [_worker_timeout(packet, _packet_prompt_size(context, packet)[1]) for packet in packets]
    return sum(max(timeouts[index : index + limit]) for index in range(0, len(timeouts), limit))


def _run_synthesis(context: RunContext) -> None:
    """Run the direct final pass or one one-to-one compaction wave followed by that pass."""
    final_packet = _packet(context, SYNTHESIS_LANE, "final-synthesis", None, ())
    context.expected_receipts[SYNTHESIS_LANE] = context.expected_receipts.get(SYNTHESIS_LANE, 0) + 1
    direct_characters, direct_bytes = _packet_prompt_size(context, final_packet)
    if direct_bytes <= _SYNTHESIS_PROMPT_MAX_BYTES:
        _progress(context, "running final synthesis", force=True)
        context.stage_starts["final-synthesis"] = time.monotonic()
        _drain(context, [final_packet], stop_at=context.deadline_mono)
        return
    _progress(
        context,
        f"final synthesis prompt measured {direct_bytes} bytes ({direct_characters} characters); compacting",
        force=True,
    )
    fixed_characters, fixed_bytes = _fixed_final_prompt_size(context, final_packet)
    if fixed_bytes > _SYNTHESIS_PROMPT_MAX_BYTES:
        _fail_synthesis(
            context,
            final_packet.packet_id,
            f"final-synthesis fixed context requires {fixed_bytes} prompt bytes "
            f"({fixed_characters} characters), above the "
            f"{_SYNTHESIS_PROMPT_MAX_BYTES}-byte host ceiling; candidate compaction cannot reduce it",
        )
        return
    compaction = _compaction_packets(context)
    if compaction is None:
        return
    if not compaction:
        _fail_synthesis(context, final_packet.packet_id, "final synthesis exceeded the host ceiling with no candidates")
        return
    terminal_reserve = max(_SYNTHESIS_TIMEOUT_FLOOR_SECONDS, _scaled_timeout(_SYNTHESIS_PROMPT_MAX_BYTES))
    if context.deadline_mono is not None:
        compaction_seconds = _compaction_wave_seconds(context, compaction)
        remaining = max(context.deadline_mono - time.monotonic(), 0.0)
        if remaining < compaction_seconds + terminal_reserve:
            _fail_synthesis(
                context,
                "synthesis-deadline",
                f"the remaining {remaining:.0f}s deadline cannot fit every bounded compaction wave and the "
                "reserved final-synthesis pass",
                DEADLINE_FAILURE_CODE,
            )
            return
    context.expected_receipts[SYNTHESIS_LANE] += len(compaction)
    _progress(context, f"running {len(compaction)} bounded synthesis compaction passes", force=True)
    context.stage_starts["synthesis-compaction"] = time.monotonic()
    stop_at = context.deadline_mono - terminal_reserve if context.deadline_mono is not None else None
    _drain(context, compaction, stop_at=stop_at)
    if any(failure.lane == SYNTHESIS_LANE for failure in context.failures):
        return
    accounting_error = _compaction_accounting_error(context)
    if accounting_error is not None:
        _fail_synthesis(context, "synthesis-compaction-accounting", accounting_error, "ACCOUNTING_IMBALANCE")
        return
    terminal_characters, terminal_bytes = _packet_prompt_size(context, final_packet)
    if terminal_bytes > _SYNTHESIS_PROMPT_MAX_BYTES:
        _fail_synthesis(
            context,
            final_packet.packet_id,
            f"the one-to-one digest representation still requires {terminal_bytes} prompt bytes "
            f"({terminal_characters} characters), above the "
            f"{_SYNTHESIS_PROMPT_MAX_BYTES}-byte host ceiling",
        )
        return
    _progress(context, "running final synthesis from bounded candidate digests", force=True)
    context.stage_starts["final-synthesis"] = time.monotonic()
    _drain(context, [final_packet], stop_at=context.deadline_mono)


def _record_imbalance(context: RunContext, packet_id: str, detail: str, lane: str = SYNTHESIS_LANE) -> None:
    """Record a broken accounting balance as a run failure that blocks `complete`.

    A count that is only printed is a report, not a guarantee. A broken balance means the run
    cannot prove nothing was lost, so it has no business claiming completeness: the failure makes
    the result `incomplete`, and its message lands in the run gaps with the exact numbers.
    """
    context.failures.append(
        PacketFailure(
            packet_id,
            lane,
            f"{lane} candidate accounting does not balance: {detail}",
            None,
            "ACCOUNTING_IMBALANCE",
            False,
        )
    )
    _progress(context, f"{lane} candidate accounting imbalance", force=True)


def _check_provenance_coverage(context: RunContext, stage_inputs: list[dict], merged: list[dict]) -> None:
    """Fail the run's completeness when the final merge lost a candidate's provenance.

    Every merge records the loser's provenance on the survivor, so the union over the
    survivors must still cover every identifier that entered the merge. A gap here means a
    candidate was silently lost between the tail universe and the final pass's input, and the
    run has no business publishing a verdict over an incomplete set. The failure takes the
    same path as the other imbalances, so it blocks `complete` instead of printing a warning.
    """
    required = {source for candidate in stage_inputs for source in _candidate_sources(candidate)}
    covered = {source for candidate in merged for source in _candidate_sources(candidate)}
    missing = sorted(required - covered)
    if missing:
        _record_imbalance(
            context,
            "synthesis-provenance",
            f"the final merge lost {len(missing)} candidate identifiers: {missing[:5]}",
        )


def _buffer_bytes(candidates: list[dict]) -> int:
    """Return the JSON size of one candidate buffer, the measure the shard target uses."""
    return len(json.dumps(candidates))


def _canonical_candidate(candidate: dict) -> str:
    """Return the full canonical content of one candidate, the encoding the identity hash uses."""
    return json.dumps(candidate, ensure_ascii=False, sort_keys=True)


def _shard_prefix(candidates: list[dict], target_bytes: int, *, identity_key: str | None = None) -> list[dict]:
    """Take a size-bounded prefix of the buffer, never two candidates with one identity.

    A candidate carried forward after its twin was sealed can share the twin's identifier, and
    the per-packet accounting reads two of one identifier in one packet as physical duplication.
    A skipped candidate waits in the buffer for the next shard.
    """
    shard = []
    seen = set()
    size = 2  # the empty array's brackets
    for candidate in candidates:
        item_bytes = len(json.dumps(candidate, ensure_ascii=False)) + 1
        if shard and size + item_bytes > target_bytes:
            break
        candidate_id = candidate.get(identity_key) if identity_key is not None else _candidate_id(candidate)
        if candidate_id in seen:
            continue
        shard.append(candidate)
        seen.add(candidate_id)
        size += item_bytes
    return shard


def _shard_packet(context: RunContext, lane: str, phase: str, shard: list[dict]) -> ReviewPacket:
    """Build one candidate-carrying packet for one shard of the tail.

    Each packet carries the rules its candidates claim, so receipt validation holds.
    """
    rules_by_id = {rule.id: rule for rule in context.rules}
    rule_ids = sorted({rule_id for candidate in shard for rule_id in candidate.get("rule_ids") or ()})
    rules = tuple(rules_by_id[rule_id] for rule_id in rule_ids if rule_id in rules_by_id)
    # Late twins can intentionally share the logical candidate ID while carrying different
    # evidence. Include their complete canonical content so their physical packets cannot share
    # a packet ID and overwrite one another's receipts before conservative reconciliation.
    identity = [_canonical_candidate(candidate) for candidate in shard]
    packet_id = f"{lane}-{phase}-{canonical_hash(identity)[:16]}"
    return ReviewPacket(packet_id, lane, phase, None, rules, candidates=tuple(shard))


def _dispatch_verification(context: RunContext, shard: list[dict]) -> ReviewPacket:
    """Send one shard to verification: packet, bookkeeping, and the seal that freezes it."""
    packet = _shard_packet(context, VERIFICATION_LANE, "verification", shard)
    context.verification_packets.append(packet)
    context.expected_receipts[VERIFICATION_LANE] = context.expected_receipts.get(VERIFICATION_LANE, 0) + 1
    context.tail_sealed_ids.update(_candidate_id(candidate) for candidate in shard)
    context.stage_starts.setdefault(VERIFICATION_LANE, time.monotonic())
    return packet


def _selected_feedback_findings(context: RunContext) -> list[dict]:
    """Return submitted responses beside their exact source findings."""
    responses = {record["finding_id"]: record["text"] for record in context.feedback_evidence}
    findings = {
        finding["finding_id"]: finding
        for finding in (context.previous_result or {}).get("findings", ())
        if isinstance(finding, dict) and isinstance(finding.get("finding_id"), str)
    }
    return [
        {
            "finding_id": finding_id,
            "finding": copy.deepcopy(findings[finding_id]),
            "response": responses[finding_id],
        }
        for finding_id in sorted(responses, key=lambda value: int(value[2:]))
    ]


def _feedback_verification_packet(context: RunContext, shard: list[dict]) -> ReviewPacket:
    """Build one verifier packet for exact-source feedback findings."""
    rules_by_id = {rule.id: rule for rule in context.rules}
    paths = tuple(
        sorted(
            {
                location["path"]
                for record in shard
                for location in record["finding"].get("locations") or ()
                if isinstance(location, dict) and location.get("path") in context.files
            }
        )
    )
    rule_ids = sorted(
        {rule_id for record in shard for rule_id in record["finding"].get("rule_ids") or () if rule_id in rules_by_id}
    )
    return ReviewPacket(
        f"verification-feedback-{canonical_hash(shard)[:16]}",
        VERIFICATION_LANE,
        "verification",
        None,
        tuple(rules_by_id[rule_id] for rule_id in rule_ids),
        paths=paths,
        feedback_findings=tuple(shard),
    )


def _feedback_verification_packets(context: RunContext) -> list[ReviewPacket]:
    """Byte-shard the submitted exact-source feedback findings once."""
    buffer = _selected_feedback_findings(context)
    if not buffer:
        return []
    target = _tail_shard_target(context, buffer)
    packets = []
    while buffer:
        packets.append(
            _feedback_verification_packet(
                context,
                _take_shard(buffer, target, identity_key="finding_id"),
            )
        )
    return packets


_TAIL_SHARD_MIN_BYTES = 25 * 1024


def _tail_shard_target(context: RunContext, buffer: list[dict]) -> int:
    """Return the shard byte target for the buffer being sealed: the unsealed backlog.

    The target tracks the backlog still waiting in this buffer, split across the worker limit, so
    the shards run in parallel on workers that would otherwise idle — and it shrinks as the buffer
    drains. Early in a run the buffer is large and full shards are right. As the producing lane
    ends, the backlog is what is left, and a small remainder seals as a small shard that finishes
    quickly instead of a full-size shard that runs alone after the lane ends. Measured on run two:
    the final verification shard sealed at 40KB of candidates when the review lane had drained and
    ran 238s alone; tracking the backlog, the trailing remainders seal smaller and finish sooner.
    The cost is more packets — each carries the ~90s fixed read — but those run in parallel on
    workers that would otherwise idle, so the wall-clock trade is positive when the buffer
    outlives the producing lane. The floor keeps a shard worth sending: below it the fixed read
    would dominate.
    """
    limit = max(_worker_limit(context, _selection(context, REVIEW_LANE).provider), 1)
    backlog = max(_buffer_bytes(buffer), 1)
    return min(_TAIL_SHARD_MAX_BYTES, max(_TAIL_SHARD_MIN_BYTES, -(-backlog // limit)))


def _take_shard(buffer: list[dict], target_bytes: int, *, identity_key: str | None = None) -> list[dict]:
    """Take one shard from the buffer, removing the taken candidates by identity."""
    shard = _shard_prefix(buffer, target_bytes, identity_key=identity_key)
    taken = {id(candidate) for candidate in shard}
    buffer[:] = [candidate for candidate in buffer if id(candidate) not in taken]
    return shard


def _review_lane_terminal(context: RunContext) -> bool:
    """Report whether every planned review packet has reached a terminal state."""
    done, planned = _review_progress_counts(context)
    return planned > 0 and done >= planned


def _seal_verification_shards(context: RunContext, pending: list[ReviewPacket]) -> None:
    """Seal one verification packet per full shard in the unverified buffer."""
    target = _tail_shard_target(context, context.tail_unverified)
    while _buffer_bytes(context.tail_unverified) >= target:
        shard = _take_shard(context.tail_unverified, target)
        pending.append(_dispatch_verification(context, shard))
        _progress(context, f"streamed a verification packet ({len(shard)} candidates)")


def _tail_accumulate(context: RunContext, candidates: list[dict], pending: list[ReviewPacket]) -> None:
    """Accumulate one review receipt while preserving independent verification identities.

    A new candidate appends. Only duplicates with the same pipeline identity may merge before
    verification; one verifier result then owns that complete logical identity. Equivalent claims
    with distinct identities stay separate until both are verified, after which the final host
    merge combines their provenance and dispositions. A duplicate whose same-ID twin already left
    also rides forward so conflicting evidence is reconciled without completion-order authority.
    The only droppable candidate is a byte-identical copy already in the stream.
    """
    for candidate in candidates:
        if any(
            _canonical_candidate(candidate) == _canonical_candidate(existing)
            for existing in context.tail_candidates
            if _same_candidate(existing, candidate)
        ):
            continue
        index = _find_duplicate(candidate, context.tail_candidates)
        if index is None or _candidate_id(context.tail_candidates[index]) != _candidate_id(candidate):
            context.tail_candidates.append(candidate)
            context.tail_unverified.append(candidate)
            continue
        kept = context.tail_candidates[index]
        if _candidate_id(kept) in context.tail_sealed_ids:
            context.tail_candidates.append(candidate)
            context.tail_unverified.append(candidate)
            continue
        # Whichever copy wins, the loser's provenance rides with it: the winner carries the
        # union in both directions, so the streamed result and the batch result carry the same
        # provenance and the coverage guard sees every identifier that entered the tail.
        if _pick_better(kept, candidate, context.receipts) is candidate:
            merged_candidate = _union_provenance(candidate, kept)
            context.tail_candidates[index] = merged_candidate
            context.tail_unverified[context.tail_unverified.index(kept)] = merged_candidate
        else:
            merged_kept = _union_provenance(kept, candidate)
            context.tail_candidates[index] = merged_kept
            context.tail_unverified[context.tail_unverified.index(kept)] = merged_kept
    _seal_verification_shards(context, pending)


def _verification_packets(context: RunContext) -> list[ReviewPacket]:
    """Packetize the candidates the stream has not dispatched yet: the sub-target remainder.

    Full shards left during the review stage through `_tail_accumulate`. The completion hook
    calls this when the last review packet reports; the mop-up drain calls it again as the safety
    net for stop paths. The buffer swap makes both calls idempotent, and the streaming sharder
    keeps duplicate logical identities in separate packets.
    """
    if not context.tail_unverified:
        return []
    buffer, context.tail_unverified = context.tail_unverified, []
    target = _tail_shard_target(context, buffer)
    packets = []
    while buffer:
        packets.append(_dispatch_verification(context, _take_shard(buffer, target)))
    return packets


def _verification_dispositions(context: RunContext) -> dict[str, dict]:
    """Return the verifier disposition for every answered candidate, reconciled once."""
    if context.verification_packets and context.verification_merged is None:
        _reconcile_verification(context)
    return context.verification_merged or {}


def _reconcile_verification(context: RunContext) -> None:
    """Account for every candidate that entered verification, and collect the dispositions.

    Every input candidate appears exactly once across its packet's dispositions; an unknown or
    malformed disposition is rejected with a gap,
    and a candidate the verifier never answered rides forward unverified with a gap. A packet
    whose arithmetic cannot close loses all its dispositions, and the imbalance blocks
    `complete`, because a run that cannot prove nothing was lost has no verdict to give. A
    candidate itself is never deleted: a refuted one keeps its disposition and the verifier's
    evidence.
    """
    if context.verification_merged is not None:
        return
    receipts = {receipt.get("packet_id"): receipt for receipt in context.receipts}
    dispositions: dict[str, dict] = {}
    feedback_dispositions: dict[str, dict] = {}
    accounting = {"in": 0, "verified": 0, "unverified": 0, "rejected": 0}
    assigned_ids: set[str] = set()
    for packet in context.verification_packets:
        if packet.feedback_findings:
            receipt = receipts.get(packet.packet_id)
            if receipt is None:
                finding_ids = [record["finding_id"] for record in packet.feedback_findings]
                context.receipt_gaps.append(
                    f"Verification {packet.packet_id} returned no receipt for feedback findings {finding_ids[:5]}."
                )
                continue
            try:
                validated = validate_feedback_dispositions(
                    receipt.get("feedback_dispositions"),
                    [record["finding_id"] for record in packet.feedback_findings],
                    _reviewed_locations(context, receipt.get("feedback_dispositions")),
                )
            except AssessmentError as error:
                context.receipt_gaps.append(
                    f"Verification {packet.packet_id} returned invalid feedback dispositions: {error}."
                )
                continue
            feedback_dispositions.update(validated)
            continue
        inputs = {_candidate_id(candidate): candidate for candidate in packet.candidates}
        assigned_ids |= set(inputs)
        accounting["in"] += len(inputs)
        receipt = receipts.get(packet.packet_id)
        if receipt is None:
            # The packet never returned (its failure became a gap, or the slice ran out): its
            # candidates ride to the verdict unverified.
            accounting["unverified"] += len(inputs)
            context.receipt_gaps.append(
                f"Verification {packet.packet_id} returned no receipt; "
                f"its {len(inputs)} candidates ride to the verdict unverified."
            )
            continue
        claimed: dict[str, dict] = {}
        packet_rejected = 0
        for position, entry in enumerate(receipt.get("dispositions") or ()):
            label = entry.get("candidate_id") if isinstance(entry, dict) else None
            label = label if isinstance(label, str) else f"disposition {position}"
            reject = None
            if not isinstance(entry, dict) or not isinstance(entry.get("candidate_id"), str):
                reject = f"{label} is not an object with a candidate_id"
            elif entry["candidate_id"] not in inputs:
                reject = f"{label} names a candidate no packet input contains"
            elif entry["candidate_id"] in claimed:
                reject = f"{label} already has a disposition from this packet"
            elif entry.get("disposition") not in ("upheld", "refuted", "uncertain"):
                reject = f"{label} is not upheld, refuted, or uncertain"
            elif entry.get("ownership") not in ("introduced_or_worsened", "pre_existing", "uncertain"):
                reject = f"{label} has no valid delta-ownership classification"
            elif not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
                reject = f"{label} carries no evidence"
            if reject is not None:
                packet_rejected += 1
                context.receipt_gaps.append(
                    f"Verification {packet.packet_id} returned an invalid disposition ({label}): {reject}; "
                    "the disposition was rejected."
                )
                continue
            candidate = inputs[entry["candidate_id"]]
            # The reviewer's position rides beside the verifier's: severity and title are the
            # first pass's confidence, and the disposition and evidence are the falsifier's.
            claimed[entry["candidate_id"]] = {
                "disposition": entry["disposition"],
                "ownership": entry["ownership"],
                "evidence": entry["evidence"],
                "severity": candidate.get("severity"),
                "title": candidate.get("title"),
            }
        missing = sorted(set(inputs) - set(claimed))
        for candidate_id in missing:
            context.receipt_gaps.append(
                f"Verification {packet.packet_id} returned no disposition for candidate {candidate_id}; "
                "it rides to the verdict unverified."
            )
        if len(inputs) != len(packet.candidates) or len(claimed) + len(missing) != len(inputs):
            # The packet's arithmetic does not close, so nothing it returned can be trusted:
            # discard its dispositions and mark every input unverified.
            _record_imbalance(
                context,
                packet.packet_id,
                f"inputs={len(inputs)} carried={len(packet.candidates)} verified={len(claimed)} "
                f"unverified={len(missing)}",
                lane=VERIFICATION_LANE,
            )
            accounting["unverified"] += len(inputs)
            accounting["rejected"] += packet_rejected
            continue
        for candidate_id, record in claimed.items():
            dispositions[candidate_id] = _combine_verification_records(dispositions.get(candidate_id), record)
        accounting["verified"] += len(claimed)
        accounting["unverified"] += len(missing)
        accounting["rejected"] += packet_rejected
    # The union of every packet's inputs must equal the accumulated stream set, and the totals
    # must close. Candidates still waiting in the unverified buffer count as accounted only
    # while the tail is open; anything else is corruption: discard the stage's dispositions.
    full = {_candidate_id(candidate) for candidate in context.tail_candidates}
    pending_ids = set() if context.tail_closed else {_candidate_id(candidate) for candidate in context.tail_unverified}
    if (
        assigned_ids | pending_ids != full
        or assigned_ids & pending_ids
        or accounting["in"] != accounting["verified"] + accounting["unverified"]
    ):
        _record_imbalance(
            context,
            "verification-accounting",
            f"totals inputs={accounting['in']} verified={accounting['verified']} "
            f"unverified={accounting['unverified']} candidate set={len(full)} assigned={len(assigned_ids)}",
            lane=VERIFICATION_LANE,
        )
        dispositions = {}
        accounting = {"in": len(full), "verified": 0, "unverified": len(full), "rejected": 0}
    context.verification_accounting = accounting
    context.verification_merged = dispositions
    context.feedback_merged = feedback_dispositions


def _candidate_sources(candidate: dict) -> list[str]:
    """Return the provenance of one candidate: its source list, or itself when raw.

    A raw candidate has no source list, so it is its own source. The union is therefore defined
    for every combination of merged and unmerged candidates.
    """
    sources = candidate.get("source_candidate_ids")
    if isinstance(sources, list) and sources:
        return [str(source) for source in sources]
    return [str(candidate.get("candidate_id") or _candidate_id(candidate))]


def _union_provenance(winner: dict, *others: dict) -> dict:
    """Return the winner carrying the union of every merged copy's provenance.

    `_pick_better` discards the loser whole, and with it the loser's source list: a candidate
    that absorbs a previous merge would publish only its own sources, and the discarded ones
    would read as dropped on the disagreement surface. The key is added only when a merge
    combined provenance, so an unmerged or same-identifier candidate is unchanged byte for byte.
    """
    union = list(dict.fromkeys(source for candidate in (winner, *others) for source in _candidate_sources(candidate)))
    if union == _candidate_sources(winner):
        return winner
    return {**winner, "source_candidate_ids": union}


def _merge_candidates(
    candidates: list[dict],
    receipts: list[dict],
    *,
    protected_ids: set[str] | None = None,
) -> list[dict]:
    """Deduplicate candidates by rule ID, path, and overlapping line ranges.

    Every merge keeps the loser's provenance on the survivor, so the union over the survivors
    still covers every identifier that entered the merge.
    """
    protected_ids = protected_ids or set()
    result: list[dict] = []
    for candidate in candidates:
        replacement_index = _find_duplicate(candidate, result, protected_ids=protected_ids)
        if replacement_index is None:
            result.append(candidate)
        else:
            kept = result[replacement_index]
            result[replacement_index] = _union_provenance(_pick_better(kept, candidate, receipts), kept, candidate)
    return result


def _find_duplicate(candidate: dict, kept: list[dict], *, protected_ids: set[str] | None = None) -> int | None:
    """Return the index of a kept candidate that duplicates the given one, or None."""
    protected_ids = protected_ids or set()
    for index, existing in enumerate(kept):
        if {_candidate_id(candidate), _candidate_id(existing)}.intersection(protected_ids) and _candidate_id(
            candidate
        ) != _candidate_id(existing):
            continue
        if _same_candidate(existing, candidate):
            return index
    return None


def _same_candidate(left: dict, right: dict) -> bool:
    """Merge only exact identities or byte-equivalent claims at the same complete locations."""
    if left.get("delta_evidence") != right.get("delta_evidence"):
        return False
    left_id = left.get("candidate_id")
    right_id = right.get("candidate_id")
    if left_id and right_id and left_id == right_id:
        return True
    left_rules = set(left.get("rule_ids") or ())
    right_rules = set(right.get("rule_ids") or ())
    if not left_rules.intersection(right_rules) or left.get("locations") != right.get("locations"):
        return False
    fields = ("title", "impact", "evidence", "fix_direction")
    left_claim = tuple(" ".join(str(left.get(field) or "").split()).casefold() for field in fields)
    right_claim = tuple(" ".join(str(right.get(field) or "").split()).casefold() for field in fields)
    return all(left_claim) and left_claim == right_claim


def _candidate_path(candidate: dict) -> str | None:
    """Return the first location path from a candidate, or None."""
    locations = candidate.get("locations") or ()
    for location in locations:
        path = location.get("path")
        if path:
            return path
    return None


def _candidate_line(candidate: dict) -> int | None:
    """Return the first location line from a candidate, or None."""
    locations = candidate.get("locations") or ()
    for location in locations:
        line = location.get("line")
        if line is not None:
            return line
    return None


def _candidate_id(candidate: dict) -> str:
    """Return the pipeline-computed stable identity of one candidate.

    The hash covers the rule identifiers, the first location path, the line, and the title, so
    the same candidate gets the same identifier in a later run and a reader can follow one
    finding across runs. Only the pipeline computes it: file-review workers never see it, while
    verification and final-synthesis workers receive it in their packet payload.
    """
    return canonical_hash(
        [
            sorted(str(rule_id) for rule_id in candidate.get("rule_ids") or ()),
            _candidate_path(candidate),
            _candidate_line(candidate),
            str(candidate.get("title") or ""),
            candidate.get("delta_evidence"),
        ]
    )[:16]


def _pick_better(left: dict, right: dict, receipts: list[dict]) -> dict:
    """Keep the candidate with longer evidence, preferring file-packet over global-packet."""
    left_is_file = _is_file_packet_candidate(left, receipts)
    right_is_file = _is_file_packet_candidate(right, receipts)
    if left_is_file and not right_is_file:
        return left
    if right_is_file and not left_is_file:
        return right
    if len(right.get("evidence") or "") > len(left.get("evidence") or ""):
        return right
    return left


def _verify_rule_coverage(packets: list[ReviewPacket], applicable: tuple[Rule, ...]) -> None:
    """Raise when the packet plan does not assign every applicable rule."""
    assigned = {rule.id for packet in packets for rule in packet.rules}
    missing = {rule.id for rule in applicable} - assigned
    if missing:
        raise RuntimeError(f"packet plan is missing rules: {sorted(missing)}")


def _is_file_packet_candidate(candidate: dict, receipts: list[dict]) -> bool:
    """Tell whether a candidate came from a file-review packet."""
    for receipt in receipts:
        if candidate in (receipt.get("candidates") or ()):
            return receipt.get("phase") == "file-review"
    return False


def _initial_packets(context: RunContext) -> list[ReviewPacket]:
    """Create the scoped-mode packets: one per file group, plus the global-rule packets."""
    return _scoped_packets(context, _applicable_rules(context))


def _scoped_packets(context: RunContext, rules: tuple[Rule, ...]) -> list[ReviewPacket]:
    """Create the file-grouped packets and the global-rule packets for the one review shape."""
    file_rules = tuple(rule for rule in rules if rule.target == "file")
    global_rules = tuple(rule for rule in rules if rule.target == "global")
    limit = _worker_limit(context, _selection(context, REVIEW_LANE).provider)
    files_per_packet = _files_per_packet(len(context.files), len(file_rules), limit)
    file_groups = tuple(
        context.files[start : start + files_per_packet] for start in range(0, len(context.files), files_per_packet)
    )
    # A registry that outgrows the work budget splits its rules across packets per file group,
    # so the rules x files bound holds for every packet. The current registry (123 file rules)
    # fits in one chunk, so this loop produces one chunk per group today.
    rule_chunks = _chunks(file_rules, _PACKET_WORK_BUDGET) if len(file_rules) > _PACKET_WORK_BUDGET else (file_rules,)
    packets = [
        _scoped_packet(context, REVIEW_LANE, "file-review", group, chunk)
        for group in file_groups
        for chunk in rule_chunks
    ]
    if global_rules:
        slots = max(1, limit - len(file_groups))
        categories = tuple(
            tuple(rule for rule in global_rules if rule.category == category)
            for category in dict.fromkeys(rule.category for rule in global_rules)
        )
        budget = _rule_budget(categories, slots)
        packets.extend(
            _packet(context, REVIEW_LANE, "scope-review", None, chunk)
            for category in categories
            for chunk in _chunks(category, budget)
        )
    return sorted(packets, key=lambda packet: len(packet.rules))


def _files_per_packet(file_count: int, rule_count: int, limit: int) -> int:
    """Return the file-group size, bounded by measured packet work instead of file count alone.

    The work in one packet is roughly rules x files, and the measured rates above put one
    rule-file unit at 1.21s median and 1.98s worst. The budget keeps a packet's worst case near
    500s, about 70% of the ~729s prompt-scaled wall that killed the 369-unit packets in the
    MR 1352 run. Inside the bound the group still grows to fill one worker wave, as before.
    """
    wave_fill = max(1, -(-file_count // max(limit, 1)))
    work_bound = max(1, _PACKET_WORK_BUDGET // max(rule_count, 1))
    return max(1, min(wave_fill, work_bound))


def _chunks(rules: tuple[Rule, ...], budget: int) -> tuple[tuple[Rule, ...], ...]:
    """Divide one category into the fewest near-equal packets that respect the rule budget."""
    count = max(-(-len(rules) // max(budget, 1)), 1)
    size, extra = divmod(len(rules), count)
    parts = []
    start = 0
    for index in range(count):
        stop = start + size + (1 if index < extra else 0)
        parts.append(rules[start:stop])
        start = stop
    return tuple(parts)


def _rule_budget(categories: tuple[tuple[Rule, ...], ...], limit: int) -> int:
    """Return the smallest packet size that still keeps the global-rule packets inside one worker wave."""
    total = sum(len(category) for category in categories)
    smallest = max(-(-total // max(limit, 1)), 1)
    for budget in range(smallest, total + 1):
        if sum(-(-len(category) // budget) for category in categories) <= limit:
            return budget
    return smallest


def _worker_limit(context: RunContext, provider_name: str) -> int:
    """Return the concurrent worker limit for one provider."""
    return context.jobs or context.providers[provider_name].initial_jobs


def _packet_files(context: RunContext, packet: ReviewPacket) -> tuple[str, ...]:
    """Return the files that one packet owns."""
    if packet.paths:
        return packet.paths
    return context.files if packet.path is None else (packet.path,)


def _packet(context: RunContext, lane: str, phase: str, path: str | None, rules: tuple[Rule, ...]) -> ReviewPacket:
    """Build one single-path or whole-scope packet."""
    files = context.files if path is None else (path,)
    fingerprint = {file: context.file_hashes.get(file) for file in files}
    packet_id = canonical_hash([lane, phase, path, [rule.id for rule in rules], fingerprint])[:16]
    return ReviewPacket(f"{lane}-{phase}-{packet_id}", lane, phase, path, rules)


def _scoped_packet(
    context: RunContext, lane: str, phase: str, paths: tuple[str, ...], rules: tuple[Rule, ...]
) -> ReviewPacket:
    """Build one multi-file packet for scoped mode."""
    fingerprint = {file: context.file_hashes.get(file) for file in paths}
    packet_id = canonical_hash([lane, phase, list(paths), [rule.id for rule in rules], fingerprint])[:16]
    return ReviewPacket(f"{lane}-{phase}-{packet_id}", lane, phase, None, rules, paths=paths)


def _canary(context: RunContext, lane: str) -> ReviewPacket:
    """Build one cheap probe that proves a provider can start, read one file, and return a receipt."""
    return _packet(context, lane, "provider-canary", context.files[0] if context.files else None, ())


def _run_canary_gate(context: RunContext, lanes: tuple[str, ...], stop_at: float | None) -> bool:
    """Prove provider access to one temporary exact-head challenge before review fan-out."""
    path = context.repository / f".remix-review-canary-{uuid.uuid4().hex}"
    challenge = secrets.token_hex(32)
    context.canary_artifact_path = path
    context.canary_challenge = challenge
    context.canary_read_attested = False
    created = False
    errors = []
    try:
        try:
            with path.open("x", encoding="ascii", newline="") as stream:
                created = True
                stream.write(challenge)
        except OSError as error:
            errors.append(f"could not create the exact-head read challenge: {error.strerror or error}")
        else:
            _drain(context, [_canary(context, lane) for lane in lanes], stop_at=stop_at)
            if not context.canary_read_attested and not _canary_failed(context):
                errors.append("provider canary did not prove an exact-head checkout read")
    finally:
        if created:
            try:
                if path.read_text(encoding="ascii") != challenge:
                    errors.append("the exact-head read challenge changed during the canary")
            except OSError as error:
                errors.append(f"could not verify the exact-head read challenge: {error.strerror or error}")
            try:
                path.unlink()
            except OSError as error:
                errors.append(f"could not remove the exact-head read challenge: {error.strerror or error}")
        context.canary_artifact_path = None
        context.canary_challenge = None
        try:
            _verify_checkout(context)
        except RuntimeError as error:
            errors.append(f"could not re-attest the review checkout after the canary: {error}")
    if errors:
        context.failures.append(
            PacketFailure(
                "review-provider-canary-gate",
                REVIEW_LANE,
                "; ".join(errors),
                _selection(context, REVIEW_LANE).provider,
                "CANARY_READ_FAILED",
                False,
            )
        )
    return not errors and not _canary_failed(context)


def _packet_payload(context: RunContext, packet: ReviewPacket, contract: dict) -> dict:
    """Materialize immutable JSON only at the provider boundary."""
    files = _packet_files(context, packet)
    owned = set(files)
    payload = {
        "schema_version": 2 if packet.phase in ("verification", "final-synthesis") else 1,
        "packet_id": packet.packet_id,
        "lane": packet.lane,
        "phase": packet.phase,
        "review_root": str(context.repository),
        "scope_patch": str(context.scope_patch),
        "receipt_contract": contract,
    }
    if packet.phase in ("final-synthesis", "synthesis-compaction"):
        payload.update(
            synthesis_context={
                "path": str(context.synthesis_context_path),
                "sha256": context.synthesis_context_sha256,
                "counts": context.synthesis_context_counts,
            },
            applicable_rule_ids=[rule.id for rule in _applicable_rules(context)],
        )
    else:
        payload.update(
            files=files,
            changes=[asdict(change) for change in context.changes if _change_path(change) in owned],
            rules=[asdict(rule) for rule in packet.rules],
            forge_evidence=context.forge_evidence,
        )
    if packet.phase == "provider-canary":
        payload["canary_artifact_path"] = str(context.canary_artifact_path)
    if packet.prior_error is not None:
        payload["prior_error"] = packet.prior_error
    if packet.phase == "verification":
        # The reconciler matches dispositions by pipeline identity, so the worker must see it.
        # The verifier returns dispositions only: the schema forbids candidates and findings.
        payload.update(
            validated_candidates=[
                {**candidate, "candidate_id": _candidate_id(candidate)} for candidate in packet.candidates
            ],
            feedback_findings=[record["finding"] for record in packet.feedback_findings],
            feedback_evidence=[
                {"finding_id": record["finding_id"], "text": record["response"]} for record in packet.feedback_findings
            ],
        )
    if packet.phase == "synthesis-compaction":
        payload.update(
            candidate_representation="full",
            validated_candidates=[_full_synthesis_candidate(context, candidate) for candidate in packet.candidates],
        )
    if packet.phase == "final-synthesis":
        gaps = [*context.evidence_gaps, *(failure.error for failure in context.failures)]
        representation = "digest" if context.synthesis_digests else "full"
        candidates = [
            (
                _digest_synthesis_candidate(context, candidate)
                if representation == "digest"
                else _full_synthesis_candidate(context, candidate)
            )
            for candidate in _synthesis_candidates(context)
        ]
        payload.update(
            candidate_representation=representation,
            validated_candidates=candidates,
            gaps=gaps,
        )
    return payload


def _synthesis_candidate_identity(candidate: dict) -> dict:
    """Return the original identity and ownership fields shared by both synthesis representations."""
    identity = {
        "candidate_id": _synthesis_candidate_id(candidate),
        "rule_ids": candidate.get("rule_ids") or [],
        "locations": [
            {"path": location.get("path", ""), "line": location.get("line")}
            for location in candidate.get("locations") or ()
        ],
        "severity": candidate.get("severity", ""),
        "title": candidate.get("title", ""),
        "delta_evidence": candidate.get("delta_evidence"),
    }
    for name in ("claim_class", "causal_basis"):
        if isinstance(candidate.get(name), str) and candidate[name]:
            identity[name] = candidate[name]
    return identity


def _synthesis_candidate_id(candidate: dict) -> str:
    """Return the host-assigned synthesis ID, computing it only for legacy raw candidates."""
    return str(candidate.get("candidate_id") or _candidate_id(candidate))


def _synthesis_verification(context: RunContext, candidate: dict, *, include_evidence: bool = True) -> dict | None:
    """Return only verifier-owned fields for a synthesis candidate."""
    record = _candidate_disposition(candidate, _verification_dispositions(context))
    if record is None:
        return None
    result = {
        "disposition": record.get("disposition"),
        "ownership": record.get("ownership"),
    }
    if include_evidence:
        result["evidence"] = record.get("evidence")
    return result


def _full_synthesis_candidate(context: RunContext, candidate: dict) -> dict:
    """Return one complete original candidate for direct final synthesis or digest creation."""
    dispositions = _verification_dispositions(context)
    return {
        **_synthesis_candidate_identity(candidate),
        "impact": candidate.get("impact", ""),
        "evidence": candidate.get("evidence", ""),
        "fix_direction": candidate.get("fix_direction", ""),
        "verification": _synthesis_verification(context, candidate),
        "drop_evidence_refs": _drop_evidence_refs(candidate, dispositions),
    }


def _digest_synthesis_candidate(context: RunContext, candidate: dict) -> dict:
    """Return one bounded digest while retaining host-owned identity and verifier authority."""
    candidate_id = _synthesis_candidate_id(candidate)
    digest = context.synthesis_digests[candidate_id]
    dispositions = _verification_dispositions(context)
    return {
        **_synthesis_candidate_identity(candidate),
        "claim_summary": digest["claim_summary"],
        "verification_summary": digest["verification_summary"],
        "verification": _synthesis_verification(context, candidate, include_evidence=False),
        "drop_evidence_refs": _drop_evidence_refs(candidate, dispositions),
    }


def _worker_read_paths(
    repository: Path,
    scope_patch: Path,
    scope_artifacts: Path | None = None,
    schema_path: Path | None = None,
) -> tuple[Path, ...]:
    """Return only the exact review snapshot and packet-owned artifact read roots."""
    paths = {repository.resolve(), scope_patch.resolve()}
    if scope_artifacts is not None:
        paths.add(scope_artifacts.resolve())
    if schema_path is not None:
        paths.add(schema_path.resolve())
    return tuple(sorted(paths, key=str))


# Worker timeout scaling, chosen from a measured full-scale run of this merge request (39 files,
# 19 receipts): file workers finished in 220 to 562 seconds, and the synthesis packet, with a
# 125KB prompt, exceeded the flat 600-second default three times and produced no verdict. The
# timeout now scales with the prompt size, and synthesis gets its own floor above that measured
# maximum, because it must read every receipt and produce the verdict.
_WORKER_TIMEOUT_BASE_SECONDS = 600.0
_WORKER_TIMEOUT_PER_KB_SECONDS = 2.0
_SYNTHESIS_TIMEOUT_FLOOR_SECONDS = 900.0


def _scaled_timeout(prompt_bytes: float) -> float:
    """Return the prompt-scaled worker timeout without the synthesis floor."""
    return _WORKER_TIMEOUT_BASE_SECONDS + _WORKER_TIMEOUT_PER_KB_SECONDS * (prompt_bytes / 1024.0)


def _worker_timeout(packet: ReviewPacket, prompt_bytes: int) -> float:
    """Return the worker timeout for one packet, scaled to its prompt size.

    A single synthesis pass carries every receipt and produces the verdict, so it gets a floor
    above the measured 562-second file-worker maximum, plus headroom for its larger prompt.
    """
    scaled = _scaled_timeout(prompt_bytes)
    if packet.phase == "final-synthesis":
        return max(_SYNTHESIS_TIMEOUT_FLOOR_SECONDS, scaled)
    return scaled


def _synthesis_prompt_bytes(file_count: int) -> int:
    """Return the predicted final prompt size after deterministic host merging."""
    return _FIXED_PROMPT_BYTES + file_count * _MEASURED_CANDIDATE_BYTES_PER_FILE


def _synthesis_reserve_seconds(context: RunContext) -> float:
    """Return the final reserve plus every predicted compaction wave at initial concurrency."""
    file_count = len(context.files)
    predicted = _synthesis_prompt_bytes(file_count)
    final = max(_SYNTHESIS_TIMEOUT_FLOOR_SECONDS, _scaled_timeout(min(predicted, _SYNTHESIS_PROMPT_MAX_BYTES)))
    if predicted <= _SYNTHESIS_PROMPT_MAX_BYTES:
        return final
    candidate_bytes = max(predicted - _FIXED_PROMPT_BYTES, 1)
    usable_packet_bytes = max(_SYNTHESIS_COMPACTION_TARGET_BYTES - _FIXED_PROMPT_BYTES, 1)
    packet_count = -(-candidate_bytes // usable_packet_bytes)
    provider = _selection(context, SYNTHESIS_LANE).provider
    wave_count = -(-packet_count // max(_worker_limit(context, provider), 1))
    return final + wave_count * _scaled_timeout(_SYNTHESIS_COMPACTION_TARGET_BYTES)


def _tail_chain_seconds(file_count: int) -> float:
    """Return the serial tail chain the review window cannot hide, at the measured per-KB rate.

    The chain is the last sub-target verification shard followed by the final pass. The remainder
    shard holds what the last review receipts produced: half a target's worth on average.
    """
    candidate_bytes = file_count * _MEASURED_CANDIDATE_BYTES_PER_FILE
    final_bytes = min(_synthesis_prompt_bytes(file_count), _SYNTHESIS_PROMPT_MAX_BYTES)
    compaction_bytes = (
        _SYNTHESIS_COMPACTION_TARGET_BYTES if _synthesis_prompt_bytes(file_count) > _SYNTHESIS_PROMPT_MAX_BYTES else 0
    )
    remainder_bytes = _FIXED_PROMPT_BYTES + min(candidate_bytes, _TAIL_SHARD_MAX_BYTES) / 2
    return (_MEASURED_SECONDS_PER_PROMPT_KB / 1024.0) * (remainder_bytes + compaction_bytes + final_bytes)


# Measured minimum stage latencies: the fastest any packet of that stage has ever finished on a
# real run. The irreducible serial depth of a run is the sum of these for the stages that must
# run in sequence, because a candidate must be produced, verified, and read by the final
# pass, and the final pass cannot start until every candidate exists. The provider read canary
# also runs before review fan-out. These are floors from
# measurement, not timeouts: a stage cannot finish faster than its fastest observed packet.
_SERIAL_DEPTH_CANARY_SECONDS = 15.0  # exact-head provider canary measured at 14.843s
_SERIAL_DEPTH_REVIEW_SECONDS = 108.0  # medium calibration file-packet minimum
_SERIAL_DEPTH_VERIFY_SECONDS = 245.0  # 13-file run verification minimum


def _serial_depth_seconds(context: RunContext) -> float:
    """Return the minimum budget compatible with the run's reserved final slice.

    The provider first proves it can read the exact-head checkout. A candidate is then produced by
    a review packet and verified before the final pass. The upstream terms are measured minimum
    latencies; the final term is the actual slice the scheduler reserves. No accepted plan can
    therefore begin with its review cutoff already in the past.
    """
    return (
        _SERIAL_DEPTH_CANARY_SECONDS
        + _SERIAL_DEPTH_REVIEW_SECONDS
        + _SERIAL_DEPTH_VERIFY_SECONDS
        + _synthesis_reserve_seconds(context)
    )


def _plan_deadline(context: RunContext) -> None:
    """Set the synthesis reserve and reject a deadline that leaves no viable upstream window.

    This is not a whole-run prediction. The gate adds measured upstream minimums to the final
    slice the scheduler actually reserves, so an accepted run can start its canary and review
    before that cutoff. The packet plan and lane counts are printed by the caller.
    """
    if context.deadline_seconds is None:
        return
    context.synthesis_reserve_seconds = _synthesis_reserve_seconds(context)
    serial_depth = _serial_depth_seconds(context)
    remaining = (
        max(context.deadline_mono - time.monotonic(), 0.0)
        if context.deadline_mono is not None
        else context.deadline_seconds
    )
    if remaining < serial_depth:
        raise PlanRefusedError(
            f"the {context.deadline_seconds:.0f}s deadline has {remaining:.0f}s remaining after preparation, below "
            "the review's minimum schedulable depth of "
            f"about {serial_depth:.0f}s: even a single file must pass the provider canary, review, "
            f"and verification before the reserved final-synthesis slice, and workers cannot "
            f"parallelize away. Raise --deadline-seconds above {int(-(-serial_depth // 1))} or accept a "
            f"incomplete result."
        )


def _plan_feedback_deadline(context: RunContext, packets: list[ReviewPacket]) -> float:
    """Return the verifier reserve after rejecting an impossible feedback deadline."""
    context.synthesis_reserve_seconds = 0.0
    if context.deadline_seconds is None:
        return 0.0
    verifier_timeout = max(
        (_worker_timeout(packet, _packet_prompt_size(context, packet)[1]) for packet in packets),
        default=0.0,
    )
    canary = _canary(context, VERIFICATION_LANE)
    required = _worker_timeout(canary, _packet_prompt_size(context, canary)[1]) + verifier_timeout
    remaining = (
        max(context.deadline_mono - time.monotonic(), 0.0)
        if context.deadline_mono is not None
        else context.deadline_seconds
    )
    if remaining < required:
        raise PlanRefusedError(
            f"the {context.deadline_seconds:.0f}s deadline has {remaining:.0f}s remaining after preparation, below "
            f"the feedback adjudication budget of about {required:.0f}s for its canary and largest verifier"
        )
    return verifier_timeout


def _review_stop_at(context: RunContext) -> float | None:
    """Return when review workers must stop so synthesis keeps its reserved slice."""
    if context.deadline_mono is None:
        return None
    return context.deadline_mono - context.synthesis_reserve_seconds


def _verification_stop_at(context: RunContext) -> float | None:
    """Return when verification must stop so the synthesis stage keeps its full reserved slice.

    Verification owns the window between the review stage and the synthesis reserve: it starts
    when review finishes and ends where synthesis must start. A saturated review leaves it no
    time, and then every candidate rides forward unverified with a gap.
    """
    if context.deadline_mono is None:
        return None
    return context.deadline_mono - context.synthesis_reserve_seconds


def _canary_failed(context: RunContext) -> bool:
    """Report whether a provider canary failed terminally."""
    return any("provider-canary" in failure.packet_id for failure in context.failures)


def _deadline_exceeded(context: RunContext) -> bool:
    """Report whether the run deadline already stopped a stage."""
    return any(failure.code == DEADLINE_FAILURE_CODE for failure in context.failures)


def _stop_stage_at_deadline(context: RunContext, pending: list[ReviewPacket]) -> None:
    """Stop the current stage at the deadline and report every packet that never ran.

    This reuses the existing stop path: terminate the pools first, then reconcile the
    bookkeeping. Packets that never ran have no receipt, so `_finish` names their rules as
    unevaluated and the run exits non-zero.
    """
    lane = REVIEW_LANE
    if pending:
        lane = pending[0].lane
    elif context.active:
        lane = next(iter(context.active.values())).lane
    _progress(context, "deadline arrived, stopping the stage", force=True)
    for pool in context.pools.values():
        pool.terminate_all()
    _cancel_in_flight(context, "deadline")
    pending.clear()
    if _deadline_exceeded(context):
        return
    if lane == VERIFICATION_LANE:
        # Verification is advisory: a spent slice never blocks the run. The reconciler marks
        # every candidate without a disposition as unverified and names each one in a gap.
        context.receipt_gaps.append(
            "the verification stage stopped at its deadline slice; "
            "candidates without a disposition ride to the verdict unverified"
        )
        return
    context.failures.append(
        PacketFailure(
            "run-deadline",
            lane,
            f"the {context.deadline_seconds:.0f}s deadline arrived and the run stopped before every packet finished",
            None,
            DEADLINE_FAILURE_CODE,
            False,
            "Re-run with a larger --deadline-seconds, a higher --jobs value, or a smaller scope.",
        )
    )


def _cancel_in_flight(context: RunContext, outcome: str) -> None:
    """Reconcile the bookkeeping after a stop path terminated the worker processes.

    Every worker still in flight will never report, so its entry must not survive in `active` or
    `worker_starts` as if it were pending. Record one timing row per in-flight worker with the
    cancellation outcome and the real elapsed time, then clear both maps. After this runs, the
    timings file accounts for every worker that started, and the progress payload reports zero
    active. Call this from every stop path after the pools are terminated.
    """
    stopped_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")  # noqa: UP017
    for worker_id, active_packet in tuple(context.active.items()):
        started_at, start_mono, prompt_bytes, prompt_characters = context.worker_starts.pop(
            worker_id, (stopped_at, time.monotonic(), 0, 0)
        )
        context.worker_timings.append(
            WorkerTiming(
                packet_id=active_packet.packet_id,
                lane=active_packet.lane,
                phase=active_packet.phase,
                attempt=active_packet.attempt,
                rule_count=len(active_packet.rules),
                file_count=len(_packet_files(context, active_packet)),
                started_at=started_at,
                duration_seconds=round(time.monotonic() - start_mono, 4),
                returncode=-1,
                outcome=outcome,
                prompt_bytes=prompt_bytes,
                prompt_characters=prompt_characters,
                reasoning=_selection(context, active_packet.lane).reasoning,
            )
        )
        del context.active[worker_id]


def _abort_moving_snapshot(context: RunContext, packet: ReviewPacket, changed_paths: list[str]) -> None:
    """Stop the run because a covered file no longer matches the run's snapshot.

    A review is a statement about one snapshot. Repairing a moving tree mid-run would mix two
    revisions of the code under one verdict, which is worse than the receipt it would save. One
    inconsistent snapshot ends the run instead: no rebuilt patch, no re-resolved scope, no
    per-receipt repair. This reuses the existing needs_user_action stop path, so `_drain` halts
    scheduling, `_finish` reports `incomplete`, and the CLI exits non-zero.
    """
    # A detached checkout at a fixed head must never change on its own; if it did, something
    # wrote into it, and that is a defect the caller needs to know about, not a normal edit.
    cause = "the review checkout changed during the run, which should never happen for a detached checkout"
    shown = ", ".join(changed_paths[:5])
    if len(changed_paths) > 5:
        shown += f", and {len(changed_paths) - 5} more"
    context.failures.append(
        PacketFailure(
            packet.packet_id,
            packet.lane,
            f"the reviewed snapshot changed: {shown}",
            _selection(context, packet.lane).provider,
            "SNAPSHOT_CHANGED",
            True,
            f"{cause[0].upper()}{cause[1:]}. Run the review again against a stable snapshot.",
        )
    )
    # Record the failure only. The `needs_user_action` stop path in `_drain` owns the order:
    # it terminates the worker processes first, then cancels their bookkeeping. The progress line
    # below therefore still counts the in-flight workers, which is correct until they are gone.
    _progress(context, "review snapshot changed mid-run, stopping", force=True)


def _start_ready(context: RunContext, pending: list[ReviewPacket]) -> None:
    for packet in tuple(pending):
        selection = _selection(context, packet.lane)
        if packet.phase == "verification" and context.verify_model is not None:
            # The verifier runs on the same provider with a fresh context; the option only
            # swaps the model, so the reviewer and the verifier need not share blind spots.
            selection = replace(selection, model=context.verify_model)
        pool = context.pools[selection.provider]
        if pool.available_slots() < 1:
            continue
        if packet.phase in ("synthesis-compaction", "final-synthesis"):
            synthesis_context_error = _synthesis_context_error(context)
            if synthesis_context_error is not None:
                pending.remove(packet)
                _fail_synthesis(context, packet.packet_id, synthesis_context_error, "SYNTHESIS_CONTEXT")
                return
        files = _packet_files(context, packet)
        current = _hashes(context.repository, files, context.file_artifacts)
        baseline = {path: context.file_hashes.get(path) for path in files}
        if current != baseline:
            changed = sorted(path for path in files if current.get(path) != baseline.get(path))
            _abort_moving_snapshot(context, packet, changed)
            return
        contract = receipt_contract(packet.phase)
        schema = contract["json_schema"]
        schema_path = context.run_dir / "schemas" / f"{canonical_hash(schema)}.json"
        write_json(schema_path, schema)
        prompt_text, prompt_payload = _prompt_payload(context, packet, contract)
        prompt_bytes = len(prompt_payload)
        prompt_characters = len(prompt_text)
        if packet.phase in ("synthesis-compaction", "final-synthesis") and prompt_bytes > _SYNTHESIS_PROMPT_MAX_BYTES:
            pending.remove(packet)
            _fail_synthesis(
                context,
                packet.packet_id,
                f"{packet.phase} requires {prompt_bytes} prompt bytes ({prompt_characters} characters), above the "
                f"{_SYNTHESIS_PROMPT_MAX_BYTES}-byte host ceiling",
            )
            return
        timeout = _worker_timeout(packet, prompt_bytes)
        if context.stage_stop_at is not None:
            remaining = context.stage_stop_at - time.monotonic()
            if packet.phase in ("provider-canary", "final-synthesis") or (
                context.review_mode == "feedback" and packet.phase == "verification"
            ):
                # The mandatory canary and synthesis passes get whatever budget their serial
                # slices hold instead of being rejected by the ordinary 600-second timeout.
                timeout = max(1.0, min(timeout, remaining))
            elif timeout > remaining:
                # This worker cannot finish inside the remaining budget, so starting it only
                # wastes a spawn. It stays pending and the `_drain` deadline path reports it.
                continue
        pending.remove(packet)
        packet.attempt += 1
        worker_id = f"{packet.packet_id}-{packet.attempt}-{uuid.uuid4().hex[:8]}"
        worker_dir = context.run_dir / "workers" / worker_id
        worker_dir.mkdir(parents=True)
        prompt_path = worker_dir / "prompt.txt"
        stdout_path = worker_dir / "stdout.json"
        stderr_path = worker_dir / "stderr.log"
        write_bytes(prompt_path, prompt_payload)
        request = WorkerRequest(
            worker_id=worker_id,
            schema_path=schema_path,
            worker_cwd=worker_dir,
            # Auto-loaded project instructions come from a bounded snapshot of the invoking
            # workspace, while reviewed-code reads are granted only from the detached head.
            project_root=context.invoking_context,
            prompt_path=prompt_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            read_paths=_worker_read_paths(
                context.repository,
                context.scope_patch,
                context.scope_artifacts,
                schema_path,
            ),
            selection=selection,
        )
        provider = context.providers[selection.provider]
        provider.prepare_workspace(request)
        spec = provider.build_worker(context.readiness[selection.provider], request)
        spec = replace(spec, timeout_seconds=timeout)
        pool.start(spec)
        packet.before_hashes = current
        context.active[worker_id] = packet
        context.worker_starts[worker_id] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),  # noqa: UP017
            time.monotonic(),
            prompt_bytes,
            prompt_characters,
        )


def _collect(context: RunContext, pending: list[ReviewPacket]) -> None:
    for provider_name, pool in context.pools.items():
        for completion in pool.poll():
            packet = context.active.pop(completion.spec.worker_id)
            _handle_completion(context, provider_name, completion, packet, pending)


def _record_timing(
    context: RunContext,
    packet: ReviewPacket,
    completion: WorkerCompletion,
    started_at: str,
    duration_seconds: float,
    prompt_bytes: int,
    prompt_characters: int,
    tokens: dict[str, int],
    outcome: str,
) -> None:
    """Record one worker process execution timing entry."""
    files = _packet_files(context, packet)
    context.worker_timings.append(
        WorkerTiming(
            packet_id=packet.packet_id,
            lane=packet.lane,
            phase=packet.phase,
            attempt=packet.attempt,
            rule_count=len(packet.rules),
            file_count=len(files),
            started_at=started_at,
            duration_seconds=duration_seconds,
            returncode=completion.returncode,
            outcome=outcome,
            prompt_bytes=prompt_bytes,
            prompt_characters=prompt_characters,
            tokens=tokens,
            reasoning=_selection(context, packet.lane).reasoning,
        )
    )


def _handle_completion(
    context: RunContext,
    provider_name: str,
    completion: WorkerCompletion,
    packet: ReviewPacket,
    pending: list[ReviewPacket],
) -> None:
    started_at, start_mono, prompt_bytes, prompt_characters = context.worker_starts.pop(
        completion.spec.worker_id,
        (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), time.monotonic(), 0, 0),  # noqa: UP017
    )
    duration_seconds = round(time.monotonic() - start_mono, 4)
    provider = context.providers[provider_name]
    tokens = provider.usage(completion.spec.stdout_path, completion.spec.stderr_path)

    def record_timing(outcome: str) -> None:
        _record_timing(
            context,
            packet,
            completion,
            started_at,
            duration_seconds,
            prompt_bytes,
            prompt_characters,
            tokens,
            outcome,
        )

    files = _packet_files(context, packet)
    current = _hashes(context.repository, files, context.file_artifacts)
    if current != packet.before_hashes:
        changed = sorted(path for path in files if current.get(path) != packet.before_hashes.get(path))
        _abort_moving_snapshot(context, packet, changed)
        record_timing("failed")
        return
    if completion.returncode:
        stdout = _worker_output(completion.spec.stdout_path)
        stderr = _worker_output(completion.spec.stderr_path)
        # A timeout kill gets its own message: "worker exited 1" tells a reader nothing.
        error = (
            f"worker timed out after {duration_seconds:.0f}s"
            if completion.timed_out
            else f"worker exited {completion.returncode}"
        )
        terminal = _retry_or_fail(context, packet, error, pending, stdout, stderr, timed_out=completion.timed_out)
        # A packet that was just split into smaller parts is recorded with its own outcome, so
        # the timings file can tell a split from a same-prompt retry.
        outcome = "failed" if terminal else ("split" if packet.packet_id in context.packet_splits else "retried")
        record_timing(outcome)
        return
    try:
        receipt = provider.decode(completion.spec.stdout_path)
    except ValueError as error:
        if context.review_mode == "feedback" and packet.phase == "verification":
            context.receipt_gaps.append(f"Verification {packet.packet_id} returned a malformed receipt: {error}.")
            record_timing("failed")
            return
        stdout = _worker_output(completion.spec.stdout_path)
        stderr = _worker_output(completion.spec.stderr_path)
        terminal = _retry_or_fail(context, packet, str(error), pending, stdout, stderr, is_decode_failure=True)
        outcome = "failed" if terminal else "retried"
        record_timing(outcome)
        return
    if packet.phase in ("synthesis-compaction", "final-synthesis"):
        synthesis_context_error = _synthesis_context_error(context)
        if synthesis_context_error is not None:
            _fail_synthesis(context, packet.packet_id, synthesis_context_error, "SYNTHESIS_CONTEXT")
            record_timing("failed")
            return
    rejection = _fatal_receipt_error(context, packet, receipt)
    if rejection is None:
        # Remove only output channels this stage cannot consume. Candidate ownership and final
        # cause membership are not repaired: malformed evidence and ambiguous grouping fail closed.
        receipt, salvage_notes = _salvage_receipt(packet, receipt)
        for note in salvage_notes:
            context.receipt_gaps.append(note)
    if rejection is None and packet.phase in ("file-review", "scope-review"):
        try:
            validate_candidate_ownership(
                receipt.get("candidates"),
                [rule.id for rule in packet.rules],
                list(files),
                delta_index=context.delta_index,
                forge_rule_ids=_forge_rule_ids(context),
            )
        except AssessmentError as error:
            rejection = str(error)
    if rejection is None and packet.phase == "synthesis-compaction":
        try:
            digests = _validated_compaction_digests(context, packet, receipt)
        except AssessmentError as error:
            rejection = str(error)
        else:
            context.synthesis_digests.update(digests)
    if rejection is None and packet.phase == "final-synthesis":
        try:
            report = _complete_final_partition(context, receipt)
        except AssessmentError as error:
            rejection = str(error)
        else:
            context.final_ranking_report = report
            if report["pipeline_placed"]:
                context.receipt_gaps.append(
                    f"Final synthesis returned {report['model_grouped']} cause groups from {report['total']} input "
                    f"candidates; the host restored {report['pipeline_placed']} omitted candidates as ordered singletons."
                )
    if rejection is not None:
        context.rejection_records.append(
            {
                "packet_id": packet.packet_id,
                "lane": packet.lane,
                "phase": packet.phase,
                "attempt": packet.attempt,
                "check": "assessment" if packet.phase == "final-synthesis" else "receipt",
                "reason": rejection[:512],
                "failure_class": "deterministic",
            }
        )
        if packet.phase == "synthesis-compaction":
            _fail_synthesis(context, packet.packet_id, rejection, "COMPACTION_RECEIPT")
            record_timing("failed")
            return
        if context.review_mode == "feedback" and packet.phase == "verification":
            context.receipt_gaps.append(f"Verification {packet.packet_id} returned a malformed receipt: {rejection}.")
            record_timing("failed")
            return
        terminal = _retry_or_fail(context, packet, rejection, pending, json.dumps(receipt)[:8192], "")
        outcome = "failed" if terminal else "rejected"
        record_timing(outcome)
        return
    record_timing("receipt")
    if packet.phase == "provider-canary":
        context.canary_read_attested = True
        _progress(context, "canary completed", force=True)
        return
    receipt.setdefault("packet_id", packet.packet_id)
    receipt.setdefault("lane", packet.lane)
    receipt.setdefault("phase", packet.phase)
    receipt.setdefault("rule_ids", [rule.id for rule in packet.rules])
    if packet.phase not in ("final-synthesis", "verification"):
        # File-review workers never see an identifier and never echo one, so the pipeline stamps
        # theirs after decoding. A verification receipt carries no candidates at all, so there is
        # nothing to stamp. A review receipt's findings are forbidden by the contract, so only
        # candidates stamp.
        for item in receipt.get("candidates") or ():
            if isinstance(item, dict):
                item["candidate_id"] = _candidate_id(item)
    receipt_path = context.run_dir / "receipts" / f"{completion.spec.worker_id}.json"
    write_json(receipt_path, receipt)
    context.receipts.append(receipt)
    # A gap records a limit and never invalidates a receipt. Carry every gap into the run gaps so
    # the reader sees what was not verified, whether or not it uses the evidence prefix.
    gaps = [str(gap) for gap in receipt.get("gaps") or ()]
    context.receipt_gaps.extend(gaps)
    if gaps:
        context.gap_packet_ids.add(receipt["packet_id"])
    context.pools[provider_name].relax()
    # Stream accepted review candidates into bounded verification packets.
    if packet.phase in ("file-review", "scope-review"):
        _tail_accumulate(context, list(receipt.get("candidates") or ()), pending)
        if _review_lane_terminal(context):
            # No more candidates can arrive once every planned review packet is terminal:
            # dispatch the sub-target remainder now instead of letting it wait for the mop-up.
            pending.extend(_verification_packets(context))
    _progress(context, "packet completed")


def _fatal_receipt_error(context: RunContext, packet: ReviewPacket, receipt: dict) -> str | None:
    """Return why one receipt is structurally unusable, or None.

    Only forbidden output channels are safely removable. Identity mismatches, unreadable canary
    proof, and malformed candidate ownership are deterministic failures that must fail closed.
    """
    if not isinstance(receipt, dict):
        return "receipt is not a JSON object"
    for name, expected in (("packet_id", packet.packet_id), ("lane", packet.lane), ("phase", packet.phase)):
        value = receipt.get(name)
        if value is not None and value != expected:
            return f"receipt {name} {value!r} does not match packet {expected!r}"
    if packet.phase == "provider-canary" and receipt.get("notes") != context.canary_challenge:
        return "provider canary did not prove an exact-head checkout read"
    if packet.phase == "verification":
        if packet.candidates and packet.feedback_findings:
            return "a verification packet cannot own candidates and feedback findings together"
        feedback_dispositions = receipt.get("feedback_dispositions")
        if not packet.feedback_findings:
            if feedback_dispositions != []:
                return "current-candidate verification must return empty feedback_dispositions"
        else:
            if receipt.get("dispositions") != []:
                return "feedback verification must return empty candidate dispositions"
            try:
                validate_feedback_dispositions(
                    feedback_dispositions,
                    [record["finding_id"] for record in packet.feedback_findings],
                    _reviewed_locations(context, feedback_dispositions),
                )
            except AssessmentError as error:
                return str(error)
    return None


def _salvage_receipt(packet: ReviewPacket, receipt: dict) -> tuple[dict, list[str]]:
    """Remove forbidden output channels and return a record of each cut.

    Returns the cleaned receipt and the list of salvage notes. Every adaptation removes a channel
    that the stage cannot consume, keeps the stage's valid channel, and names what was removed.

    - A forbidden output channel (findings on review, candidates on synthesis, either on
      verification): drop the channel, keep the receipt; the stage's own channel is the one the
      reconciler reads.
    Final cause membership and drops are not altered here. Their total partition is validated as
    one unit after salvage, because deleting an invented or duplicate membership could silently
    change which root cause the model intended.
    """
    notes = []
    cleaned = dict(receipt)

    # A forbidden output channel carries nothing the stage reads; drop it and record the cut.
    forbidden = None
    if packet.phase in ("verification", "synthesis-compaction", "final-synthesis") and (
        cleaned.get("candidates") or cleaned.get("findings")
    ):
        forbidden = "candidates" if cleaned.get("candidates") else "findings"
    elif packet.phase in ("file-review", "scope-review") and cleaned.get("findings"):
        forbidden = "findings"
    if forbidden is not None:
        count = len(cleaned.get(forbidden) or ())
        cleaned[forbidden] = []
        notes.append(
            f"{packet.phase} receipt carried {count} {forbidden} entrie(s) the contract forbids; "
            f"the channel was dropped, the receipt's own output kept."
        )

    return cleaned, notes


def _complete_final_partition(context: RunContext, receipt: dict) -> dict:
    """Validate final cause membership and restore only omitted inputs as singletons."""
    candidates = _synthesis_candidates(context)
    model_grouped = len(receipt.get("cause_groups") or ())
    normalized, diagnostics = validate_final_receipt(
        candidates,
        receipt,
        applicable_rule_ids=[rule.id for rule in _applicable_rules(context)],
        reviewed_files=list(context.files),
        verification_dispositions=_final_verification_dispositions(context, candidates),
        delta_index=context.delta_index,
        forge_rule_ids=_forge_rule_ids(context),
    )
    receipt.clear()
    receipt.update(normalized)
    context.receipt_gaps.extend(diagnostics)
    return {
        "model_grouped": model_grouped,
        "pipeline_placed": len(normalized["cause_groups"]) - model_grouped,
        "dropped": len(receipt.get("dropped") or ()),
        "total": len(candidates),
    }


def _split_timed_out_packet(context: RunContext, packet: ReviewPacket) -> list[ReviewPacket]:
    """Split one timed-out packet into smaller parts that cover exactly the same work.

    A compaction packet bisects its ordered candidate tuple. Otherwise a multi-file packet
    becomes one packet per file, and a single-file or whole-scope packet splits its rules into
    two near-equal groups. Every split strictly shrinks the parts. Final synthesis and the canary
    carry no splittable work and return nothing.
    """
    if packet.phase == "synthesis-compaction" and len(packet.candidates) > 1:
        midpoint = -(-len(packet.candidates) // 2)
        return [
            _shard_packet(context, packet.lane, packet.phase, list(candidates))
            for candidates in (packet.candidates[:midpoint], packet.candidates[midpoint:])
        ]
    if len(packet.paths) > 1:
        return [_scoped_packet(context, packet.lane, packet.phase, (path,), packet.rules) for path in packet.paths]
    if len(packet.rules) > 1:
        chunks = _chunks(packet.rules, -(-len(packet.rules) // 2))
        if packet.paths or packet.path is not None:
            files = _packet_files(context, packet)
            return [_scoped_packet(context, packet.lane, packet.phase, files, chunk) for chunk in chunks]
        # A whole-scope packet keeps the whole scope: its global rules read every file.
        return [_packet(context, packet.lane, packet.phase, None, chunk) for chunk in chunks]
    return []


def _split_conserves_work(context: RunContext, packet: ReviewPacket, parts: list[ReviewPacket]) -> tuple[bool, str]:
    """Check that the parts of a split cover exactly the packet's rules and files."""
    if packet.phase == "synthesis-compaction":
        parent_ids = [_synthesis_candidate_id(candidate) for candidate in packet.candidates]
        child_ids = [_synthesis_candidate_id(candidate) for part in parts for candidate in part.candidates]
        if parent_ids != child_ids:
            return False, "the parts changed the ordered candidate-ID sequence"
        return True, ""
    parent_pairs = {(rule.id, path) for rule in packet.rules for path in _packet_files(context, packet)}
    child_pairs = {(rule.id, path) for part in parts for rule in part.rules for path in _packet_files(context, part)}
    if parent_pairs != child_pairs:
        missing = sorted(parent_pairs - child_pairs)
        shown = ", ".join(f"{rule} on {path}" for rule, path in missing[:5])
        return False, f"the parts lost {len(missing)} rule-file pairs ({shown})"
    return True, ""


def _leaf_packets(context: RunContext, packets: list[ReviewPacket]) -> list[ReviewPacket]:
    """Resolve the packet plan to the parts that must produce receipts.

    A packet that never split is its own leaf. A split packet's coverage comes from its parts,
    recursively. The split construction conserves rules and files, so the leaf plan covers
    exactly the initial plan.
    """
    leaves = []
    stack = list(packets)
    while stack:
        packet = stack.pop()
        children = context.packet_splits.get(packet.packet_id)
        if children:
            stack.extend(children)
        else:
            leaves.append(packet)
    return leaves


def _retry_or_fail(
    context: RunContext,
    packet: ReviewPacket,
    error: str,
    pending: list[ReviewPacket],
    stdout: str = "",
    stderr: str = "",
    *,
    is_decode_failure: bool = False,
    timed_out: bool = False,
) -> bool:
    """Stop, self-repair, or retry one worker failure, and record a terminal failure only as a last resort.

    Returns:
        True when the packet is finished for good, False when it was requeued.
    """
    selection = _selection(context, packet.lane)
    provider = context.providers[selection.provider]
    if _is_input_too_large(stdout, stderr, error):
        code = (
            _SYNTHESIS_CAPACITY_FAILURE_CODE
            if packet.phase in ("synthesis-compaction", "final-synthesis")
            else "WORKER_INPUT_TOO_LARGE"
        )
        context.failures.append(
            PacketFailure(
                packet.packet_id,
                packet.lane,
                error,
                selection.provider,
                code,
                False,
                "Reduce the review scope or lower the bounded packet size before retrying.",
            )
        )
        _progress(context, "provider rejected a deterministic oversized prompt", force=True)
        return True
    if timed_out:
        # A timeout kill means the packet is too large for its wall: the same packet with the
        # same prompt hits the same wall, so a plain retry only burns the budget. The measured
        # MR 1352 run spent three identical 729s attempts on one packet this way. Split the
        # packet and retry the parts instead: each part is smaller, and together they cover
        # exactly the same rules and files, so a timeout no longer loses coverage.
        if packet.phase == "verification":
            # Verification is advisory: a dead verifier never blocks the run and never destroys
            # a candidate. The reconciler marks the packet's candidates unverified, and the
            # candidates themselves ride on to synthesis.
            context.receipt_gaps.append(f"Verification {packet.packet_id} timed out: {error}.")
            return True
        parts = _split_timed_out_packet(context, packet)
        conserves, detail = _split_conserves_work(context, packet, parts) if parts else (True, "")
        if parts and not conserves:
            # A split that loses work is a pipeline defect. Fail the packet loudly instead of
            # queueing parts that would silently drop rules, files, or candidates.
            context.failures.append(
                PacketFailure(
                    packet.packet_id,
                    packet.lane,
                    f"{error}; the split parts did not conserve the packet's coverage: {detail}",
                    selection.provider,
                    "SPLIT_COVERAGE",
                    False,
                    "The timeout split dropped work, which is a pipeline defect. Report it with this run id.",
                )
            )
            _progress(context, "packet split failed its coverage check, failing", force=True)
            return True
        if parts:
            context.packet_splits[packet.packet_id] = parts
            context.expected_receipts[packet.lane] = context.expected_receipts.get(packet.lane, 0) + len(parts) - 1
            pending.extend(parts)
            _progress(context, f"packet timed out; split into {len(parts)} smaller parts", force=True)
            return False
        context.failures.append(
            PacketFailure(
                packet.packet_id,
                packet.lane,
                f"{error}; the packet cannot be split into smaller parts",
                selection.provider,
                "WORKER_TIMEOUT",
                False,
                "The smallest possible packet still hit its timeout. Narrow the review scope, or "
                "review the named file by hand.",
            )
        )
        _progress(context, "packet timed out and cannot be split, failing", force=True)
        return True
    if not is_decode_failure and provider.needs_user_action(1, stdout, stderr):
        context.failures.append(
            PacketFailure(
                packet.packet_id,
                packet.lane,
                error,
                selection.provider,
                "WORKER_PERMISSION_REQUIRED",
                True,
                f"Allow {selection.provider} read-only access to the review workspace, run doctor with the same "
                f"options, then retry.",
            )
        )
        _progress(context, "provider permission needs user action", force=True)
        return True
    if _is_resource_failure(stdout, stderr, error) and packet.repairs < MAX_ATTEMPTS:
        pool = context.pools[selection.provider]
        if pool.limit > 1:
            pool.limit = max(1, pool.limit // 2)
            _progress(
                context,
                f"lowered {selection.provider} workers to {pool.limit} after a resource failure",
                force=True,
            )
        packet.repairs += 1
        packet.attempt = 0
        packet.prior_error = error
        pending.append(packet)
        return False
    if packet.attempt < MAX_ATTEMPTS and not _is_resource_failure(stdout, stderr, error):
        packet.prior_error = error
        pending.append(packet)
        _progress(context, f"retrying packet attempt={packet.attempt + 1}")
        return False
    if _is_resource_failure(stdout, stderr, error):
        # Fewer workers did not help, so the host itself cannot run this provider now.
        context.failures.append(
            PacketFailure(
                packet.packet_id,
                packet.lane,
                error,
                selection.provider,
                "HOST_RESOURCE_EXHAUSTED",
                True,
                f"The host could not create {selection.provider} processes even at "
                f"{context.pools[selection.provider].limit} workers. Close other work or start a new session, then "
                f"retry with a lower --jobs value.",
            )
        )
        _progress(context, "host resource limit needs user action", force=True)
        return True
    if packet.phase == "verification":
        # Verification is advisory: its failures become gaps, the reconciler carries the
        # packet's candidates forward unverified, and the candidates ride on to synthesis.
        context.receipt_gaps.append(f"Verification {packet.packet_id} failed after {MAX_ATTEMPTS} attempts: {error}.")
        return True
    context.failures.append(PacketFailure(packet.packet_id, packet.lane, error, selection.provider, "WORKER_FAILED"))
    _progress(context, f"packet failed after {MAX_ATTEMPTS} attempts", force=True)
    return True


def _is_resource_failure(stdout: str, stderr: str, error: str) -> bool:
    """Report whether a failure describes an environment limit that fewer workers can avoid."""
    text = f"{stdout}\n{stderr}\n{error}".lower()
    return any(marker in text for marker in RESOURCE_MARKERS)


def _is_input_too_large(stdout: str, stderr: str, error: str) -> bool:
    """Report whether a provider deterministically rejected the prompt's input size."""
    for source in (stdout, stderr, error):
        for bounded_output in source.split("\n...\n", 1):
            for line in bounded_output.splitlines():
                lowered = line.strip().lower()
                compact = re.sub(r"\s+", "", lowered)
                if '"input_error_code":"input_too_large"' in compact:
                    return True
                if lowered.startswith("error:") and "input exceeds the maximum length" in lowered:
                    return True
    return False


def _worker_output(path: Path) -> str:
    """Read a bounded binary head and tail for failure classification."""
    try:
        with path.open("rb") as stream:
            head = stream.read(4096)
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            if size <= 4096:
                tail = b""
            else:
                stream.seek(max(4096, size - 4096))
                tail = stream.read(4096)
        return (head + (b"\n...\n" if tail else b"") + tail).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _selection(context: RunContext, lane: str) -> ProviderSelection:
    """Resolve the provider selection for one packet lane. One lane, one provider."""
    del lane  # There is one review shape and one provider selection, so every packet uses it.
    return context.selections[0]


def _view_summary(context: RunContext, lane: str) -> dict:
    """Summarize one review view without treating missing receipts as success."""
    selection = _selection(context, lane)
    failed = any(failure.lane == lane for failure in context.failures)
    receipt_count = sum(receipt.get("lane") == lane for receipt in context.receipts)
    complete = receipt_count == context.expected_receipts.get(lane, 0)
    return {
        "provider": selection.provider,
        "model": selection.model,
        "reasoning": selection.reasoning,
        "status": "failed" if failed else "complete" if complete else "incomplete",
    }


def _render_prompt(context: RunContext, payload: dict) -> str:
    """Render one stable compact prompt from an already materialized packet payload."""
    return (
        context.instructions
        + "\n\nExecute this Remix review packet. Return only JSON matching the packet receipt contract.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def _save_run(context: RunContext) -> None:
    """Persist the small public run manifest from typed runtime state."""
    write_json_atomic(
        context.run_dir / "run.json",
        {
            "schema_version": 3,
            "workflow": "remix-review",
            "validation_level": "default",
            "run_id": context.run_dir.name,
            "status": context.status,
            "review_identity": context.review_identity,
            "result_sha256": context.result_sha256,
            "scope": context.scope,
            "selections": [asdict(selection) for selection in context.selections],
        },
    )


def _persist_terminal_result(context: RunContext, result: dict) -> None:
    """Atomically persist result bytes, their digest, then the terminal manifest.

    Args:
        context: Run context that owns the terminal artifacts.
        result: Complete or incomplete public result without a self-hash.

    Raises:
        RuntimeError: If the atomically written result cannot be hashed.
    """
    context.status = result["status"]
    result_path = context.run_dir / "result.json"
    write_json_atomic(result_path, result)
    context.result_sha256 = file_hash(result_path)
    if context.result_sha256 is None:
        raise RuntimeError("The terminal review result could not be hashed.")
    _save_run(context)


def _default_base(repository: Path) -> str:
    for candidate in ("origin/main", "origin/develop", "main", "develop", "HEAD~1"):
        if run_git(repository, "rev-parse", "--verify", f"{candidate}^{{commit}}", check=False).returncode == 0:
            return candidate
    return "HEAD~1"


_NON_FINAL_STATUSES = frozenset(
    {
        "created",
        "in_progress",
        "manual",
        "pending",
        "preparing",
        "queued",
        "requested",
        "running",
        "scheduled",
        "waiting",
        "waiting_for_resource",
    }
)
_FAILED_CHECK_STATUSES = frozenset({"failed", "failure"})


def _required_checks_final(evidence: dict) -> bool:
    """Return True when no captured required check is in a non-final state."""
    return not any(
        check.get("required") and str(check.get("status", "")).lower() in _NON_FINAL_STATUSES
        for check in evidence.get("checks", ())
    )


def _applicable_rules(context: RunContext) -> tuple[Rule, ...]:
    """Exclude forge-only rules when their evidence cannot prove a result."""
    evidence = context.forge_evidence
    description_ok = evidence.get("description_state") == "available"
    checks_ok = evidence.get("checks_state") == "available" and _required_checks_final(evidence)
    return tuple(
        rule
        for rule in context.rules
        if rule.evidence is None
        or (rule.evidence == "description" and description_ok)
        or (rule.evidence == "checks" and checks_ok)
    )


def _forge_rule_ids(context: RunContext) -> tuple[str, ...]:
    """Return check-only rule IDs backed by immutable required exact-head evidence."""
    evidence = context.forge_evidence
    if evidence.get("checks_state") != "available" or not _required_checks_final(evidence):
        return ()
    failed_required = any(
        isinstance(check, dict)
        and check.get("required") is True
        and check.get("allow_failure") is False
        and check.get("sha") == context.head_sha
        and str(check.get("status") or "").lower() in _FAILED_CHECK_STATUSES
        for check in evidence.get("checks", ())
    )
    if not failed_required:
        return ()
    return tuple(rule.id for rule in _applicable_rules(context) if rule.evidence == "checks")


def _evidence_gaps(evidence: dict) -> tuple[str, ...]:
    """Describe unavailable remote evidence without turning it into a finding."""
    if evidence.get("description_state") == "not_applicable":
        return (
            (
                "Incomplete info: Remix Review does not ingest measured exact-head coverage reports; verify the 75% "
                "requirement through the test or CI coverage report."
            ),
        )
    gaps = []
    if evidence.get("description_state") != "available":
        gaps.append("Incomplete info: review description was unavailable.")
    if evidence.get("checks_state") != "available":
        reason = evidence.get("checks_reason") or "exact-head checks were unavailable."
        gaps.append(f"Incomplete info: {reason}")
    elif not _required_checks_final(evidence):
        gaps.append("Incomplete info: required exact-head checks were not final.")
    return tuple(gaps)


def _cleanup_transient(run_dir: Path) -> tuple[str, ...]:
    """Remove the raw worker prompts and output, and report every path that failed to clear."""
    errors = []
    for name in ("workers", "scope-artifacts"):
        target = run_dir / name
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        except OSError as error:
            errors.append(f"{target} ({error.strerror or error})")
    return tuple(errors)


def _stage_invoking_context(root: Path, destination: Path, rules: list[Rule]) -> Path:
    """Copy only trusted project instructions and rule-source documents for worker auto-load."""
    root = root.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    destination = destination.resolve()
    for name in ("AGENTS.md", "CLAUDE.md"):
        source = root / name
        if source.is_file():
            shutil.copy2(source, destination / name)
    agents = destination / ".agents"
    agents.mkdir()
    for name in ("instructions.md", "instructions.local.md"):
        source = root / ".agents" / name
        if source.is_file():
            shutil.copy2(source, agents / name)
    for name in ("context", "rules"):
        source = root / ".agents" / name
        if source.is_dir():
            shutil.copytree(source, agents / name)
    for rule in rules:
        for source_record in rule.sources:
            relative = Path(str(source_record.get("path") or ""))
            source = (root / relative).resolve()
            try:
                source.relative_to(root)
            except ValueError as error:
                raise ValueError(f"rule {rule.id} source escapes the invoking workspace") from error
            if not relative.parts or relative.is_absolute() or not source.is_file():
                raise ValueError(f"rule {rule.id} names missing source {relative}")
            target = (destination / relative).resolve()
            try:
                target.relative_to(destination)
            except ValueError as error:
                raise ValueError(f"rule {rule.id} source escapes the staged invoking context") from error
            if target.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return destination.resolve()


def _create_external_run_root(root: Path) -> Path:
    """Create a short temporary root outside the repository for checkout and trusted context."""
    root = root.resolve()
    staging_root = Path(tempfile.mkdtemp(prefix="rr-")).resolve()
    try:
        staging_root.relative_to(root)
    except ValueError:
        pass
    else:
        shutil.rmtree(staging_root)
        raise RuntimeError("The temporary review workspace was created inside the caller repository.")
    return staging_root


def _change_path(change: ChangeEntry) -> str:
    """Return the logical head-side path, or the deleted base-side path, for one change."""
    path = change.new_path or change.old_path
    if path is None:
        raise ValueError("a change entry must name an old or new path")
    return path


def _hashes(
    repository: Path, files: tuple[str, ...], file_artifacts: dict[str, str] | None = None
) -> dict[str, str | None]:
    """Hash each file's exact readable artifact for snapshot drift checks."""
    artifacts = file_artifacts or {}
    return {path: file_hash(artifacts.get(path, repository / path)) for path in files}


def _git_root() -> Path:
    return Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel").stdout.decode("utf-8").strip()).resolve()
