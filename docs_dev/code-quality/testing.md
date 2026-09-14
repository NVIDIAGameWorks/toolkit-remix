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
.\_build\windows-x86_64\release\tests-<extension.name>.bat -- --no-window             # all groups, headless
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default -- --no-window  # user tests only, headless
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default -f <pattern> -- --no-window  # filtered, headless
.\_build\windows-x86_64\release\tests-<extension.name>.bat -n default --coverage -- --no-window    # coverage, headless
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

Use `-- --no-window` when running local extension test scripts. It keeps Kit headless and avoids opening test windows.
Omit it when you need visible UI to debug widget focus, rendering, or modal behavior. This matches the `repo.toml`
`repo_test` suites, which already pass `--no-window` after the repo-test argument separator.

- The first `--` separates test-runner flags from Kit flags; `--no-window` is passed to Kit.
- Use `--dev` when you intentionally want to see local E2E tests run in a visible Kit window during development.
- Use `-n default -f <pattern>` when you need to isolate a specific failure.
- If a visible window opens unexpectedly, check the launch command because Kit probably did not receive `--no-window`.

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

## Test Classification and Coverage

Classify the behavior and dependencies a test actually exercises before checking its structure. A directory, test
name, imported module, or runner group declares intent but does not prove the test's boundary.

| Kind | Exercised boundary | Structure |
|------|--------------------|-----------|
| Unit | One isolated method or logic behavior, with external dependencies mocked | One ordered AAA cycle per test or subtest |
| E2E | A real workflow through actual UI controls or public service/API entry points, with real application components and data | UI: narrative workflow comments, no structural AAA sections; service/API: AAA is permitted |

[Service/API tests](../patterns/services.md#testing) exercise the live router and real workflow data. They belong in
the existing `tests/e2e/` suite and may use AAA; the absence of UI does not make them unit tests. No separate test
category, directory, or runner group is needed. Renaming a mocked UI workflow does not exempt it from the E2E
requirements or establish coverage of the real UI path.

Move an isolated method test mistakenly placed in `tests/e2e/` into the unit suite and retain its valid AAA structure.
Do not also recommend removing those markers. A real UI E2E containing AAA sections needs narrative workflow comments.

### Coverage by Boundary

- Independently testable logic maps to one unit-test file per source file and one test class per source class.
- Rendered interactions require E2E coverage. Do not demand artificial unit tests solely to duplicate that coverage.
  Mixed modules need unit coverage for independent logic and E2E coverage for rendered behavior.
- Preserve the trivial-glue exception. Mechanical forwarding to an already-tested shared factory needs no additional
  test that only repeats its wiring. Existing tests suffice when they exercise the changed contract; new predicates,
  branches, callback semantics, or other behavior still need coverage at the appropriate boundary.
- Documentation, agent instructions, declarative review registries, and agent configuration do not require unit-test
  file mappings. These boundaries do not change the measured [coverage requirement](#coverage-requirement).

---

## Unit Tests (`tests/unit/`)

Unit tests are **method-level tests**. Each test targets a single public method and verifies one specific behavior of
that method.

- Inherit `omni.kit.test.AsyncTestCase`
- Mock all external dependencies (USD stage, carb settings, HTTP calls, job queue)
- Prefer `mock.patch.object(module_or_object, "name")` over broad string-based patching like
  `mock.patch("package.module.name")`. Object patching binds to the imported object under test, catches missing
  attributes earlier, and avoids brittle module-path strings. Import modules under their real names before patching.
- **Cover all code paths** — happy path, error cases, edge cases, boundary conditions, and invalid input. If a method
  has an `if/else`, there should be tests for both branches.
- Test one behavior per test method using the Arrange/Act/Assert pattern
- Assert specific values, not just that code ran without exceptions

Unit tests must not create live windows or widgets, render or locate controls, issue gestures, or verify rendered
focus, layout, visibility, selection, or modal behavior. Models, predicates, formatting, commands, callbacks, and
controller logic can be unit-tested with live UI dependencies mocked at the subject boundary. An imported UI module,
immutable value type, or frame wait alone does not prove live UI testing; inspect the executed interaction.

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
- The markers must describe the execution: correct labels do not excuse multiple independent actions hidden in one
  section or helper. Helpers and setup/teardown methods need no AAA markers of their own.
- Fixture preparation, shared immutable case tables, and cleanup do not themselves count as additional Acts. Neither
  does an `assertRaises` context enclosing the single action that must raise; use it as required by the exception
  assertion rule. Subsequent cleanup must not exercise another behavior under test.

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

E2E tests verify **real workflows** from start to finish through their public entry point: actual UI controls or a
service/API. UI workflows use narrative comments rather than Arrange/Act/Assert sections and may exercise multiple
steps (open a window, fill fields, click buttons, verify results, open another window, etc.). Service/API workflows
may use AAA and need not drive UI controls.

- Use a real running Kit instance with real workflow data and application components; see [Real E2E Data](#real-e2e-data)
- Inherit `omni.kit.test.AsyncTestCase` (same base class as unit tests)
- **Trigger the action under test through its real public entry point** — actual controls for a UI workflow or the
  live service/API for a service workflow. Fixture preparation and cleanup may use APIs, but must not perform the
  action whose path the test claims to exercise
- **Verify results** through UI state, API responses/status, domain state, filesystem checks, or USD stage values as
  appropriate
- In UI E2Es, use `await ui_test.human_delay()` for frame waits — **never** `time.sleep()` or `next_update_async()`
- Local `tests-<extension.name>.bat` runs can stay headless by adding `-- --no-window`. Omit it when visible UI helps
  debug widget focus, rendering, or modal behavior. Add `--dev` when you intentionally want to watch local E2E tests run.
- Reserved for behaviors that cannot be meaningfully tested with mocks
- For UI automation details, see
  the [Kit UI test framework](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html#omni-kit-ui-test-writing-ui-tests)

### Real E2E Data

These requirements apply to both UI and service/API E2Es.

Prefer representative repository projects and the [shared test utilities](#shared-test-utilities). A small stage
created through real USD APIs is valid when it provides the behavior the workflow needs; do not load a larger project
solely because one exists. A dialog or other stage-independent workflow needs no artificial stage setup.

Do not replace workflow data or exercised application components with mocks, fakes, stubs, or canned responses. This
includes fake stages, mocked domain models, and replacement service responses. If the required real service or data
cannot be exercised, record the limitation and do not claim E2E coverage for the replaced path.

A narrow interception may observe or suppress an irreversible external effect, such as terminating the test process,
only when the real application path reaches that terminal boundary, the interception supplies no workflow data, and
the test verifies that the effect was requested. For example, clicking the real Exit button and verifying the request
to quit may intercept process termination; replacing the dialog's decision logic or input data is not permitted.

The presence of `mock` alone is not evidence of a violation. Identify the exact data or application component replaced
and explain how that replacement bypasses the claimed workflow.

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
    async with open_test_project("usd/my_project/project.usda") as project_path:
        # project_path is an OmniUrl to the opened project in a temp directory
        # stage is already open - drive the UI workflow from here
        ...
    # stage is closed and temp directory is cleaned up automatically
```

By default, `open_test_project()` resolves test data from the resource extension configured by the
`/exts/omni.flux.utils.widget/default_resources_ext` setting, matching `get_test_data()`. Pass `ext_name` only when the
project lives in a specific extension's `data/tests/` directory. Pass `context_name` when testing non-default USD
contexts.

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

Shared test assets belong in the centralized resources extension, not in runtime extension test packages and not in
test-dependency Python fixture modules. Use `open_test_project()` for shared Remix project trees so the test works on a
temporary copy and opens it through the standard helper. Use `get_test_data()` only for immutable single-file assets or
expected outputs from `lightspeed.trex.app.resources/data/tests`.

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
- **Service/API contract** — the real endpoint returns the expected response/status and domain state changes as required
- **USD stage** — prims exist, attributes have expected values, layers are composed correctly
- **Filesystem** — output files were created, directories have expected contents

Workflows like project wizard, ingestion, asset replacements, texture conversion, and packaging produce side effects
beyond the UI. Verify the actual workflow outcome; construction, rendering, no exception, or an incidental callback
alone is insufficient. Supplementary assertions are welcome, and a callback assertion is valid when the requested
notification or terminal effect is itself the contract. See [Test Value and Consolidation](#test-value-and-consolidation).

---

## What is Not a Good Test

- Tests with no assertions, or assertions that cannot detect a relevant regression
- Tests that repeat their setup, implementation logic, or repository declarations as expected values
- Tests that only cover the happy path and ignore errors, edge cases, and invalid input
- Tests with magic `sleep`/delay to handle timing — fix the async code instead
- Tests that pass alone but fail alongside others — shared mutable state is leaking
- Unit tests with more than one Act — split them into separate test methods

### Test Value and Consolidation

Every test needs an assertion tied to an observable contract. A weak-assertion finding must identify a plausible
regression that the test would miss. Non-null, callback, and call-count assertions are valid when they establish that
contract; their syntax alone is not a defect. For example, a notification test may assert the subscriber's payload,
whereas assigning a label in setup and asserting that same assigned value proves no application behavior.

Distinguish two opportunities:

- **Redundant coverage:** identify both tests and show that one fully covers the other's behavior and useful failure
  signal, so removing the weaker test loses no meaningful protection.
- **Duplicated mechanics:** cite substantial repeated setup or scenario logic and propose an existing helper, a small
  local helper, or parameterized cases that preserve distinct outcomes, isolation, and useful failure messages. Unit
  parameterization must retain an independent AAA cycle and identifying title for every case.

Compare changed tests with directly relevant neighbors; do not audit the whole repository. Short setup repetition,
common assertion syntax, and complementary unit/E2E coverage do not establish redundancy. Different branches and
outcomes still need their own cases, even when their mechanics can be shared. Do not introduce a configurable test
framework merely to eliminate a few repeated lines.

### Review Evidence

Report only violations introduced or worsened by the current delta. Cite the changed trigger and the executed
interaction, replaced data, missing outcome, or duplicated code; import-only or formatting changes do not expose
unrelated historical test debt. For coverage findings, identify the changed behavior missing protection and inspect
existing shared tests before requesting another test file.

Classify before recommending structure or relocation, using [Test Classification and Coverage](#test-classification-and-coverage).
Group manifestations that share one corrective change under the same classification defect. Structure and
maintainability violations are policy/maintainability findings unless separate evidence establishes a functional
failure. The existing review verification and causal grouping remain responsible for validating and combining claims.

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

---

## CI Test Coverage Warning

Every merge request runs the non-blocking `check-tests-written` job. When an extension has modified Python source but
no modified files under its `tests/` directory, the job finishes with a warning and posts a merge request note naming
the extensions. It never blocks the merge — it exists to start a conversation about whether tests were missed.

Add or update the matching tests to clear it, or apply the `no-tests-needed` label when tests genuinely do not apply
(a pure refactor with existing coverage, a revert, or a generated-code update). See
[`repo-tools.md`](../tools/repo-tools.md#repo-subcommands-repobat) for the underlying `repo.bat check_tests_written`
subcommand.
