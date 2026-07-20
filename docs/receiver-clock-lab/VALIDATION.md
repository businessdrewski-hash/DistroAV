# Receiver Clock Lab Validation Results

> **Test author:** Andrew Carriker  
> **Original test date:** July 19, 2026  
> **Final document update:** July 20, 2026  
> **Research repository:** https://github.com/businessdrewski-hash/DistroAV  
> **Research branch:** `receiver-clock-lab`  
> **Upstream repository:** https://github.com/DistroAV/DistroAV  
> **Stock base commit:** `038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8`  
> **Final research build:** DistroAV Receiver Clock Lab `6.2.1.2`

## Purpose

This document records the experiment history and validation evidence for the Receiver Clock Lab implementation.

For exact reproduction setup and measurement instructions, see [REPRODUCTION.md](REPRODUCTION.md).

For the final code architecture and integration map, see [IMPLEMENTATION.md](IMPLEMENTATION.md).

## Executive summary

The original system repeatedly accumulated approximately:

- **50 ms of A/V drift every 25 minutes**
- approximately **2 ms/minute**
- audio progressively ahead of video
- near-baseline sync again after the NDI receiver was rebuilt

A formal stock DistroAV control measured **-109.540 ms of movement over 60.775 minutes**, equivalent to **-1.8024 ms/minute** or **-30.040 ppm**.

The investigation identified and tested three receiver-side changes:

1. **Receiver-generated timestamps**  
   Audio and video timestamps delivered to OBS are generated from a receiver-owned monotonic timeline instead of remaining dependent on sender-derived timing.

2. **A shared process-wide receiver epoch**  
   Separate Receiver-Paced DistroAV source instances use one common clock domain instead of creating independent local clocks.

3. **Automatic unbuffered OBS async video**  
   Receiver-Paced mode enables `obs_source_set_async_unbuffered(..., true)` so a temporary OBS video backlog cannot become permanent added delay.

The strongest completed results were:

| Test | Duration | Result |
|---|---:|---|
| Stock Direct control | 60.775 min | **-1.8024 ms/min** drift |
| Receiver-Paced long test | 96.079 min | approximately **-0.0020 ms/min** at DistroAV output |
| Separate-source regression before shared epoch | ~14.5 min | approximately **4.6–5.2 ms/min** |
| Shared-epoch validation | 26.5 min | approximately **0.001 ms/min or less** at DistroAV output |
| Buffered downstream test | ~108 min | persistent approximately **350 ms** OBS-side step |
| Unbuffered normal test | 22.7 min | no persistent downstream jump |
| Unbuffered stress test | 61.7 min | largest disturbance recovered in approximately **0.27 seconds** |

On this tested system, the final build appears to solve both:

- long-term audio/video clock drift.
- persistent OBS-side asynchronous video backlog.

The remaining known behavior is occasional repeated FrameSync video imagery during timing disturbances. Every instrumented repeat recovered, final repeat debt returned to zero, and the repeats did not accumulate into lasting A/V desynchronization.

## 1. Measurement boundaries

The investigation separated three timing boundaries.

### 1.1 Incoming NDI capture relationship

Incoming NDI timestamp and timecode values describe the timing relationship presented to the receiver.

Movement here does not prove that the same movement reaches OBS output.

### 1.2 DistroAV output relationship

```text
output_video_minus_output_audio_projected_ns
```

This measures the timestamps DistroAV actually submits to OBS.

It was the primary metric for determining whether the receiver implementation propagated progressive drift.

### 1.3 Downstream OBS-selected relationship

```text
selected_video_minus_filtered_audio_projected_ns
```

This measures video selected by OBS's asynchronous video path against audio observed after the OBS audio filter/mixer boundary.

It allowed a fault after `obs_source_output_video(...)` to be separated from a fault already present at DistroAV output.

## 2. Formal stock DistroAV control

A long stock-control capture established the measured baseline.

- Duration: **60.775 minutes**
- Mode: Stock Direct
- Metric: `selected_video_minus_filtered_audio_projected_ns`
- Starting offset: **-54.893150 ms**
- Final offset: **-164.433400 ms**
- Total movement: **-109.540250 ms**
- Linear slope: **-30.040 ppm**
- Equivalent drift: **-1.8024 ms/minute**

This independently reproduced the original real-world estimate of approximately 50 ms every 25 minutes.

The relationship returned close to baseline after the receiver was rebuilt, which implicated accumulated receiver-side timing or buffering state rather than a permanent sender offset.

## 3. First implementation: source-local Receiver-Paced timestamps

The first experimental version used NDI FrameSync for media selection but generated final OBS timestamps from a receiver-owned monotonic schedule.

Each source maintained:

- a receiver-owned epoch based on `os_gettime_ns()`.
- the OBS audio sample rate.
- the OBS video FPS numerator and denominator.
- cumulative delivered audio frames.
- cumulative receiver video ticks.
- next audio and video deadlines.

Audio and video were pulled according to local receiver deadlines.

Late audio could use bounded catch-up pulls. Missed video ticks were advanced rather than retained as permanent scheduling debt.

This first implementation used one independent epoch per source instance.

## 4. Early Receiver-Paced validation

| Test | Duration | Drift expected from old behavior | Final DistroAV output offset | Measured slope |
|---|---:|---:|---:|---:|
| Test A | 4.4 min | ~8.8 ms | +0.28 ms | -0.003 ms/min |
| Test B | 16 min | ~32 ms | -0.39 ms | -0.0024 ms/min |
| Test C | 28.3 min | ~57 ms | -0.35 ms | -0.0014 ms/min |
| Test D | 96.079 min | ~192 ms | -0.214 ms | approximately -0.0020 ms/min |

These tests showed that receiver-generated output timestamps prevented the original approximately 2 ms/minute movement from propagating into DistroAV's OBS output when video and embedded desktop audio were received through the same source instance.

## 5. Formal 96-minute Receiver-Paced validation

### 5.1 DistroAV output boundary

- Duration: **96.079 minutes**
- Metric: `output_video_minus_output_audio_projected_ns`
- Starting offset: **-0.026388 ms**
- Final offset: **-0.214438 ms**
- Total movement: **-0.188050 ms**
- Approximate slope: **-0.0020 ms/minute**
- Median output offset: approximately **-0.110 ms**
- Approximate 90% range: **-1.163 ms to +1.062 ms**

### 5.2 Downstream selected-video boundary

- Metric: `selected_video_minus_filtered_audio_projected_ns`
- Starting offset: **-27.451104 ms**
- Final offset: **-27.541554 ms**
- Total movement: **-0.090450 ms**
- Linear slope: approximately **-0.00094 ms/minute**
- Equivalent rate difference: approximately **-0.016 ppm**

### 5.3 Additional counters

- Incoming capture relationship movement: approximately **+6.564 ms**
- Empty audio pulls: **0**
- Empty video pulls: **0**
- NDI-reported dropped audio frames: **0**
- NDI-reported dropped video frames: **0**
- Audio catch-ups: **0**
- Video catch-ups: **0**
- Repeated video frames: **262**
- Approximate repeat rate: one every **22 seconds**

### 5.4 Interpretation

The incoming capture relationship continued to move, but the timestamps delivered by DistroAV and selected by OBS remained essentially bounded for more than 96 minutes.

This was strong evidence that the receiver-paced output timeline prevented the original accumulating drift.

A near-zero final value alone would not have been sufficient. The important result was that incoming timing movement did not propagate into progressive output movement.

## 6. Separate-source clock-domain regression

The source-local Receiver-Paced implementation worked when video and embedded desktop audio came through one NDI source.

A new failure appeared when video, desktop audio, and microphone were represented by three separate DistroAV source instances.

### 6.1 Test layout

1. NDI video-only source.
2. NDI desktop-audio-only source.
3. NDI microphone-audio-only source.

### 6.2 Result

Over approximately **14.5 minutes**:

- video moved approximately **66–76 ms** relative to both audio sources.
- equivalent slope: approximately **4.6–5.2 ms/minute**.
- desktop audio and microphone stayed aligned within approximately **0.003 ms**.
- DistroAV-submitted video and OBS-selected video moved together.
- selected-video-minus-submitted-video gap stayed near **22.6 ms**.
- the downstream gap changed by only approximately **0.001 ms**.
- downstream OBS jump events: **0**.
- NDI-reported dropped frames: **0**.
- repeat debt recovered to zero.

