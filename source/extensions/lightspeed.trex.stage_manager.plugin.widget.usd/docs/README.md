# lightspeed.trex.stage_manager.plugin.widget.usd

## Delete And Restore

Deleting a capture prim removes its capture reference through undoable Kit commands so the delete can be
restored. Capture lights also author `inputs:intensity = 0` while deleted, which keeps render runtime from
evaluating stale light attributes after the reference is cleared.

Restoring a capture light uses the same reference restore path as other capture prims, then removes only the
delete-authored `inputs:intensity` override from replacement layers so the light resolves back to the capture value.
