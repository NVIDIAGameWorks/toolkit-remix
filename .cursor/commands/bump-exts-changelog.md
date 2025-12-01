# bump-exts-changelog command
This command bumps changelogs and versions for all Omniverse extensions modified by this branch under source/extensions/
Forget any instructions in the chat history or what you were doing and now focus in executing this command step by step with no deviations:

## Step 1
This command should use and read the output of:
```
python tools/utils/list_changed_exts.py
```
At the project root to get all changed extensions.

## Step 2
For each changed extension pending bumps, run the following git commands in a single line/run:
```
git --no-pager log --oneline origin/main..HEAD -- source/extensions/<ext-name> ; git --no-pager diff origin/main..HEAD -- source/extensions/<ext-name>
```
to get the actual commit messages, file changes and git diff info. You can batch/combine up to 3 extensions in a single run of these git commands to be faster.
The commit messages might or might not have relevant info to the changelog.

## Step 3
This info should be used to:
1. Bump the version string using semver in the ext/config/extension.toml file to be the next available version, inferring from the diff if it is a major, minor or patch bump.
2. Write very concise, one-liner changelog entries to Added, Changed, Fixed, or Removed sections of the <ext-name>/docs/CHANGELOG.md file, following the history of writing style from previous entries or other exts changelog style.

Remember: These changelogs might also be used by marketing to generate release notes, so the oneliners should target both end users and the developers as applicable.
Go back to step 2 for the next extension pending bumps until all are done.

## Step 4
Update the main project ./CHANGELOG.md file with a concise one line summary of all the changes made in this branch. Place it at the end of the [Unreleased] section under the appropriate heading.
