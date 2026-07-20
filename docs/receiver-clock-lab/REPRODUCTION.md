# DistroAV Receiver Clock Fork — Reproduction and Validation

## Purpose

This document records the A/V drift problem, the experimental receiver-clock changes, and the validation results observed on the tested two-PC OBS/NDI setup.

The fork is based on DistroAV 6.2.1 and adds an experimental **Receiver-Paced** mode. The goal is to prevent long-term audio/video drift without PPM correction, periodic source resets, or gradual sync adjustments.

---

## Test setup

- Gaming PC sends 4K60 NDI.
- Stream PC receives the NDI feeds in OBS.
- OBS audio rate: 48 kHz.
- Tests used video, desktop audio, and microphone feeds in both combined and separate-source layouts.
- Diagnostics compared:
  - incoming NDI timing,
  - DistroAV-submitted audio/video timestamps,
  - OBS-filtered audio,
  - OBS-selected video,
  - FrameSync repeats and recovery,
  - NDI queue/drop statistics.

---

## Original failure

With stock DistroAV timing, audio and video advanced at slightly different effective rates.

### Stock test

- Duration: **60.775 minutes**
- Selected video minus filtered audio:
  - Start: **-54.893 ms**
  - End: **-164.433 ms**
- Total change: **-109.540 ms**
- Drift rate: **-1.802 ms/min**
- Equivalent clock error: **-30.040 ppm**

This closely matched the real-world observation of roughly **50 ms of drift every 25 minutes**.

The NDI Monitor application stayed visually current while the OBS preview could fall behind, indicating that at least part of the problem occurred inside the OBS/DistroAV receive and async-video path rather than in the sender or network alone.

---

## First fix: receiver-paced timestamps

The first fix stopped forwarding sender-derived timestamps as the final OBS timestamps.

Instead:

- audio timestamps were generated from cumulative delivered samples,
- video timestamps were generated from receiver video ticks,
- both were based on a local receiver monotonic clock,
- NDI FrameSync was used to select/resample media, not as the final timestamp authority.

### Receiver-paced validation

- Duration: **96.079 minutes**
- Selected video minus filtered audio:
  - Start: **-27.451 ms**
  - End: **-27.542 ms**
- Total change: **-0.090 ms**
- Drift rate: approximately **-0.00094 ms/min**
- Equivalent clock error: approximately **-0.016 ppm**

DistroAV output video minus output audio changed by only **-0.188 ms** over the same test, approximately **-0.002 ms/min**.

### Result

The original approximately **1.8–2.0 ms/min** drift was reduced to roughly **0.001 ms/min**, effectively zero within measurement noise.

---

## New issue exposed by the first fix

When video, desktop audio, and microphone were split into three separate NDI source instances, each source created its own receiver-clock epoch.

Each source was locally stable, but the independently created clocks did not remain aligned with one another.

### Separate-source test

Layout:

1. NDI video-only source
2. NDI desktop-audio-only source
3. NDI microphone-audio-only source

Observed behavior:

- video drifted approximately **4.6–5.2 ms/min** relative to both audio sources,
- desktop audio and microphone stayed aligned within a few microseconds,
- DistroAV-submitted video and OBS-selected video moved together,
- the selected-versus-submitted video gap stayed nearly constant,
- no growing downstream OBS gap was present during that sample.

This localized the new drift to the use of independent receiver-paced source clocks, not to the two audio streams or OBS's downstream video queue.

### Combined-source control test

When video and embedded desktop audio were received through one NDI source:

- video versus embedded desktop audio changed by only about **0.002 ms total** over roughly 4.8 minutes,
- the separate microphone also remained within approximately **0.1 ms**.

This supported the conclusion that the separate receiver-clock domains caused the new drift.

---

## Second fix: shared receiver timebase

All Receiver-Paced source instances were changed to share one process-wide receiver epoch.

The implementation also:

- preserved a single common monotonic time origin,
- joined newly created sources at the next valid audio block or video tick,
- avoided replaying historical ticks when a source joined later,
- used exact rational OBS frame-rate math instead of repeatedly adding a truncated nanosecond frame interval.

### Initial shared-clock test

- Duration: approximately **5.5 minutes**
- DistroAV output video versus desktop audio: about **+0.015 ms/min**
- DistroAV output video versus microphone: about **+0.012 ms/min**
- OBS-selected video versus desktop audio: about **+0.024 ms/min**
- OBS-selected video versus microphone: about **+0.020 ms/min**
- desktop audio versus microphone: effectively zero
- NDI video/audio drops: zero

This was already approximately **200–400 times smaller** than the previous 4.6–5.2 ms/min separate-source drift.

### Longer shared-clock test

- Duration: **26.5 minutes**
- Video versus desktop audio trend: approximately **+0.0007 ms/min**
- Video versus microphone trend: approximately **-0.0004 ms/min**
- Desktop audio versus microphone trend: approximately **-0.0011 ms/min**
- OBS-selected video versus audio: approximately **+0.002 to +0.003 ms/min**

