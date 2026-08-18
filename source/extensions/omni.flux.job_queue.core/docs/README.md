# omni.flux.job_queue.core

SQLite-backed typed job graphs, exact-type scheduling, and explicit Apply/Reapply/Revert handling.

## Responsibilities

- Persist current graph structure, typed job payloads, inputs, outputs, progress, failures, and Apply lifecycle.
- Schedule runnable jobs from committed state with independent concurrency limits per exact job type.
- Resolve typed literal inputs and output-to-input connections.
- Run all Apply mutations sequentially on the Kit event loop while moving SQLite work off that loop.
- Recover interrupted execution and active Apply operations.

Queue widgets, product-specific jobs, display adapters, targets, and Apply handlers belong to product extensions.
Incompatible queue files are replaced with the current schema; this extension does not migrate old contracts.

## Typed jobs and graphs

Jobs declare immutable class-level ports and return a concrete `JobOutputs` mapping. Progress is structured and awaited.

```python
import dataclasses
import pathlib

from omni.flux.job_queue.core import get_job_queue
from omni.flux.job_queue.core.job import (
    Job,
    JobGraph,
    JobInputPort,
    JobInputs,
    JobOutputPort,
    JobOutputs,
    JobProgress,
    JobProgressCallback,
)
from omni.flux.job_queue.core.persistence import PersistenceCodec, get_registry

SOURCE = JobInputPort("source", pathlib.Path)
TEXT = JobOutputPort("text", str)


@dataclasses.dataclass
class ReadText(Job):
    input_ports = (SOURCE,)
    output_ports = (TEXT,)

    async def execute(
        self,
        job_directory: pathlib.Path,
        inputs: JobInputs,
        progress_callback: JobProgressCallback,
    ) -> JobOutputs:
        await progress_callback(JobProgress(detail=f"Reading in {job_directory}"))
        return JobOutputs({TEXT: inputs[SOURCE].read_text(encoding="utf-8")})


read_text_codec = PersistenceCodec(
    "example.ReadText",
    ReadText,
    lambda value: (value.job_id, value.name, value.skip_reason, value.apply_binding),
    lambda value: ReadText(*value),
)
get_registry().register_codecs([read_text_codec])
job = ReadText()
graph = JobGraph(name="Read text")
graph.add_job(job)
graph.bind(job, SOURCE, pathlib.Path("input.txt"))
queue_job = get_job_queue().submit(graph)[0]
outputs = await queue_job.outputs()
```

Register product codecs during extension startup. Registrations remain process-owned until the queue core shuts down,
so active jobs can finish and serialize their results while dependent product extensions are stopping.

Use `JobGraph.connect(source.output(output_port), target.input(input_port))` for one typed data edge and
`JobGraph.depends_on(target, prerequisite)` for control-only ordering. Call `connect()` again with the same output
endpoint to fan one value out to another input. Port value types must match exactly. A job may set `skip_reason` before
submission, and skips propagate recursively to descendants with the immediate upstream reason. `input_ports`,
`output_ports`, and `max_concurrency` are type declarations and cannot be shadowed on an instance.
`try_update_queued_job()` conditionally replaces a payload only while the scheduler has not claimed it.
Use `iter_snapshot()` for lazy ordered full-queue inspection and `get_job_snapshot(job_id)` for targeted updates; snapshot
queries never load persisted job payloads, outputs, or Apply receipts. Snapshots expose `submitted_at` plus
nullable `started_at` and `completed_at` lifecycle timestamps.
Use `get_job_details(job_id)` for typed declared ports and related data/control edges without loading the job payload.
Pass `include_values=True` only when the caller needs decoded available inputs, literal values, or completed outputs.

## Persistence

Every custom job, record, handler class, target, and receipt uses an explicitly registered `PersistenceCodec`. The codec
keeps the stable database identity beside the exact Python type and optional encode/decode pair; it is a value, not a plugin
class. Custom values must provide both an encoder and decoder. There is no dataclass introspection, dynamic import, callable,
or pickle fallback.
Core registers type identities for the supported native port boundary: `bool`, `int`, `float`, `str`, `bytes`, `list`,
`dict`, `tuple`, `set`, `frozenset`, `pathlib.Path`, and `uuid.UUID`. Products should use explicit record types when a
collection needs a stronger contract.

