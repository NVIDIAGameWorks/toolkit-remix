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
from dataclasses import asdict, dataclass
from pathlib import Path

from .artifacts import canonical_hash


__all__ = [
    "ASSESSMENT_POLICY_HASH",
    "ASSESSMENT_POLICY_VERSION",
    "RUBRIC_HASH",
    "RUBRIC_VERSION",
    "SCORE_CATEGORY_BY_CLAIM_CLASS",
    "SCORE_DECIMAL_PLACES",
    "SCORE_FORMULA_VERSION",
    "SCORE_ROUNDING_MODE",
    "SEVERITY_PENALTIES",
    "WORKLOAD_METRIC_VERSION",
    "Rule",
    "load_rule_registry",
    "receipt_contract",
]


RUBRIC_VERSION = "1"
ASSESSMENT_POLICY_VERSION = "6"
WORKLOAD_METRIC_VERSION = "rule_change_units_v1"
SCORE_FORMULA_VERSION = "linear_snapshot_pool_v1"
SCORE_ROUNDING_MODE = "half_up"
SCORE_DECIMAL_PLACES = 2
SEVERITY_PENALTIES = {
    "critical": 3,
    "high": 3,
    "major": 3,
    "medium": 2,
    "moderate": 2,
    "minor": 1,
    "low": 1,
    "nit": 1,
}
SCORE_CATEGORY_BY_CLAIM_CLASS = {
    "behavioral_bug": "merge_readiness",
    "functional_gap": "merge_readiness",
    "static_correctness": "merge_readiness",
    "unclassified": "merge_readiness",
    "contract": "architecture_and_simplicity",
    "policy": "maintainability",
    "maintainability": "maintainability",
    "nit": "maintainability",
}
RUBRIC_HASH = canonical_hash(
    {"version": RUBRIC_VERSION, "categories": ["architecture_and_simplicity", "maintainability", "merge_readiness"]}
)
ASSESSMENT_POLICY_HASH = canonical_hash(
    {
        "version": ASSESSMENT_POLICY_VERSION,
        "workload_metric": WORKLOAD_METRIC_VERSION,
        "score_formula": SCORE_FORMULA_VERSION,
        "score_categories": SCORE_CATEGORY_BY_CLAIM_CLASS,
        "severity_penalties": SEVERITY_PENALTIES,
        "rounding": {"mode": SCORE_ROUNDING_MODE, "decimal_places": SCORE_DECIMAL_PLACES},
    }
)


_EXPECTED_RULE_FILES = {
    "A": "a-scope.json",
    "B": "b-logic.json",
    "C": "c-dependencies-api.json",
    "D": "d-quality.json",
    "E": "e-unit-tests.json",
    "F": "f-e2e-coverage.json",
    "G": "g-domain.json",
    "H": "h-delivery.json",
    "I": "i-mr-description.json",
}

_RULE_ID = re.compile(f"[{''.join(_EXPECTED_RULE_FILES)}][0-9]{{2,}}")


@dataclass(frozen=True)
class Rule:
    """One normalized review rule loaded from the canonical registry."""

    id: str
    target: str
    check: str
    sources: list[dict]
    category: str
    category_name: str
    evidence: str | None = None


def load_rule_registry(rules_dir: Path) -> tuple[list[Rule], str]:
    """Load the flat canonical rule registry.

    Args:
        rules_dir: Directory that holds one JSON file per rule category.

    Returns:
        The normalized rules in file order, and the registry content hash.

    Raises:
        ValueError: When a category file name, rule id, or evidence value is
            invalid, when a rule id repeats, or when a category has no rules.
    """
    rules = []
    seen = set()
    for path in sorted(Path(rules_dir).glob("*.json")):
        category = json.loads(path.read_text(encoding="utf-8"))
        if path.name != _EXPECTED_RULE_FILES.get(category.get("category")):
            raise ValueError(f"unexpected rule category file: {path.name}")
        for value in category.get("rules", []):
            rule = Rule(**value, category=category["category"], category_name=category["name"])
            rule_id = rule.id
            if not isinstance(rule_id, str) or not _RULE_ID.fullmatch(rule_id):
                raise ValueError(f"invalid rule id in {path.name}: {rule_id}")
            if rule.evidence not in (None, "description", "checks"):
                raise ValueError(f"invalid evidence in {path.name}: {rule_id}")
            if rule_id in seen:
                raise ValueError(f"duplicate rule id: {rule_id}")
            seen.add(rule_id)
            rules.append(rule)
    if set(_EXPECTED_RULE_FILES) != {rule.category for rule in rules}:
        raise ValueError("rule registry is incomplete")
    return rules, canonical_hash([asdict(rule) for rule in rules])


