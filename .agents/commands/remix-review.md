# remix-review

Run the Packman script directly. It owns scope resolution, provider readiness, canaries, workers, retries, and final
synthesis. The `scope` command is the only way to identify the scope and changed-file count for approval; never
inspect the target for findings or delegate review outside the script. `packet-worker.md` is the canonical worker and
receipt contract.

## Request intent

Before starting either workflow, use the request and conversation context to establish the intended scope.
"Follow-up review" alone does not mean updating existing MR threads.

| Established intent | Existing workflow |
| --- | --- |
| Another full review of the revised MR | `remix-review` |
| Verify fixes or explanations in existing discussions, reply, or resolve threads | `remix-review-follow-up` |
| A new full review and follow-up on existing discussions | Both workflows, retaining separate state and outputs |
| Intent remains ambiguous | Ask before starting either workflow |

For ambiguous requests, ask: "Do you want a new full review, follow-up on existing MR threads, or both?"
A clear earlier instruction remains sufficient; do not force a menu or repeat a question already answered.

Full MR/PR reviews automatically compare scores and carry saved review decisions from the latest valid review unless
`--from-scratch` is selected. Carry-over requires current verification; it never imports live discussions or authorizes
thread mutations or new feedback decisions. "Both" invokes the existing workflows; it adds no combined mode or merged
result format.

When both workflows are requested, select the existing completed result that owns the discussions by path or run ID
before starting either workflow. Retain it as the thread-follow-up input regardless of execution order. If the intended
existing run is unclear, ask. The thread-follow-up input is independent of the score-comparison selection.

## Workflow

1. Pick the scope from the request, then run the read-only `scope` command with that scope. It resolves the same forge
   target and the same immutable range as `review`, and returns `changed_files`, `scope_line`, and the selected
   `previous_run` ID or null, and `decision_counts` for refutations and active acceptances. Never compute the count with
   a local `git diff` or a direct `glab`/`gh` call.
   Include any requested `--previous-run RUN_ID` or `--from-scratch` option in this preview.
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
   `scope_line` and `changed_files` from the `scope` command. Show its `previous_run` as Comparison, or none, and its
   decision counts:

   ```text
   Scope: merge request 1336: dev/branch at bad3e0574605 against main at 44d988f1b8d1, 42 changed files
   Comparison: none
   Saved decisions: 0 refutations, 0 active acceptances
   Rules: invoking workspace, loaded registry
   Review: Codex, default model, medium reasoning
   Whole-change review: high reasoning
   Verification: default model
   Workers: 22
   Deadline: none
   ```

   For feedback, list the selected actions and omit Whole-change review; that pass runs only in full reviews.
   With no challenges, show `Review: explicit decisions`,
   `Verification: skipped`, and `Workers: 0`; omit Rules and provider/model settings from the preview. The CLI still
   requires `--agent`, but this path needs no provider installation, login, readiness check, or `doctor`.
   For a local range the first line reads `Scope: local range origin/main..HEAD (44d988f1b8d1..3d7637b243f3), not a
   merge request, 12 changed files`.
   State that shared review boundaries, instructions for the current phase, and assigned rule sources come from a
   bounded invoking-workspace snapshot, never the reviewed head.
   Re-show the plan after a requested change. Approval belongs to the skill, not the script.
3. Pass only approved `--agent`, `--model`, `--reasoning`, `--verify-model`, `--high-level-reasoning`, `--jobs`, and
   `--deadline-seconds` values, with the same scope options as `scope`. Omit unselected options from that list.
   Preserve the previewed comparison:
   pass `--previous-run RUN_ID` using the returned `previous_run`, or `--from-scratch` when it is null. Do not select
   the latest run again after approval, even if new results become available. This fixes the choice for this run;
   future reviews still default to automatic selection. Feedback requires explicit intent, `--previous-run RUN_ID`,
   and `--feedback PATH`.
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
   action. F-IDs are local to this result; candidate IDs remain provenance. Group `gaps` entries prefixed
   `MR advisory (RULE_ID):` under MR advisories, separately from uncertainty gaps. Always disclose uncertainty gaps
   alongside scores and the verdict. Show actionable and accepted finding counts, each accepted finding's rationale,
   source decision and current verification, and rechecked refutations or unsuccessful historical matches. When every
   surviving finding is exempt, render `CLEAN — no remaining findings requiring changes; N accepted findings remain.`
   `CLEAN` does not establish that accepted defects were fixed or uncertain concerns disproved.
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
   settings only when workers are required, and retry once.
   Exit `1`: render the terminal result or standalone preparation-time `runtime_error`. Exit `2`: render usage.
   Exit `130`: render interruption. Stop.

