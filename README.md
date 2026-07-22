# DistroAV Receiver Clock Lab — Live Diagnostics Build Package

This package extends the existing `receiver-clock-lab` branch only. It does **not** add Sync Guardian, Multichannel Bridge, PPM correction, resampling, or another clock controller.

## What it adds

- An OBS dock named **DistroAV Receiver Clock Health**.
- Plain-language `GOOD`, `WATCH`, `WARNING`, `WAITING`, and `DATA STALE` states.
- A live final A/V difference where:
  - positive means audio appears late relative to video;
  - negative means video appears late relative to audio.
- One-minute and ten-minute movement rates in milliseconds per minute.
- Separate visibility into:
  - DistroAV output A/V timing;
  - OBS video-selection/async-queue movement;
  - OBS audio/filter-path movement;
  - NDI receive queues and drops;
  - receiver-clock deadline error and catch-ups;
  - repeated video identity debt and recovery;
  - data freshness.
- One complete OBS log summary per source every second while diagnostics are enabled.
- Additional event log entries for:
  - health-state transitions;
  - NDI queue pressure starting or clearing;
  - NDI drop counters increasing;
  - downstream video-gap jumps;
  - new video-repeat-debt high-water marks.
- A twelve-hour in-memory flight recorder at one sample per second.
- Faster live CSV flushing, approximately every four seconds.
- Automatic removal and recreation of stale/duplicate Clock Lab probe filters when a source loads.

## Files to upload

Upload these files to the same paths on the `receiver-clock-lab` branch:

```text
.github/workflows/build-receiver-clock-live-diagnostics.yml
src/receiver-clock-diagnostics-dock.cpp
src/receiver-clock-diagnostics-dock.h
tools/apply-receiver-clock-live-diagnostics.py
```

The workflow applies the remaining source edits in its temporary runner checkout. It does not commit those generated edits back to the branch.

## Build on GitHub

1. Upload all four files above while preserving their paths.
2. Commit them to `receiver-clock-lab`.
3. Open the repository's **Actions** tab.
4. Select **Build Receiver Clock Live Diagnostics**.
5. Choose **Run workflow**.
6. Download either the standard Windows x64 zip or the portable Windows x64 zip from the run's **Artifacts** section.

The build identifies itself as **DistroAV Receiver Clock Lab 6.2.1.3**.

## Optional: commit the generated C++ edits permanently

From a local checkout of `receiver-clock-lab`, copy the package files into the repository and run:

```powershell
python .\tools\apply-receiver-clock-live-diagnostics.py
python .\tools\apply-receiver-clock-live-diagnostics.py --check
git diff --check
```

The patcher is strict, transactional, and idempotent. It refuses to write anything unless every expected 6.2.1.2 source anchor is present.

## Running the test

1. Install the built zip using the same method as the existing Receiver Clock Lab build.
2. Start OBS and select **Receiver-Paced** for the NDI source under test.
3. Enable **Receiver Clock diagnostics** in that source's properties.
4. Open **Docks → DistroAV Receiver Clock Health**.
5. Record for the full three-hour test without rebuilding the source.
6. Save the receiver OBS log and the per-source CSV from the DistroAV plugin configuration folder.
7. Use **Copy summary** in the dock near the beginning, around each hour, and at the end.

## How to read the likely-cause result

- **OBS audio path growth**: the final drift is appearing after DistroAV output in the post-filter/mixer audio path. This is the primary new measurement for the reported “audio becomes late” symptom.
- **OBS video queue growth**: submitted video stays aligned, but OBS-selected video moves away from it.
- **DistroAV output movement**: the relationship is already changing when DistroAV hands media to OBS, so the receiver-clock/output path needs investigation.
- **NDI receive pressure**: queues and drops suggest the receiver is being starved or overloaded before output.
- **Large static offset**: the A/V difference is large, but the history does not show continued growth.
- **Stable or undetermined**: no measured path is growing fast enough to identify a culprit yet.

## Diagnostic files

The existing per-source live CSV remains in the OBS plugin configuration folder and is named from the OBS source UUID:

```text
receiver-clock-lab-<source-uuid>.csv
```

The source-properties export button still writes:

```text
receiver-clock-lab.csv
```

## Downstream clean-replacement revision

This revision targets `receiver-clock-downstream-diagnostics`, triggers on every
push to that branch, and accepts either Receiver Clock Lab buildspec `6.2.1.1` or
`6.2.1.2` as the pre-patch version.
