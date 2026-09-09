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

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from remix_review_internal import cli, review_pipeline, review_scope
from remix_review_internal.providers.base import ProviderSetupRequired, SetupIssue
from remix_review_internal.review_scope import ForgeEvidence, ReviewTarget, RevisionSnapshot


_MR_URL = "https://gitlab-master.nvidia.com/lightspeedrtx/lightspeed-kit/-/merge_requests/1336"
_GITLAB_SSH_ORIGIN = "ssh://git@gitlab-master.nvidia.com:12051/g/p.git"
_GITHUB_SCP_ORIGIN = "git@github.com:owner/repo.git"
_REPO = Path(".")
_MR_BASE = "44d988f1b8d181b34cb5acdd68d53d12579ef7b2"
_MR_HEAD = "bad3e0574605c463da734b7ead42974443eb556a"
_TARGET = ReviewTarget(
    kind="gitlab_mr",
    review=_MR_URL,
    url=_MR_URL,
    number=1336,
    source_branch="dev/ptrottier/review-code-change-skill",
    target_branch="main",
    base=_MR_BASE,
    head=_MR_HEAD,
    fetch_ref="refs/merge-requests/1336/head",
    forge_evidence=ForgeEvidence("unavailable", "", "unavailable", ()),
)


def _git(remote_url: str):
    """Return a `run_git` stand-in that answers only the origin URL query."""

    def run_git(_repository, *argv, **_kwargs):
        assert argv[:2] == ("remote", "get-url"), argv
        return subprocess.CompletedProcess(argv, 0, remote_url.encode(), b"")

    return run_git


def _no_probe(argv, **_kwargs):
    raise AssertionError(f"no CLI probe expected, got {argv}")