Script JSON is the terminal source of truth. Never infer an outcome from provider exit conventions or reconstruct an
assessment from worker output. Render the three score categories with their ceilings, `overall_branch`, `previous`,
`delta`, `comparison`, `weak_areas`, diagnostics, and `recovered_candidate_ids` when present.

## Review and scoring guarantees

Every full review is an independent snapshot of its current exact `base_sha..head_sha` delta. A NUL-safe Git manifest
covers additions, copies, modifications, renames, type changes, deletions, modes, and gitlinks. Deleted and non-regular
entries receive readable artifacts. The complete manifest remains public scope even when few files yield findings.

Git-backed candidates require an exact current-delta trigger that introduced or worsened the defect. A manifestation
may be outside its hunk when the candidate explains the causal path, but supporting evidence cannot establish
ownership. Formatting, import-order, documentation, version-only, or isolated test edits do not expose unrelated
debt. The only non-Git exception is an immutable failed required exact-head forge check; optional, pending, manual,
unavailable, allow-failure, and GitHub rollup checks cannot produce findings.

The captured MR description supplies context and explicit behavioral acceptance criteria for I05; its findings
require an introduced or worsened code defect with valid delta evidence. Description checks I01–I04 and I06–I10
are marked `advisory: true`: report evidenced omissions and suggested corrections through `gaps`, without severity,
F-IDs, code-delta requirements, or effects on scores, ceilings, or verdicts. Missing evidence remains uncertainty,
not an established omission. Advisory content never invalidates a review; malformed receipts and worker failures
still follow the normal completion checks. Feedback preserves these entries. See `packet-worker.md` for the contract.

The host indexes both sides of the current delta, assigns every applicable rule at least once, and independently
verifies candidates. Discovery evidence limits become disclosed gaps; they never justify forced `PASS` or skipping
an assigned rule. The host excludes upheld pre-existing candidates before final synthesis. A valid `uncertain` disposition
or upheld candidate with uncertain ownership is excluded from synthesis and scoring and becomes a gap retaining its
candidate ID, title, and verifier evidence. The disposition remains recorded; uncertainty is never `PASS` or `refuted`.
Missing or malformed receipts, invalid delta evidence, missing provenance, and incomplete rule coverage still fail
closed. Final synthesis groups confirmed current causes, classifies them, supplies grounded score rationales and
context, and issues a verdict for its cause groups. The host applies explicit acceptance afterward and derives the
published verdict. It assigns each finding to exactly one score category by claim class:

```text
contract                                                    -> architecture_and_simplicity
policy/maintainability/nit                                  -> maintainability
behavioral_bug/functional_gap/static_correctness/unclassified -> merge_readiness
```

See `packet-worker.md` for packet and receipt details.

The host derives deterministic work units from every applicable file rule crossed with every unique logical Git
change, plus every applicable global rule. It counts `L` added plus removed lines within text diff hunks, excluding
patch headers and binary patch data. The current point pool is `max(5, ceil(1.5 * sqrt(L)))`. Each non-exempt finding
contributes one severity penalty to its host-mapped category; the most severe non-exempt finding sets its ceiling:

```text
severity            penalty  ceiling
critical/high/major  6        6
medium/moderate      3        8
minor/low/nit        1        10
```

