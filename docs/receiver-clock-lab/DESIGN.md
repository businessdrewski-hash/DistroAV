# Receiver Clock Lab design

## Purpose

Receiver Clock Lab is an experimental DistroAV receive-path change designed to prevent progressive A/V drift in a two-computer OBS/NDI workflow.

The original failure accumulated gradually under Stock DistroAV Direct Receive. Audio became increasingly early relative to video at approximately 1.8–2.0 ms per minute. Rebuilding the receiver returned the source close to its original sync relationship.

The final design does not estimate drift and does not apply a downstream correction. Instead, it changes how audio and video are scheduled and timestamped before they are delivered to OBS.

The core design principle is:

> Audio and video delivered to OBS should share one receiver-owned clock and one receiver-owned epoch.

---

## Existing DistroAV 6.2.1 behavior

### Stock Direct Receive

The direct receive path waits for `NDIlib_recv_capture_v3(...)` and immediately outputs whichever sender-paced audio or video frame arrives.

The outgoing OBS timestamps are derived from the incoming NDI timestamp or source timecode.

Conceptually:

```text
receive NDI frame
copy or convert frame
copy sender-derived timestamp
send frame to OBS
```

This means the sender remains an important timestamp authority even though OBS is presenting and mixing the media according to clocks on the receiving computer.

### Stock FrameSync

The existing FrameSync path creates an NDI FrameSync instance and repeatedly polls it.

The stock implementation:

- Uses NDI FrameSync for audio sample conversion and media selection
- Requests fixed-size audio blocks
- Polls in a loop with a fixed sleep
- Suppresses some duplicate output by checking returned source timestamps
- Continues to derive outgoing OBS timestamps from NDI timestamps or timecodes

FrameSync therefore selects synchronized NDI media, but it does not establish one receiver-owned OBS output cadence.

---

## Failure model

The measured pipeline showed that the problem was not a large error at initial capture and was not an accumulating error in the OBS audio handoff.

The important relationships were:

```text
incoming NDI capture timing
DistroAV output timing
OBS-selected video timing
filtered OBS mixer-audio timing
```

The Stock Direct control showed:

- Incoming capture A/V moved only a few milliseconds
- DistroAV direct output reflected similar movement
- Filtered OBS audio remained effectively locked to DistroAV audio
- OBS-selected video moved by more than 100 ms relative to DistroAV video output

This indicates that sender-derived timing and receiver-side presentation timing were being allowed to interact without one common receiver scheduler.

The receiver consumes:

- Audio according to the receiver audio clock
- Video according to the receiver OBS video cadence

If outgoing timestamps remain tied to sender timing, a small mismatch between the two computers can accumulate into visible drift.

---

## New receive modes

The test branch keeps multiple modes so the failure and fix can be compared in the same build.

### Mode 0: Stock Direct

```text
mode=0
```

Behavior:

- Uses the ordinary direct NDI receive path
- FrameSync disabled
- Sender-derived timestamps preserved
- No receiver-owned audio/video scheduler
- Serves as the formal control

### Mode 1: Stock FrameSync reference

```text
mode=1
```

Behavior:

- Uses the existing DistroAV FrameSync behavior
- Preserves reference scheduling and timestamp behavior
- Exists for comparison
- Does not use the new receiver-owned timestamp authority

### Mode 2: Receiver-Paced / OBS-Paced

```text
mode=2
```

Behavior:

- Uses NDI FrameSync for media selection and audio conversion
- Uses one receiver-owned epoch
- Schedules audio from receiver audio deadlines
- Schedules video from receiver OBS frame deadlines
- Generates outgoing audio and video timestamps locally
- Resets all receiver scheduler state when the receiver is rebuilt

---

## Shared receiver scheduling state

Receiver-Paced mode adds receiver-owned scheduling state associated with the NDI source.

The state contains the information required to generate both streams from one local timeline:

- Receiver epoch in the `os_gettime_ns()` domain
- OBS audio sample rate
- Audio block size or requested sample count
- Total audio samples delivered
- Next audio deadline
- OBS video frame interval
- Total receiver video ticks
- Next video deadline
- Scheduler initialization state
- Catch-up counters
- Empty-pull counters
- Repeated-frame counters
- Queue-depth observations
- Diagnostic timestamps and probe state

The exact implementation details may be grouped into structures or source-local fields, but the functional requirement is that both media paths reference the same epoch.

---

## Receiver epoch

A new absolute receiver epoch is created after the NDI receiver and FrameSync objects are successfully built.

The epoch is based on:

```cpp
os_gettime_ns()
```