The raw values moved by roughly 1–2 ms from sample to sample, but there was no sustained movement in one direction.

### Result

The separate-source drift fell from **4.6–5.2 ms/min** to values around **0.001 ms/min or less**, effectively eliminating it.

---

## Downstream OBS video-delay finding

A later approximately 108-minute test showed that DistroAV's submitted timestamps remained aligned, but OBS's selected video experienced a one-time downstream delay increase.

### Long test

- DistroAV output video versus desktop audio: approximately **-0.0012 ms/min**
- DistroAV output video versus microphone: approximately **+0.0025 ms/min**
- Audio sources remained aligned.
- Around **106.4 minutes**, the OBS-selected-video gap increased by approximately **350 ms**.
- Selected video remained roughly **381 ms behind** DistroAV-submitted video afterward.
- NDI reported zero dropped video/audio frames.
- FrameSync repeat debt returned to zero.

This localized the event to the OBS async-video selection/buffering path after DistroAV submitted correctly timed frames.

It also matched the original real-world observation that NDI Monitor stayed current while the OBS preview could gradually or suddenly fall behind.

---

## Third fix: unbuffered OBS video in Receiver-Paced mode

DistroAV's Lowest Latency setting already calls:

```cpp
obs_source_set_async_unbuffered(source, true);
```

Testing showed that this prevents OBS from retaining stale queued video after a disturbance.

The clock fork was therefore updated so **Receiver-Paced mode automatically uses unbuffered OBS async video**, regardless of the separately selected NDI decode/color-format latency option.

This keeps the newest available video frame instead of allowing an OBS-side backlog to accumulate.

---

## Lowest Latency validation

### Normal test

- Duration: **22.7 minutes**
- OBS selected-video delay stayed near **15.5 ms**
- Beginning: approximately **15.44 ms**
- End: approximately **15.63 ms**
- Trend: approximately **0.002 ms/min**
- Large persistent downstream jumps: zero
- Repeated frames: **41**
- Recovered repeats: **41**
- Final repeat debt: zero

No measurable OBS-preview drift developed relative to DistroAV's submitted video.

### Stress test

The stream PC was deliberately disturbed to provoke timing jumps.

- Duration: approximately **61.7 minutes**
- Normal downstream gap: approximately **15.4 ms**
- Trend: approximately **0.0025 ms/min**
- Largest observed temporary gap: approximately **30.6 ms**
- Recovery time: approximately **0.27 seconds**
- Permanent added delay: none
- Persistent jump events: zero
- Repeated frames: **582**
- Recovered repeats: **582**
- Final repeat debt: zero
- NDI-dropped video frames: zero

The 582 repeats occurred mainly in bursts during the stress portion, rather than at a constant rate. The largest sampled burst added eight repeats. All repeat debt was recovered.

### Result

Unbuffered mode changed the failure behavior from:

```text
system disturbance -> stale OBS video backlog -> permanent added delay
```

to:

```text
system disturbance -> brief repeat/drop activity -> return to normal delay
```

---

## Repeated-frame interpretation

A repeat means FrameSync returned the same underlying source-frame identity for more than one receiver video tick.

At 60 FPS, one repeated display interval is approximately **16.7 ms**.

These events may appear as a tiny hitch during smooth motion, but they did not:

- accumulate into A/V drift,
- create permanent video latency,
- leave unrecovered repeat debt,
- indicate hundreds of permanently lost frames.

The stress test produced many repeats because the receiver was deliberately disturbed. They appeared primarily in clusters and recovered afterward.

---

## Overall measured improvement

### Original stock behavior

- Approximately **1.8–2.0 ms/min** A/V drift
- Roughly **50 ms every 25 minutes**
- OBS preview could visibly fall behind NDI Monitor

### Receiver-paced, before shared clock

- Original within-source drift reduced to approximately **0.001 ms/min**
- Separate source instances then drifted by **4.6–5.2 ms/min**

### Shared receiver timebase

- Separate-source drift reduced to approximately **0.001 ms/min or less**
- Audio sources remained effectively locked

### Shared receiver timebase plus unbuffered OBS video

- OBS downstream delay stayed near **15.4–15.5 ms**
- Measured downstream slope: approximately **0.002–0.0025 ms/min**
- Deliberate disturbances recovered without permanent delay
- No persistent queue jump was observed during the stress test

---

## Conclusion

On the tested system, the final clock fork appears to solve both major sync failures:

1. **Long-term rate drift between NDI audio and video**
2. **OBS async-video backlog causing the preview and recording to fall behind**

The remaining known behavior is occasional FrameSync repeat activity, especially during system stalls. It can produce a one-frame micro-hitch, but all logged repeats recovered and did not create lasting A/V desynchronization.

The build remains experimental and should still be validated through additional long recordings and CI builds before production integration.
