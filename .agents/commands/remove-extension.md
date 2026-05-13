# remove-extension

Destructive. Confirm explicit user approval before delete. Ref: `docs_dev/architecture/overview.md` App Files vs Ext
Deps.

## Steps

1. Tell user exact `<ext-name>` to delete; wait for confirmation.
2. Find refs before edits:

   ```bash
   grep -r "<ext-name>" source/extensions/ --include="*.toml" -l
   grep -r "<ext-name>" source/apps/ -l
   grep -r "<ext-name>" source/extensions/ --include="*.py" -l
   ```

3. Remove `<ext-name>` from `[dependencies]` in all found `extension.toml`.
4. Remove app `.kit` dependency entries.
5. Remove Python imports + API use. If import was only dep reason, Step 3 must remove dep too.
6. Delete only after cleanup:

   ```bash
   rm -rf source/extensions/<ext-name>
   ```

7. Run `.\build.bat`; trace missing refs back through Steps 3-5.
8. Run tests for previous dependents.
