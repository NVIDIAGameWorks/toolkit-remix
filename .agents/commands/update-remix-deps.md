# update-remix-deps

Updates RTX Remix target dependencies (`rtx-remix-hdremix` and `rtx-remix-omni_core_materials`) to the latest main
branch build. Both packages always share the same version — they come from the same repository.

**Arguments:** none (auto-detect from git history) or a specific version tag like `ext-abc1234-main`.

**Critical:** Git hashes are NOT chronological alphabetically. `ext-fed1a35` may be older than `ext-51aa1d4`. Always
compare by actual git history, not by string sort.

## Step 1 — Set Up Branch

Fetch and checkout (or create) the dependabot branch:

```bash
git fetch origin
git checkout -B dependabot/update-rtx-remix-target-deps origin/dependabot/update-rtx-remix-target-deps 2>/dev/null || \
git checkout -b dependabot/update-rtx-remix-target-deps origin/main
```

Then rebase onto main:

```bash
git rebase origin/main
```

## Step 2 — Check Current vs. Available Versions

```bash
echo "=== Current ===" && \
git show HEAD:deps/target-deps.packman.xml | grep -A1 "rtx-remix-hdremix\|rtx-remix-omni_core_materials" | grep version= && \
echo "=== main ===" && \
git show origin/main:deps/target-deps.packman.xml | grep -A1 "rtx-remix-hdremix\|rtx-remix-omni_core_materials" | grep version=
```

Exit early if already at the target version.

## Step 2b — Check remix_runtime

If the dependabot commit also changed `rtx-remix-remix_runtime`, show the old and new versions and **ask the user** whether to include that bump. The runtime has an independent release cadence and may not be officially released yet — do not update it without explicit confirmation.

## Step 3 — Update deps/target-deps.packman.xml

Update both `rtx-remix-hdremix` and `rtx-remix-omni_core_materials` version attributes to the new version tag. Only update `rtx-remix-remix_runtime` if the user confirmed it in Step 2b.

## Step 4 — Update CHANGELOG.md

Replace the existing RTX Remix dependency line in the `[Unreleased]` section (or add one if absent) with:

```
- Bump RTX Remix dependencies to `<new-version>`
```

## Step 5 — Commit and Offer to Push

```bash
git add deps/target-deps.packman.xml CHANGELOG.md
git commit -m "chore: bump RTX Remix dependencies to <new-version>"
```

Ask the user if they want to push.
