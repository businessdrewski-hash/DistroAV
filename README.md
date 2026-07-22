# DistroAV Receiver Clock Live Diagnostics 6.2.1.4

This is an upload-and-build overlay for the branch:

```text
receiver-clock-downstream-diagnostics
```

It keeps the existing receiver-clock fix. It does not add PPM correction, resampling, Sync Guardian, or another clock-control loop.

## Fixes in this revision

### Live diagnostics dock is registered independently

The dock no longer depends on successful NDI feature registration or on a single OBS finished-loading event.

The build now:

- queues dock registration as soon as the OBS main window is available;
- retries registration when OBS reports `OBS_FRONTEND_EVENT_FINISHED_LOADING`;
- automatically shows the dock after registration;
- adds the normal **Docks → DistroAV Receiver Clock Health** toggle;
- adds a fallback **Tools → DistroAV Receiver Clock Health** action;
- retries once after removing a stale plugin-specific dock ID;
- logs a clear success or failure message.

Expected success log:

```text
[receiver-clock-lab] Live diagnostics dock registered and available in Docks menu
```

### Probe-filter replication is repaired

The diagnostic video/audio probes now have a controlled lifecycle:

- diagnostics enabled: exactly one video probe and one audio probe;
- diagnostics disabled: all Clock Lab probes are removed and none are installed;
- source create/load: cleanup is deferred to the OBS UI event loop so saved filters have finished restoring first;
- NDI receiver reset or ordinary source setting reset: probes are not rebuilt;
- source destruction: every remaining Clock Lab probe is removed by internal filter ID;
- queued cleanup uses an OBS weak-source reference so a deleted source cannot be accessed later;
- attached filters do not keep a second source-owned reference.

Expected lifecycle logs include:

```text
[receiver-clock-lab] Probe reconcile source='...' reason=source-create ...
[receiver-clock-lab] Probe reconcile source='...' reason=source-load ...
[receiver-clock-lab] Probe destroy cleanup source='...' ...
```

## Files to upload

Extract the ZIP and upload these files while preserving their paths:

```text
.github/workflows/build-receiver-clock-live-diagnostics.yml
src/receiver-clock-diagnostics-dock.cpp
src/receiver-clock-diagnostics-dock.h
tools/apply-receiver-clock-live-diagnostics.py
tools/verify-receiver-clock-live-diagnostics-build.py
```

The other Markdown files are documentation only.

## Build

1. Open `receiver-clock-downstream-diagnostics` on the GitHub website.
2. Choose **Add file → Upload files**.
3. Upload the five operational files above with their folders intact.
4. Commit directly to `receiver-clock-downstream-diagnostics`.
5. Open **Actions → Build Receiver Clock Live Diagnostics**.
6. Open the run triggered by that commit.
7. Confirm all steps are green, especially:
   - **Apply live diagnostics and probe lifecycle patch**
   - **Verify generated source patch**
   - **Verify diagnostics code is linked into the packaged DLL**
8. Download an artifact beginning with:

```text
receiver-clock-live-diagnostics-6.2.1.4-
```

Do not use an artifact from the generic **Build Project** workflow.

## Install and verify in OBS

1. Fully exit OBS, including its system-tray process.
2. Install or copy the downloaded 6.2.1.4 artifact over the previous test build.
3. Start OBS.
4. Look for the dock immediately.
5. If it is not open, use either:
   - **Docks → DistroAV Receiver Clock Health**
   - **Tools → DistroAV Receiver Clock Health**
6. Open the NDI source properties and enable **Receiver Clock diagnostics**.
7. Open the source’s Filters window:
   - diagnostics on should settle at exactly two Clock Lab probes;
   - diagnostics off should settle at zero Clock Lab probes;
   - changing latency, clock mode, or resetting the NDI receiver should not add more probes.

## Build identity

```text
DistroAV Receiver Clock Lab 6.2.1.4
```

The GitHub workflow patches only its temporary checkout. It does not commit generated C++ changes back to the branch.