This places the scheduler in the same local monotonic clock domain used for the receiver-side observations and deadlines.

The epoch is not learned from incoming NDI timestamps.

The epoch is recreated when:

- The NDI receiver is created
- The NDI receiver is rebuilt
- FrameSync is recreated
- The source changes in a way that requires receiver reconstruction
- Receiver-Paced mode is reinitialized

The reset clears accumulated scheduler state so a rebuilt receiver begins from a fresh local timeline.

---

## Audio scheduling changes

### Previous behavior

Stock receive paths output audio when frames are returned by the NDI receive or FrameSync APIs.

Outgoing audio timestamps remain influenced by sender-derived timing.

### Receiver-Paced behavior

Audio is scheduled according to receiver-owned audio deadlines.

The outgoing timestamp is generated from cumulative delivered samples:

```text
audio timestamp =
    receiver epoch
    + cumulative delivered audio samples / OBS sample rate
```

In nanoseconds:

```text
audio_timestamp_ns =
    receiver_epoch_ns
    + samples_delivered * 1,000,000,000 / sample_rate
```

### Functional changes

Receiver-Paced audio processing:

- Reads the OBS audio sample rate
- Requests audio from NDI FrameSync
- Uses FrameSync for sample-rate conversion between independent clocks
- Advances the local audio timeline only by samples actually delivered
- Sends the locally generated timestamp to OBS
- Tracks the next receiver audio deadline
- Detects late audio work
- Allows bounded catch-up when appropriate
- Avoids unlimited catch-up loops
- Records empty audio pulls
- Records audio catch-up events
- Records queue-depth and diagnostic timing

### Why cumulative samples are used

The number of samples delivered is the most direct description of elapsed audio time in OBS.

At 48 kHz:

```text
48,000 delivered samples = 1 second
```

This prevents the audio timeline from depending on callback arrival jitter or sender timestamp movement.

---

## Video scheduling changes

### Previous behavior

Stock receive paths output video when the NDI receive or FrameSync API returns a frame.

Outgoing video timestamps remain influenced by sender-derived timing or source timecode.

### Receiver-Paced behavior

Video is pulled and emitted according to receiver OBS frame deadlines.

The outgoing timestamp is generated from receiver video ticks:

```text
video timestamp =
    receiver epoch
    + receiver video tick * OBS frame interval
```

At 60 FPS:

```text
frame interval ≈ 16.666667 ms
```

### Functional changes

Receiver-Paced video processing:

- Reads the OBS video frame interval
- Maintains a receiver-side next-video deadline
- Pulls video from NDI FrameSync near the OBS frame deadline
- Generates the outgoing timestamp from the local epoch and video tick count
- Increments the tick count according to receiver cadence
- Detects missed deadlines
- Skips missed ticks instead of allowing lateness to remain in the schedule
- Records empty video pulls
- Detects repeated FrameSync images
- Records video catch-up or skipped-tick events
- Records queue-depth and diagnostic timing

### Why missed ticks are skipped

If the receive loop is late and simply shifts every future deadline later, the lateness becomes permanent and can accumulate.

Receiver-Paced mode instead calculates which receiver tick should currently be active and advances to that tick.

Conceptually:

```text
if current time is past one or more video deadlines:
    advance to the current receiver tick
    do not replay every missed scheduling interval
```

This keeps the long-term schedule aligned with the receiver clock.

---

## NDI FrameSync responsibility

NDI FrameSync remains part of Receiver-Paced mode, but its responsibility is narrowed.

FrameSync is used for:

- Selecting source audio and video
- Converting audio sample cadence between independent systems
- Returning media appropriate for the receiver pull request
- Absorbing small sender/receiver clock differences at the media-selection level

FrameSync is not treated as the OBS timestamp authority.

DistroAV owns:

- Receiver deadlines
- Receiver epoch
- Audio sample timeline
- Video tick timeline
- OBS output timestamps
- Late-work policy
- Reset policy

This separation is central to the design.

---

## Timestamp authority changes

### Stock modes

Stock Direct and Stock FrameSync preserve sender-derived timing behavior.

Possible incoming authorities include:

- NDI frame timestamp
- NDI source timecode
- Existing DistroAV conversion logic

### Receiver-Paced mode

Receiver-Paced mode replaces the outgoing timestamp authority with local values.

The incoming timestamps are still logged for diagnostics, but they are not used as the final OBS output clock.

This allows the test to compare:

```text
incoming capture relationship
versus
receiver-owned output relationship
```

The incoming timing can move without forcing the OBS output timing to drift.

---

## Processing functions changed

The primary receive-path changes are in:

