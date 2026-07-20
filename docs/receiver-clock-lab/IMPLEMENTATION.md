# Implementation

This is the complete change inventory relative to stock DistroAV 6.2.1 at commit `038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8`.

## Core receiver changes: `src/ndi-source.cpp`

### 1. Receiver clock modes

The NDI Source properties add three explicit paths:

1. Stock direct receive.
2. Stock FrameSync.
3. Receiver-Paced FrameSync.

Stock paths remain available as controls. Selecting a different mode rebuilds the NDI receiver and FrameSync instance.

### 2. Receiver-owned timestamp scheduler

Receiver-Paced mode creates a local scheduler with:

- OBS audio sample rate.
- OBS rational video frame rate.
- cumulative delivered audio samples.
- cumulative video ticks.
- next audio and video deadlines.
- bounded catch-up counters.

Audio timestamps are calculated from the shared epoch plus cumulative delivered samples. Video timestamps are calculated from the shared epoch plus exact rational frame ticks. Incoming NDI timestamp and timecode values are retained for diagnostics but are not used as final OBS timestamps in Receiver-Paced mode.

The loop pulls audio and video only when their receiver deadlines are due. Audio catch-up is capped to four blocks per pull. Video skips overdue scheduler ticks instead of moving the complete timeline later.

### 3. Shared receiver clock domain

A process-wide monotonic epoch is protected by a mutex. Every Receiver-Paced source uses that same epoch.

A source created later does not replay time from the original epoch. It joins at the first complete audio block and video tick at or after its local 100 ms startup guard. This preserves a common coordinate system without creating a large startup catch-up burst.

A production rewrite could replace the single process-wide domain with an explicit clock-group object keyed by a user-selected group or a stable sender identity. The essential rule is that every source intended to remain synchronized must generate timestamps from the same epoch and rate definitions.

### 4. Exact rational video timing

Video timing stores `fps_num` and `fps_den` and recalculates each timestamp from the tick index:

```cpp
shared_epoch + ticks * fps_den * 1,000,000,000 / fps_num
```

It does not repeatedly add a truncated integer frame interval. Catch-up math uses the same rational rate.

### 5. Automatic unbuffered OBS video

Stock DistroAV enables `obs_source_set_async_unbuffered()` only when the Latency setting is Lowest.

This fork enables it when either:

- Latency is Lowest, or
- Receiver Clock mode is Receiver-Paced.

Receiver-Paced mode already controls playout timing. Allowing OBS to build another async-video backlog can make the preview and recording move behind the frames DistroAV is currently submitting. Unbuffered mode makes OBS prefer current video and discard stale queued frames after a hitch.

This does not force the NDI receiver's fastest color format. The existing Latency setting still controls that separate NDI choice.

### 6. Diagnostics hooks

The source records these stages without changing media:

- NDI capture timestamp, timecode, dimensions, sample count, and capture wall time.
- receiver scheduler epoch, deadlines, errors, ticks, catch-ups, and empty pulls.
- DistroAV output audio and video timestamps and wall times.
- OBS-filtered audio timestamp.
- OBS-selected async-video timestamp.
- NDI total, dropped, and queued frame counts.
- repeated source-frame identity, consecutive repeats, recovered repeats, repeat debt, maximum debt, and source-frame skips.
- submitted-to-selected downstream video gap and large gap-step events.

Private OBS filters are attached only as observation probes. They do not resample, delay, or rewrite the media.

## Diagnostics implementation

### `src/receiver-clock-diagnostics.h`

Defines event types, scheduler snapshots, stage observations, repeat/debt state, downstream-gap state, thread-safe storage, and CSV export interfaces.

### `src/receiver-clock-diagnostics.cpp`

Implements synchronized stage collection, 250 ms samples, event rows, repeat recovery accounting, downstream gap-step detection, bounded in-memory history, and CSV serialization.

### `src/plugin-main.cpp`

Registers the private audio and video diagnostic probe source types before the normal NDI source is registered.

## UI and project files

### `data/locale/en-US.ini`

Adds labels and descriptions for receiver clock modes, diagnostics, CSV export, and latency choices. Receiver-Paced text now states that OBS video is automatically unbuffered.

### `CMakeLists.txt`

Adds the diagnostics source/header to the plugin build. Adds a small CTest executable for diagnostics serialization and enables the `tests` source tree.

### `buildspec.json`

Changes the experimental package display name to `DistroAV Receiver Clock Lab` and increments the fork build to `6.2.1.2`. The package identity remains separate from a production DistroAV release.

### `.gitignore`

Allows the new `tests` and `tools` directories to be tracked.

### `README.md`

Adds a warning that this is an experimental clock fork and links only to the three concise clock-lab documents.

## Tools and tests

### `tools/analyze-receiver-clock-log.py`

Analyzes exported CSV files for duration, linear drift slopes, A/V relationships, selected-versus-submitted video delay, persistent gap steps, NDI drops, repeat clusters, recovered repeat debt, and scheduler health.

### `tests/receiver-clock-diagnostics-test.cpp`

Checks basic diagnostics sampling and CSV output without requiring a live NDI stream.

## Documentation and test data

The old long-form worklog, design, analysis, diagnostics, install, and reproduction documents are removed. They are replaced by:

- `README.md`
- `IMPLEMENTATION.md`
- `TESTING.md`

The two original CSV captures remain as raw reference data.

## Minimal rewrite recipe

A developer rewriting this independently should:

1. Keep stock receive paths unchanged as controls.
2. Create one monotonic clock-domain object shared by all synchronized receiver instances.
3. Convert cumulative audio samples and rational video ticks into timestamps from that domain.
4. Join newly created sources at the next valid block/tick instead of restarting the domain.
5. Use NDI FrameSync only to select/resample media, not as the final timestamp authority.
6. Use bounded catch-up so a temporary stall skips stale schedule positions instead of permanently moving latency later.
7. Submit Receiver-Paced video through OBS's unbuffered async path.
8. Measure capture, submission, OBS selection, queue health, and repeat identity independently so a future fault can be localized to one stage.
