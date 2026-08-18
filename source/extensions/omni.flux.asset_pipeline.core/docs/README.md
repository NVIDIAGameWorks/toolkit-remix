# omni.flux.asset_pipeline.core

Generic pipeline framework for sequential asset processing steps.

## Responsibilities

- Define the generic `PipelineItem[T]`, `PipelineContext[T]`, and `PipelineStep` contracts.
- Validate context and item compatibility before any step mutates data.
- Run enabled steps in order and record per-step execution state for status/debugging.
- Keep contract data on concrete typed subclasses, not on generic metadata dictionaries.

## Non-Responsibilities

- Does not define concrete processing steps.
- Does not own UI.
- Does not own fan-out, graph execution, job dependencies, or aggregation.
- Does not provide rollback storage or a generic revert API.

## Architecture

```text
Caller / product pipeline owner
        |
        v
+-----------------+      contains       +---------------------+
| PipelineContext |-------------------->| PipelineItem[]      |
| items           |                     | typed subclasses    |
| execution_state |                     | no file assumption  |
+-----------------+                     +---------------------+
        |
        | validate_pipeline()
        v
+----------------------+     rejects bad      +------------------+
| PipelineStep contract|--------------------->| validation error |
| context_type         |     authoring        +------------------+
| item_types           |
+----------------------+
        |
        | run_pipeline()
        v
+-----------------+     mutates existing item objects
| PipelineStep A  |------------------------------------+
+-----------------+                                    |
        |                                              |
        v                                              v
+-----------------+                           +-----------------+
| PipelineStep B  |-------------------------->| execution_state |
+-----------------+                           | did_run/skipped |
                                              | reason/error    |
                                              +-----------------+
```

The framework intentionally stays small. Product extensions provide concrete
items, typed contexts if needed, and the concrete step implementations.

## Key Classes

- `PipelineItem[T]` - wraps one typed `value`. Product-specific fields belong on
  subclasses.
- `PipelineContext[T]` - holds the ordered item list and `execution_state`.
- `PipelineStep` - declares `context_type` and `item_types`, validates
  compatibility, checks sparse/idempotent work with `should_run()`, and mutates
  items in `run()`.
- `validate_pipeline()` - rejects duplicate step names, wrong contexts, and
  wrong item types before mutation.
- `run_pipeline()` - validates once, runs enabled steps in order, and records
  ran/skipped/error state. Its optional async progress callback is awaited
  immediately before each runnable step and receives the configured one-based
  step index and total; disabled and no-op steps retain their positions but do
  not report progress.

## Design Decisions

- **Validation before mutation**: `validate()` catches compatibility/configuration
  errors. `should_run()` is only for no-op checks after validation succeeds.
- **No hidden item conversion**: steps mutate existing item objects or typed child
  records in place. They do not replace one item type with another at boundaries.
- **No generic metadata dumping ground**: framework state is generic; product
  contracts live on explicit product item/context fields.
- **No rollback history**: execution state explains what ran or skipped. Product
  workflows that need apply/unapply semantics should model those operations
  explicitly at the caller or job layer.
- **No concrete I/O ownership**: product contexts and product runners own heavy
  resources such as USD contexts, stage caches, temp directories, and cleanup.
  The generic framework only validates and executes the ordered step list.
- **Linear only**: callers use a job queue or graph orchestration when one request
  expands into many jobs.

## Usage

```python
from dataclasses import dataclass

from omni.flux.asset_pipeline.core import PipelineContext, PipelineItem, PipelineStep, run_pipeline


@dataclass
class MyItem(PipelineItem[str]):
    source_label: str = ""


class MyStep(PipelineStep):
    item_types = (MyItem,)

    @property
    def name(self) -> str:
        return "my_step"

    @property
    def description(self) -> str:
        return "Prefix processed values"

    def should_run(self, context: PipelineContext) -> bool:
        return any(not item.value.startswith("processed:") for item in context.items)

    async def run(self, context: PipelineContext) -> None:
        for item in context.items:
            if not item.value.startswith("processed:"):
                item.value = f"processed:{item.value}"


context = PipelineContext(items=[MyItem(value="albedo", source_label="workflow_input")])
await run_pipeline([MyStep()], context)
```

Callers that surface progress can pass an async callback without storing UI or
product state in the pipeline context:

```python
async def report_step(step: PipelineStep, index: int, total: int) -> None:
    print(f"{step.description} ({index}/{total})")


await run_pipeline([MyStep()], context, on_step_started=report_step)
```