### 6.3 Localization

Both audio sources remained aligned while video moved relative to both.

DistroAV-submitted video and OBS-selected video moved together while their separation remained constant.

The new error was therefore already present at the DistroAV video-submission boundary. It was not caused by either audio source or by an accumulating downstream OBS queue.

The source-local implementation had created independent Receiver-Paced clock domains across separate source instances.

## 7. Combined-source control

A control layout used:

1. one NDI source containing video plus embedded desktop audio.
2. one separate NDI microphone source.

Over approximately **4.7–4.9 minutes**:

- video versus embedded desktop audio stayed near zero.
- video/desktop versus the separate microphone remained below approximately **0.1 ms**.
- the previous **4.6–5.2 ms/minute** video movement did not appear.

This confirmed that the regression was caused by independent Receiver-Paced source clocks rather than the microphone, desktop audio, sender, network, or OBS downstream video selection.

## 8. Final clock design: shared process-wide epoch

All Receiver-Paced source instances were changed to use one process-wide monotonic epoch.

Each source continued to own its own:

- NDI receiver.
- NDI FrameSync instance.
- audio sample count.
- video tick count.
- media-selection state.
- local deadlines.

All generated OBS timestamps, however, existed in one common clock domain.

The first Receiver-Paced source established the epoch with a short startup lead based on `os_gettime_ns()`.

A source created or rebuilt later joined at the next complete audio block or video tick at or after current receiver time plus that startup lead.

Rebuilding one source no longer created an unrelated new clock domain while other Receiver-Paced sources remained active.

Exact rational video timing was retained so rates such as 60000/1001 would not accumulate truncated integer interval error.

## 9. Shared-clock validation

### 9.1 Initial shared-clock test

- Duration: approximately **5.5 minutes**
- Shared epoch reported by all three sources: **55033763614600 ns**
- DistroAV output video versus desktop audio: approximately **+0.015 ms/minute**
- DistroAV output video versus microphone: approximately **+0.012 ms/minute**
- OBS-selected video versus desktop audio: approximately **+0.024 ms/minute**
- OBS-selected video versus microphone: approximately **+0.020 ms/minute**
- Desktop audio versus microphone: effectively zero
- Repeated frames: **21**
- Recovered repeats: **21**
- Final repeat debt: **0**
- NDI-reported dropped frames: **0**

This reduced the previous 4.6–5.2 ms/minute regression by roughly two orders of magnitude.

### 9.2 26.5-minute shared-clock test

- DistroAV output video versus desktop audio: approximately **+0.0007 ms/minute**
- DistroAV output video versus microphone: approximately **-0.0004 ms/minute**
- Desktop audio versus microphone: approximately **-0.0011 ms/minute**
- OBS-selected video versus audio: approximately **+0.002 to +0.003 ms/minute**
- Repeated frames: **93**
- Recovered repeats: **93**
- Final repeat debt: **0**
- NDI-reported dropped frames: **0**

The raw offsets moved slightly from sample to sample, but no sustained movement comparable to the earlier 4.6–5.2 ms/minute regression remained.

### 9.3 Result

The shared epoch corrected the separate-source clock-domain problem.

Video, desktop audio, and microphone could remain separate DistroAV source instances while participating in one receiver-owned OBS timeline.

## 10. Long buffered test: downstream OBS video jump

A later long run showed that DistroAV's submitted audio and video remained aligned while OBS-selected video experienced a one-time persistent delay increase.

### 10.1 First 106.4 minutes

- OBS-selected video remained approximately **30–31 ms** behind DistroAV-submitted video.
- the downstream gap was stable.
- DistroAV output video versus desktop audio: approximately **-0.0012 ms/minute**.
- DistroAV output video versus microphone: approximately **+0.0025 ms/minute**.
- desktop audio and microphone remained aligned.
- repeat debt returned to zero.
- NDI-reported dropped frames remained zero.

### 10.2 Jump event

At approximately **106.4 minutes**:

- OBS-selected video suddenly moved approximately **350 ms** farther behind.
- selected video then remained approximately **381 ms behind** DistroAV-submitted video.
- DistroAV's direct output boundary did not show a matching A/V jump.
- repeat debt returned to zero.
- NDI-reported drop counters did not explain the persistent step.