def receipt_contract(phase: str) -> dict:
    """Return the small JSON contract expected from native workers."""
    location = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "line": {"type": ["integer", "null"]},
        },
        "required": ["path", "line"],
        "additionalProperties": False,
    }
    delta_evidence = {
        "type": ["object", "null"],
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "line": {"type": ["integer", "null"]},
            "side": {"type": "string", "enum": ["base", "head", "file"]},
            "basis": {"type": "string", "minLength": 1},
        },
        "required": ["path", "line", "side", "basis"],
        "additionalProperties": False,
    }
    finding = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "severity": {"type": "string"},
            "impact": {"type": "string"},
            "evidence": {"type": "string"},
            "fix_direction": {"type": "string"},
            "rule_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
            "locations": {"type": "array", "minItems": 1, "items": location},
            "delta_evidence": delta_evidence,
        },
        "required": [
            "title",
            "severity",
            "impact",
            "evidence",
            "fix_direction",
            "rule_ids",
            "locations",
            "delta_evidence",
        ],
        "additionalProperties": False,
    }
    properties = {
        "schema_version": {
            "type": "integer",
            "const": 2 if phase in ("verification", "final-synthesis") else 1,
        },
        "packet_id": {"type": "string"},
        "lane": {"type": "string"},
        "phase": {"type": "string"},
        "status": {"type": "string"},
        "rule_ids": {"type": "array", "items": {"type": "string"}},
        "candidates": {"type": "array", "items": finding},
        "findings": {"type": "array", "items": finding, "maxItems": 0},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": ["string", "null"], "enum": ["CLEAN", "CHANGES_REQUIRED", None]},
        "verdict_basis": {"type": ["string", "null"]},
        "dependencies_read": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    }
    dropped = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "reason_code": {"type": "string", "enum": ["verifier_refuted"]},
            "reason": {"type": "string", "minLength": 1},
            "evidence_refs": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["verification"]},
                        "candidate_id": {"type": "string"},
                    },
                    "required": ["kind", "candidate_id"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["candidate_id", "reason_code", "reason", "evidence_refs"],
        "additionalProperties": False,
    }
    if phase not in ("file-review", "scope-review"):
        # Only review phases may originate candidates. Keep every other or retired phase
        # fail-closed without carrying a phase-specific contract.
        properties["candidates"]["maxItems"] = 0
    if phase == "final-synthesis":
        # The final pass groups one causal defect and its manifestations without re-authoring
        # finding prose. Ordered group primaries replace the old independent ranking; supporting
        # test manifestations stay as evidence instead of becoming duplicate comments.
        properties["cause_groups"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "primary_candidate_id": {"type": "string"},
                    "supporting_candidate_ids": {"type": "array", "items": {"type": "string"}},
                    "claim_class": {
                        "type": "string",
                        "enum": [name for name in SCORE_CATEGORY_BY_CLAIM_CLASS if name != "unclassified"],
                    },
                    "causal_basis": {"type": "string", "minLength": 1},
                },
                "required": [
                    "primary_candidate_id",
                    "supporting_candidate_ids",
                    "claim_class",
                    "causal_basis",
                ],
                "additionalProperties": False,
            },
        }
        properties["dropped"] = {"type": "array", "items": dropped}
        category_assessment = {
            "type": "object",
            "properties": {
                "rationale": {"type": "string", "minLength": 1},
                "candidate_ids": {"type": "array", "items": {"type": "string"}},
                "rule_ids": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": location},
            },
            "required": ["rationale", "candidate_ids", "rule_ids", "locations"],
            "additionalProperties": False,
        }
        properties["scorecard_assessment"] = {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "object",
                    "properties": {
                        "architecture_and_simplicity": category_assessment,
                        "maintainability": category_assessment,
                        "merge_readiness": category_assessment,
                    },
                    "required": ["architecture_and_simplicity", "maintainability", "merge_readiness"],
                    "additionalProperties": False,
                }
            },
            "required": ["categories"],
            "additionalProperties": False,
        }
    if phase == "verification":
        # A verification worker falsifies deduplicated candidates and returns dispositions only.
        # The schema forbids candidates and findings outright, so an invention needs the worker
        # to violate the contract, not just misunderstand it.
        properties["dispositions"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "disposition": {"type": "string", "enum": ["upheld", "refuted", "uncertain"]},
                    "evidence": {"type": "string", "minLength": 1},
                    "ownership": {
                        "type": "string",
                        "enum": ["introduced_or_worsened", "pre_existing", "uncertain"],
                    },
                },
                "required": ["candidate_id", "disposition", "evidence", "ownership"],
                "additionalProperties": False,
            },
        }
        properties["feedback_dispositions"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "minLength": 1},
                    "disposition": {
                        "type": "string",
                        "enum": ["upheld", "refuted", "cannot_verify"],
                    },
                    "basis": {"type": "string", "minLength": 1},
                    "evidence": {"type": "array", "items": location},
                },
                "required": ["finding_id", "disposition", "basis", "evidence"],
                "additionalProperties": False,
            },
        }
    if phase == "synthesis-compaction":
        properties["verdict"] = {"type": "null"}
        properties["verdict_basis"] = {"type": "null"}
        properties["candidate_digests"] = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "minLength": 1},
                    "claim_summary": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 384,
                        "pattern": r"\S",
                    },
                    "verification_summary": {"type": "string", "maxLength": 128},
                },
                "required": ["candidate_id", "claim_summary", "verification_summary"],
                "additionalProperties": False,
            },
        }
    return {
        "phase": phase,
        "json_schema": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }
