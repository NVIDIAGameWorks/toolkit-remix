# kit-test

Rules in `.agents/context/project.md`. Direct ext BAT -> add `-- --no-window`; visible UI only on ask.
`repo.toml` `repo_test` already headless.

Run:

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat -- --no-window
```

E2E -> headless; no focus steal.

Filter:

```bat
.\_build\windows-x86_64\release\tests-<extension-name>.bat -n default -f test_gradient -- --no-window
```

Output: `_testoutput/exttest_<sanitized_name>/` (dots -> underscores).

Troubleshoot:

- `syncing registry:` hang -> network/firewall; use `-f` only when narrowing.
- Startup pass + tests hang -> dependency resolution.
- Timeout 300s -> inspect `.dmp.zip` + logs.
- Discovery -> Kit imports `tests`; export new test classes in `tests/__init__.py`.
