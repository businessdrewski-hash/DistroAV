# A/V Desync Analysis Guide

## Purpose

This guide explains the best places to measure A/V timing in DistroAV and OBS so a developer can determine **where desync first begins**.

The important lesson from this project was that one final A/V offset is not enough. A changing offset only proves that drift exists somewhere. To locate the cause, the pipeline must be measured at several boundaries.

---

## How the investigation narrowed the delay

Over the course of this project, different possible delay points were tested separately.

Early tests changed:

- Audio sample-rate settings
- FrameSync on and off
- Hardware acceleration
- Source Timing and Network Timing
- NDI bandwidth
- Color settings
- Separate versus combined audio paths
- Sender-side versus receiver-side correction
- Audio PPM correction
- Video timing adjustment
- Receiver resets and rebuilds
- Encoding overload, shader compilation, and alt-tab events

Those tests showed that the slow drift was repeatable, survived many setting changes, and returned close to baseline whenever the receiver was rebuilt.

The next stage measured timing inside OBS callbacks and tracked the offset over long recordings. That established the approximate drift rate and separated gradual drift from sudden jumps.

The final stage used custom DistroAV builds to test each major boundary:

1. Incoming NDI audio and video
2. DistroAV capture and FrameSync
3. Timestamps passed to `obs_source_output_audio` and `obs_source_output_video`
4. Video timing selected downstream by OBS
5. Filtered OBS mixer-audio timing
6. Queue depth, repeats, empty pulls, drops, and catch-ups

That boundary-by-boundary test showed that the audio handoff remained stable while the dominant accumulating delay appeared between DistroAV video output and OBS-selected video.

---

## Pipeline map

```text
Incoming NDI audio/video
        |
        v
DistroAV receive / FrameSync
        |
        v
obs_source_output_audio()
obs_source_output_video()
        |
        +----------------------+
        |                      |
        v                      v
OBS mixer audio         OBS-selected video
        |                      |
        +----------+-----------+
                   |
                   v
             Final A/V result
```

The best measurement points are the handoffs between these stages.

---

## 1. Incoming NDI timing

### Where to measure

Immediately after:

```cpp
NDIlib_recv_capture_v3(...)
NDIlib_framesync_capture_audio(...)
NDIlib_framesync_capture_video(...)
```

Record:

- NDI timestamp or timecode
- Local `os_gettime_ns()` observation time
- Audio sample count and sample rate
- Video frame identity
- Queue depth if available

### Main relationship

```text
capture_video_minus_capture_audio_projected_ns
```

### What it proves

If this relationship already drifts, the movement exists at or before DistroAV capture.

If it remains stable while later values move, the cause is downstream.

Do not compare raw callback arrival times by themselves. Audio and video arrive on different callbacks, so both must be projected into the same local time domain.

---

## 2. DistroAV output timing

### Where to measure

Immediately around:

```cpp
obs_source_output_audio(...)
obs_source_output_video(...)
```

### Main relationship

```text
output_video_minus_output_audio_projected_ns
```

### What it proves

This is the exact timing relationship DistroAV gives OBS.

Compare it with incoming capture timing:

- If capture and output move together, DistroAV is passing the movement downstream.
- If capture moves but output stays stable, DistroAV is normalizing it.
- If output moves more than capture, DistroAV scheduling or timestamp handling is adding error.

---

## 3. OBS-selected video timing

### Where to measure

Observe the frame OBS actually selects after DistroAV calls:

```cpp
obs_source_output_video(...)
```

### Main relationship

```text
selected_video_minus_output_video_projected_ns
```

### What it proves

This isolates delay added after DistroAV outputs video.

If it changes steadily while DistroAV output remains stable, OBS is selecting video progressively later or earlier relative to the submitted frames.

This was the most revealing measurement in the project. The Stock Direct control accumulated more than 100 ms here while the audio handoff remained stable.

---

## 4. OBS mixer-audio timing

### Where to measure

Use an audio filter or callback close to the OBS mixer path.

### Main relationship

```text
filtered_audio_minus_output_audio_projected_ns
```

### What it proves

This isolates the audio handoff.

If it remains near zero, OBS is consuming DistroAV audio consistently and the visible desync is probably caused by video becoming late.

If it changes, inspect audio buffering, resampling, callback cadence, sample accounting, and timestamp rewriting.

This measurement prevents a late video path from being misdiagnosed as “audio rushing.”

---

## 5. End-to-end A/V timing

### Main relationship

```text
selected_video_minus_filtered_audio_projected_ns
```

This is the closest diagnostic approximation to the A/V relationship OBS presents or records.

For video-minus-audio fields:

- More negative means audio is moving further ahead of video.
- More positive means video is moving further ahead of audio.
- A constant non-zero value is a static offset.
- A value that changes over time is drift.

Always report:

```text
starting value
final value
total movement
slope over time
```

---

## 6. Receiver scheduler timing

Instrument the receive loop itself.

Record:

- Receiver epoch
- Current `os_gettime_ns()`
- Next audio deadline
- Next video deadline
- Actual pull times
- Lateness
- Missed ticks
- Catch-up events
- Loop sleep time

Healthy receiver-owned timing should follow:

```text
audio deadline = epoch + cumulative sample duration
video deadline = epoch + video tick × frame interval
```

Look for:

- A fixed sleep becoming the real scheduler
- Late work permanently shifting future deadlines
- Audio and video using different epochs
- Missed video ticks accumulating instead of being skipped

---

## 7. Supporting counters

These counters help explain why an offset moved:

```text
empty_audio_pulls
empty_video_pulls
repeated_video_frames
ndi_dropped_audio_frames
ndi_dropped_video_frames
audio_catchups
video_catchups
max_ndi_queued_audio_frames
max_ndi_queued_video_frames
```

### Repeated frames

Repeated video images can indicate:

- The receiver pulled before the next source frame was ready
- Sender and receiver frame phases are misaligned
- A source or network frame was genuinely missing

Track repeats separately from A/V drift.

### Empty pulls

Recurring empty pulls can indicate:

- Pulling too early
- Insufficient buffering
- Network interruption
- Incorrect scheduler phase

### Queue depth

A steadily growing queue can indicate accumulating latency even when timestamps appear stable.

### Dropped frames

If drift occurs with zero NDI-reported drops, ordinary packet loss is less likely to be the cause.

---

## 8. Reset and discontinuity logging

Log every:

- Receiver rebuild
- FrameSync recreation
- Source reconnect
- Audio-device reset
- Resolution or frame-rate change
- Encoding overload
- Shader-compilation stall
- Alt-tab event

Record the time and reason.

A gradual slope and a sudden step are different problems:

```text
Gradual change over minutes:
likely clock or cadence mismatch

Sudden jump:
likely drop, stall, reconnect, queue flush, or timestamp discontinuity
```

Do not calculate one drift slope across an unexplained reset or step.

---

## Minimum useful diagnostic set

If only a small amount of instrumentation can be added, use:

```text
capture_video_minus_capture_audio_projected_ns
output_video_minus_output_audio_projected_ns
selected_video_minus_output_video_projected_ns
filtered_audio_minus_output_audio_projected_ns
selected_video_minus_filtered_audio_projected_ns
```

Plus:

```text
timing_mode
receiver_reset_count
empty_audio_pulls
empty_video_pulls
repeated_video_frames
NDI drop counters
catch-up counters
queue depth
```

This is enough to determine whether the error begins:

- Before DistroAV
- At DistroAV output
- In downstream video
- In downstream audio
- In the receiver scheduler
- During a drop or discontinuity

---

## Recommended analysis order

### 1. Confirm continuity

Check:

- Mode
- Duration
- Resets
- Reconnects
- Drops
- Empty pulls

### 2. Check the final A/V relationship

Inspect:

```text
selected_video_minus_filtered_audio_projected_ns
```

Determine whether the movement is gradual or stepped.

### 3. Check the audio handoff

Inspect:

```text
filtered_audio_minus_output_audio_projected_ns
```

If stable, audio is probably not where the drift accumulates.

### 4. Check the video handoff

Inspect:

```text
selected_video_minus_output_video_projected_ns
```

If this follows the final drift, the dominant error is in downstream video timing.

### 5. Compare capture with DistroAV output

Inspect:

```text
capture_video_minus_capture_audio_projected_ns
output_video_minus_output_audio_projected_ns
```

This shows whether DistroAV passes, adds, or removes incoming movement.

### 6. Correlate counters and events

Compare any movement with:

- Repeats
- Empty pulls
- Queue growth
- Drops
- Catch-ups
- Reset events

---

## Common result patterns

### Incoming timing movement

```text
capture A/V changes
output A/V changes similarly
downstream handoffs remain stable
```

The movement already exists at capture and is being passed through.

### DistroAV output problem

```text
capture A/V stable
output A/V drifts
```

DistroAV timestamp conversion, FrameSync handling, queueing, or scheduling is introducing error.

### Downstream video drift

```text
output A/V nearly stable
selected video minus output video drifts
audio handoff remains stable
```

The accumulating delay is in receiver-side video selection or presentation cadence.

### Downstream audio drift

```text
video handoff stable
filtered audio minus output audio drifts
```

Inspect mixer scheduling, resampling, and sample accounting.

### Queue accumulation

```text
offset changes
queue depth rises steadily
receiver reset clears both
```

Latency is accumulating through buffering.

### Discontinuity

```text
offset jumps suddenly
drop, empty pull, overload, or reconnect occurs at the same time
```

This is a step event, not slow clock drift.

---

## Best code locations to inspect

The main DistroAV file is:

```text
src/ndi-source.cpp
```

Prioritize:

- Receiver and FrameSync creation/destruction
- `NDIlib_recv_capture_v3(...)`
- `NDIlib_framesync_capture_audio(...)`
- `NDIlib_framesync_capture_video(...)`
- Incoming timestamp conversion
- `obs_source_output_audio(...)`
- `obs_source_output_video(...)`
- Receive-thread wait and sleep logic
- Audio sample accounting
- Video deadline accounting
- Reset and reconnect handling

For downstream confirmation, probe:

- OBS-selected source video
- Audio filter or mixer timing
- Source frame queueing
- OBS interpretation of submitted timestamps

---

## Final recommendation

The most useful pair of measurements is:

```text
DistroAV output video
versus
OBS-selected video
```

and:

```text
DistroAV output audio
versus
OBS mixer audio
```

Together, they reveal whether the apparent desync is caused by audio movement, video movement, both, or incoming timing being passed through.

The strongest diagnosis identifies:

1. The last boundary where timing remained stable
2. The first boundary where the relationship began changing
