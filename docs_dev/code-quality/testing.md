# Automated Testing Guidelines

## Running Tests

### Via `repo.bat test` (recommended)

```text
.\repo.bat test                                                        # run all test suites
.\repo.bat test -b <extension.name>                                    # single extension
.\repo.bat test -b <extension.name> --coverage                         # single extension with coverage
.\repo.bat test -b <extension.name> -- -n default                      # pass extra args to test runner
.\repo.bat test -l                                                     # list all test buckets
```

Use `-b` to select an extension bucket and `--` to pass extra args to the underlying test runner.

### Via test scripts (direct)

```text
.\_build\windows-x86_64\release\tests-<extension.name>.bat             # all groups
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default  # user tests only (preferred)
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default -f <pattern>  # filter by name
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default --coverage    # with coverage
```

| Flag           | Description                                                                             |
|----------------|-----------------------------------------------------------------------------------------|
| *(none)*       | Runs all test groups, including the startup test                                        |
| `-n default`   | Skip the startup test — runs only user-written tests. Use this by default to save time. |
| `-f <pattern>` | Filter tests by name pattern (auto-wrapped with `*...*`, partial names work)            |
| `--coverage`   | Collect code coverage for the extension                                                 |

Test output lands in `_testoutput/exttest_<sanitized_name>/` (dots replaced with underscores). Default timeout:
300 seconds.

### Local E2E execution

When you run an extension's `tests-<extension>.bat` locally and it includes E2E tests, **do not run multiple test
scripts in parallel**. These tests open real Kit windows and dialogs, and parallel local runs can steal focus, click
the wrong window, or leave modal dialogs open for another test process.

- Run one extension BAT at a time for local E2E workflows
- If you need to isolate a failure, use `-n default -f <pattern>` instead of starting a second BAT in parallel
- Treat conflicting windows, missing button queries, and unexpected modal state as likely parallel-run interference first

### Troubleshooting

**Registry sync hang:** Tests hang at `syncing registry: 'omniverse://kit-extensions.ov.nvidia.com/...'` when a
dependency is not cached locally. This is a network/firewall issue — ensure VPN/proxy allows access to the Omniverse
registry, or check `_build/windows-x86_64/release/extscache/` for the missing extension. Use `-f` to filter to just your
tests as a workaround.

**Startup test vs real test:** The runner launches two processes per extension — a startup test (~5s, verifies the
extension loads) and the real test (runs all `AsyncTestCase` subclasses). If startup passes but the real test hangs, the
issue is usually dependency resolution (see registry sync above).

**Timeout:** Default is 300 seconds. If exceeded, the process is crash-dumped and the test is marked as failed. Check
`.dmp.zip` and log files in `_testoutput/exttest_<sanitized_name>/`.

---

## Coverage Requirement

**All code must have at least 75% test coverage. This is a hard PR requirement.**

Coverage measures how much of the extension's current code is exercised by its tests — not just new lines, but the
overall logic. If your changes bring the extension below 75%, write additional tests to cover the gap before submitting.

After running with `--coverage`, look in `_testoutput/exttest_<sanitized_name>/` for:

- `coverage.xml` — machine-readable report (line/branch coverage per file)
- `htmlcov/index.html` — browsable HTML report

---

## Test Infrastructure

### Test Dependencies and Settings Extensions

Tests run inside a Kit instance that needs specific settings and helper extensions. This project uses a two-layer
architecture to provide them:

**Settings extensions** configure Kit for test mode (fast shutdown, ignore unsaved stages, etc.):

- `omni.flux.tests.settings` — base settings for all Flux extensions
- `lightspeed.trex.tests.settings` — additional Remix-specific settings (loads at `order = -1000` so it's early)

**Dependency aggregators** bundle common test dependencies so each extension only needs one line:

- `omni.flux.tests.dependencies` — pulls in `omni.flux.tests.settings`, `omni.flux.utils.tests`, `omni.kit.ui_test`
- `lightspeed.trex.tests.dependencies` — pulls in the Flux aggregator plus `lightspeed.trex.tests.settings`

Some dependencies use **deferred loading** via the `deferred_dependencies` setting — they are loaded after the test
extension is fully up. This avoids circular dependency issues with heavy extensions like
`lightspeed.trex.app.resources`.

### Declaring Tests in `extension.toml`

Each extension's `config/extension.toml` declares one or more `[[test]]` sections:

```toml
[[test]]
dependencies = [
    "lightspeed.trex.tests.dependencies",
]

stdoutFailPatterns.exclude = [
    "*[omni.kit.registry.nucleus.utils.common] Skipping deletion of:*",
]
```

| Field                        | Purpose                                                                              |
|------------------------------|--------------------------------------------------------------------------------------|
| `dependencies`               | Extensions loaded only for tests — not part of runtime dependencies                  |
| `args`                       | `--/setting=value` flags passed to Kit at test launch (Carbonite settings overrides) |
| `stdoutFailPatterns.exclude` | Globs for stdout lines that should not cause test failure                            |
| `name`                       | Test group name. Omit for the default group; use `"startup"` for load-only tests     |

The **two-group pattern** is standard — most extensions have both:

```toml
# Default group: runs the full test suite
[[test]]
dependencies = [
    "lightspeed.trex.tests.dependencies",
]

# Startup group: verifies the extension loads without errors
[[test]]
name = "startup"
dependencies = [
    "lightspeed.trex.tests.dependencies",
]
```

Use `args` when tests need specific Carbonite settings:

```toml
[[test]]
dependencies = [
    "lightspeed.trex.tests.dependencies",
]
args = [
    "--/exts/omni.flux.utils.widget/default_resources_ext='lightspeed.trex.app.resources'",
]
```

### Test Directory Structure

For the full extension directory layout (including tests),
see [Extension Guide — Directory Layout](../architecture/extension-guide.md#directory-layout).

**One test file per source file.** Each source module should have a corresponding test file with the same name
prefixed by `test_`:

```text
my_ext/
├── api.py          → tests/unit/test_api.py
├── models.py       → tests/unit/test_models.py
├── resolvers.py    → tests/unit/test_resolvers.py
└── widget.py       → tests/e2e/test_widget.py
```

Files that are pure re-exports, type stubs, or trivial glue (`__init__.py`, `extension.py` with no logic) can
be skipped. When in doubt, write the test file — an empty test class is cheaper than a gap in coverage.

When a source file defines multiple classes (e.g., `models.py` with `Workflow`, `WorkflowInput`, `Preset`),
create **one test class per source class** in the same test file:

```python
# test_models.py
class TestWorkflow(omni.kit.test.AsyncTestCase):
    ...

class TestWorkflowInput(omni.kit.test.AsyncTestCase):
    ...

class TestPreset(omni.kit.test.AsyncTestCase):
    ...
```

After writing tests, update `extension.toml` to declare them and specify any required arguments.

### Test Export

Every `tests/__init__.py` must export its test classes so the test runner can discover them. An empty
`tests/__init__.py` causes the test runner to find nothing, even if test files exist.

Keep test package exports explicit. `tests/__init__.py` must import each test class from its concrete module, for
example `from .unit.test_my_module import TestMyModule`. For the full rule and export template, see [Extension Guide —
`tests/__init__.py` Export Pattern](../architecture/extension-guide.md#tests-export-pattern).

---

## Planning Tests

For any non-trivial feature or change, plan your tests before writing code:

1. Explore the existing code and understand the design before writing anything.
2. Write both the feature plan and the test plan before touching source files.
3. The test plan should list specific test names — not just "add unit tests". Example:
   `test_job_is_cancelled_when_websocket_disconnects`, not "test cancellation".
4. Get the plan reviewed and agreed on before proceeding to implementation.

---

## Test Naming

Test names must clearly state what is being done, under what condition, and what the expected outcome is.

Pattern: `test_<action>_<condition>_<expected_outcome>`

- Good: `test_process_with_invalid_path_should_raise_error`
- Good: `test_job_is_cancelled_when_websocket_disconnects`
- Good: `test_validate_with_empty_input_returns_false`
- Bad: `test_cancellation`, `test_job_1`, `test_process`
- Subtests: name via `subTest(title=<descriptive_string>)` (e.g. `title="should_delete=True"`)

---

## Unit Tests (`tests/unit/`)

Unit tests are **method-level tests**. Each test targets a single public method and verifies one specific behavior of
that method.

- Inherit `omni.kit.test.AsyncTestCase`
- Mock all external dependencies (USD stage, carb settings, HTTP calls, job queue)
- **Cover all code paths** — happy path, error cases, edge cases, boundary conditions, and invalid input. If a method
  has an `if/else`, there should be tests for both branches.
- Test one behavior per test method using the Arrange/Act/Assert pattern
- Assert specific values, not just that code ran without exceptions

### Arrange / Act / Assert

Every unit test must follow this pattern strictly, in this order, with **exactly one Act**:

```python
async def test_process_returns_converted_paths_when_inputs_are_valid(self):
    # Arrange
    converter = TextureConverter(output_dir="/tmp/out")
    paths = ["/src/tex_a.png", "/src/tex_b.png"]

    # Act
    result = converter.process(paths)

    # Assert
    self.assertEqual(result, ["/tmp/out/tex_a.dds", "/tmp/out/tex_b.dds"])
```

**Rules:**

- Arrange → Act → Assert. This order is fixed. Never rearrange, interleave, or repeat sections.
- **One Act per test.** If you need to test two different actions (e.g. `do` and `undo`), write two separate tests.
- Assertions come last and are never followed by more actions.
- No `Arrange → Assert → Act → Assert` loops — these tests are testing two things and are harder to diagnose when they
  fail.

### Subtests

Use `self.subTest()` for parameterized cases. Each subtest has its own Arrange, Act, and Assert:

```python
async def test_validate_returns_expected_result_for_each_input(self):
    cases = [
        ("valid_path.png", True),
        ("", False),
        ("../escape.png", False),
    ]
    for path, expected in cases:
        with self.subTest(title=f"path={path}"):
            # Arrange
            validator = PathValidator()

            # Act
            result = validator.validate(path)

            # Assert
            self.assertEqual(result, expected)
```

- `with self.subTest(title=...)` is the outermost wrapper inside the loop
- Arrange, Act, and Assert all live **inside** the `subTest` block
- Never build a shared result before the loop and then assert inside it — that hides which case failed
- The `title` must identify the failing case from the test report

---

## E2E Tests (`tests/e2e/`)

E2E tests verify **full user-visible workflows** from start to finish. They drive the application the way a user would —
through the UI. Unlike unit tests, E2E tests do not follow the Arrange/Act/Assert pattern — a single test can exercise
a complete multi-step workflow (open a window, fill fields, click buttons, verify results, open another window, etc.).

- Use a real running Kit instance with real data
- Inherit `omni.kit.test.AsyncTestCase` (same base class as unit tests)
- **Trigger actions through UI elements** — not by calling internal methods directly
- **Verify results** through UI state, filesystem checks, or USD stage values as appropriate
- Use `await ui_test.human_delay()` for frame waits — **never** `time.sleep()` or `next_update_async()`
- When running locally through an extension `tests-<extension>.bat`, never run multiple E2E test processes in parallel.
  These tests open real windows and can interfere with each other across processes.
- Reserved for behaviors that cannot be meaningfully tested with mocks
- For UI automation details, see
  the [Kit UI test framework](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html#omni-kit-ui-test-writing-ui-tests)

### Setup / Teardown

Basic stage setup in `setUp`/`tearDown`:

```python
import omni.kit.test
import omni.usd
from omni.kit import ui_test
from omni.kit.test_suite.helpers import arrange_windows, wait_stage_loading


class TestMyFeatureWorkflow(omni.kit.test.AsyncTestCase):

    async def setUp(self):
        await omni.usd.get_context().new_stage_async()
        self.stage = omni.usd.get_context().get_stage()

    async def tearDown(self):
        await wait_stage_loading()
        if omni.usd.get_context().get_stage():
            await omni.usd.get_context().close_stage_async()
```

### Shared Test Utilities

The project provides reusable context managers and helpers for common test scenarios. Use these instead of writing
custom setup/teardown logic.

**`open_test_project`** (`omni.flux.utils.tests.context_managers`) — copies a test project to a temp directory, opens
the stage, and cleans up on exit. This is the standard way to test workflows that need a project (ingestion, asset
replacement, project wizard, etc.):

```python
from omni.flux.utils.tests.context_managers import open_test_project


async def test_ingestion_workflow(self):
    async with open_test_project("usd/my_project/project.usda", __name__) as project_path:
        # project_path is an OmniUrl to the opened project in a temp directory
        # stage is already open — drive the UI workflow from here
        ...
    # stage is closed and temp directory is cleaned up automatically
```

The `ext_name` parameter (typically `__name__`) is used to resolve the test data path relative to the extension's
`data/tests/` directory. Pass `context_name` when testing non-default USD contexts.

**`get_test_data_path`** (`omni.kit.test_suite.helpers`) — resolves a path relative to the extension's own `data/tests/`
directory. Use this when test data lives alongside the extension:

```python
from omni.kit.test_suite.helpers import get_test_data_path

project_path = get_test_data_path(__name__, "usd/full_project/full_project.usda")
```

**`get_test_data`** (`omni.flux.utils.widget.resources`) — resolves test data from the **centralized resources
extension** (typically `lightspeed.trex.app.resources`). Use this when test data is shared across extensions:

```python
from omni.flux.utils.widget.resources import get_test_data

shared_asset_path = get_test_data("usd/shared_project/project.usda")
```

The resources extension is configured via the `/exts/omni.flux.utils.widget/default_resources_ext` Carbonite setting.
Tests that use `get_test_data` must declare the resources extension in their `[[test]]` dependencies or args.

For widget-specific setup/teardown, use `@asynccontextmanager` or an async class with `__aenter__`/`__aexit__` to
encapsulate window creation and cleanup. Search existing e2e tests in the codebase for patterns.

### Finding UI Elements

Use `ui_test.find()` / `ui_test.find_all()` with a query path that follows the UI widget hierarchy. The general
syntax is `"WindowTitle//Frame/**/WidgetType[*].property=='value'"`.

There are several ways to locate elements — choose the most stable option available:

**By `identifier` (preferred — explicit, stable):**

```python
ui_test.find(f"{window.title}//Frame/**/Button[*].identifier=='create'")
ui_test.find(f"{window.title}//Frame/**/TreeView[*].identifier=='asset_tree'")
ui_test.find_all(f"{window.title}//Frame/**/Label[*].identifier=='item_title'")
```

**By `.text` (useful when identifier is not set — matches visible label/button text):**

```python
ui_test.find(f"{window.title}//Frame/**/Button[*].text=='Create'")
ui_test.find(f"{window.title}//Frame/**/Label[*].text=='No prims found'")
```

**By `.name` (matches the style/widget name):**

```python
ui_test.find(f"{window.title}//Frame/**/Image[*].name=='Refresh'")
```

**By widget type + index (when no distinguishing property exists):**

```python
tree_views = ui_test.find_all(f"{window.title}//Frame/**/TreeView[*]")
second_tree = tree_views[1]
```

**By window title (to find dialog windows):**

```python
dialog = ui_test.find("Confirm Tag Deletion")
file_picker = ui_test.find("Select a project file location")
```

**Relative search within a parent widget:**

```python
labels = parent_widget.find_all("/Label[*].identifier=='tag'")
```

### Driving Interactions and Waiting

After every UI action, call `await ui_test.human_delay()` to let the Kit event loop process and render. For longer
operations (ingestion, file I/O), pass a higher frame count:

```python
await button.click()
await ui_test.human_delay()  # default: 1 frame

await ingest_button.click()
await ui_test.human_delay(50)  # wait longer for heavy operations
```

For text input, use `human_delay_speed` to control typing simulation:

```python
await field.input("new_value", human_delay_speed=3)
```

**When to use `human_delay()`:** after opening/creating a window, after clicking, after expanding/collapsing tree nodes,
after drag-and-drop, after any async UI update, and in `finally` blocks during cleanup.

### Verifying Results

E2E tests can verify through multiple channels depending on the workflow:

- **UI state** — widgets appear, display expected values, are enabled/disabled
- **USD stage** — prims exist, attributes have expected values, layers are composed correctly
- **Filesystem** — output files were created, directories have expected contents

Workflows like project wizard, ingestion, asset replacements, texture conversion, and packaging produce side effects
beyond the UI. Always verify the actual outcome, not just that the UI looks right.

---

## What is Not a Good Test

- Tests with no assertions (or only `assertIsNotNone`)
- Tests that replicate implementation logic rather than testing behavior
- Tests that only cover the happy path and ignore errors, edge cases, and invalid input
- Tests with magic `sleep`/delay to handle timing — fix the async code instead
- Tests that pass alone but fail alongside others — shared mutable state is leaking
- Unit tests with more than one Act — split them into separate test methods

---

## Skipping Tests

Skipping a test should be a last resort — fix the test first. When a skip is necessary, always include a Jira ticket
or explanation so it can be tracked and resolved:

```python
@unittest.skip("Widget interaction broken after viewport refactor - REMIX-4099")
async def test_duplicate_selected_mesh(self):
    ...
```

---

## Debugging Tests

Attaching a debugger to a test run requires the `break` flag to make the test process wait before continuing. The
procedure and IDE-specific attach steps are in [
`debugging.md` → Debugging Tests and Startup Logic](../tools/debugging.md#debugging-tests-and-startup-logic).
