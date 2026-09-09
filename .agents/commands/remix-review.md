# remix-review

Run the Packman script directly. It owns scope resolution, provider readiness, canaries, workers, retries, and final
synthesis. The `scope` command is the only way to identify the scope and changed-file count for approval; never
inspect the target for findings or delegate review outside the script. `packet-worker.md` is the canonical worker and
receipt contract.

## Workflow

1. Pick the scope from the request, then run the read-only `scope` command with that scope. It resolves the same forge
   target and the same immutable range as `review`, and it returns `changed_files` and one `scope_line`. Never compute
   the count with a local `git diff` or a direct `glab`/`gh` call.
   - The user names a merge request or pull request (a URL, `!1336`, `#42`, "my MR", "the MR for this branch"):
     pass `--review`. The script reviews the exact forge diff: the MR source branch at its head commit, against the
     MR target at its base commit. Never replace `--review` with `--base` and `--head`, and never fall back to the
     local branch when `--review` fails. The local branch can hold commits that are not in the MR, so its file set
     is not the MR. When the user names an MR and you do not know its number or URL, ask for it. Only the CLI of that
     link's forge is needed: `glab` for a GitLab URL, `gh` for a GitHub URL, never both.
   - The user names a local branch or a committed range: pass `--base` and `--head`. The plan must call the scope a
     local range, so the user can see that it is not the MR.
   A `scope` exit `3` is the same `setup_required` contract as step 6; a `scope` exit `1` names why the range cannot
   be resolved. Both stop the workflow before the plan.
2. Show this plan and wait for approval, replacing each value with the requested settings. The first line is the
   `scope_line` and `changed_files` from the `scope` command:

   ```text
   Scope: merge request 1336: dev/branch at bad3e0574605 against main at 44d988f1b8d1, 42 changed files
   Rules: invoking workspace, loaded registry
   Review: Codex, default model, medium reasoning
   Verification: default model
   Workers: 22
   Deadline: none
   ```

   For a local range the first line reads `Scope: local range origin/main..HEAD (44d988f1b8d1..3d7637b243f3), not a
   merge request, 12 changed files`.
   State that project instructions and rules come from a bounded invoking-workspace snapshot, never the reviewed head.
   Re-show the plan after a requested change. Approval belongs to the skill, not the script.
3. Pass only approved `--agent`, `--model`, `--reasoning`, `--verify-model`, `--jobs`, and `--deadline-seconds` values,
   with the same scope options as the `scope` command. Omit options the user did not select. Use
   `--previous-run RUN_ID` only for an explicitly requested score comparison or feedback adjudication. Feedback
   additionally requires explicit user intent and `--feedback PATH`.
4. Start one foreground `review` command. Never start reviewers separately. The first `[remix-review] scope` line
   names the exact MR source branch, head commit, target branch, and base commit, or the local range. Relay it, so the
   user can check that the reviewed range is the one they asked for. Do not use `--jobs 1` merely to inspect ordering;
   use `timings.json`. Identify a user-selected one-worker run as a serialized diagnostic whose elapsed time is not
   representative.
5. Keep the foreground handle until exit and relay each `[remix-review]` line. If output is held for 60 seconds, run
   read-only `progress` with the same `--review` target, or use the disclosed run ID with `progress --run RUN_ID` for a
   local range. Continue waiting on the foreground handle. A stale heartbeat does not prove that a run is active.
6. Exit `0`: render Scope, Findings, Scorecard, Gaps, Coverage, Failures, and Verdict from the returned JSON. An
   `incomplete` result has no findings, scorecard, or verdict. Show any `needs_user_action` provider, lane, code, and
   action. F-IDs are local to this result; candidate IDs remain provenance.
