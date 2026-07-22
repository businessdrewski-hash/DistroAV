# 6.2.1.4 changes

## Dock visibility

- Registers the dock immediately through the OBS main-window event queue.
- Retries after `OBS_FRONTEND_EVENT_FINISHED_LOADING`.
- Removes the previous dependency on `plugin_features_registered` for dock creation.
- Automatically shows the registered dock.
- Adds a Tools-menu fallback action.
- Recovers once from a stale plugin-specific dock ID.
- Adds packaged-DLL marker verification to CI so a successful artifact cannot silently omit the dock code.

## Filter lifecycle

- Replaces unconditional probe rebuilding with deferred reconciliation.
- Removes every existing diagnostic probe by internal source ID before installing anything.
- Installs one video and one audio probe only when diagnostics are enabled.
- Installs no probes when diagnostics are disabled.
- Does not reconcile probes for ordinary NDI receiver resets or unrelated source updates.
- Defers create/load reconciliation until saved OBS filters have been restored.
- Uses weak source references for queued work.
- Releases the creator reference immediately after attaching each private filter.
- Performs full by-ID cleanup when the NDI source is destroyed.

## Diagnostics retained

- One-second sampling.
- Approximately twelve hours of in-memory history.
- Live dock with final A/V, output A/V, OBS video path, OBS audio path, trends, queues, drops, deadlines, catch-ups, repeat debt, and likely-cause text.
- No PPM controller, resampler, or clock-rate correction.