A category without non-exempt findings has ceiling `10`. Each category score is
`ceiling * max(point_pool - penalty_points, 0) / point_pool`. Grouped or supporting manifestations of one cause are
charged once. The host uses exact fractions and publishes category scores and deltas half-up to two decimals.
`overall_branch` is the mean of the published category scores, rounded half-up to two decimals. The score basis
records `sqrt_pool_scaled_ceiling_v1`, the point pool, and the canonical `rule_change_units_v3` workload: rule-change
units, unique logical changes, changed text lines, and hash. Scores reflect confirmed defects requiring changes in
the current delta. Accepted defects remain findings in their original categories but contribute neither penalties
nor severity ceilings. The host publishes `CHANGES_REQUIRED` when any non-exempt finding remains, otherwise `CLEAN`.

Prompts above the conservative 768 KiB UTF-8 ceiling receive one identity-preserving compaction wave; a second
overflow is `SYNTHESIS_CAPACITY`. Original candidate fields remain authoritative. Results retain every verification
disposition and verifier/verdict disagreement. The compatibility `synthesis.accounting` object remains empty;
`merge_yield` reports actual host input/output counts. A provenance imbalance fails the review.

## Previous review and saved decisions

Full MR/PR reviews automatically select the newest valid completed schema-3 result with the same canonical
`review_identity` from the current checkout's `_build/remix-review/`. Malformed, incomplete, and unrelated automatic
candidates are skipped. `scope` returns the selected `previous_run` ID or null, and `review` prints its selection.
The skill preserves the previewed choice through an explicit option; direct CLI calls retain automatic selection.
`--previous-run RUN_ID` is a strict override. Local ranges require this explicit option because their identity is
repository-wide. `--from-scratch` disables comparison and imported decisions for that invocation and conflicts with
`--previous-run` and `--feedback`. Its result starts fresh history for subsequent automatic selection.

Score comparison remains display-only. Before provider setup, the host validates safe containment, workflow/status,
exact result-byte hash, review identity, and saved decisions. It retains the prior score basis, published scores,
and self-contained `review_decisions`; it never resolves prior Git objects or reads old receipts to reconstruct them.
Older results without decisions have empty history.

Discovery reviews the full current scope independently. Only verification receives relevant saved decisions, selected
by overlapping rules and files, including available rename mappings. Copies do not inherit acceptance. These hints
do not establish that two findings share a cause. The verifier checks current code, ownership, causal identity, and
the accepted scope. A verified rebuttal may refute a recurring claim; explicit acceptance keeps a confirmed defect
visible while exempting it from scores. New, worsened, or out-of-scope defects remain scored. An uncertain acceptance
match leaves a confirmed defect scored and discloses a gap. When history cannot fit the packet budget, the host
discloses the omission and reviews the candidate without granting an exemption.

Result schema 3 retains `review_decisions` with stable decision IDs, original findings, source run/hash/head,
explanations, refutation evidence, acceptance state, and latest verification tied to a run/head. Unmatched decisions
survive later reviews. Current `score_exemptions` contain `{finding_id, decision_id}` bindings rebuilt after
verification; every source candidate in a grouped finding must match the same active acceptance. Neither historical
exemptions nor an old F-ID authorize a current exemption. Incomplete results publish neither reusable decisions nor
exemptions. Final synthesis receives no historical decisions and cannot grant exemptions.

Matching policy, formula, rubric, rules, and validation level make the scores comparable. Base, head, tree, workload,
and point-pool changes do not invalidate comparison. The host subtracts the already-published normalized scores and
penalties; it never recalculates the previous result with the current pool. Contract changes retain the selected
previous result but produce `delta: null` and `comparison.reason_code: "assessment_changed"`. With no selected result,
the reason is `no_previous_run`. Review-identity mismatch or malformed explicitly selected artifacts fail before
provider setup. Valid saved `linear_snapshot_pool_v1` results remain selectable and display their original published
scores unchanged; comparison with the current formula produces `assessment_changed` and no delta.

For thread-only follow-up after a rebase, use `remix-review-follow-up`; rewritten history alone does not require a
new full review. A full MR/PR review after a rebase uses the current base and head with the same automatic comparison.

## Fast feedback adjudication