### 10.3 Localization

The permanent step occurred after `obs_source_output_video(...)`, inside OBS's asynchronous video buffering and selection path.

This matched the practical observation that the NDI feed could remain current outside OBS while the OBS preview and recording path fell behind.

## 11. Automatic unbuffered OBS async video

DistroAV's Lowest Latency setting already enabled:

```cpp
obs_source_set_async_unbuffered(obs_source, true);
```

Testing indicated that this prevented OBS from preserving a stale queue of asynchronous video frames after a receiver disturbance.

Receiver-Paced mode was updated to enable OBS async-video unbuffering automatically, independently of the NDI decode/color-format latency choice.

Expected failure behavior changed from:

```text
receiver disturbance
→ stale OBS video backlog
→ permanent added delay
```

to:

```text
receiver disturbance
→ temporary repeat/drop activity
→ return to normal delay
```

## 12. Unbuffered validation

### 12.1 22.7-minute normal test

- Duration: **22.7 minutes**
- Downstream selected-video gap at start: approximately **15.44 ms**
- Downstream selected-video gap at end: approximately **15.63 ms**
- Long-term trend: approximately **+0.002 ms/minute**
- Large persistent downstream jumps: **0**
- Repeated frames: **41**
- Recovered repeats: **41**
- Final repeat debt: **0**

No measurable OBS-selected-video drift developed relative to DistroAV-submitted video.

### 12.2 61.7-minute stress test

The receiver was deliberately disturbed during the final portion of the run.

- Total duration: approximately **61.7 minutes**
- Normal downstream selected-video gap: approximately **15.4 ms**
- Long-term trend: approximately **+0.0025 ms/minute**
- Largest temporary disturbance:
  - time: approximately **54.82 minutes**
  - peak gap: approximately **30.6 ms**
  - recovery time: approximately **0.27 seconds**
- Permanent added delay: **0**
- Persistent downstream jump events: **0**
- Repeated frames: **582**
- Recovered repeats: **582**
- Final repeat debt: **0**
- NDI-reported dropped video frames: **0**

The repeats were concentrated during deliberate stress and occurred in bursts rather than at a constant rate.

Diagnostic samples commonly showed bursts of three to six repeats, with a maximum sampled burst of eight.

### 12.3 Result

Unbuffered async video prevented receiver disturbances from becoming permanent OBS-side latency in these completed tests.

## 13. Sender-overload control

The sender was deliberately overloaded at 4K using NVENC P7.

Observed stress:

- OBS rendering lag: approximately **10.4%**
- OBS encoding lag: approximately **18.1%**
- hundreds of sender-side frame losses

Despite the overload, A/V timing recovered afterward.

This falsified the simpler theory that every missing sender frame necessarily creates one permanent frame of receiver-side A/V delay.

## 14. Repeated-frame interpretation

A repeated FrameSync image means the same underlying NDI video identity was returned for more than one receiver video tick.

At 60 FPS:

```text
one display interval ≈ 16.7 ms
```

A repeat can therefore appear as a brief motion hitch.

In the completed tests, repeats did not:

- accumulate into long-term A/V drift.
- leave unrecovered repeat debt.
- create permanent downstream video latency.
- correspond one-for-one with permanently lost sender frames.

The 582-repeat stress result should not be interpreted as 582 permanently lost video frames.

The repeats were mostly clustered during deliberate disturbances, and every logged repeat was later matched by recovered source-frame advancement.

This remains a motion-smoothness issue worth improving, but it is separate from the resolved accumulating A/V-sync problem.

## 15. Complete validation summary

