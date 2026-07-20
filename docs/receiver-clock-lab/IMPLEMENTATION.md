# Implementation

This document inventories every material behavioral, source-file, build, diagnostics, and project change relative to stock DistroAV 6.2.1 at commit `038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8`.

It is intentionally not a line-by-line translation of the Git diff. The diff remains the exact record of every edit; this document explains the architecture, integration points, rationale, lifecycle, and tradeoffs a developer would need to understand or independently rewrite the experiment.

## Scope

The branch changes only the NDI receiver path. It does not combine audio tracks, change sender behavior, or alter DistroAV output features.

The experiment has two separable parts:

1. **Receiver clock implementation** — the timing behavior being tested.
2. **Diagnostic scaffolding** — observation and CSV tooling used to prove where timing changes occur.

The clock implementation can be rewritten without retaining all diagnostic code. The diagnostic code is deliberately more extensive because the purpose of this branch is to localize faults rather than serve as a minimal production patch.

## Core receiver changes: `src/ndi-source.cpp`

### 1. Receiver clock modes

The NDI Source properties add three explicit paths:

1. Stock direct receive.
2. Stock FrameSync.
3. Receiver-Paced FrameSync.

Stock paths remain available as controls. Selecting a different mode rebuilds the NDI receiver and FrameSync instance.

`ndi_source_update()` maps the selected mode to the existing `framesync_enabled` state:

- Stock direct receive disables FrameSync.
- Stock FrameSync enables the original FrameSync path.
- Receiver-Paced enables FrameSync and the new local scheduler.

This keeps the old direct and FrameSync implementations available for A/B testing instead of replacing them globally.

### 2. Receiver-owned timestamp scheduler

Receiver-Paced mode creates a local `receiver_clock_schedule_t` for each NDI Source. It stores:

- OBS audio sample rate.
- OBS rational video frame rate.
- cumulative delivered audio samples.
- cumulative video ticks.
- next audio and video deadlines.
- bounded catch-up counters.
- empty-pull counters.
- source-frame repeat and recovery state used by diagnostics.

Audio timestamps are calculated from the shared epoch plus cumulative delivered audio samples. Video timestamps are calculated from the shared epoch plus exact rational frame ticks.

Incoming NDI timestamp and timecode values are retained for diagnostics and source-frame identity, but they are not used as final OBS timestamps in Receiver-Paced mode.

The final timestamp substitution occurs through the optional `receiver_timestamp_ns` argument added to:

- `ndi_source_thread_process_audio3()`
- `ndi_source_thread_process_video2()`

When that argument is nonzero, it becomes the timestamp submitted to OBS. The stock paths call the same functions without the override and therefore retain the selected NDI timestamp or timecode behavior.

### 3. Shared receiver clock domain

A process-wide monotonic epoch is protected by `receiver_clock_domain_mutex` and returned by `receiver_clock_shared_epoch()`.

Every Receiver-Paced source has its own NDI receiver, FrameSync object, scheduling counters, and receiver thread, but all of those schedulers generate timestamps in the same coordinate system.

This is necessary for a layout such as:

- source 1: video with audio disabled.
- source 2: desktop audio-only.
- source 3: microphone audio-only.

If each source starts an independent local epoch, their timestamps can begin close together but still represent separate timelines. Sharing the epoch makes their audio sample counts and video tick counts comparable inside OBS.

A source created later does not replay time from the original epoch. `receiver_clock_schedule_t::reset()` joins it at the first complete audio block and video tick at or after a local 100 ms startup guard. This preserves the common coordinate system without creating a large startup catch-up burst.

The process-wide epoch persists for the life of the loaded plugin process. Resetting or recreating one source does not reset the common domain for other sources.

A production rewrite could replace this single process-wide domain with an explicit clock-group object keyed by a user-selected group or stable sender identity. The essential rule is that every source intended to remain synchronized must generate timestamps from the same epoch and rate definitions.

### 4. Exact rational video timing

Video timing stores `fps_num` and `fps_den` and recalculates each timestamp from the tick index:

```cpp
shared_epoch + ticks * fps_den * 1,000,000,000 / fps_num
```

It does not repeatedly add a truncated integer frame interval. Catch-up math uses the same rational rate.

For rates such as 60000/1001, repeatedly adding an integer nanosecond approximation would introduce its own rounding error. Recalculating from the absolute tick index prevents that rounding remainder from accumulating frame after frame.

