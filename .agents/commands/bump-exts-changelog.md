# bump-exts-changelog

Bump changed extension versions/changelogs under `source/extensions/`. Order fixed.

## Step 0 - Ask

Ask both at once:

1. Jira ticket `REMIX-XXXX` or skip.
2. Base branch, default `main`.

Carry as `<ticket>`, `<base>`. Empty ticket -> omit ticket prefix.

## Step 1 - List Changed Exts

Windows:

```powershell
cmd /c tools\packman\python.bat tools\utils\list_changed_exts.py --base <base>
```

POSIX:

```bash
./tools/packman/python.sh tools/utils/list_changed_exts.py --base <base>
```

## Step 2 - Inspect Each Ext

For each changed ext, including those whose version was already bumped:

```bash
git --no-pager log --oneline origin/<base>..HEAD -- source/extensions/<ext-name> ; git --no-pager diff origin/<base>..HEAD -- source/extensions/<ext-name>
```

Batch up to 3 exts/run. Use real diff + commits; commit text may be low signal.

## Step 3 - Extension Version + Changelog

For each surviving changed ext:

1. Compare against `origin/<base>:source/extensions/<ext-name>/config/extension.toml` and select the version for the
   extension's complete change using `docs_dev/getting-started/review-checklist.md` -> Version Bumping and Dependency
   Updates. Recheck any existing branch bump against that policy before keeping it.
2. Append concise one-line entry as last item in the changelog section for the resolved extension version:
   Added/Changed/Fixed/Removed.
3. Keep empty line below added section.

Never insert at top. Match existing style. No Jira prefix in extension changelog. Write for users + devs where useful.

## Step 4 - Root Changelog

When preparing the MR summary/release-facing entry, ensure root `CHANGELOG.md`, `## [Unreleased]`, has one concise
branch-level entry in the correct section. Append as the last item at the bottom of that section to preserve
chronological order; never insert at the top or reorder existing entries. If `<ticket>` set:
`<ticket>: <one-line summary>`. Else no prefix.

Do not add a fresh root changelog entry for every follow-up commit on a branch that has not merged yet; keep those
details in the modified extensions' `docs/CHANGELOG.md` files instead.

## Gotchas

- `list_changed_exts.py` can say 0 when branch already touched changelog/version. Cross-check:
  `git diff origin/<base>..HEAD --name-only -- source/extensions/`.
- Keep one resolved version per MR. If later changes require a higher bump, update the branch's version and its
  existing changelog section together; never rename a published base-version section.
- `lint_code.bat all` may auto-fix unrelated exts. Stage only current MR scope; split unrelated fixes.
