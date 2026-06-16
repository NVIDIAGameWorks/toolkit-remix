# Viewport Selection and Manipulators

Viewport selection can involve multiple systems responding to the same click: Kit prim picking, HdRemix mesh picking,
custom gizmos, and transform manipulators. Keep these responsibilities separate.

## Kit 110 viewport startup

Kit 110 can expose viewport APIs before the render product, camera, viewport handle, and stage are all stable. Apply the
HdRemix renderer settings early, but select the HdRemix renderer on the viewport only after the viewport signature is
ready and has remained stable for the configured frame count.

Standalone viewport extension tests do not load the full TREX app viewport settings. Keep their test settings aligned
with the app by disabling Kit's stock viewport window startup UI and setting
`/exts/lightspeed/trex/viewports/shared/widget/registerOpenGLSceneLayers=false` when tests do not need the OpenGL
gizmo layers.

## Selection ownership

`GlobalSelection` owns explicit viewport and gizmo pick requests. A gizmo click finalizes the logical prim selection
directly and invalidates the in-flight mesh pick for that same click so a late HdRemix result cannot steal focus.
`SelectionDefault` also consumes the matching release event when another layer has already handled the click.

`on_selection_changed()` should mirror the current USD selection into Remix highlighting. If a viewport subsystem needs
to suppress a stale pick result, keep that ownership tied to the click or pick token that produced it.

## Selection tree sync

Selection tree callbacks bridge UI selection and USD stage selection. A TreeView model rebuild can briefly emit an empty
selection even though there was no tree input and USD still has selected prims. Treat that as a synthetic UI pulse and
leave the USD selection alone. Programmatic tree actions should select their intended USD paths once; avoid keeping a
separate pending path list just to replay the same selection later.

## StageCraft transform redirects

StageCraft uses `PrimTransformManipulator` to keep the visible selection on the logical prim while redirecting transform
operations to the prims returned by `filter_transformable_prims()`.

Filter StageCraft selections before calling the base Kit transform manipulator handler. The base handler immediately
rebuilds its transform model and pivot from the incoming selection, so passing a stale captured mesh selection through
first can hide or flicker the xform manipulator before Remix selection restoration runs.

Use this behavior split:

- Valid StageCraft selection: set the path redirect, then call the base handler so Kit still updates pivot and transform
  model state.
- Invalid StageCraft selection: clear the redirect and transform model so real non-transformable picks still disable the
  manipulator.