```cpp
ndi_source_thread_process_audio3(...)
ndi_source_thread_process_video2(...)
```

Their Receiver-Paced behavior differs from stock modes in four main ways:

1. They follow receiver-owned deadlines.
2. They use NDI FrameSync as a media provider rather than as timestamp authority.
3. They generate outgoing OBS timestamps from one shared epoch.
4. They update diagnostics and scheduler counters at each boundary.

Stock and reference modes remain available so their original behavior can be measured in the same binary.

---

## Receive-loop changes

The receive thread was changed to support two independent deadline streams derived from the same epoch.

The loop must decide whether audio, video, or both are due.

Conceptually:

```text
initialize shared epoch
initialize next audio deadline
initialize next video deadline

while receiver is active:
    determine current receiver time

    if audio is due:
        process receiver-paced audio

    if video is due:
        process receiver-paced video

    sleep or wait until the next relevant deadline
```

Important behavior:

- Audio and video have independent deadlines
- Both deadlines share the same absolute epoch
- The loop avoids a fixed arbitrary polling cadence as its timing authority
- Late work is handled explicitly
- Receiver reconstruction fully reinitializes the schedule

---

## Reset and rebuild behavior

A receiver rebuild must wipe all state that could preserve the previous timing relationship.

Receiver-Paced reset includes:

- Receiver epoch
- Audio samples delivered
- Video tick count
- Next audio deadline
- Next video deadline
- Catch-up state
- Previous-frame identity used for repeat detection
- Queue observations
- Diagnostic baselines tied to the old receiver instance
- FrameSync-associated state

This matches the observed system behavior: rebuilding the NDI receiver returns the source close to baseline sync.

The test branch treats a receiver reset as a clean timing reset rather than attempting to preserve learned drift information.

---

## Diagnostics added

The branch adds boundary-by-boundary CSV diagnostics so the failure cannot be hidden by one corrected or derived value.

The diagnostics record relationships including:

```text
capture_video_minus_capture_audio_projected_ns
output_video_minus_output_audio_projected_ns
selected_video_minus_output_video_projected_ns
filtered_audio_minus_output_audio_projected_ns
selected_video_minus_filtered_audio_projected_ns
```

These fields separate:

- Incoming NDI timing
- DistroAV output timing
- OBS downstream video selection
- OBS downstream audio handoff
- End-to-end selected video versus mixer audio

### Counters added

The diagnostics also record:

- NDI-reported dropped audio frames
- NDI-reported dropped video frames
- Empty audio pulls
- Empty video pulls
- Repeated video frames
- Audio catch-ups
- Video catch-ups or skipped ticks
- Maximum queued audio frames
- Maximum queued video frames
- Active timing mode
- Test duration and sample count

### Diagnostic probes

The branch adds probes around:

- DistroAV audio output
- DistroAV video output
- OBS-selected video
- Filtered OBS mixer audio

These probes are intended for experimentation and validation. They are not necessarily all required in a final production patch.

---

## CSV analysis tool

A Python analysis script was added:

```text
tools/analyze-receiver-clock-log.py
```

The script analyzes the full capture rather than relying on one raw final row.

It reports:

- Duration
- Active mode
- Starting relationship
- Final relationship
- Total change
- Drift slope in ppm
- Pull, drop, repeat, catch-up, and queue counters

Conversion used:

```text
1 ppm = 0.06 ms/minute
```

The script allows Stock Direct and Receiver-Paced tests to be compared using the same methodology.

---

## Source property and UI changes

The test build adds a source property for selecting the receive timing mode.

The UI identifies the experimental build as:

```text
DistroAV Receiver Clock Lab 6.2.1.1
```

The available modes distinguish:

- Stock Direct
- Stock FrameSync reference
- Receiver-Paced / OBS-Paced

The mode is written into diagnostics so exported results can be identified without relying only on operator notes.

Locale text was added for the new source properties and labels.

---

## Build-system changes

The build files were updated to compile and package the new experimental source files.

Changes include registering:

```text
src/receiver-clock-diagnostics.cpp
src/receiver-clock-diagnostics.h
tests/receiver-clock-diagnostics-test.cpp
```

The build metadata was also updated to identify the experimental version.

Documentation and test directories were allowed through `.gitignore` so they can be included in the branch.

The exact set of build-file changes in the research branch may include:

```text
CMakeLists.txt
buildspec.json
.gitignore
data/locale/en-US.ini
```

These are support changes for the experiment, not part of the core clock algorithm.

---

## Diagnostics startup hardening

The diagnostics system originally associated probes using a raw pointer stored through OBS settings.

That was unsafe across:

- OBS restart
- Filter recreation
- Source reconstruction
- Stale settings restoration

The test branch replaced that lifecycle with a safer token-based registry and shared ownership.

The hardening changes:

- Generate a diagnostics token
- Store the token rather than a raw object pointer
- Resolve the token through a registry
- Use shared ownership while a probe is active
- Disable or log safely if the token cannot be resolved
- Remove the registry entry when probes detach

This change prevents the diagnostics harness from dereferencing stale state after restart.

It does not change the A/V synchronization algorithm.

---

## Repeated-frame detection

Receiver-Paced validation exposed occasional cases where NDI FrameSync returned the same video image on consecutive OBS ticks.

The branch adds detection and counting for this condition.

A repeated frame means:

- OBS requested the next receiver video tick
- FrameSync returned an image matching the previously emitted image
- The frame was delivered again or observed as a repeat

This is tracked separately from:

- Empty video pulls
- NDI-reported dropped frames
- A/V drift
- Scheduler catch-up

Repeated-frame reduction is future video-pacing work and is not required to establish whether the A/V drift was fixed.

---

## Unit and test support

A diagnostics-focused test source was added:

```text
tests/receiver-clock-diagnostics-test.cpp
```

The test support is intended to validate deterministic pieces of the instrumentation and timing calculations where possible.

A production patch should retain unit-testable scheduler math even if the verbose research diagnostics are later reduced.

Potential units suitable for isolated tests include:

- Sample-count-to-time conversion
- Video-tick-to-time conversion
- Deadline advancement
- Missed-tick calculation
- Bounded catch-up limits
- Epoch reset behavior
- Sign and relationship calculations

---

## Files changed in the research branch

The complete experimental branch changes or adds files in these areas.

### Core implementation

```text
src/ndi-source.cpp
src/plugin-main.cpp
```

### Diagnostics

```text
src/receiver-clock-diagnostics.cpp
src/receiver-clock-diagnostics.h
```

### User interface and localization

```text
data/locale/en-US.ini
buildspec.json
```

### Build and repository support

```text
CMakeLists.txt
.gitignore
```

### Test and analysis tools

```text
tests/receiver-clock-diagnostics-test.cpp
tools/analyze-receiver-clock-log.py
```

### Documentation

```text
README.md
docs/receiver-clock-lab/README.md
docs/receiver-clock-lab/DESIGN.md
docs/receiver-clock-lab/DIAGNOSTICS.md
docs/receiver-clock-lab/INSTALL-TEST-BUILD.md
docs/receiver-clock-lab/REPRODUCTION.md
docs/receiver-clock-lab/AI-WORKLOG.md
```

Some documentation files may be omitted or reorganized without changing the plugin.

---

## What is not part of the final synchronization design

The Receiver Clock Lab does not require:

- Downstream audio PPM feedback correction
- Downstream video timestamp steering
- A learned drift baseline
- A controller that continuously chases measured error
- Periodic automatic receiver resets
- Sender-side changes
- Multitrack audio combination
- Changes to OBS core
- Changes to the NDI sender
- A new external synchronization service

The final design fixes the scheduling authority at the receive boundary.

---

## Control and validation result

The formal Stock Direct control reproduced the issue:

```text
Duration: 60.78 minutes
End-to-end movement: -109.540 ms
Drift rate: approximately -1.802 ms/minute
```

The Receiver-Paced validation produced:

```text
Duration: 96.08 minutes
End-to-end movement: -0.090 ms
Drift rate: approximately -0.00094 ms/minute
```

Both tests showed similar small movement in the incoming capture relationship.

Only the Stock Direct control allowed that timing difference to become large downstream video movement.

This supports the design decision to replace mixed sender/receiver output timing with one receiver-owned OBS timeline.

---

## Production reduction strategy

The research branch contains more instrumentation and selectable behavior than a production patch should require.

A production-sized implementation can likely be reduced to:

- One receiver scheduler
- One shared receiver epoch
- Receiver-paced audio deadlines
- Receiver-paced video deadlines
- Locally generated OBS timestamps
- NDI FrameSync for media selection and sample conversion
- Explicit reset behavior
- Focused scheduler unit tests
- Minimal diagnostic counters
- Optional temporary source property during evaluation

After validation, the following can be reduced or removed:

- Verbose CSV logging
- Downstream diagnostic filters
- Research-only source modes
- Detailed per-boundary probes
- Experimental branding
- Large documentation worklog
- Temporary startup diagnostics registry

The resulting production change should remain confined primarily to the DistroAV NDI source receiver and should require no OBS-core or sender modification.
