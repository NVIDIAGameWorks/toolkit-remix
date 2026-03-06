# remove-extension

Safely remove an extension from the project. This is a destructive, hard-to-reverse operation — confirm with the user
before deleting anything.

*Dependency patterns: `docs_dev/architecture/overview.md` → App Files vs. Extension Dependencies section*

## Step 1 — Confirm Intent

Tell the user which extension will be deleted and ask for explicit confirmation before proceeding.

## Step 2 — Find All References

Search for every reference to the extension name across the repo:

```
grep -r "<ext-name>" source/extensions/ --include="*.toml" -l
grep -r "<ext-name>" source/apps/ -l
grep -r "<ext-name>" source/extensions/ --include="*.py" -l
```

Collect the full list before making any changes.

## Step 3 — Remove from `extension.toml` Dependencies

For each extension found in Step 2 that lists `<ext-name>` as a dependency, remove that line from its `[dependencies]`
section.

## Step 4 — Remove from `.kit` App Files

For each app file found in Step 2, remove the dependency entry.

## Step 5 — Remove Python Imports

For each `.py` file found in Step 2, remove the import statement and any code that used the removed extension's API. If
the import was the only reason for a dependency, ensure you also cleaned that up in Step 3.

## Step 6 — Delete the Extension Directory

```
rm -rf source/extensions/<ext-name>
```

Only do this after Steps 3–5 are complete.

## Step 7 — Verify the Build

Run `.\build.bat` and confirm it completes without errors. If the build fails with a missing reference, trace it back
through Steps 3–5.

## Step 8 — Run Affected Tests

Run tests for any extension that previously depended on the removed one to confirm nothing broke silently.