### 5. Deadline-driven pulling and bounded recovery

The Receiver-Paced branch inside `ndi_source_thread()` pulls audio and video only when their receiver deadlines are due.

#### Audio behavior

- The normal request unit is 1024 audio frames.
- If the receiver thread is late, it may request multiple blocks in one pull.
- One pull is capped at four blocks so a temporary stall cannot create an unbounded recovery request.
- Successful pulls advance the schedule by the actual number of returned samples.
- Empty pulls advance by the number of requested samples so the receiver clock does not remain stuck on an expired deadline and later replay stale schedule positions.

The four-block limit bounds work per loop; it does not pretend a large stall never happened. If more recovery is needed, later loop iterations continue catching up.

#### Video behavior

- The scheduler calculates how many complete video ticks are already overdue.
- Overdue ticks are skipped before requesting the current FrameSync frame.
- The next submitted frame receives the timestamp for the current receiver tick.
- An empty video pull still advances the scheduler by one tick.

Skipping stale video schedule positions is intentional. Moving the entire receiver timeline later after every hitch would convert a temporary stall into permanent added latency.

### 6. Automatic unbuffered OBS video

Stock DistroAV enables `obs_source_set_async_unbuffered()` only when the Latency setting is Lowest.

This fork enables it when either:

- Latency is Lowest, or
- Receiver Clock mode is Receiver-Paced.

Receiver-Paced mode already controls playout timing. Allowing OBS to build another async-video backlog can make the preview and recording move behind the frames DistroAV is currently submitting.

Unbuffered mode makes OBS prefer current video and discard stale queued frames after a hitch.

This does not force the NDI receiver's fastest color format. The existing Latency setting still controls that separate NDI choice.

### 7. Diagnostics hooks

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

## Code integration map

| Behavior | Primary symbol or location | Purpose |
|---|---|---|
| Receiver mode selection | `ndi_source_getproperties()` and `ndi_source_update()` | Exposes the three paths, maps them to FrameSync state, and requests receiver rebuilds when the mode changes. |
| Shared clock origin | `receiver_clock_shared_epoch()` | Returns one mutex-protected monotonic epoch for every Receiver-Paced source. |
| Per-source scheduler | `receiver_clock_schedule_t` | Holds rate definitions, counters, deadlines, catch-up state, and diagnostic frame-identity state. |
| Join existing timeline | `receiver_clock_schedule_t::reset()` | Aligns a newly initialized or reset source to the next valid audio block and video tick after the startup guard. |
| Exact audio timestamp | `receiver_clock_schedule_t::audio_timestamp_ns()` | Converts cumulative delivered samples into nanoseconds from the shared epoch. |
| Exact video timestamp | `receiver_clock_schedule_t::video_timestamp_ns()` | Converts an absolute rational frame tick into nanoseconds from the shared epoch. |
| Receiver-Paced playout | Receiver-Paced branch in `ndi_source_thread()` | Pulls FrameSync media on local deadlines and applies bounded recovery after stalls. |
| Final audio timestamp | `ndi_source_thread_process_audio3()` | Uses the receiver timestamp override in Receiver-Paced mode; otherwise preserves stock source timing. |
| Final video timestamp | `ndi_source_thread_process_video2()` | Uses the receiver timestamp override in Receiver-Paced mode; otherwise preserves stock source timing. |
| OBS queue policy | `ndi_source_update()` | Forces async unbuffered video for Receiver-Paced mode independently of the NDI color-format latency choice. |
| Diagnostics sampling | `sample_diagnostics` lambda in `ndi_source_thread()` | Samples scheduler and NDI queue state at most once every 250 ms. |
| Downstream OBS observation | `clocklab_audio_probe_filter()` and `clocklab_video_probe_filter()` | Records timestamps after OBS has accepted or selected media without modifying it. |
| Probe lifetime lookup | `register_clocklab_diagnostics()`, `acquire_clocklab_diagnostics()`, and `unregister_clocklab_diagnostics()` | Lets private OBS filters safely acquire shared diagnostic storage through an opaque token. |
| CSV export | `export_clocklab_diagnostics()` | Writes the current source's bounded diagnostic history to `receiver-clock-lab.csv`. |

## Source lifecycle and threading

