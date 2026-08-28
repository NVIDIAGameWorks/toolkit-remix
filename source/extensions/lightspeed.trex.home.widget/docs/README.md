# lightspeed.trex.home.widget

Builds the StageCraft Home workspace and its New, Open, Resume, and recent-project experiences.

## Responsibilities

- Create and dock the Home window and report when its visible controls can accept input.
- Refresh recent projects when Home becomes visible and cancel that work when Home hides or is destroyed.
- Populate recent-project cards, persist changed validation entries in one guarded write, and report when the list is ready.
- Launch project creation workflows and publish open requests after lightweight card and path guards.

## Non-Responsibilities

- Does not close the application splash or publish `USER_READY`; `lightspeed.trex.app.setup` owns that boundary.
- Does not validate and serialize project metadata; `lightspeed.trex.recent_projects.core` owns those operations.
- Does not create the StageCraft USD context or workspace layout.
- Does not perform full open-time validation, repair, or workspace transitions; `lightspeed.trex.control.stagecraft` owns them.

## Architecture

`HomePageWindow` owns the Kit workspace window and deferred docking task. After a visible docked frame receives a final
UI update, it reports `HOME_INTERACTIVE` to application setup.

`HomePageWidget` builds the actions and recent-project tree. Visibility transitions are the single owner of refresh
scheduling. Each refresh has a generation token, so replaced, hidden, or teardown-time tasks cannot update the model or
write cache data. The current refresh validates projects serially on the Kit thread, yielding after each eight cache
changes, then merges and saves those changes before running thumbnail metadata reads with at most eight concurrent
operations. It reports `RECENTS_READY` after the current list is applied. After its card and filesystem guards pass,
opening a project publishes one request for StageCraft to validate and handle.

`HomePageWidget` explicitly owns the Project Wizard completion subscription and releases it when the wizard completes
or the widget is destroyed.