class TestCheckForgeCli(unittest.TestCase):
    def _check(self, review, *, origin=_GITLAB_SSH_ORIGIN, executable, probe=_no_probe):
        with (
            mock.patch.object(review_scope, "run_git", _git(origin)),
            mock.patch.object(review_scope, "resolve_executable", lambda _name: executable),
            mock.patch.object(review_scope, "run_probe", probe),
        ):
            review_scope.check_forge_cli(_REPO, review)

    def _issue(self, review, **kwargs) -> SetupIssue:
        with self.assertRaises(ProviderSetupRequired) as raised:
            self._check(review, **kwargs)
        (issue,) = raised.exception.issues
        return issue

    def test_missing_cli_names_install_and_host_login_from_ssh_origin(self):
        # Act
        issue = self._issue("!1336", executable=None)

        # Assert
        self.assertEqual(
            ("glab", ("scope",), "FORGE_CLI_NOT_FOUND"), (issue.provider, issue.affected_lanes, issue.code)
        )
        self.assertIn("glab auth login --hostname gitlab-master.nvidia.com", issue.message)
        self.assertIn("new terminal", issue.message)

    def test_review_url_host_wins_over_origin(self):
        # Act
        issue = self._issue(_MR_URL, origin=_GITHUB_SCP_ORIGIN, executable=None)

        # Assert
        self.assertEqual("glab", issue.provider)
        self.assertIn("--hostname gitlab-master.nvidia.com", issue.message)

    def test_github_pull_uses_gh_with_scp_origin_host(self):
        # Act
        issue = self._issue("#42", origin=_GITHUB_SCP_ORIGIN, executable=None)

        # Assert
        self.assertEqual("gh", issue.provider)
        self.assertIn("gh auth login --hostname github.com", issue.message)

    def test_logged_out_host_joins_cli_diagnostic(self):
        # Arrange
        def probe(argv, **_kwargs):
            self.assertEqual(("auth", "status", "--hostname", "gitlab-master.nvidia.com"), tuple(argv[1:]))
            return subprocess.CompletedProcess(argv, 1, b"", b"ERROR\n X host has not been\n authenticated.\n")

        # Act
        issue = self._issue("!1336", executable=Path("glab"), probe=probe)

        # Assert
        self.assertEqual("FORGE_AUTH_REQUIRED", issue.code)
        self.assertIn("glab auth login --hostname gitlab-master.nvidia.com", issue.message)
        self.assertTrue(issue.message.endswith("host has not been authenticated."), issue.message)

    def test_logged_in_host_passes(self):
        # Arrange
        def probe(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        # Act / Assert: no exception
        self._check("!1336", executable=Path("glab"), probe=probe)


class TestCliRouting(unittest.TestCase):
    def _run(self, argv, **patches):
        """Run `cli.main` with the forge check, provider preflight, and git root stubbed."""
        emitted = []
        defaults = {
            "check_forge_cli": lambda _repository, _review: None,
            "_git_root": lambda: _REPO,
            "_readiness": mock.Mock(side_effect=AssertionError("provider preflight must not run")),
        }
        defaults.update(patches)
        with mock.patch.multiple(cli, emit_json=emitted.append, **defaults):
            code = cli.main(argv)
        return code, emitted

    def test_forge_failure_exits_3_before_provider_preflight(self):
        # Arrange
        def fail(_repository, _review):
            raise ProviderSetupRequired((SetupIssue("glab", ("scope",), "FORGE_CLI_NOT_FOUND", "install glab"),))

        # Act
        code, emitted = self._run(["review", "--agent", "claude", "--review", _MR_URL], check_forge_cli=fail)

        # Assert
        self.assertEqual(3, code)
        (payload,) = emitted
        self.assertEqual(("setup_required", "forge_preflight"), (payload["status"], payload["stage"]))
        self.assertIn("Install or reinstall", payload["question"])
        self.assertIn("new terminal", payload["question"])
        self.assertEqual("FORGE_CLI_NOT_FOUND", payload["errors"][0]["code"])

    def test_local_range_skips_forge_check(self):
        # Arrange
        no_forge = mock.Mock(side_effect=AssertionError("no forge check for a local range"))

        # Act
        code, _emitted = self._run(
            ["review", "--agent", "claude", "--base", "HEAD~1"],
            check_forge_cli=no_forge,
            _readiness=mock.Mock(side_effect=KeyboardInterrupt),
        )

        # Assert
        self.assertEqual(130, code)

    def test_named_review_snapshots_forge_base_and_head(self):
        """A named MR is snapshotted at the forge base and head; local refs never enter."""
        # Arrange
        seen = {}

        def resolve_revision_snapshot(_repository, base_ref, head_ref):
            seen["range"] = (base_ref, head_ref)
            raise KeyboardInterrupt

        pipeline = {
            "resolve_review": lambda _repository, _review, **_kwargs: _TARGET,
            "resolve_revision_snapshot": resolve_revision_snapshot,
            "_git_root": lambda: _REPO,
        }

        # Act
        with mock.patch.multiple(review_pipeline, **pipeline):
            code, _emitted = self._run(
                ["review", "--agent", "claude", "--review", _MR_URL],
                _readiness=lambda _selections, _providers, *_args: {},
            )

        # Assert
        self.assertEqual(130, code)
        self.assertEqual((_MR_BASE, _MR_HEAD), seen["range"])

    def test_scope_command_reports_forge_target_and_change_count(self):
        # Arrange
        snapshot = RevisionSnapshot(_MR_BASE, _MR_HEAD, _MR_BASE, _MR_HEAD, "tree")
        pipeline = {
            "resolve_review": lambda _repository, _review, **_kwargs: _TARGET,
            "resolve_revision_snapshot": lambda _repository, base_ref, head_ref: snapshot,
            "count_changes": lambda _repository, _snapshot: 42,
            "_git_root": lambda: _REPO,
        }

        # Act
        with mock.patch.multiple(review_pipeline, **pipeline):
            code, emitted = self._run(["scope", "--review", _MR_URL])

        # Assert
        self.assertEqual(0, code)
        (payload,) = emitted
        self.assertEqual(
            ("gitlab_mr", 1336, "dev/ptrottier/review-code-change-skill", "main", _MR_BASE, _MR_HEAD, 42),
            (
                payload["kind"],
                payload["number"],
                payload["source_branch"],
                payload["target_branch"],
                payload["base"],
                payload["head"],
                payload["changed_files"],
            ),
        )
        self.assertNotIn("fetch_ref", payload)
        self.assertIn("merge request 1336", payload["scope_line"])
        self.assertIn(f"against main at {_MR_BASE[:12]}", payload["scope_line"])

    def test_scope_command_rejects_review_with_local_range(self):
        # Act
        code, emitted = self._run(["scope", "--review", _MR_URL, "--base", "main"])

        # Assert
        self.assertEqual(2, code)
        self.assertEqual("usage_error", emitted[0]["error"])

    def test_provider_login_failure_asks_the_user_to_log_in(self):
        # Arrange
        issue = SetupIssue("claude", ("primary",), "AUTH_REQUIRED", "Claude Code is not authenticated.")

        # Act
        code, emitted = self._run(
            ["review", "--agent", "claude", "--base", "HEAD~1"],
            _readiness=mock.Mock(side_effect=ProviderSetupRequired((issue,))),
        )

        # Assert
        self.assertEqual(3, code)
        (payload,) = emitted
        self.assertEqual("provider_preflight", payload["stage"])
        self.assertIn("your own terminal", payload["question"])
        self.assertNotIn("nstall", payload["question"])
        self.assertNotIn("PATH", payload["question"])
        self.assertNotIn("me to fix", payload["question"])

    def test_provider_auth_check_and_model_failures_keep_agent_repair_question(self):
        for code in ("AUTH_CHECK_FAILED", "INVALID_MODEL"):
            with self.subTest(code=code):
                # Arrange
                issue = SetupIssue("claude", ("primary",), code, "not established")

                # Act
                exit_code, emitted = self._run(
                    ["review", "--agent", "claude", "--base", "HEAD~1"],
                    _readiness=mock.Mock(side_effect=ProviderSetupRequired((issue,))),
                )

                # Assert
                self.assertEqual(3, exit_code)
                self.assertIn("me to fix", emitted[0]["question"])


class TestCountChanges(unittest.TestCase):
    def test_count_matches_manifest_enumeration_for_rename_delete_and_odd_paths(self):
        # Arrange: one raw -z diff with a rename, a delete, and a path with a space and a colon.
        raw = (
            b":100644 100644 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb R100\0"
            b"old/name.py\0new/name.py\0"
            b":100644 000000 cccccccccccccccccccccccccccccccccccccccc 0000000000000000000000000000000000000000 D\0"
            b"gone.py\0"
            b":000000 100644 0000000000000000000000000000000000000000 dddddddddddddddddddddddddddddddddddddddd A\0"
            b"odd dir/a:b.txt\0"
        )
        snapshot = RevisionSnapshot("base", "head", _MR_BASE, _MR_HEAD, "tree")
        seen = {}

        def run_git(_repository, *argv, **_kwargs):
            seen["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, raw, b"")

        # Act
        with mock.patch.object(review_scope, "run_git", run_git):
            count = review_scope.count_changes(_REPO, snapshot)

        # Assert: three logical changes, enumerated with the manifest's exact flags and range.
        self.assertEqual(3, count)
        self.assertEqual(
            ("diff", "--raw", "-z", "--no-abbrev", "--find-renames", "--find-copies", "--find-copies-harder"),
            seen["argv"][:7],
        )
        self.assertEqual((_MR_BASE, _MR_HEAD, "--"), seen["argv"][7:])


if __name__ == "__main__":
    unittest.main()
