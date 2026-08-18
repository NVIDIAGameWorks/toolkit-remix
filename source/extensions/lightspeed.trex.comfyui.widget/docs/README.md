# lightspeed.trex.comfyui.widget

UI extension for ComfyUI integration in RTX Remix. Provides the visual components for
server setup, workflow configuration, and the ComfyUI workspace window.

## Responsibilities

- Create and register server setup and workflow workspaces with Managed/External setup tabs.
- Render connection controls that split a complete URL pasted into Host across the Protocol, Host, and Port fields,
  plus a persistent connection banner, workflow selection, presets, and typed workflow input editors.
- Show the exact verified endpoint and **Open Browser** only while ComfyUI is connected; expose **Show Logs** only
  after a connection failure to open an in-app modal with the exact endpoint and captured connection error in a
  selectable, copyable, read-only multiline field.
- Keep setup and persisted queue work available without a project while disabling Run with exact guidance until a
  live stage can resolve the selected materials.
- Adapt ComfyUI jobs for the shared queue, contributing Focus over live, effectively visible owner objects in the
  job's saved USD context, Open Workflow, and Retarget to the material graph row and saved/connected
  server information before the generation job's Inputs. Context-qualified core visibility events refresh Focus
  availability and guidance.
- Keep every workspace bound to the injected USD context.

## Non-Responsibilities

- Starting or installing a managed ComfyUI server; the Managed setup tab is disabled until that support exists.
- Owning connection state, workflow loading, preset persistence, or job creation;
  `lightspeed.trex.comfyui.core` owns them.
- Viewing or owning logs emitted by the external ComfyUI server process; that server owns its console and process logs.
- Persisting or executing queued jobs; `omni.flux.job_queue.core` owns queue behavior.

## Architecture

```text
ComfyUI workspace window
        |
        v
+------------------------+
| Managed | External     |
| (Soon)  | (Active)     |
+------------------------+
| endpoint + connect     |
+------------------------+
        |
        | reads and updates
        v
+---------------------+      events      +------------------+
| ComfyUICore         |<---------------->| Workflow widgets |
| settings + prepare  |                  | presets + inputs |
+---------------------+                  +------------------+
                                               | edits generic
                                               | Python values
                                               v
                                      +----------------------+
                                      | Native property model|
                                      +----------------------+

Workflow widgets -- accepted submission --> ComfyUICore --> shared queue core
ComfyUI display adapter -----------------> shared queue widget and job details
Core visibility event --> ComfyUI adapter subscription --> ComfyUI queue rows refresh
```

- **Server setup**: The disabled Managed tab communicates future support. In the active External tab, pasting a
  complete URL into Host parses it and updates Protocol, Host, and Port for a running ComfyUI server. The widget then
  renders Disconnected, Connecting, Connected, or Connection Failed. Only the Connected banner exposes the exact
  verified endpoint and **Open Browser**; only Connection Failed exposes **Show Logs** for the current connection
  error. Each compact banner action is right-aligned inline to the right of the flexible wrapped status text.
- **Widget -> Core separation**: Widgets never manage server state directly. They call `ComfyUICore`
  methods to prepare an immutable submission, confirm any skipped jobs, submit the accepted request, resolve saved
  workflows, and retarget queued jobs. Widgets only render the returned state and react to context-qualified shared
  events.
- **Context-aware**: All widgets accept `context_name` to support multi-context scenarios.
- **Project boundary**: Workflow selection and queue access remain available without a stage. Run listens to stage
  lifecycle changes because only new material resolution needs a live stage; submitted generation and processing
  continue independently, while Apply validates the exact captured project later.

### Key Classes

- `ComfyUIWidgetExtension` owns workspace registration and the ComfyUI job display adapter lifecycle.
- `ComfySetupWorkspace` and `WorkflowSetupWorkspace` host the two AI Tools workspace windows.
- `ComfySetupAdvancedWidget` renders the setup tabs plus external-server connection settings and state.
- `WorkflowSetupWidget` coordinates workflow refresh, selection, presets, and typed inputs.
- `ComfyUIDisplayAdapter` maps ComfyUI generation into the shared queue presentation. Its workflow actions belong to
  the parent material graph; the generation child remains free of duplicate action icons and owns a dedicated
  ComfyUI server details section before its typed Inputs. While the queue is visible, its adapter subscription refreshes
  ComfyUI rows after a core visibility event so Focus availability and guidance stay current.
