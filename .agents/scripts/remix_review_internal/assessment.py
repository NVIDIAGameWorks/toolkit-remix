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
import json
import re
from fractions import Fraction
from pathlib import PurePosixPath

from .artifacts import canonical_hash
from .rules import (
    SCORE_CATEGORY_BY_CLAIM_CLASS,
    SCORE_FORMULA_VERSION,
    SEVERITY_CEILINGS,
    SEVERITY_PENALTIES,
    WORKLOAD_METRIC_VERSION,
    point_pool_for_lines,
)


__all__ = [
    "SCORE_CATEGORIES",
    "AssessmentError",
    "materialize_feedback_adjudication",
    "materialize_findings",
    "materialize_scorecard",
    "validate_candidate_ownership",
    "validate_feedback",
    "validate_feedback_dispositions",
    "validate_feedback_operations",
    "validate_final_receipt",
    "validate_review_decisions",
    "validate_score_exemptions",
]


SCORE_CATEGORIES = (
    "architecture_and_simplicity",
    "maintainability",
    "merge_readiness",
)

_RECOVERED_CLASS = "unclassified"
_CLAIM_CLASSES = frozenset(SCORE_CATEGORY_BY_CLAIM_CLASS) - {_RECOVERED_CLASS}
_RECOVERED_BASIS = "The host restored a candidate omitted by final synthesis as a conservative singleton."
_FINDING_ID = re.compile(r"F-(\d{4,})$")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}$")
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_REVIEW_RUN_ID = re.compile(r"review-[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?")
_FEEDBACK_TOTAL_BYTES = 64 * 1024
_FEEDBACK_TEXT_BYTES = 8 * 1024


def _validate_feedback_text(text: object) -> None:
    """Require one nonempty printable response within the feedback text limit."""
    if (
        not isinstance(text, str)
        or not text
        or text != text.strip()
        or not text.isprintable()
        or len(text.encode("utf-8")) > _FEEDBACK_TEXT_BYTES
    ):
        raise AssessmentError("feedback text is invalid")


