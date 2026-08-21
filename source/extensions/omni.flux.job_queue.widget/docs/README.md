# omni.flux.job_queue.widget

Hierarchical UI for queues owned by `omni.flux.job_queue.core`.

## Responsibilities

- Render every job graph as a collapsed native TreeView root with topologically ordered job children.
- Preserve graph expansion and job selection across event-driven refreshes by durable IDs.
- Filter child jobs while retaining roots with matches; aggregate root status from every child.
- Provide generic Apply, Reapply, Decline, Revert, and selected-graph Delete controls.
- Expose persistent Start and Stop controls for the core-owned scheduler, with Running, Stopping, and Stopped status.
- Confirm Revert and selected-graph Delete, and report exact bulk-action results with native notifications.
- Provide exact-job-type display adapters for job names, user-facing progress, focus/edit, and product actions.
- Show graph summaries, topology, exclusive child-state counts, and clickable child navigation in the details panel.
- Show typed job ports, available values, product metadata/actions, logs, and explicitly labelled technical diagnostics.

## Non-Responsibilities

- Persisting graphs, jobs, execution state, outputs, or Apply lifecycle state.
- Scheduling or executing jobs.
- Applying or reverting product data.
- Defining product-specific job or Apply handler types.

## Architecture

```text
QueueInterface events + snapshots
              |
              v
         QueueModel
          /      \
         v        v
  Queue Tree   Details Panel
         |
         v
Exact JobDisplayAdapter

ApplyExecutor <--- generic Check / X actions
```

`QueueWidget.show(True)` subscribes to targeted progress, job, structural mutation, and external-condition events before
its initial synchronization. Worker-event bursts are coalesced into one UI-loop drain. Progress batches mutate retained
labels in place, targeted job events evaluate only their own filter membership, structural events synchronize once while
retaining unchanged rows, and external conditions compare adapter presentation values before invalidating affected
visible rows. Native TreeView virtualization builds cells only for the viewport, while collapsed children have no cells
to update. Decorative alternating backgrounds rebuild only when visible membership changes. The widget never polls and
never owns a scheduler. Its toolbar
subscribes to the persistent scheduler-enabled setting for the widget lifetime and changes only that setting; core owns
the scheduler and stops or starts new dispatch work. Active jobs finish before the toolbar changes from **Stopping** to
**Stopped**, and its tooltip names every graph still finishing.

`QueueWidget` and `JobDetailsPanel` both report `destroyed` after `destroy()`. An owning workspace window reads that
state to rebuild dead content instead of showing it again, and to skip a second cleanup.

Filters determine which children are visible and which children graph or footer actions capture. Aggregate root status
still considers every child, and the root tooltip reports exact state counts plus decisive jobs hidden by filters.
Graph details merge states that share one user-facing label and describe terminal execution counts as finished jobs.

Check and X reserve every eligible captured job synchronously before scheduling work, so repeated gestures and jobs later
in a bulk sequence are disabled immediately. Core Apply execution remains the authoritative cross-view deduplication
boundary. Apply-operation failures retain the prior stable disposition, remain available for an explicit retry, and do
not automatically loop. Filter-scoped root and footer actions remain available for other eligible jobs. Selected-graph
Delete remains available for completed work and warns that queue cleanup does not restore project changes.

Display adapters register one explicit `name` and one exact `job_type`. Lookup never walks inheritance or depends on
registration order. Active adapters may provide user-facing status and progress phrases, a temporary waiting reason,
an ordered collection of product actions with stable IDs, and ordered product-detail sections with explicit placement
and optional local directories. They may create one model-scoped action event subscription while the queue is visible.
The queue owns that subscription; the product adapter handles its events and requests the appropriate model rows to
refresh. Generic fallbacks do not expose persisted exception text or implementation class names.
Graph labels always come from the persisted graph snapshot.

Selected-graph Delete first renames every existing queue-owned `<database parent>/jobs/<job_id>` directory into
same-volume inactive staging directories. All selected graphs are removed in one SQLite transaction; if staging or
SQLite deletion fails, every directory is restored and every graph remains. After SQLite commits, staged files are
deleted asynchronously. Cleanup failure cannot resurrect committed graph deletions; a warning identifies each retained
inactive staging directory.

`JobDetailsPanel.show(True)` subscribes before reading model selection. Hiding the panel releases its subscriptions.
The panel reads topology, ports, and optional typed values only through `QueueInterface.get_job_details`. A compact
three-row identity header places the ellipsized title and graph actions first, then the graph/stage context, then the
status and progress; complete title text remains available in a tooltip. Overview, product sections, and the
severity-aware log viewer place common information first. Every
information group uses the native collapsible property frame and retains its expanded state through live refreshes.
Inputs, outputs, topology, identifiers, and durable diagnostics follow as structured key/value sections. Inputs and
outputs use native expandable trees for dataclasses, mappings, sequences, enums, paths, and IDs instead of displaying
object representations. Their aligned key/value columns use the shared monospace font without reducing the standard
label size. Nested data indents inside one proportional key column, so every value retains a stable second-column
boundary; long keys ellipsize and expose their complete text in a tooltip.
Exact directories appear as actions in their owning Inputs, Outputs, or product section. Logs own their copy action;
technical sections own actions that copy their identifiers and diagnostics. Technical exception types and tracebacks
appear only in the final **Technical details** section. Detail labels use the same standard sizes as the rest of the app.

The five columns are **Job / Stage**, **Status**, **Completed**, **Apply**, and **Actions**. Status combines the current
state with structured job or graph progress. Completed shows execution completion time; clicking its header or any
completed timestamp toggles the persistent relative/absolute format. Only graph roots are
draggable or deletable. A one-job graph still renders as a root and one child. The toolbar filter button opens one
Stage Manager-style popup containing the graph/stage, status, and Apply filters. The Apply filter exposes the five
durable dispositions directly: **Not Ready**, **No Apply Needed**, **Ready to Apply**, **Applied**, and **Declined**.
The adjacent **AUTO**/**MANUAL** badge toggles the persistent automatic-Apply preference. Detailed operation failures
remain in Status and tooltips.