Each NDI Source continues to use the existing DistroAV receiver thread model.

### Creation

`ndi_source_create()` allocates the source state and diagnostic owner.

Diagnostic probes use shared ownership so a filter callback cannot dereference diagnostic state that has already been destroyed.

### Settings update

`ndi_source_update()` treats changes to the source name, bandwidth, latency, hardware acceleration, color configuration, receiver clock mode, or derived FrameSync state as receiver-resetting changes.

Changing the clock mode therefore destroys and recreates both the NDI receiver and FrameSync instance rather than trying to mutate scheduler ownership while the old receive path is active.

Diagnostics can be enabled or disabled without rebuilding the NDI receiver. A mode change is recorded as a diagnostic event when diagnostic storage exists.

### Receiver reset

Inside `ndi_source_thread()`, a requested reset:

1. marks a receiver-reset event.
2. destroys the existing FrameSync object.
3. destroys the existing NDI receiver.
4. creates the replacement NDI receiver.
5. creates FrameSync when the selected mode requires it.
6. calls `receiver_clock_schedule_t::reset()` only for Receiver-Paced mode.
7. marks the receiver-ready event.

The scheduler therefore starts only after the replacement FrameSync object exists.

### Hidden and inactive sources

The existing DistroAV source-visibility behavior remains in control of whether the receiver thread starts or stops.

A hidden source that remains connected avoids busy-waiting by sleeping briefly before checking again.

A source that later resumes in Receiver-Paced mode rejoins the process-wide domain instead of creating a new unrelated timestamp origin.

### Destruction

The source thread is stopped and joined before receiver resources are released.

Diagnostic probes are removed and their shared registry token is unregistered as part of source cleanup.

## Important implementation decisions and tradeoffs

### NDI FrameSync still selects media

Receiver-Paced mode does not replace NDI FrameSync's buffering, audio conversion, or frame-selection behavior.

It changes when DistroAV asks FrameSync for media and which timestamps DistroAV submits to OBS.

The NDI source timestamp and timecode are still recorded because they are useful for identifying repeated or skipped source frames, even though they no longer control final OBS timing.

### The OBS configuration defines the receiver rates

The scheduler reads the OBS audio sample rate and rational OBS video frame rate when it resets. Those rates define the receiver timeline.

The implementation assumes that sources intended to synchronize are being consumed by the same OBS process and should conform to that OBS output timing domain.

### Audio and video recover differently

Audio recovery is bounded by requesting up to four 1024-frame blocks in one pull.

Video recovery skips obsolete receiver ticks and requests only the current frame.

This difference is deliberate: audio is continuous sample data, while replaying every stale video tick after a hitch would build visible latency.

### Empty pulls do not freeze time

An empty audio or video FrameSync result increments diagnostics and advances the relevant schedule.

Otherwise, a temporary lack of media would leave the next deadline permanently in the past and could cause repeated stale recovery attempts.

This favors maintaining the receiver's real-time position over replaying media that was unavailable at its intended deadline.

### Shared domain is broad by design

The experiment uses one domain for the entire OBS process because it is simple and directly tests whether separate source instances can remain aligned.

A production implementation may need multiple independent groups when unrelated NDI programs are used in the same OBS process. That grouping policy is outside the scope of this branch.

### Unbuffered video is part of the fix, not only a latency preference

Receiver-generated timestamps can remain correct at DistroAV output while OBS-selected video stays permanently behind because of a retained async-video queue.

Receiver-Paced mode therefore forces unbuffered OBS video so a receiver-side hitch can recover to current frames instead of preserving stale backlog.

## Essential clock fix versus diagnostic scaffolding

### Essential to reproduce the timing behavior

A minimal independent rewrite needs:

- the three-path mode separation or equivalent stock control path.
- a clock domain shared by all sources that must synchronize.
- per-source cumulative audio sample and rational video tick counters.
- joining an existing clock domain at current valid positions.
- deadline-driven FrameSync pulls.
- bounded audio catch-up and skipped stale video ticks.
- receiver-generated final OBS timestamps.
- unbuffered OBS async video in the receiver-paced path.

### Diagnostic-only or replaceable infrastructure

The following are valuable for proving behavior but are not required for the clock algorithm itself:

- `Diagnostics` history storage and CSV serialization.
- private OBS audio and video probe source types.
- opaque token registry for probe access.
- repeat-debt and downstream-gap event classification.
- the Python CSV analysis tool.
- the diagnostics serialization CTest.

A production implementation should retain enough telemetry to distinguish NDI arrival, DistroAV submission, and OBS selection, but it does not have to preserve this exact storage or export design.

## Diagnostics implementation

### `src/receiver-clock-diagnostics.h`

Defines event types, scheduler snapshots, stage observations, repeat/debt state, downstream-gap state, thread-safe storage, and CSV export interfaces.

### `src/receiver-clock-diagnostics.cpp`

Implements synchronized stage collection, 250 ms samples, event rows, repeat recovery accounting, downstream gap-step detection, bounded in-memory history, and CSV serialization.

The storage is synchronized because audio, video, receiver-thread sampling, property actions, and private OBS filter callbacks can occur on different threads.

### `src/plugin-main.cpp`

Registers the private audio and video diagnostic probe source types before the normal NDI source is registered.

The probes are private implementation details and do not appear as normal user-addable OBS sources.

## UI and project files

### `data/locale/en-US.ini`

Adds labels and descriptions for receiver clock modes, diagnostics, CSV export, and latency choices.

Receiver-Paced text states that OBS video is automatically unbuffered.

### `CMakeLists.txt`

Adds the diagnostics source/header to the plugin build.

Adds a small CTest executable for diagnostics serialization and enables the `tests` source tree.

### `buildspec.json`

Changes the experimental package display name to `DistroAV Receiver Clock Lab` and increments the fork build to `6.2.1.2`.

The package identity remains separate from a production DistroAV release.

### `.gitignore`

Allows the new `tests` and `tools` directories to be tracked.

### `README.md`

Adds a warning that this is an experimental clock fork and links to the focused clock-lab documents.

## Tools and tests

### `tools/analyze-receiver-clock-log.py`

Analyzes exported CSV files for:

- duration.
- linear drift slopes.
- A/V relationships.
- selected-versus-submitted video delay.
- persistent gap steps.
- NDI drops.
- repeat clusters.
- recovered repeat debt.
- scheduler health.

### `tests/receiver-clock-diagnostics-test.cpp`

Checks basic diagnostics sampling and CSV output without requiring a live NDI stream.

This test validates diagnostic storage and serialization only.

It does not simulate NDI FrameSync or prove long-run A/V synchronization. That still requires the live procedures in `TESTING.md`.

## Documentation and test data

The focused clock-lab documentation is:

- `README.md`
- `IMPLEMENTATION.md`
- `REPRODUCTION.md`
- `TESTING.md`

The two original CSV captures remain as raw reference data.

`REPRODUCTION.md` records the original environment, observed failure, experiments, and measurements.

It is intentionally separate from this implementation inventory so historical investigation does not obscure the final code path.

## Known boundaries for a production rewrite

Before upstreaming or rewriting this experiment, a maintainer should decide:

- whether clock domains should be process-wide, keyed by sender, or explicitly user-grouped.
- whether the 100 ms startup guard should remain fixed or be derived from receiver conditions.
- whether 1024-frame audio blocks and the four-block catch-up cap should be configurable or calculated.
- how rate or OBS configuration changes should force domain or scheduler reinitialization.
- what should happen when a source remains disconnected for a long interval and then returns.
- how much downstream OBS telemetry is appropriate in a normal release build.
- whether private filters are the preferred long-term way to observe OBS-selected timestamps.

These are product and integration decisions, not evidence that the experiment requires every diagnostic component to become permanent DistroAV code.

## Minimal rewrite recipe

A developer rewriting this independently should:

1. Keep stock receive paths unchanged as controls.
2. Create one monotonic clock-domain object shared by all synchronized receiver instances.
3. Convert cumulative audio samples and rational video ticks into timestamps from that domain.
4. Join newly created or reset sources at the next valid block or tick instead of restarting the domain.
5. Use NDI FrameSync only to select or resample media, not as the final timestamp authority.
6. Pull media according to receiver-owned deadlines.
7. Use bounded audio catch-up so one stall cannot create unbounded work.
8. Skip overdue video schedule positions instead of permanently moving latency later.
9. Submit Receiver-Paced video through OBS's unbuffered async path.
10. Measure capture, submission, OBS selection, queue health, and repeat identity independently so a future fault can be localized to one stage.