7. Exit `3`: the review did not start. Render every `setup_required` error, ask its returned question, and stop. The
   question names the remedy by code, for the forge CLI (`glab` or `gh`, whichever the link needs) and the provider CLI
   (`codex`, `claude`, `cursor-agent`) alike:
   - `CLI_NOT_FOUND`, `CLI_UNEXECUTABLE`, and their `FORGE_` forms: the user installs or reinstalls the CLI. A CLI
     installed during the session is not on the PATH of the running shell, so the user opens a new terminal, logs in
     there, and restarts the agent session before the retry.
   - `AUTH_REQUIRED` and `FORGE_AUTH_REQUIRED`: the user runs the login command from the error in their own terminal.
     The login is interactive (a browser or a token prompt). Never run a login yourself, and never read or store a
     token.
   Wait for the user to report the step done, then retry the same command. Never change the scope to a local range as
   a workaround. For every other code (a model or a reasoning value, a missing configuration file, an auth status the
   CLI could not report), after explicit repair approval, fix only the listed setup, run `doctor` with identical
   settings, and retry once.
   Exit `1`: render the terminal result or standalone preparation-time `runtime_error`. Exit `2`: render usage.
   Exit `130`: render interruption. Stop.

Script JSON is the terminal source of truth. Never infer an outcome from provider exit conventions or reconstruct an
assessment from worker output. Render the three score categories, `overall_branch`, `previous`, `delta`, `comparison`,
`weak_areas`, diagnostics, and `recovered_candidate_ids` when present.

## Review and scoring guarantees

Every full review is an independent snapshot of its current exact `base_sha..head_sha` delta. A NUL-safe Git manifest
covers additions, copies, modifications, renames, type changes, deletions, modes, and gitlinks. Deleted and non-regular
entries receive readable artifacts. The complete manifest remains public scope even when few files yield findings.

Git-backed candidates require an exact current-delta trigger that introduced or worsened the defect. A manifestation
may be outside its hunk when the candidate explains the causal path, but supporting evidence cannot establish
ownership. Formatting, import-order, documentation, version-only, or isolated test edits do not expose unrelated
debt. The only non-Git exception is an immutable failed required exact-head forge check; optional, pending, manual,
unavailable, allow-failure, and GitHub rollup checks cannot produce findings.

The host indexes both sides of the current delta, assigns every applicable rule at least once, and independently
verifies candidates. It excludes upheld pre-existing candidates before final synthesis. Ownership uncertainty,
invalid delta evidence, missing provenance, or incomplete rule coverage fails closed. Final synthesis groups current
causes, classifies them, supplies grounded score rationales and context, and issues the verdict. The host, not the
model's category nominations, assigns each finding to exactly one score category by claim class:

```text
contract                                                    -> architecture_and_simplicity
policy/maintainability/nit                                  -> maintainability
behavioral_bug/functional_gap/static_correctness/unclassified -> merge_readiness
```

See `packet-worker.md` for packet and receipt details.

The host derives deterministic work units from every applicable file rule crossed with every unique logical Git
change, plus every applicable global rule. With `U` unique units, the current point pool is
`max(5, U.bit_length())`. Each current finding contributes one severity penalty to its host-mapped category:

```text
critical/high/major = 3
medium/moderate     = 2
minor/low/nit       = 1
```

Each category score is `10 * max(point_pool - penalty_points, 0) / point_pool`. Grouped or supporting manifestations
of one cause are charged once. The host uses exact fractions and publishes category scores, their mean, and deltas
half-up to two decimals. The score basis records
`linear_snapshot_pool_v1`, the point pool, and the canonical `rule_change_units_v1` workload count and hash. Scores
answer how good the current delta is now; no previous result can change current scope, findings, penalties, verdict,
or score.

Prompts above the conservative 768 KiB UTF-8 ceiling receive one identity-preserving compaction wave; a second
overflow is `SYNTHESIS_CAPACITY`. Original candidate fields remain authoritative. Results retain every verification
disposition and verifier/verdict disagreement. The compatibility `synthesis.accounting` object remains empty;
`merge_yield` reports actual host input/output counts. A provenance imbalance fails the review.

## Optional score comparison

`--previous-run RUN_ID` may attach display-only comparison data to a normal full review. It accepts only a retained,
complete schema-3 snapshot under the caller repository's `_build/remix-review/`. Before provider setup, the
host validates safe containment, workflow/status, exact result-byte hash, and review identity, then reads only the
prior score basis and published scores. It never resolves prior Git objects, fetches historical state, checks ancestry,
or sends prior state to workers.

