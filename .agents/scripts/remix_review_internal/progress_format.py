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

__all__ = ["format_header", "format_progress", "format_stage_done", "format_summary"]

_PREFIX = "[remix-review]"


def _fmt_duration(seconds: float) -> str:
    """Format seconds into a short human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_progress(
    elapsed: float,
    review_completed: int,
    review_expected: int,
    verification_completed: int,
    verification_expected: int,
    synthesis_completed: int,
    synthesis_expected: int,
    active_workers: int,
    worker_limit: int,
    candidate_count: int,
    retries: int = 0,
    splits: int = 0,
    worker_limit_lowered: bool = False,
    remaining_estimate: float | None = None,
    estimate_source: str = "predicted",
) -> str:
    """Return a single-line status string that fits in 120 columns.

    The primary fraction is the stage with unfinished upstream work (review
    while review is going, then the first unfinished tail stage), because its
    denominator is fixed and it is what a reader tracks. When verification
    streams inside the review wave, a compact marker shows its in-flight
    count.

    Args:
        elapsed: Seconds since the run started.
        review_completed: Review packets that returned a receipt or failure.
        review_expected: Review packets planned at startup (fixed denominator).
        verification_completed: Verification packets done.
        verification_expected: Verification packets expected so far (grows).
        synthesis_completed: Synthesis packets done.
        synthesis_expected: Synthesis packets expected so far (grows).
        active_workers: Workers currently running.
        worker_limit: Maximum concurrent workers.
        candidate_count: Deduplicated candidates accumulated so far.
        retries: Packets that retried with the same prompt (non-timeout).
        splits: Packets that split after a timeout.
        worker_limit_lowered: Whether the worker limit was reduced after a resource error.
        remaining_estimate: Estimated seconds remaining, or None when it cannot be computed.
        estimate_source: "predicted" (from the planner's static estimate) or
            "measured" (derived from the rate of completed packets).

    Returns:
        A status line at most 120 characters wide.
    """
    elapsed_str = _fmt_duration(elapsed)

    # --- Primary stage and fraction ---
    # The stage with unfinished upstream work. Its denominator is fixed
    # (review) or grows (tail), but it is the stage a reader tracks.
    if review_expected == 0:
        stage = "preparing scope"
        frac = ""
    elif review_completed < review_expected:
        stage = "review"
        frac = f"{review_completed}/{review_expected}"
    elif verification_completed < verification_expected:
        stage = "verify"
        frac = f"{verification_completed}/{verification_expected}"
    elif synthesis_completed < synthesis_expected:
        stage = "synth"
        frac = f"{synthesis_completed}/{synthesis_expected}"
    else:
        stage = "done"
        frac = ""

    # --- Tail markers for overlapping stages ---
    # Verification streams inside the review wave. Show its in-flight count compactly.
    # Only show a marker when that stage has work in flight (expected > 0
    # and not yet complete) AND it is not the primary stage.
    tail_str = (
        f"+verify {verification_completed}/{verification_expected}"
        if review_completed < review_expected
        and verification_expected > 0
        and verification_completed < verification_expected
        else ""
    )

    # --- Workers ---
    workers_str = f"{active_workers}/{worker_limit} workers"

    # --- Candidates ---
    cand_str = f"{candidate_count} found"

    # --- Abnormal flags ---
    flags = []
    if retries:
        flags.append(f"retry={retries}")
    if splits:
        flags.append(f"split={splits}")
    if worker_limit_lowered:
        flags.append("limit lowered")
    flags_str = f" [{', '.join(flags)}]" if flags else ""

    # --- Remaining estimate ---
    # Omit rather than show zero. A measured estimate and a predicted
    # estimate are different claims: show which one is in use.
    if remaining_estimate is not None and remaining_estimate > 0:
        remain_str = f" ~{_fmt_duration(remaining_estimate)} left"
        if estimate_source == "measured":
            remain_str += " (est.)"
        else:
            remain_str += " (planned)"
    else:
        remain_str = ""

    # --- Assemble ---
    # Layout: [remix-review] <elapsed> <stage> [<frac>] [<tail>] <busy> <found> [<flags>] [<remain>]
    parts = [_PREFIX, elapsed_str, stage]
    if frac:
        parts.append(frac)
    if tail_str:
        parts.append(tail_str)
    parts.append(workers_str)
    parts.append(cand_str)
    line = " ".join(parts)
    if flags_str:
        line += flags_str
    if remain_str:
        line += remain_str

    return line


def format_header(file_count: int, packet_count: int, worker_limit: int, expected_seconds: float | None) -> str:
    """Return a one-line plan header printed at the start of the run."""
    if expected_seconds is not None:
        return f"{_PREFIX} reviewing {file_count} files in {packet_count} packets with {worker_limit} workers (~{_fmt_duration(expected_seconds)})"
    return f"{_PREFIX} reviewing {file_count} files in {packet_count} packets with {worker_limit} workers"


def format_stage_done(stage: str, completed: int, expected: int, duration: float, candidate_count: int) -> str:
    """Return a one-line stage-completion marker, forced off the 15s cadence.

    Over a 30-minute run this gives a reader four or five permanent marks
    in the scrollback instead of a stream of identical lines.
    """
    if stage == "review":
        return f"{_PREFIX} review done: {completed}/{expected} packets in {_fmt_duration(duration)}, {candidate_count} findings"
    if stage == "verify":
        return f"{_PREFIX} verification done: {completed}/{expected} packets in {_fmt_duration(duration)}"
    if stage == "synthesis":
        return f"{_PREFIX} synthesis done: {completed}/{expected} packets in {_fmt_duration(duration)}"
    return f"{_PREFIX} {stage} done: {completed}/{expected} packets in {_fmt_duration(duration)}"


def format_summary(
    elapsed: float,
    status: str,
    verdict: str | None,
    findings: int,
    gaps: int,
    failures: int,
) -> str:
    """Return a one-line summary printed at the end of the run."""
    verdict_str = f" {verdict}" if verdict else ""
    return (
        f"{_PREFIX} done in {_fmt_duration(elapsed)} status={status}{verdict_str} "
        f"findings={findings} gaps={gaps} failures={failures}"
    )
