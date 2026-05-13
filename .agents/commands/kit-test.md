# kit-test

Command rules in `.agents/context/project.md`; no extra flags.

Run:

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat
```

E2E present -> one extension BAT at a time; real windows/dialogs conflict.

Filter:

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat -n default -f test_gradient
```

Output: `_testoutput/exttest_<sanitized_name>/` (dots -> underscores).

Troubleshoot:

- `syncing registry:` hang -> network/firewall; use `-f` only when narrowing.
- Startup pass + tests hang -> dependency resolution.
- Timeout 300s -> inspect `.dmp.zip` + logs.
- Discovery -> Kit imports `tests`; export new test classes in `tests/__init__.py`.
