# Kit Extension Tests

See `.agents/context/project.md` for the command table and rules (no extra flags).

## Run Tests

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat
```

If the selected extension includes local E2E tests, run only one extension BAT at a time. These runs open real Kit
windows and modal dialogs, so parallel local executions can click the wrong window or leave conflicting UI state behind.

## Filter Tests

Use `-n default` to skip the startup test and `-f <pattern>` to filter by name:

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat -n default -f test_gradient
```

## Test Output

`_testoutput/exttest_<sanitized_name>/` (dots replaced with underscores).

## Troubleshooting

- **Registry sync hang**: Tests hang at `syncing registry:` — network/firewall issue. Use `-f` to filter.
- **Startup test vs real test**: Runner launches two processes (startup + real). If startup passes but
  tests hang, it's dependency resolution.
- **Timeout**: Default 300s. Check `.dmp.zip` and logs in test output folder.
- **Test discovery**: Kit imports the `tests` subpackage. New test classes must be in `tests/__init__.py`.