Matching policy, formula, rubric, rules, and validation level make the scores comparable. Base, head, tree, workload,
and point-pool changes do not invalidate comparison. The host subtracts the already-published normalized scores and
penalties; it never recalculates the previous result with the current pool. Contract changes produce `delta: null` and
`comparison.reason_code: "assessment_changed"`. A review without `--previous-run` uses
`comparison.reason_code: "no_previous_run"`. Review-identity mismatch or malformed explicitly selected artifacts fail
before provider setup.

For a rebased branch, review its current base and head and optionally add `--previous-run` for display comparison.

## Fast feedback adjudication

Use `--previous-run RUN_ID --head SOURCE_HEAD --feedback PATH` to challenge findings without changing the reviewed
snapshot. The head and tree must exactly match the source result. The UTF-8 JSON envelope is limited to 64 KiB, binds
the source run and exact result hash, and contains unique current public F-IDs with trimmed printable text no larger
than 8 KiB:

```json
{
  "schema_version": 1,
  "previous_run_id": "review-...",
  "previous_result_sha256": "...",
  "responses": [{"finding_id": "F-0013", "text": "The response and supporting rationale."}]
}
```

Feedback requires a schema-3 Policy-6 source with matching review identity, formula, exact head/tree, and canonical
forge-evidence hash. A remote hash mismatch or missing evidence requires a separately approved full review; the script
never broadens the run silently.

The fast path runs one exact-head canary, verifies only selected findings, and recalculates the source snapshot on the
host. It runs no discovery, current-candidate verification, host merge, compaction, or final synthesis. Responses are
untrusted evidence. Independent exact-head evidence may mark a finding `refuted`; that removes the finding and its
category penalties while preserving the source point pool. `upheld`, `cannot_verify`, or malformed evidence preserves
the finding and score contribution. Accepted response text records proven refutations. The result's `adjudication`
binds the source run/hash and selected F-IDs; surviving F-IDs keep their source labels and gaps are valid.

## Progress output

The foreground run emits at most one status line every 15 seconds plus one completion mark per finished stage:

```text
[remix-review] 16.0m review 47/68 +verify 0/10 22/22 workers 354 found ~23.8m left (est.)
```

Elapsed time precedes the earliest unfinished primary stage. `+verify` shows overlapping verification, workers show
busy/current limit, `found` is the deduplicated candidate count, and optional retry/split counts report repaired
packets. Estimates start only after enough review completions. Stage lines include duration; deadline-cut stages do not
receive a completion mark. Feedback reports its canary and selected verification only. `progress` reads the same state
without starting or changing a review.

## Surface

```text
.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py review
  --agent <codex|claude|cursor>
  [--model M] [--reasoning R] [--verify-model M]
  [--jobs N] [--deadline-seconds S]
  [--previous-run REVIEW_RUN_ID]
  [--feedback PATH]
  [--review URL_OR_ID | --base REF --head REF]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py scope
  [--review URL_OR_ID | --base REF --head REF]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py progress
  [--review URL_OR_ID] [--run RUN_ID]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py doctor
  --agent <codex|claude|cursor> [--model M] [--reasoning R]
```

Cursor Agent is accepted but not review-ready because its isolated artifact directory cannot load project rules and
skills without writing configuration into the real workspace. Choose Codex or Claude Code; `doctor` reports Cursor's
setup failure.

`--review` resolves the exact MR/PR base and head from the forge and fetches that review ref, so the reviewed range is
the MR source branch at its head commit against the MR target at its base commit, never the local branch. Before the
provider preflight the script checks that the CLI of that forge (`glab` or `gh`) is installed and logged in to the
forge host; a failure is a `setup_required` exit `3` with the exact install or login command. Local refs resolve exact
base, head, and tree IDs. Both use a private detached checkout without moving or reading caller branch, index, or
worktree content. The script verifies tracked bytes, ignored/untracked entries, and final tree state; cleanup failure
makes the result incomplete. Without `--review`, head defaults to `HEAD` and base auto-detects a main-like ref, then
`HEAD~1`; that range is the local branch, and it can differ from an MR. `scope` takes the same scope options, runs the
same forge check and range resolution as `review`, and returns the resolved target, its base and head, `changed_files`
counted with the manifest's enumeration, and `scope_line`. It starts no provider and no review.

