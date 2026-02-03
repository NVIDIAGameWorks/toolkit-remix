# Environment Setup

This guide covers setting up your development environment for the RTX Remix Toolkit.

## Pre-commit Hooks (Optional)

Optional git hooks are available using [pre-commit](https://pre-commit.com/) to help maintain code quality:

- **On commit:** Auto-format with ruff
- **On push:** Lint check with ruff (aborts push if issues found)

### Installation

**Windows:**
```batch
install_hooks.bat
```

**Linux/Mac:**
```bash
./install_hooks.sh
```

### Uninstallation

**Windows:**
```batch
uninstall_hooks.bat
```

**Linux/Mac:**
```bash
./uninstall_hooks.sh
```

To also remove the `.venv` directory, add the `-c` flag:

**Windows:**
```batch
uninstall_hooks.bat -c
```

**Linux/Mac:**
```bash
./uninstall_hooks.sh -c
```

### Usage

- **Skip hooks temporarily:** `git commit --no-verify` or `git push --no-verify`
- **Run manually:** `pre-commit run --all-files`

### Troubleshooting

If your hooks fail to run (e.g., pre-push errors), try reinstalling with the `-f` flag to replace any existing or legacy hooks:

**Windows:**
```batch
install_hooks.bat -f
```

**Linux/Mac:**
```bash
./install_hooks.sh -f
```

This replaces existing hooks and often resolves conflicts with legacy hooks that may have been set up previously.

### Alternative: Manual Scripts

If you prefer not to use pre-commit hooks, you can run our convenience scripts directly:

- **Format code:** `format_code.bat` (Windows) or `./format_code.sh` (Linux/Mac)
- **Lint code:** `lint_code.bat` (Windows) or `./lint_code.sh` (Linux/Mac)