def _validated_feedback_records(value: object) -> list[dict]:
    """Return exact, bounded feedback records."""
    if not isinstance(value, (list, tuple)):
        raise AssessmentError("feedback must be an array")
    expected = {"finding_id", "text"}
    records, seen = [], set()
    for record in value:
        if not isinstance(record, dict) or set(record) != expected:
            raise AssessmentError("feedback record fields are not exact")
        finding_id = record.get("finding_id")
        text = record.get("text")
        if not isinstance(finding_id, str) or _FINDING_ID.fullmatch(finding_id) is None:
            raise AssessmentError("feedback finding_id is invalid")
        if finding_id in seen:
            raise AssessmentError(f"feedback repeats duplicate finding_id {finding_id}")
        _validate_feedback_text(text)
        seen.add(finding_id)
        records.append(copy.deepcopy(record))
    if (
        len(json.dumps(records, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        > _FEEDBACK_TOTAL_BYTES
    ):
        raise AssessmentError("feedback exceeds 64 KiB")
    return records


def validate_feedback(value: object) -> list[dict]:
    """Validate canonical accepted feedback records."""
    return _validated_feedback_records(value)


def validate_feedback_operations(value: object, schema_version: int = 2) -> list[dict]:
    """Normalize bounded feedback input into explicit operations.

    Args:
        value: Submitted operations, or schema-1 rebuttal records.
        schema_version: Input schema; version 1 contains challenges only.

    Returns:
        Validated operations, with an action and exactly one target per record.

    Raises:
        AssessmentError: If fields, targets, text, duplicates, or size are invalid.
    """
    if type(schema_version) is not int or schema_version not in (1, 2):
        raise AssessmentError("feedback schema version is invalid")
    if schema_version == 1:
        return [{"action": "challenge", **record} for record in validate_feedback(value)]
    if not isinstance(value, (list, tuple)):
        raise AssessmentError("feedback operations must be an array")
    records, seen = [], set()
    for record in value:
        if not isinstance(record, dict):
            raise AssessmentError("feedback operation is invalid")
        action = record.get("action")
        if action not in ("challenge", "accept_tradeoff", "revoke_acceptance"):
            raise AssessmentError("feedback action is invalid")
        target = "decision_id" if action == "revoke_acceptance" else "finding_id"
        if set(record) != {"action", target, "text"}:
            raise AssessmentError("feedback operation fields are not exact")
        identifier = record[target]
        pattern = _HEX_DIGEST if target == "decision_id" else _FINDING_ID
        if not isinstance(identifier, str) or pattern.fullmatch(identifier) is None:
            raise AssessmentError(f"feedback {target} is invalid")
        if (target, identifier) in seen:
            raise AssessmentError(f"feedback repeats or conflicts on {target} {identifier}")
        _validate_feedback_text(record["text"])
        seen.add((target, identifier))
        records.append(copy.deepcopy(record))
    if len(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _FEEDBACK_TOTAL_BYTES:
        raise AssessmentError("feedback exceeds 64 KiB")
    return records


def _decision_id(record: dict) -> str:
    """Bind one decision identifier to its immutable source and explicit response."""
    return canonical_hash(
        {
            "source_result_sha256": record["source_result_sha256"],
            "source_run_id": record["source_run_id"],
            "review_identity": record["review_identity"],
            "finding_id": record["finding"]["finding_id"],
            "kind": record["kind"],
            "text": record["text"],
        }
    )


def _decision_evidence(value: object, *, required: bool) -> None:
    """Validate retained evidence locations without rereading a historical checkout."""
    if not isinstance(value, list) or (required and not value):
        raise AssessmentError("review decision evidence is invalid")
    seen = set()
    for location in value:
        if not isinstance(location, dict) or set(location) != {"path", "line"}:
            raise AssessmentError("review decision evidence location is invalid")
        path, line = location["path"], location["line"]
        if (
            not isinstance(path, str)
            or not path
            or not path.isprintable()
            or PurePosixPath(path).is_absolute()
            or any(part in ("", ".", "..") for part in path.split("/"))
            or "\\" in path
            or ":" in path
            or (line is not None and (type(line) is not int or line < 1))
            or (path, line) in seen
        ):
            raise AssessmentError("review decision evidence location is invalid")
        seen.add((path, line))


def validate_review_decisions(value: object, *, review_identity: str | None = None) -> list[dict]:
    """Validate self-contained historical decisions and their immutable identifiers.

    Args:
        value: Saved decision records; an absent collection is represented by an empty list.
        review_identity: Expected canonical review identity, when validating a saved result.

    Returns:
        Independent copies of validated decisions in stable identifier order.

    Raises:
        AssessmentError: If source identity, evidence, state, or decision ownership is malformed.
    """
    if not isinstance(value, list):
        raise AssessmentError("review_decisions must be an array")
    fields = {
        "decision_id",
        "kind",
        "state",
        "source_run_id",
        "source_result_sha256",
        "review_identity",
        "head",
        "finding",
        "text",
        "verification",
        "last_verification",
        "revocation",
    }
    decisions, seen = [], set()
    for record in value:
        if not isinstance(record, dict) or set(record) != fields:
            raise AssessmentError("review decision fields are not exact")
        for name in ("decision_id", "source_result_sha256", "review_identity"):
            if not isinstance(record[name], str) or _HEX_DIGEST.fullmatch(record[name]) is None:
                raise AssessmentError(f"review decision {name} is invalid")
        if review_identity is not None and record["review_identity"] != review_identity:
            raise AssessmentError("review decision belongs to another review")
        if not isinstance(record["source_run_id"], str) or _REVIEW_RUN_ID.fullmatch(record["source_run_id"]) is None:
            raise AssessmentError("review decision source run is invalid")
        if record["kind"] not in ("refuted", "accepted") or record["state"] not in ("active", "revoked"):
            raise AssessmentError("review decision kind or state is invalid")
        head = record["head"]
        if (
            not isinstance(head, dict)
            or set(head) != {"base_sha", "head_sha", "head_tree_sha"}
            or any(not isinstance(head[name], str) or _GIT_OBJECT_ID.fullmatch(head[name]) is None for name in head)
        ):
            raise AssessmentError("review decision source head is invalid")
        finding = record["finding"]
        if not isinstance(finding, dict):
            raise AssessmentError("review decision source finding is invalid")
        validate_feedback([{"finding_id": finding.get("finding_id"), "text": record["text"]}])
        candidate_id = _candidate_id(finding)
        source_ids = _string_list(finding.get("source_candidate_ids"), "review decision source candidates")
        if candidate_id not in source_ids or len(set(source_ids)) != len(source_ids):
            raise AssessmentError("review decision source finding provenance is invalid")
        if not _string_list(finding.get("rule_ids"), "review decision rules"):
            raise AssessmentError("review decision source finding has no rules")
        if (
            not isinstance(finding.get("claim_class"), str)
            or finding["claim_class"] not in SCORE_CATEGORY_BY_CLAIM_CLASS
        ):
            raise AssessmentError("review decision source finding claim class is invalid")
        _severity_debt(finding.get("severity"), finding["finding_id"])
        _decision_evidence([finding.get("primary_location")], required=True)
        if "locations" in finding:
            _decision_evidence(finding["locations"], required=False)
        if any(name in finding and not isinstance(finding[name], str) for name in ("title", "evidence")):
            raise AssessmentError("review decision source finding text is invalid")
        verification = record["verification"]
        if record["kind"] == "refuted":
            if (
                record["state"] != "active"
                or not isinstance(verification, dict)
                or set(verification) != {"basis", "evidence"}
            ):
                raise AssessmentError("refutation verification is invalid")
            if not isinstance(verification["basis"], str) or not verification["basis"].strip():
                raise AssessmentError("refutation verification requires a basis")
            _decision_evidence(verification["evidence"], required=True)
        elif verification is not None:
            raise AssessmentError("acceptance must not fabricate refutation verification")
        revocation = record["revocation"]
        if record["state"] == "revoked":
            if not isinstance(revocation, dict) or set(revocation) != {"run_id", "text"}:
                raise AssessmentError("review decision revocation is invalid")
            if not isinstance(revocation["run_id"], str) or _REVIEW_RUN_ID.fullmatch(revocation["run_id"]) is None:
                raise AssessmentError("review decision revocation run is invalid")
            validate_feedback([{"finding_id": finding["finding_id"], "text": revocation["text"]}])
        elif revocation is not None:
            raise AssessmentError("active review decision has a revocation")
        latest = record["last_verification"]
        if latest is not None:
            if not isinstance(latest, dict) or set(latest) != {
                "run_id",
                "head_sha",
                "candidate_ids",
                "status",
                "basis",
                "evidence",
            }:
                raise AssessmentError("review decision latest verification is invalid")
            if (
                not isinstance(latest["run_id"], str)
                or _REVIEW_RUN_ID.fullmatch(latest["run_id"]) is None
                or not isinstance(latest["head_sha"], str)
                or _GIT_OBJECT_ID.fullmatch(latest["head_sha"]) is None
                or latest["status"] not in ("applicable", "not_applicable", "uncertain")
                or not isinstance(latest["basis"], str)
                or not latest["basis"].strip()
            ):
                raise AssessmentError("review decision latest verification metadata is invalid")
            candidate_ids = _string_list(latest["candidate_ids"], "review decision latest candidates")
            if not candidate_ids or len(set(candidate_ids)) != len(candidate_ids):
                raise AssessmentError("review decision latest candidates are invalid")
            _decision_evidence(latest["evidence"], required=latest["status"] != "uncertain")
        if record["decision_id"] in seen or record["decision_id"] != _decision_id(record):
            raise AssessmentError("review decision identifier is inconsistent or duplicated")
        seen.add(record["decision_id"])
        decisions.append(copy.deepcopy(record))
    return sorted(decisions, key=lambda decision: decision["decision_id"])


def validate_score_exemptions(value: object, findings: list[dict], decisions: list[dict]) -> list[dict]:
    """Validate current finding bindings to active explicit acceptances."""
    if not isinstance(value, list):
        raise AssessmentError("score_exemptions must be an array")
    finding_ids = {finding["finding_id"] for finding in findings}
    accepted_ids = {
        record["decision_id"] for record in decisions if record["kind"] == "accepted" and record["state"] == "active"
    }
    records, seen = [], set()
    for record in value:
        if not isinstance(record, dict) or set(record) != {"finding_id", "decision_id"}:
            raise AssessmentError("score exemption fields are not exact")
        finding_id, decision_id = record["finding_id"], record["decision_id"]
        if (
            not isinstance(finding_id, str)
            or finding_id not in finding_ids
            or finding_id in seen
            or not isinstance(decision_id, str)
            or decision_id not in accepted_ids
        ):
            raise AssessmentError("score exemption must bind a current finding to one active acceptance")
        seen.add(finding_id)
        records.append(copy.deepcopy(record))
    return sorted(records, key=lambda record: _finding_sequence(record["finding_id"]))


def materialize_feedback_adjudication(
    run_id: str,
    previous_result: dict,
    previous_result_sha256: str,
    submitted_feedback: object,
    feedback_dispositions: object,
    *,
    reviewed_locations: set[tuple[str, int | None]],
) -> dict:
    """Derive one same-snapshot result from independently verified feedback.

    Args:
        run_id: Immutable identifier for the adjudication run.
        previous_result: Validated source snapshot result.
        previous_result_sha256: SHA-256 of the source result bytes.
        submitted_feedback: Bounded explicit operations, or legacy challenge records.
        feedback_dispositions: Independently verified dispositions keyed by finding ID.
        reviewed_locations: Exact-head locations allowed as adjudication evidence.

    Returns:
        Current findings, accepted feedback, scorecard, verdict, and adjudication metadata.

    Raises:
        AssessmentError: If the source result, selections, evidence, or score state is invalid.
    """
    if not isinstance(run_id, str) or not run_id:
        raise AssessmentError("feedback adjudication run_id must be nonempty")
    if not isinstance(previous_result, dict):
        raise AssessmentError("feedback adjudication previous result is invalid")
    if (
        previous_result.get("schema_version") != 3
        or previous_result.get("workflow") != "remix-review"
        or previous_result.get("status") != "complete"
    ):
        raise AssessmentError("feedback adjudication requires a complete snapshot result")
    previous_run_id = previous_result.get("run_id")
    if not isinstance(previous_run_id, str) or not previous_run_id or previous_run_id == run_id:
        raise AssessmentError("feedback adjudication previous run_id is invalid")
    if not isinstance(previous_result_sha256, str) or _HEX_DIGEST.fullmatch(previous_result_sha256) is None:
        raise AssessmentError("feedback adjudication previous result hash is invalid")

    schema_version = (
        1
        if isinstance(submitted_feedback, (list, tuple))
        and all(isinstance(record, dict) and "action" not in record for record in submitted_feedback)
        else 2
    )
    submitted = validate_feedback_operations(submitted_feedback, schema_version)
    if not submitted:
        raise AssessmentError("feedback adjudication requires submitted feedback")
    source_findings = previous_result.get("findings")
    if not isinstance(source_findings, list):
        raise AssessmentError("feedback adjudication source findings are invalid")
    findings_by_id = {}
    for finding in source_findings:
        finding_id = finding.get("finding_id") if isinstance(finding, dict) else None
        if (
            not isinstance(finding_id, str)
            or finding_id in findings_by_id
            or not isinstance(finding.get("candidate_id"), str)
            or not finding["candidate_id"]
        ):
            raise AssessmentError("feedback adjudication source finding is invalid")
        _finding_sequence(finding_id)
        _severity_debt(finding.get("severity"), finding_id)
        findings_by_id[finding_id] = finding

    selected_ids = sorted(
        (record["finding_id"] for record in submitted if "finding_id" in record), key=_finding_sequence
    )
    if any(finding_id not in findings_by_id for finding_id in selected_ids):
        raise AssessmentError("feedback adjudication must select a public source finding")
    decisions = validate_review_decisions(
        previous_result.get("review_decisions", []), review_identity=previous_result.get("review_identity")
    )
    exemptions = validate_score_exemptions(previous_result.get("score_exemptions", []), source_findings, decisions)
    decisions_by_id = {decision["decision_id"]: decision for decision in decisions}
    exempt_by_id = {record["finding_id"]: record["decision_id"] for record in exemptions}
    revoked_ids = {record["decision_id"] for record in submitted if record["action"] == "revoke_acceptance"}
    if any(
        decision_id not in decisions_by_id or decisions_by_id[decision_id]["kind"] != "accepted"
        for decision_id in revoked_ids
    ):
        raise AssessmentError("feedback revocation must select a saved acceptance")
    if any(exempt_by_id.get(finding_id) in revoked_ids for finding_id in selected_ids):
        raise AssessmentError("feedback operations conflict with acceptance revocation")
    challenged_ids = [record["finding_id"] for record in submitted if record["action"] == "challenge"]
    dispositions = validate_feedback_dispositions(
        feedback_dispositions,
        challenged_ids,
        reviewed_locations,
    )
    refuted = {
        finding_id for finding_id, disposition in dispositions.items() if disposition["disposition"] == "refuted"
    }
    findings = [copy.deepcopy(finding) for finding in source_findings if finding["finding_id"] not in refuted]
    accepted = {record["finding_id"]: record for record in validate_feedback(previous_result.get("feedback", []))}
    submitted_by_id = {record["finding_id"]: record for record in submitted if "finding_id" in record}
    accepted.update(
        {finding_id: {"finding_id": finding_id, "text": submitted_by_id[finding_id]["text"]} for finding_id in refuted}
    )
    feedback = validate_feedback([accepted[finding_id] for finding_id in sorted(accepted, key=_finding_sequence)])
    affected_decisions = set()
    for operation in submitted:
        if operation["action"] == "revoke_acceptance":
            decision_id = operation["decision_id"]
            decision = decisions_by_id[decision_id]
            if decision["state"] != "revoked":
                decision.update(state="revoked", revocation={"run_id": run_id, "text": operation["text"]})
            exempt_by_id = {finding_id: owner for finding_id, owner in exempt_by_id.items() if owner != decision_id}
            affected_decisions.add(decision_id)
            continue
        finding_id = operation["finding_id"]
        if operation["action"] == "challenge" and finding_id not in refuted:
            continue
        kind = "refuted" if operation["action"] == "challenge" else "accepted"
        decision = {
            "kind": kind,
            "state": "active",
            "source_run_id": previous_run_id,
            "source_result_sha256": previous_result_sha256,
            "review_identity": previous_result.get("review_identity"),
            "head": {name: previous_result["head"].get(name) for name in ("base_sha", "head_sha", "head_tree_sha")},
            "finding": copy.deepcopy(findings_by_id[finding_id]),
            "text": operation["text"],
            "verification": {name: copy.deepcopy(dispositions[finding_id][name]) for name in ("basis", "evidence")}
            if kind == "refuted"
            else None,
            "last_verification": None,
            "revocation": None,
        }
        decision_id = decision["decision_id"] = _decision_id(decision)
        old_id = exempt_by_id.pop(finding_id, None)
        # A refutation does not withdraw the user's acceptance of a tradeoff. Only explicit
        # revocation or revised acceptance does; future reuse still requires current verification.
        if old_id is not None and kind == "accepted" and old_id != decision_id:
            decisions_by_id[old_id].update(state="revoked", revocation={"run_id": run_id, "text": operation["text"]})
            exempt_by_id = {identifier: owner for identifier, owner in exempt_by_id.items() if owner != old_id}
            affected_decisions.add(old_id)
        decisions_by_id[decision_id] = decision
        affected_decisions.add(decision_id)
        if kind == "accepted":
            exempt_by_id[finding_id] = decision_id
    decisions = validate_review_decisions(
        list(decisions_by_id.values()), review_identity=previous_result.get("review_identity")
    )
    exemptions = validate_score_exemptions(
        [{"finding_id": finding_id, "decision_id": decision_id} for finding_id, decision_id in exempt_by_id.items()],
        findings,
        decisions,
    )
    scorecard = _materialize_feedback_scorecard(previous_result, findings, exemptions)
    diagnostics = tuple(
        f"Finding {finding_id} could not be verified."
        for finding_id in challenged_ids
        if dispositions[finding_id]["disposition"] == "cannot_verify"
    )
    return {
        "findings": findings,
        "feedback": feedback,
        "review_decisions": decisions,
        "score_exemptions": exemptions,
        "scorecard": scorecard,
        "verdict": "CHANGES_REQUIRED"
        if any(finding["finding_id"] not in exempt_by_id for finding in findings)
        else "CLEAN",
        "diagnostics": diagnostics,
        "adjudication": {
            "source_run_id": previous_run_id,
            "source_result_sha256": previous_result_sha256,
            "finding_ids": selected_ids,
            "decision_ids": sorted(affected_decisions),
        },
    }


def validate_feedback_dispositions(
    value: object,
    selected_ids: list[str],
    reviewed_locations: set[tuple[str, int | None]],
) -> dict[str, dict]:
    """Validate and key one exact-head disposition per selected finding."""
    expected = set(selected_ids)
    if len(expected) != len(selected_ids):
        raise AssessmentError("feedback adjudication dispositions must match selected findings")
    if isinstance(value, list):
        keyed = {}
        for record in value:
            finding_id = record.get("finding_id") if isinstance(record, dict) else None
            if finding_id not in expected or finding_id in keyed:
                raise AssessmentError("feedback adjudication dispositions must match selected findings")
            keyed[finding_id] = record
    elif isinstance(value, dict):
        keyed = value
    else:
        raise AssessmentError("feedback adjudication dispositions must match selected findings")
    if set(keyed) != expected:
        raise AssessmentError("feedback adjudication dispositions must match selected findings")
    normalized = {}
    for finding_id in selected_ids:
        record = keyed[finding_id]
        if not isinstance(record, dict) or set(record) != {"finding_id", "disposition", "basis", "evidence"}:
            raise AssessmentError(f"feedback disposition for {finding_id} is invalid")
        if record["finding_id"] != finding_id:
            raise AssessmentError(f"feedback disposition for {finding_id} has invalid ownership")
        disposition = record["disposition"]
        basis = record["basis"]
        evidence = record["evidence"]
        if disposition not in {"upheld", "refuted", "cannot_verify"}:
            raise AssessmentError(f"feedback disposition for {finding_id} is invalid")
        if not isinstance(basis, str) or not basis.strip():
            raise AssessmentError(f"feedback disposition for {finding_id} has no basis")
        if not isinstance(evidence, list):
            raise AssessmentError(f"feedback disposition for {finding_id} has invalid evidence")
        if disposition in {"upheld", "refuted"} and not evidence:
            raise AssessmentError(f"feedback disposition for {finding_id} requires exact-head evidence")
        seen = set()
        for location in evidence:
            if not isinstance(location, dict) or set(location) != {"path", "line"}:
                raise AssessmentError(f"feedback disposition for {finding_id} has invalid evidence")
            path, line = location["path"], location["line"]
            if (
                not isinstance(path, str)
                or not path
                or (line is not None and (type(line) is not int or line < 1))
                or (path, line) not in reviewed_locations
                or (path, line) in seen
            ):
                raise AssessmentError(f"feedback disposition for {finding_id} has invalid evidence")
            seen.add((path, line))
        normalized[finding_id] = copy.deepcopy(record)
    return normalized


def _materialize_feedback_scorecard(previous_result: dict, findings: list[dict], exemptions: list[dict]) -> dict:
    """Recalculate snapshot scores after independently verified feedback."""
    scorecard = previous_result.get("scorecard")
    head = previous_result.get("head")
    if not isinstance(scorecard, dict) or not isinstance(head, dict):
        raise AssessmentError("feedback adjudication previous score state is invalid")
    if not isinstance(head.get("base_sha"), str) or not isinstance(head.get("head_sha"), str):
        raise AssessmentError("feedback adjudication previous head is invalid")
    basis = scorecard.get("basis")
    categories = scorecard.get("categories")
    if not isinstance(categories, dict) or set(categories) != set(SCORE_CATEGORIES):
        raise AssessmentError("feedback adjudication previous categories are invalid")

    source_findings = previous_result["findings"]
    source_by_id = {finding["finding_id"]: finding for finding in source_findings}
    candidate_to_finding = {}
    for finding in source_findings:
        finding_id = finding["finding_id"]
        source_ids = finding.get("source_candidate_ids")
        if not isinstance(source_ids, list):
            raise AssessmentError("feedback adjudication previous finding provenance is invalid")
        for candidate_id in source_ids:
            if not isinstance(candidate_id, str) or not candidate_id:
                raise AssessmentError("feedback adjudication previous finding provenance is invalid")
            owner = candidate_to_finding.setdefault(candidate_id, finding_id)
            if owner != finding_id:
                raise AssessmentError("feedback adjudication previous finding provenance is ambiguous")
    category_ids = {}
    for name in SCORE_CATEGORIES:
        category = categories[name]
        finding_ids = category.get("finding_ids") if isinstance(category, dict) else None
        candidate_ids = category.get("candidate_ids") if isinstance(category, dict) else None
        if (
            not isinstance(finding_ids, list)
            or len(set(finding_ids)) != len(finding_ids)
            or any(finding_id not in source_by_id for finding_id in finding_ids)
            or not isinstance(candidate_ids, list)
            or any(candidate_id not in candidate_to_finding for candidate_id in candidate_ids)
            or list(dict.fromkeys(candidate_to_finding[candidate_id] for candidate_id in candidate_ids)) != finding_ids
        ):
            raise AssessmentError("feedback adjudication previous category citations are invalid")
        category_ids[name] = finding_ids

    def receipt_for(kept: list[dict]) -> dict:
        kept_by_id = {finding["finding_id"]: finding for finding in kept}
        return {
            "cause_groups": [
                {
                    "primary_candidate_id": finding["candidate_id"],
                    "supporting_candidate_ids": [],
                    "claim_class": finding.get("claim_class"),
                    "causal_basis": finding.get("causal_basis"),
                }
                for finding in kept
            ],
            "scorecard_assessment": {
                "categories": {
                    name: {
                        "rationale": "Score recalculated from current snapshot penalties.",
                        "candidate_ids": [
                            kept_by_id[finding_id]["candidate_id"]
                            for finding_id in category_ids[name]
                            if finding_id in kept_by_id
                        ],
                        "rule_ids": list(
                            dict.fromkeys(
                                rule_id
                                for finding_id in category_ids[name]
                                if finding_id in kept_by_id
                                for rule_id in kept_by_id[finding_id].get("rule_ids") or ()
                            )
                        ),
                        "locations": [
                            copy.deepcopy(kept_by_id[finding_id]["primary_location"])
                            for finding_id in category_ids[name]
                            if finding_id in kept_by_id
                            and isinstance(kept_by_id[finding_id].get("primary_location"), dict)
                        ],
                    }
                    for name in SCORE_CATEGORIES
                }
            },
        }

    source = materialize_scorecard(
        receipt_for(source_findings),
        findings=source_findings,
        score_basis=basis,
        exempt_finding_ids=[record["finding_id"] for record in previous_result.get("score_exemptions", [])],
    )
    if source["overall_branch"] != scorecard.get("overall_branch") or any(
        source["categories"][name][key] != categories[name].get(key)
        for name in SCORE_CATEGORIES
        for key in ("score", "penalty_points", "ceiling", "finding_ids")
    ):
        raise AssessmentError("feedback adjudication previous scorecard is not reproducible")
    previous = _previous_snapshot(
        {
            "run_id": previous_result["run_id"],
            "base_sha": head["base_sha"],
            "head_sha": head["head_sha"],
            "point_pool": basis.get("point_pool") if isinstance(basis, dict) else None,
            "categories": {
                name: {
                    "score": categories[name]["score"],
                    "penalty_points": categories[name]["penalty_points"],
                    "ceiling": categories[name]["ceiling"],
                }
                for name in SCORE_CATEGORIES
            },
            "overall_branch": scorecard["overall_branch"],
        }
    )
    return materialize_scorecard(
        receipt_for(findings),
        findings=findings,
        score_basis=basis,
        previous_scorecard=previous,
        exempt_finding_ids=[record["finding_id"] for record in exemptions],
    )


class AssessmentError(ValueError):
    """Report final-synthesis output that cannot be published safely."""


def _candidate_id(candidate: dict) -> str:
    """Return one required pipeline candidate identifier."""
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise AssessmentError("a final-input candidate has no candidate_id")
    return candidate_id


def _string_list(value: object, name: str) -> list[str]:
    """Validate and return one list of nonempty strings."""
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise AssessmentError(f"{name} must be an array of nonempty strings")
    return value


def _locations(value: object, allowed_paths: set[str], owner: str = "score") -> list[dict]:
    """Validate evidence locations against the reviewed scope."""
    if not isinstance(value, list):
        raise AssessmentError(f"{owner} locations must be an array")
    locations = []
    for location in value:
        if not isinstance(location, dict) or set(location) != {"path", "line"}:
            raise AssessmentError(f"{owner} locations must contain only path and line")
        path, line = location["path"], location["line"]
        if not isinstance(path, str) or not path or path not in allowed_paths:
            raise AssessmentError(f"{owner} location {path!r} is outside the reviewed scope")
        if line is not None and (type(line) is not int or line < 1):
            raise AssessmentError(f"{owner} location lines must be positive integers or null")
        locations.append(location)
    return locations


def validate_candidate_ownership(
    candidates: object,
    applicable_rule_ids: tuple[str, ...] | list[str],
    reviewed_files: tuple[str, ...] | list[str],
    *,
    delta_index: dict[str, dict] | None = None,
    forge_rule_ids: tuple[str, ...] | list[str] | set[str] = (),
) -> None:
    """Require every candidate to cite an applicable rule, reviewed location, and delta trigger."""
    if not isinstance(candidates, list):
        raise AssessmentError("review candidates must be an array")
    allowed_rules = set(applicable_rule_ids)
    allowed_paths = set(reviewed_files)
    forge_rules = set(forge_rule_ids)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise AssessmentError("a review candidate is not an object")
        rule_ids = _string_list(candidate.get("rule_ids"), "candidate rule_ids")
        if not rule_ids:
            raise AssessmentError("candidate rule_ids must include an applicable rule")
        unknown_rule = next((rule_id for rule_id in rule_ids if rule_id not in allowed_rules), None)
        if unknown_rule is not None:
            raise AssessmentError(f"candidate cites inapplicable rule {unknown_rule}")
        locations = _locations(candidate.get("locations"), allowed_paths, "candidate")
        if not locations:
            raise AssessmentError("candidate locations must include a reviewed path")
        if delta_index is None:
            continue
        evidence = candidate.get("delta_evidence")
        if evidence is None:
            if set(rule_ids).issubset(forge_rules):
                continue
            raise AssessmentError("candidate delta_evidence is required")
        if not isinstance(evidence, dict) or set(evidence) != {"path", "line", "side", "basis"}:
            raise AssessmentError("candidate delta_evidence must contain only path, line, side, and basis")
        path, line, side, basis = evidence["path"], evidence["line"], evidence["side"], evidence["basis"]
        if not isinstance(path, str) or not path or path not in allowed_paths or path not in delta_index:
            raise AssessmentError(f"candidate delta_evidence path {path!r} is outside the original delta")
        if not isinstance(basis, str) or not basis.strip():
            raise AssessmentError("candidate delta_evidence basis must be nonempty")
        indexed = delta_index[path]
        if not isinstance(indexed, dict):
            raise AssessmentError("host delta index is invalid")
        if side == "file":
            if line is not None or indexed.get("file") is not True:
                raise AssessmentError("candidate file-level delta_evidence is outside the original delta")
            continue
        if side not in {"base", "head"}:
            raise AssessmentError("candidate delta_evidence side is invalid")
        if type(line) is not int or line < 1 or not _line_in_intervals(line, indexed.get(side)):
            raise AssessmentError("candidate delta_evidence line is outside the original delta")


def _line_in_intervals(line: int, intervals: object) -> bool:
    """Tell whether one positive line lies inside a host-owned inclusive interval."""
    if not isinstance(intervals, (list, tuple)):
        raise AssessmentError("host delta index intervals are invalid")
    for interval in intervals:
        if (
            not isinstance(interval, (list, tuple))
            or len(interval) != 2
            or type(interval[0]) is not int
            or type(interval[1]) is not int
            or interval[0] < 1
            or interval[1] < interval[0]
        ):
            raise AssessmentError("host delta index intervals are invalid")
        if interval[0] <= line <= interval[1]:
            return True
    return False


def validate_final_receipt(
    candidates: list[dict],
    receipt: dict,
    *,
    applicable_rule_ids: tuple[str, ...] | list[str] = (),
    reviewed_files: tuple[str, ...] | list[str] = (),
    verification_dispositions: dict[str, dict] | None = None,
    delta_index: dict[str, dict] | None = None,
    forge_rule_ids: tuple[str, ...] | list[str] | set[str] = (),
) -> tuple[dict, tuple[str, ...]]:
    """Validate and conservatively complete one final-synthesis receipt.

    Omission is the only recoverable partition fault: each omitted known candidate becomes an
    ordered singleton group. Invented or duplicate membership is ambiguous and therefore fails
    closed. Score evidence is checked against host-owned candidate, rule, and path sets.

    Args:
        candidates: Deduplicated candidates supplied to final synthesis.
        receipt: Decoded final-synthesis receipt.
        applicable_rule_ids: Host-owned rule identifiers evaluated by this review.
        reviewed_files: Host-owned logical paths in the immutable review scope.
        verification_dispositions: Host-reconciled verifier evidence keyed by final or source
            candidate identifier. Default-review drops are valid only when this evidence
            independently refutes the candidate.
        delta_index: Host-owned original-delta changed-line and file-level index.
        forge_rule_ids: Applicable required-check rule identifiers exempt from Git ownership.

    Returns:
        A normalized receipt and bounded recovery diagnostics.

    Raises:
        AssessmentError: When required final output is missing, invented, duplicated, or
            insufficiently grounded.
    """
    if not isinstance(receipt, dict):
        raise AssessmentError("final synthesis did not return an object")
    normalized = copy.deepcopy(receipt)
    verification_dispositions = verification_dispositions or {}
    validate_candidate_ownership(
        candidates,
        applicable_rule_ids,
        reviewed_files,
        delta_index=delta_index,
        forge_rule_ids=forge_rule_ids,
    )
    candidate_by_id: dict[str, dict] = {}
    for candidate in candidates:
        candidate_id = _candidate_id(candidate)
        if candidate_id in candidate_by_id:
            raise AssessmentError(f"final input repeats candidate {candidate_id}")
        candidate_by_id[candidate_id] = candidate
    known = set(candidate_by_id)

    groups = normalized.get("cause_groups")
    if not isinstance(groups, list):
        raise AssessmentError("final synthesis omitted cause_groups")
    model_group_count = len(groups)
    seen: set[str] = set()
    kept: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise AssessmentError("a cause group is not an object")
        primary = group.get("primary_candidate_id")
        supporting = _string_list(group.get("supporting_candidate_ids"), "supporting_candidate_ids")
        claim_class = group.get("claim_class")
        causal_basis = group.get("causal_basis")
        if not isinstance(primary, str) or primary not in known:
            raise AssessmentError(f"cause group names unknown primary {primary!r}")
        recovered_group = claim_class == _RECOVERED_CLASS and not supporting and causal_basis == _RECOVERED_BASIS
        if claim_class not in _CLAIM_CLASSES and not recovered_group:
            raise AssessmentError(f"cause group has invalid claim class {claim_class!r}")
        if not isinstance(causal_basis, str) or not causal_basis.strip():
            raise AssessmentError("cause group causal_basis must be nonempty")
        members = [primary, *supporting]
        if len(set(members)) != len(members):
            raise AssessmentError(f"cause group repeats candidate {primary}")
        unknown = next((candidate_id for candidate_id in members if candidate_id not in known), None)
        if unknown is not None:
            raise AssessmentError(f"cause group names unknown candidate {unknown}")
        duplicate = next((candidate_id for candidate_id in members if candidate_id in seen), None)
        if duplicate is not None:
            raise AssessmentError(f"candidate {duplicate} belongs to more than one disposition")
        if _is_test_candidate(candidate_by_id[primary]):
            production_primary = next(
                (
                    candidate_id
                    for candidate_id in supporting
                    if _production_location(candidate_by_id[candidate_id]) is not None
                ),
                None,
            )
            if production_primary is not None:
                # The group already asserts one causal defect. Within that bounded membership,
                # prefer the actionable production location and keep the test manifestation as
                # evidence; this is normalization, never a new semantic merge.
                group["primary_candidate_id"] = production_primary
                group["supporting_candidate_ids"] = [
                    primary,
                    *(candidate_id for candidate_id in supporting if candidate_id != production_primary),
                ]
        seen.update(members)
        kept.update(members)

    dropped = normalized.get("dropped")
    if not isinstance(dropped, list):
        raise AssessmentError("final synthesis omitted dropped")
    for entry in dropped:
        if not isinstance(entry, dict):
            raise AssessmentError("a dropped disposition is not an object")
        candidate_id = entry.get("candidate_id")
        reason_code = entry.get("reason_code")
        reason = entry.get("reason")
        evidence_refs = entry.get("evidence_refs")
        if not isinstance(candidate_id, str) or candidate_id not in known:
            raise AssessmentError(f"final synthesis dropped unknown candidate {candidate_id!r}")
        if candidate_id in seen:
            raise AssessmentError(f"candidate {candidate_id} belongs to more than one disposition")
        if reason_code != "verifier_refuted":
            raise AssessmentError(f"drop for candidate {candidate_id} has invalid reason_code {reason_code!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise AssessmentError(f"drop for candidate {candidate_id} has no grounded reason")
        if not isinstance(evidence_refs, list) or not evidence_refs:
            raise AssessmentError(f"drop for candidate {candidate_id} has no verification evidence_refs")
        source_ids = candidate_by_id[candidate_id].get("source_candidate_ids")
        required_ids = (
            {str(source_id) for source_id in source_ids}
            if isinstance(source_ids, list) and source_ids
            else {candidate_id}
        )
        seen_refs: set[str] = set()
        for evidence_ref in evidence_refs:
            if not isinstance(evidence_ref, dict) or set(evidence_ref) != {"kind", "candidate_id"}:
                raise AssessmentError(f"drop for candidate {candidate_id} has an invalid evidence_ref")
            reference_id = evidence_ref["candidate_id"]
            if evidence_ref["kind"] != "verification" or reference_id not in required_ids:
                raise AssessmentError(f"drop for candidate {candidate_id} cites unrelated verification evidence")
            if reference_id in seen_refs:
                raise AssessmentError(f"drop for candidate {candidate_id} repeats verification {reference_id}")
            seen_refs.add(reference_id)
        if seen_refs != required_ids:
            raise AssessmentError(f"drop for candidate {candidate_id} does not cite every source verification")
        for reference_id in required_ids:
            disposition = verification_dispositions.get(reference_id)
            if not (
                isinstance(disposition, dict)
                and disposition.get("disposition") == "refuted"
                and isinstance(disposition.get("evidence"), str)
                and disposition["evidence"].strip()
            ):
                raise AssessmentError(
                    f"drop for candidate {candidate_id} is not grounded by refuted verification for every source"
                )
        seen.add(candidate_id)

    diagnostics = []
    for candidate_id in candidate_by_id:
        if candidate_id in seen:
            continue
        groups.append(
            {
                "primary_candidate_id": candidate_id,
                "supporting_candidate_ids": [],
                "claim_class": _RECOVERED_CLASS,
                "causal_basis": _RECOVERED_BASIS,
            }
        )
        kept.add(candidate_id)
        seen.add(candidate_id)
        diagnostics.append(f"Final synthesis omitted candidate {candidate_id}; the host restored it as a singleton.")

    for group in groups:
        primary = group["primary_candidate_id"]
        disposition = verification_dispositions.get(primary)
        if not isinstance(disposition, dict) or disposition.get("ownership") != "introduced_or_worsened":
            raise AssessmentError(f"cause group primary {primary} lacks introduced-or-worsened verification ownership")

    verdict = normalized.get("verdict")
    if verdict not in ("CLEAN", "CHANGES_REQUIRED"):
        raise AssessmentError("final synthesis must return CLEAN or CHANGES_REQUIRED")
    if model_group_count and verdict == "CLEAN":
        raise AssessmentError("final synthesis cannot return CLEAN with an actionable cause group")
    verdict_basis = normalized.get("verdict_basis")
    if not isinstance(verdict_basis, str) or not verdict_basis.strip():
        raise AssessmentError("final synthesis verdict_basis must be nonempty")
    if diagnostics:
        # An omitted actionable candidate can never coexist safely with CLEAN. The final worker
        # saw the complete input, but the host owns all score arithmetic. Validate the original
        # verdict first so omission does not accidentally repair a second protocol fault.
        normalized["verdict"] = "CHANGES_REQUIRED"

    assessment = normalized.get("scorecard_assessment")
    categories = assessment.get("categories") if isinstance(assessment, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(SCORE_CATEGORIES):
        raise AssessmentError("scorecard assessment must contain exactly the three canonical categories")
    known_rules = set(applicable_rule_ids) or {
        str(rule_id) for candidate in candidates for rule_id in candidate.get("rule_ids") or ()
    }
    known_paths = set(reviewed_files) or {
        str(location.get("path"))
        for candidate in candidates
        for location in candidate.get("locations") or ()
        if isinstance(location, dict) and isinstance(location.get("path"), str)
    }
    for category_name in SCORE_CATEGORIES:
        category = categories[category_name]
        if not isinstance(category, dict) or set(category) != {
            "rationale",
            "candidate_ids",
            "rule_ids",
            "locations",
        }:
            raise AssessmentError(f"score category {category_name} is not an object")
        rationale = category.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise AssessmentError(f"score category {category_name} must have a rationale")
        cited_candidates = _string_list(category.get("candidate_ids"), "score candidate_ids")
        cited_rules = _string_list(category.get("rule_ids"), "score rule_ids")
        cited_locations = _locations(category.get("locations"), known_paths)
        unknown_candidate = next((candidate_id for candidate_id in cited_candidates if candidate_id not in kept), None)
        if unknown_candidate is not None:
            raise AssessmentError(f"score category {category_name} cites noncanonical candidate {unknown_candidate}")
        unknown_rule = next((rule_id for rule_id in cited_rules if rule_id not in known_rules), None)
        if unknown_rule is not None:
            raise AssessmentError(f"score category {category_name} cites inapplicable rule {unknown_rule}")
        if not (cited_candidates or cited_rules or cited_locations):
            raise AssessmentError(f"score category {category_name} has no grounded evidence")
    if not groups and normalized["verdict"] != "CLEAN":
        raise AssessmentError("final synthesis cannot require changes when no canonical cause group remains")

    return normalized, tuple(diagnostics)


def _source_ids(candidate: dict) -> list[str]:
    """Return one candidate and any transitive source identifiers without duplicates."""
    return list(
        dict.fromkeys(
            [
                _candidate_id(candidate),
                *(str(source) for source in candidate.get("source_candidate_ids") or ()),
            ]
        )
    )


def _is_test_path(value: str) -> bool:
    """Tell whether one repository-relative path is conventionally test-owned."""
    path = PurePosixPath(value.replace("\\", "/"))
    components = {part.casefold() for part in path.parts[:-1]}
    stem = path.stem.casefold()
    return bool(components.intersection({"test", "tests"}) or stem.startswith("test_") or stem.endswith("_test"))


def _production_location(candidate: dict) -> dict | None:
    """Return the first concrete non-test anchor, never treating no anchor as production."""
    return next(
        (
            location
            for location in candidate.get("locations") or ()
            if isinstance(location, dict)
            and isinstance(location.get("path"), str)
            and location["path"]
            and not _is_test_path(location["path"])
        ),
        None,
    )


def _is_test_candidate(candidate: dict) -> bool:
    """Tell whether every actionable location is unambiguously test-owned."""
    paths = [
        str(location.get("path"))
        for location in candidate.get("locations") or ()
        if isinstance(location, dict) and isinstance(location.get("path"), str) and location["path"]
    ]
    return bool(paths) and all(_is_test_path(path) for path in paths)


def _manifestations(candidate: dict, sources: dict[str, dict]) -> list[dict]:
    """Resolve a compacted candidate back to the original manifestations still on disk."""
    source_ids = candidate.get("source_candidate_ids")
    if isinstance(source_ids, list) and source_ids:
        candidate_id = _candidate_id(candidate)
        resolved = [
            candidate if str(source) == candidate_id else sources[str(source)]
            for source in source_ids
            if str(source) == candidate_id or str(source) in sources
        ]
        if resolved:
            return resolved
    return [candidate]


def materialize_findings(
    candidates: list[dict],
    normalized_receipt: dict,
    dispositions: dict[str, dict] | None = None,
    source_candidates: list[dict] | None = None,
) -> list[dict]:
    """Materialize one production-primary finding per validated cause group."""
    by_id = {_candidate_id(candidate): candidate for candidate in candidates}
    source_by_id = {
        _candidate_id(candidate): candidate
        for candidate in (source_candidates if source_candidates is not None else candidates)
    }
    dispositions = dispositions or {}
    findings = []
    for group in normalized_receipt["cause_groups"]:
        canonical_primary_id = group["primary_candidate_id"]
        grouped = [
            by_id[canonical_primary_id],
            *(by_id[candidate_id] for candidate_id in group["supporting_candidate_ids"]),
        ]
        manifestations = list(
            {
                _candidate_id(manifestation): manifestation
                for candidate in grouped
                for manifestation in _manifestations(candidate, source_by_id)
            }.values()
        )
        preferred = next(
            (candidate for candidate in manifestations if _production_location(candidate) is not None), None
        )
        primary = preferred or manifestations[0]
        primary_id = _candidate_id(primary)
        supports = [candidate for candidate in manifestations if _candidate_id(candidate) != primary_id]
        primary_locations = list(primary.get("locations") or ())
        primary_location = _production_location(primary) or (primary_locations[0] if primary_locations else None)
        if primary_location is not None:
            primary_locations = [
                primary_location,
                *(location for location in primary_locations if location != primary_location),
            ]
        source_ids = list(
            dict.fromkeys(
                [
                    *(_candidate_id(candidate) for candidate in grouped),
                    *(source for candidate in (primary, *supports) for source in _source_ids(candidate)),
                ]
            )
        )
        rule_ids = list(
            dict.fromkeys(
                str(rule_id) for candidate in (primary, *supports) for rule_id in candidate.get("rule_ids") or ()
            )
        )
        findings.append(
            {
                **primary,
                "candidate_id": primary_id,
                "finding_id": _format_finding_id(len(findings) + 1),
                "source_candidate_ids": source_ids,
                "claim_class": group["claim_class"],
                "causal_basis": group["causal_basis"],
                # Ownership follows the canonical trigger even when presentation promotes a
                # production manifestation over a test-primary candidate.
                "delta_evidence": copy.deepcopy(by_id[canonical_primary_id].get("delta_evidence")),
                "primary_location": primary_location,
                "locations": primary_locations,
                "rule_ids": rule_ids,
                "supporting_evidence": [
                    {
                        "candidate_id": _candidate_id(candidate),
                        "title": candidate.get("title", ""),
                        "evidence": candidate.get("evidence", ""),
                        "rule_ids": list(candidate.get("rule_ids") or ()),
                        "locations": list(candidate.get("locations") or ()),
                        "verification": dispositions.get(_candidate_id(candidate)),
                    }
                    for candidate in supports
                ],
                "verification": dispositions.get(primary_id) or dispositions.get(canonical_primary_id),
            }
        )
    return findings


def materialize_scorecard(
    normalized_receipt: dict,
    *,
    findings: list[dict] | None = None,
    score_basis: dict | None = None,
    previous_scorecard: dict | None = None,
    comparison_reason: str | None = None,
    exempt_finding_ids: tuple[str, ...] | list[str] | set[str] = (),
) -> dict:
    """Return host-owned scores for the current snapshot and an optional comparison."""
    if (
        not isinstance(score_basis, dict)
        or set(score_basis) != {"formula", "point_pool", "workload"}
        or score_basis.get("formula") != SCORE_FORMULA_VERSION
        or type(score_basis.get("point_pool")) is not int
        or score_basis["point_pool"] < 1
    ):
        raise AssessmentError("score basis is invalid")
    workload = score_basis["workload"]
    if (
        not isinstance(workload, dict)
        or set(workload) != {"metric", "units", "changes", "lines", "sha256"}
        or workload.get("metric") != WORKLOAD_METRIC_VERSION
        or type(workload.get("units")) is not int
        or workload["units"] < 0
        or type(workload.get("changes")) is not int
        or workload["changes"] < 0
        or type(workload.get("lines")) is not int
        or workload["lines"] < 0
        or not isinstance(workload.get("sha256"), str)
        or _HEX_DIGEST.fullmatch(workload["sha256"]) is None
    ):
        raise AssessmentError("score workload is invalid")
    point_pool = score_basis["point_pool"]
    if point_pool != point_pool_for_lines(workload["lines"]):
        raise AssessmentError("score point pool does not match workload lines")
    assessment = normalized_receipt.get("scorecard_assessment")
    categories = assessment.get("categories") if isinstance(assessment, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(SCORE_CATEGORIES):
        raise AssessmentError("scorecard assessment must contain exactly the three canonical categories")
    categories = copy.deepcopy(categories)
    findings = findings or []
    findings_by_id, candidate_to_finding = {}, {}
    for finding in findings:
        finding_id = finding.get("finding_id") if isinstance(finding, dict) else None
        candidate_id = finding.get("candidate_id") if isinstance(finding, dict) else None
        source_ids = finding.get("source_candidate_ids") if isinstance(finding, dict) else None
        if (
            not isinstance(finding_id, str)
            or finding_id in findings_by_id
            or not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(source_ids, list)
            or candidate_id not in source_ids
            or len(set(source_ids)) != len(source_ids)
            or any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
        ):
            raise AssessmentError("score finding identity is invalid")
        _finding_sequence(finding_id)
        findings_by_id[finding_id] = finding
        for source_id in source_ids:
            owner = candidate_to_finding.setdefault(source_id, finding_id)
            if owner != finding_id:
                raise AssessmentError(f"score candidate {source_id} belongs to multiple findings")
    penalty_by_id = {
        finding_id: _severity_debt(finding.get("severity"), finding_id)
        for finding_id, finding in findings_by_id.items()
    }
    if (
        not isinstance(exempt_finding_ids, (list, tuple, set, frozenset))
        or any(not isinstance(finding_id, str) or finding_id not in findings_by_id for finding_id in exempt_finding_ids)
        or len(set(exempt_finding_ids)) != len(exempt_finding_ids)
    ):
        raise AssessmentError("score exemptions must reference unique current findings")
    exempt_ids = set(exempt_finding_ids)
    finding_ids_by_category = {name: [] for name in SCORE_CATEGORIES}
    for name in SCORE_CATEGORIES:
        category = categories[name]
        if not isinstance(category, dict) or set(category) != {
            "rationale",
            "candidate_ids",
            "rule_ids",
            "locations",
        }:
            raise AssessmentError(f"score category {name} is invalid")
        candidate_ids = _string_list(category["candidate_ids"], "score candidate_ids")
        unknown = next(
            (candidate_id for candidate_id in candidate_ids if candidate_id not in candidate_to_finding), None
        )
        if unknown is not None:
            raise AssessmentError(f"score category {name} cites unknown candidate {unknown}")
    for finding_id, finding in findings_by_id.items():
        category_name = SCORE_CATEGORY_BY_CLAIM_CLASS.get(finding.get("claim_class"))
        if category_name is None:
            raise AssessmentError(f"finding {finding_id} has invalid claim class {finding.get('claim_class')!r}")
        finding_ids_by_category[category_name].append(finding_id)
    groups = normalized_receipt.get("cause_groups", [])
    if not isinstance(groups, list) or (groups and len(groups) != len(findings)):
        raise AssessmentError("score findings do not match canonical cause groups")
    previous = _previous_snapshot(previous_scorecard)
    recovered = []
    for group in groups:
        if group.get("claim_class") != _RECOVERED_CLASS:
            continue
        recovered.append(group["primary_candidate_id"])
    penalties = {}
    for name in SCORE_CATEGORIES:
        finding_ids = finding_ids_by_category[name]
        categories[name]["candidate_ids"] = [findings_by_id[finding_id]["candidate_id"] for finding_id in finding_ids]
        categories[name]["rule_ids"] = list(
            dict.fromkeys(
                rule_id for finding_id in finding_ids for rule_id in findings_by_id[finding_id].get("rule_ids") or ()
            )
        )
        categories[name]["locations"] = [
            copy.deepcopy(findings_by_id[finding_id]["primary_location"])
            for finding_id in finding_ids
            if isinstance(findings_by_id[finding_id].get("primary_location"), dict)
        ]
        charged_ids = [finding_id for finding_id in finding_ids if finding_id not in exempt_ids]
        penalties[name] = sum(penalty_by_id[finding_id] for finding_id in charged_ids)
        ceiling = min(
            (_severity_ceiling(findings_by_id[finding_id].get("severity")) for finding_id in charged_ids),
            default=10,
        )
        categories[name]["penalty_points"] = penalties[name]
        categories[name]["ceiling"] = ceiling
        categories[name]["score"] = _score_value(point_pool, penalties[name], ceiling)
        categories[name]["finding_ids"] = finding_ids
    if comparison_reason not in (None, "assessment_changed"):
        raise AssessmentError("comparison reason is invalid")
    if previous is None and comparison_reason is not None:
        raise AssessmentError("comparison reason requires a previous scorecard")
    if (
        previous is not None
        and "ceiling" not in previous["categories"][SCORE_CATEGORIES[0]]
        and comparison_reason != "assessment_changed"
    ):
        raise AssessmentError("legacy score comparison requires assessment_changed")
    reason = "no_previous_run" if previous is None else comparison_reason
    overall = _overall_score([categories[name]["score"] for name in SCORE_CATEGORIES])
    comparable = previous is not None and reason is None
    delta = (
        {
            "categories": {
                name: {
                    "score": _score_delta(previous["categories"][name]["score"], categories[name]["score"]),
                    "penalty_points": (penalties[name] - previous["categories"][name]["penalty_points"]),
                }
                for name in SCORE_CATEGORIES
            },
            "overall_branch": _score_delta(previous["overall_branch"], overall),
        }
        if comparable
        else None
    )
    weak_areas = [
        {
            "category": name,
            "score": categories[name]["score"],
            "rationale": categories[name]["rationale"],
            "finding_ids": categories[name]["finding_ids"],
        }
        for name in SCORE_CATEGORIES
        if categories[name]["score"] <= 7
    ]
    return {
        "categories": categories,
        "overall_branch": overall,
        "basis": copy.deepcopy(score_basis),
        "recovered_candidate_ids": recovered,
        "previous": previous,
        "delta": delta,
        "comparison": {"comparable": comparable, "reason_code": reason},
        "weak_areas": weak_areas,
        "diagnostics": [],
    }


def _severity_debt(value: object, finding_id: str) -> int:
    """Return the integer snapshot penalty for one normalized severity."""
    penalty = SEVERITY_PENALTIES.get(value.strip().casefold()) if isinstance(value, str) else None
    if penalty is None:
        raise AssessmentError(f"finding {finding_id} has unknown severity {value!r}")
    return penalty


def _severity_ceiling(value: object) -> int:
    """Return the category ceiling one charged severity imposes, or 10 when it imposes none."""
    return SEVERITY_CEILINGS.get(value.strip().casefold(), 10) if isinstance(value, str) else 10


def _score_value(point_pool: int, penalty_points: int, ceiling: int = 10) -> float:
    """Return the density score scaled to the severity ceiling and rounded half-up to two decimal places."""
    if (
        type(point_pool) is not int
        or point_pool < 1
        or type(penalty_points) is not int
        or penalty_points < 0
        or type(ceiling) is not int
        or not 0 <= ceiling <= 10
    ):
        raise AssessmentError("score inputs are invalid")
    return _rounded_score(Fraction(ceiling * max(point_pool - penalty_points, 0), point_pool))


def _overall_score(scores: list[int | float]) -> float:
    """Return the exact mean of the published category scores rounded half-up to two decimal places."""
    if len(scores) != len(SCORE_CATEGORIES) or any(
        type(score) not in (int, float) or not 0 <= score <= 10 for score in scores
    ):
        raise AssessmentError("overall score inputs are invalid")
    return _rounded_score(sum((Fraction(str(score)) for score in scores), Fraction()) / len(scores))


def _legacy_overall_score(point_pool: int, penalties_by_category: dict[str, int]) -> float:
    """Return the legacy mean of unrounded linear scores rounded half-up to two decimal places."""
    if not isinstance(penalties_by_category, dict) or set(penalties_by_category) != set(SCORE_CATEGORIES):
        raise AssessmentError("overall score penalties are invalid")
    scores = []
    for name in SCORE_CATEGORIES:
        penalty = penalties_by_category[name]
        if type(penalty) is not int or penalty < 0:
            raise AssessmentError("overall score penalties are invalid")
        if type(point_pool) is not int or point_pool < 1:
            raise AssessmentError("score inputs are invalid")
        scores.append(Fraction(10 * max(point_pool - penalty, 0), point_pool))
    return _rounded_score(sum(scores, Fraction()) / len(scores))


def _score_delta(previous_score: int | float, current_score: int | float) -> float:
    """Return one published score change rounded half-up."""
    if any(type(value) not in (int, float) or not 0 <= value <= 10 for value in (previous_score, current_score)):
        raise AssessmentError("score delta values are invalid")
    return _rounded_score(Fraction(str(current_score)) - Fraction(str(previous_score)))


def _rounded_score(value: Fraction) -> float:
    """Round one exact score half-up to two decimal places."""
    sign = -1 if value < 0 else 1
    scaled = abs(value) * 100
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    if remainder * 2 >= scaled.denominator:
        whole += 1
    return float(sign * Fraction(whole, 100))


def _format_finding_id(sequence: int) -> str:
    """Format one positive monotonic finding sequence."""
    return f"F-{sequence:04d}"


def _finding_sequence(finding_id: str) -> int:
    """Return the integer portion of one canonical finding identifier."""
    match = _FINDING_ID.fullmatch(finding_id)
    if match is None:
        raise AssessmentError(f"invalid finding_id {finding_id!r}")
    sequence = int(match.group(1))
    if sequence < 1 or _format_finding_id(sequence) != finding_id:
        raise AssessmentError(f"invalid finding_id {finding_id!r}")
    return sequence


def _previous_snapshot(value: dict | None) -> dict | None:
    """Return a minimal nonrecursive score snapshot or None."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "run_id",
        "base_sha",
        "head_sha",
        "point_pool",
        "categories",
        "overall_branch",
    }:
        raise AssessmentError("previous scorecard is invalid")
    if (
        not isinstance(value["run_id"], str)
        or not value["run_id"]
        or not isinstance(value["base_sha"], str)
        or not value["base_sha"]
        or not isinstance(value["head_sha"], str)
        or not value["head_sha"]
        or type(value["point_pool"]) is not int
        or value["point_pool"] < 1
        or not isinstance(value["categories"], dict)
    ):
        raise AssessmentError("previous scorecard is invalid")
    categories = value["categories"]
    category_fields = {"score", "penalty_points"}
    if any(isinstance(category, dict) and "ceiling" in category for category in categories.values()):
        category_fields.add("ceiling")
    if set(categories) != set(SCORE_CATEGORIES) or any(
        not isinstance(categories[name], dict)
        or set(categories[name]) != category_fields
        or type(categories[name].get("score")) not in (int, float)
        or not 0 <= categories[name]["score"] <= 10
        or type(categories[name].get("penalty_points")) is not int
        or categories[name]["penalty_points"] < 0
        or categories[name]["score"]
        != _score_value(value["point_pool"], categories[name]["penalty_points"], categories[name].get("ceiling", 10))
        for name in SCORE_CATEGORIES
    ):
        raise AssessmentError("previous scorecard categories are invalid")
    overall = value.get("overall_branch")
    expected_overall = (
        _overall_score([categories[name]["score"] for name in SCORE_CATEGORIES])
        if "ceiling" in category_fields
        else _legacy_overall_score(
            value["point_pool"], {name: categories[name]["penalty_points"] for name in SCORE_CATEGORIES}
        )
    )
    if type(overall) not in (int, float) or not 0 <= overall <= 10 or overall != expected_overall:
        raise AssessmentError("previous scorecard overall is invalid")
    return copy.deepcopy(value)