`--jobs` defaults to 22 for Codex/Claude and 8 for Cursor, controls bounded packet sizing, and may decrease after an
environment-limit failure. Timeouts split packets while conserving file, rule, or candidate coverage; an unsplittable
part fails. `--deadline-seconds` has no default and covers preparation, provider readiness, forge resolution, scope
setup, and workers. Planning reserves the serial tail and predicted compaction before worker start. At expiry, the host
terminates workers and publishes no assessment.

`--verify-model` selects another model on the same provider. A separate context remains independent even with the same
model. Verification tries to falsify each candidate against code, callers, and tests; terminal failure or uncertain
ownership fails closed.

## Failure handling

- Environment-limit failures reduce concurrency and retry within the bounded repair budget.
- Timeouts split packets. Context-limit failures never retry an identical prompt; fixed or terminal overflow is
  `SYNTHESIS_CAPACITY` with no assessment.
- Denied read-only or web access is a gap; denied write access or an unclassified denial stops the run. Other worker
  failures receive bounded retry, then remain recorded failures.
- Every receipt is validated against its packet and phase. A terminal rejection, canary proof failure, checkout
  re-attestation failure, packet failure, or unevaluated applicable rule makes the run `incomplete` without findings,
  scorecard, or verdict.

## Prerequisites and artifacts

The script is deliberately simple: it reads the forge through one CLI and nothing else. The user sets up these
prerequisites once, in their own terminal, before the first review:

| Need | When | Install | Log in |
| --- | --- | --- | --- |
| Git and Packman Python | always | repository checkout | none |
| One provider CLI on PATH | always | `codex`, `claude`, or `cursor-agent` | `codex login`, `claude auth login`, or `cursor-agent login` |
| `glab` on PATH | the link is a GitLab MR | GitLab CLI | `glab auth login --hostname gitlab-master.nvidia.com` (this repository's host) |
| `gh` on PATH | the link is a GitHub PR | GitHub CLI | `gh auth login --hostname <host>` |

Only the CLI of the link's forge is needed, never both. A login is interactive (browser or token prompt) and belongs to
the user's own terminal. A CLI installed during a session is not on the PATH of the running shell: open a new terminal
for the login, and restart the agent session before the retry. `scope` and `review` check the forge CLI first and stop
with exit `3` and the exact command from this table when it is missing or logged out.

Workers are noninteractive and read only the detached workspace, packet artifacts, immutable forge evidence, and
bounded invoking-context snapshot. The selected account and endpoint pass through unchanged; `doctor` reports sanitized
identity and checks reads, denied writes, and context discovery.

A complete run keeps `result.json`, `run.json`, `progress.json`, `timings.json`, and `receipts/`; it removes workers,
scope artifacts, and external context. Terminal persistence atomically writes `result.json`, hashes its exact bytes,
then writes adjacent `run.json` with `result_sha256`. Cleanup failure makes the result incomplete. Unfinished runs keep
diagnostic artifacts; preparation-time refusal removes its provisional run directory.

## Policy

- Review only exact MR/PR metadata, Git diff, and repository files; never Jira or other external requirements.
- Capture at most one exact-head forge-check snapshot. Never wait for, poll, trigger, or retry CI. Missing or non-final
  evidence is an `Incomplete info` gap; local ranges do not schedule forge-only rules and report that measured coverage
  remains subject to the test or CI coverage report.
- Never edit source, caller branch/index/worktree state, review text, comments, discussions, or approvals. Remote scope
  resolution may fetch the exact review ref into caller-repository object/ref metadata.
- Post findings or follow up only through an explicitly authorized `remix-review-post-threads` or
  `remix-review-follow-up` invocation.