Use `--previous-run RUN_ID --head SOURCE_HEAD --feedback PATH` for explicit challenges, acceptances, or revocations
without changing the reviewed snapshot. The head and tree must exactly match the source result. The UTF-8 JSON
envelope is limited to 64 KiB and binds the source run and exact result hash. Every response requires nonempty,
trimmed printable `text` no larger than 8 KiB. Schema 1 remains a challenge-only input; schema 2 names each action:

```json
{
  "schema_version": 2,
  "previous_run_id": "review-...",
  "previous_result_sha256": "...",
  "responses": [{"action": "challenge", "finding_id": "F-0013", "text": "The response and supporting rationale."}]
}
```

| Action | Target | Effect |
| --- | --- | --- |
| `challenge` | Current `finding_id` | Independently verify the supplied rebuttal. |
| `accept_tradeoff` | Current `finding_id` | Explicitly accept the defect within the scope stated in `text`. |
| `revoke_acceptance` | Retained `decision_id` | Withdraw acceptance, even when its original finding is absent. |

Unknown targets, duplicate operations, and conflicting operations are rejected. Create decisions only from explicit
user intent; a discussion reply or phrase such as "won't fix" does not itself authorize acceptance.

Feedback requires a schema-3 Policy-9 source with matching review identity, formula, exact head/tree, and canonical
forge-evidence hash. A remote hash mismatch or missing evidence requires a separately approved full review; the script
never broadens the run silently.

Challenges run one exact-head canary and verification only for selected findings. The host recalculates the source
snapshot without discovery, current-candidate verification, merge, compaction, or final synthesis. Responses are
untrusted evidence. An independently verified `refuted` disposition removes the finding and saves its complete
context, rebuttal, and verifier evidence before removal. `upheld`, `cannot_verify`, or malformed evidence preserves
the finding and any existing acceptance. Saved `feedback` text continues to record proven refutations only.

Acceptance and revocation are host operations on the validated result. With no challenges, no provider readiness,
canary, or worker runs; verification is skipped with zero inputs. Acceptance leaves the finding visible and removes
its penalty and severity ceiling. Revised acceptance revokes the superseded decision. Revocation restores affected
score contributions and retains the revoked decision to prevent reuse; repeated revocation is a no-op. Renewed
acceptance creates a new decision. No challenge implicitly revokes acceptance.

Derivatives preserve the source pool, surviving F-IDs, and saved decisions, reproduce the source scores with their
existing exemptions, then apply the requested operations. `adjudication` binds the source run/hash, selected F-IDs,
and affected decision IDs. New decisions require a current-policy review; older feedback text is not reconstructed
into decisions, and cross-policy comparison retains the original scores with `assessment_changed` and no delta.

## Progress output

The foreground run emits at most one status line every 15 seconds plus one completion mark per finished stage:

```text
[remix-review] 16.0m review 47/68 +verify 0/10 22/22 workers 354 found ~23.8m left (est.)
```

Elapsed time precedes the earliest unfinished primary stage. `+verify` shows overlapping verification, workers show
busy/current limit, `found` is the deduplicated candidate count, and optional retry/split counts report repaired
packets. Estimates start only after enough review completions. Stage lines include duration; deadline-cut stages do not
receive a completion mark. Feedback reports its challenge canary and verification when needed; host-only operations
skip verification. `progress` reads the same state without starting or changing a review.

## Surface

```text
.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py review
  --agent <codex|claude|cursor>
  [--model M] [--reasoning R] [--verify-model M] [--high-level-reasoning R]
  [--jobs N] [--deadline-seconds S]
  [--previous-run REVIEW_RUN_ID | --from-scratch]
  [--feedback PATH]
  [--review URL_OR_ID | --base REF --head REF]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py scope
  [--previous-run REVIEW_RUN_ID | --from-scratch]
  [--review URL_OR_ID | --base REF --head REF]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py progress
  [--review URL_OR_ID] [--run RUN_ID]

.agents/scripts/run_packman_python.cmd .agents/scripts/remix_review.py doctor
  --agent <codex|claude|cursor> [--model M] [--reasoning R] [--high-level-reasoning R]
```

