# lightspeed.trex.packaging.window

Shows packaging-time unresolved asset rows and applies Ignore, Replace, and Remove Reference fixes.

## Repair Behavior

Missing-reference rows carry the layer identifier that authored the unresolved asset. That layer can be a
referenced USD asset layer outside the opened mod stage's local layer stack. Reference repairs use the composed
stage prim path and the asset replacement core. If the authoring layer is external, the repair is authored through
the current local mod edit target instead of opening or editing the external layer directly.