| Test | Mode | Duration | Primary result |
|---|---|---:|---|
| Early Test A | Receiver-Paced | 4.4 min | +0.28 ms final output offset; -0.003 ms/min |
| Early Test B | Receiver-Paced | 16 min | -0.39 ms final output offset; -0.0024 ms/min |
| Early Test C | Receiver-Paced | 28.3 min | -0.35 ms final output offset; -0.0014 ms/min |
| Stock control | Stock Direct | 60.775 min | -109.540 ms movement; -1.8024 ms/min |
| Receiver-Paced long test | Source-local Receiver-Paced | 96.079 min | -0.188 ms DistroAV output movement; ~-0.0020 ms/min |
| Separate-source regression | Independent source-local clocks | ~14.5 min | video moved ~4.6–5.2 ms/min relative to both audio sources |
| Combined-source control | Video + embedded desktop audio | ~4.8 min | combined video/audio near zero; separate mic within ~0.1 ms |
| Initial shared-clock test | Shared Receiver-Paced epoch | ~5.5 min | common epoch confirmed; large regression removed |
| Shared-clock validation | Shared Receiver-Paced epoch | 26.5 min | DistroAV output relationships ~0.001 ms/min or less |
| Buffered downstream test | Shared clock, buffered OBS video | ~108 min | one persistent ~350 ms downstream jump after ~106.4 min |
| Unbuffered normal test | Shared clock + unbuffered video | 22.7 min | gap stayed near 15.5 ms; no persistent jump |
| Unbuffered stress test | Shared clock + unbuffered video | 61.7 min | largest disturbance recovered in ~0.27 s; no permanent delay |
| Sender-overload control | 4K NVENC P7 overload | stress segment | timing recovered despite rendering/encoding losses |

## 16. Final pass criteria

The final receiver-clock implementation is considered successful when:

- stock behavior reproduces a sustained multi-millisecond-per-minute slope.
- Receiver-Paced output timing remains bounded around its starting relationship.
- direct DistroAV output drift remains below **±0.05 ms/minute**.
- separate Receiver-Paced source instances use one shared epoch.
- separate video, desktop-audio, and microphone sources remain aligned.
- OBS-selected video does not acquire a persistent downstream step after a disturbance.
- repeat debt returns to zero.
- unexplained NDI drop counters do not increase.
- source reconstruction cleanly rejoins the shared timeline.
- a long recording remains visibly synchronized against an external reference.

The completed stock, 96-minute, shared-clock, unbuffered, and stress tests met the timing-related criteria in this environment.

## 17. Known limitations

The completed tests do not yet prove:

- correct behavior at every supported frame rate.
- correct behavior at sample rates other than 48 kHz.
- correct behavior on macOS or Linux.
- correct behavior with every NDI bandwidth and color-format setting.
- correct behavior under every GPU, CPU, network, or OBS overload scenario.
- whether OBS async-video unbuffering should become the upstream default for this mode.
- whether the shared epoch should ultimately be process-wide, OBS-instance-wide, sender-keyed, or owned by a formal synchronization service.
- whether repeat frequency can be reduced further without compromising clock stability.

The implementation remains experimental until it receives clean CI results, additional independent long recordings, and maintainer review.

## 18. Final conclusion

The original setup repeatedly accumulated approximately **50 ms of A/V drift every 25 minutes**.

A formal stock capture measured **-109.540 ms over 60.775 minutes**, equivalent to approximately **-1.8024 ms/minute**.

The first Receiver-Paced implementation reduced the original output drift to approximately **-0.0020 ms/minute over 96.079 minutes**.

That implementation then exposed a new **4.6–5.2 ms/minute** disagreement when separate source instances used independent local receiver clocks.

Changing all Receiver-Paced source instances to one shared process-wide epoch reduced the separate-source movement to approximately **0.001 ms/minute or less** at the DistroAV output boundary.

A later approximately 108-minute test localized one persistent approximately **350 ms** step to OBS's asynchronous video path after DistroAV had already submitted correctly timed video.

Automatically enabling unbuffered OBS async video for Receiver-Paced mode prevented that failure in subsequent completed tests.

During the 61.7-minute stress run, the largest temporary delay recovered in approximately **0.27 seconds** and left no permanent added latency.

On this system, the final combination of:

- receiver-generated audio and video timestamps.
- one shared receiver epoch.
- exact rational video timing.
- bounded deadline catch-up.
- NDI FrameSync for media selection.
- automatic unbuffered OBS async video.

appears to solve both the long-term A/V rate drift and the persistent OBS-side video-backlog problem.

The remaining known issue is occasional repeated video imagery during timing disturbances. It may create a brief one-frame motion hitch, but every logged repeat recovered, final repeat debt returned to zero, and no completed test showed repeats accumulating into lasting A/V desynchronization.
