# bump-exts-changelog

Bumps changelogs and versions for all Omniverse extensions modified by this branch under `source/extensions/`.
Follow these steps exactly in the order listed. Do not skip or reorder steps:

## Step 0 — Setup

**Before doing anything else**, use the question tool to ask the user both questions at once:

1. **Jira ticket number** — format is `REMIX-XXXX`. Offer a "Skip / no ticket" option.
2. **Base branch** — the branch to compare against (default: `main`). Offer `main` as the default and let the user
   specify another if needed.

Carry the answers forward as `<ticket>` and `<base>` throughout all subsequent steps.
If the user skipped the ticket, treat `<ticket>` as empty and omit it wherever it would be used.

## Step 1

Run the following at the project root to get all changed extensions:

```
python tools/utils/list_changed_exts.py --base <base>
```

## Step 2

For each changed extension pending bumps, run the following git commands in a single line/run:

```
git --no-pager log --oneline origin/<base>..HEAD -- source/extensions/<ext-name> ; git --no-pager diff origin/<base>..HEAD -- source/extensions/<ext-name>
```

to get the actual commit messages, file changes and git diff info. You can batch/combine up to 3 extensions in a single
run of these git commands to be faster.
The commit messages might or might not have relevant info to the changelog.

## Step 3

This info should be used to:

1. Bump the version string using semver in the `config/extension.toml` file to be the next available version,
   inferring from the diff if it is a major, minor or patch bump.
2. Write very concise, one-liner changelog entries at the **end** of the appropriate Added, Changed, Fixed, or Removed
   section in `<ext-name>/docs/CHANGELOG.md`, following the writing style of previous entries.
3. Ensure there is an empty line below the added section (there should always be an empty line between version
   sections).

Remember: These changelogs might also be used by marketing to generate release notes, so the one-liners should target
both end users and developers as applicable.
Go back to Step 2 for the next extension pending bumps until all are done.

## Step 4

Update the main project `./CHANGELOG.md` file with a concise one-line summary of all the changes made in this branch.
Place it at the END of the `[Unreleased]` section under the appropriate heading (it should be the last item in the
Added, Changed, Fixed, or Removed section of the Unreleased section).
If `<ticket>` is set, prefix the line with it: `<ticket>: <one-liner summary>`. Otherwise write the summary without a
prefix.
