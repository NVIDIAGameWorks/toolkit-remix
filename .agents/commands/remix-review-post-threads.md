# remix-review-post-threads

Post a completed `remix-review` result as inline MR/PR threads. This command is separately authorized and
command-only; invocation authorizes only these thread creations.

## Gate

- Require a completed result from the current task context or an explicit path/run ID. Otherwise stop:
  `Run remix-review first, then invoke remix-review-post-threads.`
- Read result schemas 1, 2, and 3. Schema 3 uses result-local F-IDs and grouped primary locations. Schema 2 retains
  grouped-primary/index behavior; schema 1 retains per-file/index behavior. Block malformed results instead of
  falling back to another schema.
- Reject schema-3 feedback adjudication derivatives; they do not create new review roots.
- Require a GitLab MR or GitHub PR scope. Derive forge and hostname from the result. Before any write, require the
  matching authenticated CLI: `glab auth status --hostname <host>` or `gh auth status --hostname <host>`.
- Fetch the authenticated account, live review, diff, and every complete discussion/comment page. The live head must
  equal the reviewed head; a moved head requires a new review.
- If this run already has `follow-up.json`, create no roots. Report the existing state and stop.

## Post

- Use only result findings. Map `major`/`high` to `P0`, `medium` to `P1`, and `low`/`minor` to `P2`. Skip and
  report unknown severity.
- For schema 3, deduplicate by `(run_id, finding_id)`. Create one thread at `primary_location`; include supporting
  manifestations in its body and never post them separately. For schema 2, use grouped primary/index identity. For
  schema 1, retain one thread per independently actionable file.
- If no valid inline position exists, skip and report it; never post a general comment.
- Body: `[P#] **Title**`, concrete problem and impact, suggested direction, then the matching marker:

  ```text
  <!-- remix-review run=<run-id> finding_id=F-0001 finding=<index> location=1 -->
  ```

  Schema-1/2 results use
  `<!-- remix-review run=<run-id> finding=<one-based-index> location=<one-based-index> -->`.
- Refresh every discussion/comment page before each write. A matching marker, same-run receipt, or equivalent live
  thread means handled. A receipted thread absent live is dismissed and must never be recreated.
- Post sequentially through `glab api` or `gh api`. Retain each returned ID and verify author, path, line, body, and
  unresolved state. Stop on first failure and report successful partial posts.

Never edit, delete, resolve, or reply to threads; change source, review metadata, approvals; or touch CI.

## Required output

After the completed-result gate, atomically persist exactly one cumulative `post-threads.json` beside `result.json`.
Never mutate the canonical result or include this sidecar in its hash. The receipt is cumulative only within this run:
start from this run's existing valid `post-threads.json`, never traverse earlier review runs.

```json
{
  "schema_version": 1,
  "workflow": "remix-review-post-threads",
  "status": "complete",
  "review": "https://forge.example/review/123",
  "run_id": "review-...",
  "review_identity": "opaque-review-identity",
  "reviewed_head": "40-character-sha",
  "counts": {"posted": 0, "handled": 0, "dismissed": 0, "skipped": 0, "failed": 0},
  "thread_receipts": [
    {
      "finding_id": "F-0001",
      "finding": 1,
      "location": 1,
      "thread_id": "thread-id",
      "message_id": null,
      "state": "open",
      "marker": "exact-marker",
      "url": "thread-url"
    }
  ]
}
```

`status` is `complete`, `partial`, or `blocked`. Use an empty `thread_receipts` array when none exist.
`finding_id`, `finding`, `location`, and `message_id` are nullable for schema-1/2 compatibility and direct
follow-up regressions. `state` is `open`, `resolved`, or `dismissed`. Schema-1/2 sidecars use
`review_identity: null`; their live-review gates remain mandatory.

Before `complete`, refresh the live head once more; a moved head makes the result `partial`. Carry every same-run
receipt forward unless its state changes, and never drop a dismissed receipt.