For runs that dispatch workers, choose Codex or Claude Code. Cursor Agent is accepted by the CLI but cannot load
project rules and skills in its isolated artifact directory without writing configuration into the real workspace;
`doctor` reports that setup failure. This restriction does not apply to acceptance/revocation-only feedback.

`--review` resolves the exact MR/PR base and head from the forge and fetches that review ref, so the reviewed range is
the MR source branch at its head commit against the MR target at its base commit, never the local branch. Before the
provider preflight the script checks that the CLI of that forge (`glab` or `gh`) is installed and logged in to the
forge host; a failure is a `setup_required` exit `3` with the exact install or login command. Local refs resolve exact
base, head, and tree IDs. Both use a private detached checkout without moving or reading caller branch, index, or
worktree content. The script verifies tracked bytes, ignored/untracked entries, and final tree state; cleanup failure
makes the result incomplete. Without `--review`, head defaults to `HEAD` and base auto-detects a main-like ref, then
`HEAD~1`; that range is the local branch, and it can differ from an MR. `scope` takes the same scope options, runs the
same forge check and range resolution as `review`, and returns the resolved target, its base and head, `changed_files`
counted with the manifest's enumeration, `scope_line`, the selected `previous_run` ID or null, and
`decision_counts: {refuted, accepted}`. It starts no provider and no review.

`--jobs` defaults to 22 for Codex/Claude and 8 for Cursor, controls bounded packet sizing, and may decrease after an
environment-limit failure. Timeouts split packets while conserving file, rule, or candidate coverage; an unsplittable
part fails. `--deadline-seconds` has no default and covers preparation, provider readiness, forge resolution, scope
setup, and workers. Planning reserves the serial tail and predicted compaction before worker start. At expiry, the host
terminates workers and publishes no assessment.

`--verify-model` selects another model on the same provider. A separate context remains independent even with the same
model. Current-candidate verification tries to falsify each claim against code, callers, and tests; terminal failure
still fails closed, while valid uncertainty becomes a disclosed gap.

The `J` (holistic) rules are global rules that review the whole change as one unit. They hunt for bugs between changed
components, design problems in the complete change, and duplicate logic between changed files. Their scope-review
packets use `--high-level-reasoning` (default `high`) on the same provider and model. Other packets use `--reasoning`
(default `medium`). The whole-change pass runs only in full reviews and follows the same evidence and delta-ownership
requirements as other code-defect rules.

Full reviews check provider readiness and run an exact-head read canary for each distinct provider/model/reasoning
selection used by the review, whole-change pass, or verifier override. `doctor` probes its configured primary and
whole-change selections. Challenge feedback checks only its effective verifier selection; acceptance/revocation-only
feedback requires no provider, canary, or `doctor`.

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

The script reads the forge through its CLI. The user sets up the applicable prerequisites once, in their own terminal:

| Need | When | Install | Log in |
| --- | --- | --- | --- |
| Git and Packman Python | always | repository checkout | none |
| One provider CLI on PATH | full review, feedback with challenges, or `doctor` | `codex` or `claude` | `codex login` or `claude auth login` |
| `glab` on PATH | the link is a GitLab MR | GitLab CLI | `glab auth login --hostname gitlab-master.nvidia.com` (this repository's host) |
| `gh` on PATH | the link is a GitHub PR | GitHub CLI | `gh auth login --hostname <host>` |

Only the CLI of the link's forge is needed, never both. A login is interactive (browser or token prompt) and belongs to
the user's own terminal. A CLI installed during a session is not on the PATH of the running shell: open a new terminal
for the login, and restart the agent session before the retry. `scope` and `review` check the forge CLI first and stop
with exit `3` and the exact command from this table when it is missing or logged out.

Workers are noninteractive and read only the detached workspace, packet artifacts, immutable forge evidence,
bounded invoking-context snapshot, and packet-declared `sdk_roots` for API evidence. Each worker receives shared
review boundaries and only its current phase's instructions. Staged entrypoints load the review context without
importing general implementation, delegation, completion-gate, or memory-promotion workflows. Assigned rule sources
remain staged reference evidence. The selected
account and endpoint pass through unchanged; `doctor` reports sanitized identity and checks reads, denied writes, and
context discovery.

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