## Scheduling and lifecycle

Persisted execution states are:

```text
QUEUED -> SCHEDULED -> IN_PROGRESS -> DONE
                              |       FAILED
                              +-----> SKIPPED (descendants)
```

`WAITING_FOR_DEPENDENCIES` and `UNKNOWN` are derived display states and cannot be stored. The scheduler is enabled by
default, reacts to queue and readiness notifications, and applies `Job.max_concurrency` independently to each exact job
type. `get_schedule_block_reason()` must be fast and side-effect-free; notify the queue when its external condition changes.
The scheduler checks persisted data/control prerequisites before invoking product readiness and rechecks prerequisites in
the claiming transaction. If product readiness code raises, that queued job fails with a safe public reason while its
diagnostic is retained and later job types remain eligible for the same claim pass. Committed progress uses a dedicated
targeted notification carrying the job ID and `JobProgress`; consumers do not reload a full snapshot or treat it as an
execution transition. External product-readiness changes separately notify presentation consumers; internal execution
transitions wake the scheduler without causing a global presentation scan. Progress and Apply-only child changes do not
wake a full runnable scan; execution, topology, type, and setting changes wake it.
Jobs may raise `JobExecutionError(reason, diagnostic)` to preserve raw diagnostics while exposing explicit safe failure
text. Unexpected execution failures use a generic user-facing reason.

The queue owns each job directory and writes timestamped lifecycle and failure entries to `logs/stdout.log` and
`logs/stderr.log`. `QueueInterface.delete_graph()` stages those directories on the same volume inside the graph-deletion
transaction, restores them if the database write fails, and cleans committed staging afterward. Startup restores staged
directories when their graph still exists and finishes cleanup when the graph was already deleted.

## Apply lifecycle

`ApplyBinding` connects one declared output to one exact `ApplyHandler` type and target. Handlers declare exact input,
target, and durable receipt types plus one policy: `ALWAYS_AUTOMATIC`, `ALWAYS_MANUAL`, or `FOLLOW_GLOBAL`.
The global automatic Apply preference defaults to enabled for new users and persists every explicit user change.

Disposition (`NOT_READY`, `NOT_APPLICABLE`, `PENDING`, `APPLIED`, `DECLINED`) is durable user intent. Operation
(`IDLE`, active work, or failure) records current/retry state without overwriting disposition.
Before the first external mutation, the runtime calls `capture_receipt()` and commits the exact typed result while the
operation is active. It then passes that durable receipt to idempotent `apply()` and `revert()` methods. Reapply and
interrupted-operation retries reuse the receipt without recapturing the already changed target; successful Revert clears
it. Handler availability is derived only from the live exact-type registry; it is never stored as a second operation state.
Missing handlers retain their disposition, operation failure, receipt, and diagnostic. Registration wakes the runtime and
visible widgets, then reconciles eligible pending jobs using the indexed stable handler identity without loading unrelated
job payloads.
Concurrent explicit requests reserve the exact job across queued and active work: identical Apply or Revert callers share
one operation, while a conflicting operation is rejected until the reservation settles. Decline cancels a same-job Apply
that is reserved but has not started. When a failed Apply retains a receipt, Decline runs the handler's idempotent Revert
before recording `DECLINED`; failed cleanup retains the receipt and a retryable Revert failure. A failed Apply retry from
`DECLINED` returns to `PENDING`, so the queue never reports a potentially mutated target as declined. Committed queue and
Apply notifications isolate and log subscriber exceptions so one listener cannot fail the write or prevent later listeners
from observing it.
Handlers may raise `ApplyExecutionError(reason, diagnostic)` for product-specific safe text. The diagnostic is stored in
`apply_error`; the safe text is stored separately in `apply_reason`. Unexpected failures use operation-specific generic
text and are never classified from exception-message substrings. Receipt validation or persistence failures occur before
the external mutation. A process interruption or completion-persistence failure records a retryable operation failure while
preserving the original receipt, so the idempotent handler can safely finish the same operation after restart.
