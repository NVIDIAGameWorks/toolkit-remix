# lightspeed.event.validate_project

Keeps an opened RTX Remix project's workfile, capture, and replacement layer structure valid.

## Responsibilities

- Coalesce relevant stage and layer event bursts into one validation on the next update.
- Skip anonymous startup stages, which do not represent projects.
- Repair layer ordering, capture paths, locks, and muteness for named project stages.

## Non-responsibilities

- Validating Project Wizard schema or dependency requirements before a project opens.
- Treating the anonymous Home stage as a project.

## Architecture

`EventValidateProjectCore` owns the stage and layer subscriptions and one pending validation task. Uninstalling releases
the subscriptions and cancels pending work. The existing layer-manager and Kit command APIs remain the authorities for
discovering and repairing project layers.
