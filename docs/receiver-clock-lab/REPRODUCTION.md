# DistroAV Receiver A/V Drift Reproduction and Validation

> **Status:** Experimental reproduction and validation document  
> **Purpose:** Provide a repeatable method for reproducing long-term A/V drift in DistroAV, measuring it objectively, and validating a receiver-paced timing fix.  
> **Last updated:** 2026-07-20  
> **Test author:** [FILL IN: NAME / GITHUB USERNAME]  
> **Repository / branch:** `businessdrewski-hash/DistroAV`, research branch `receiver-clock-lab`; reduced branch `receiver-clock-minimal`

---

## 1. Summary

This document records the complete reproduction and validation history for progressive A/V desynchronization in a two-PC OBS setup using DistroAV as the NDI receiver.

The original affected configuration accumulated approximately:

- **50 ms of A/V drift every 25 minutes**
- approximately **2 ms/minute**
- audio progressively ahead of video
- sync returned close to baseline when the NDI receiver was rebuilt

A formal stock-control capture later measured **-109.540 ms of end-to-end movement over 60.775 minutes**, equivalent to **-1.802 ms/minute** or approximately **-30.040 ppm**.

The investigation produced three related receiver-side changes:

1. **Receiver-paced timestamps:** audio and video timestamps are generated from one receiver-owned monotonic timeline rather than allowing sender-derived timing to remain authoritative at the OBS output boundary.
2. **Shared process-wide receiver epoch:** separate Receiver-Paced NDI source instances join one common clock domain rather than creating independent source-local clocks.
3. **Unbuffered OBS async video:** Receiver-Paced mode automatically enables `obs_source_set_async_unbuffered(..., true)` so an OBS-side video backlog cannot become a permanent delay after a stall.

The strongest completed results were:

- Stock control: **-1.802 ms/minute**
- 96.079-minute Receiver-Paced test: approximately **-0.00094 ms/minute**
- Separate-source failure before shared epoch: approximately **4.6–5.2 ms/minute**
- 26.5-minute shared-epoch test: approximately **0.001 ms/minute or less** at the DistroAV output boundary
- 22.7-minute unbuffered test: downstream OBS video delay stayed near **15.5 ms**, with no persistent jump
- 61.7-minute stress test: the largest disturbance recovered in approximately **0.27 seconds** and added no permanent delay

The remaining observed issue is occasional repeated FrameSync video images during receiver disturbances. Every instrumented repeat recovered, final repeat debt returned to zero, and the repeats did not accumulate into lasting A/V desynchronization.

---

## 2. Scope

This document covers:

1. The hardware and software environment.
2. The exact OBS and DistroAV configuration.
3. The steps used to reproduce the original progressive drift.
4. The measurements used to distinguish incoming NDI timing from DistroAV output timing.
5. The receiver-paced implementation used for the validation test.
6. The acceptance criteria used to determine whether the fix worked.

This document does **not** attempt to resolve occasional repeated video frames returned by NDI FrameSync. That behavior is being tracked separately and does not change the long-term A/V drift conclusion.

---

## 3. Test Topology

```text
[Gaming / Sender PC]
        |
        | NDI over Ethernet
        v
[Streaming / Receiver PC]
        |
        v
[DistroAV NDI Source in OBS]
        |
        v
[OBS preview / recording / stream output]
```

### Network path

- Connection type: [FILL IN: DIRECT ETHERNET / SWITCH / ROUTER]
- Link speed: [FILL IN: 1 GbE / 2.5 GbE / 10 GbE]
- Switch/router model: [FILL IN]
- Sender NIC model: [FILL IN]
- Receiver NIC model: [FILL IN]
- Jumbo frames: [FILL IN: ENABLED / DISABLED]
- Energy-efficient Ethernet: [FILL IN: ENABLED / DISABLED]
- Other notable network settings: [FILL IN]

---

## 4. Hardware

### Gaming / Sender PC

- CPU: [FILL IN]
- GPU: [FILL IN]
- RAM: [FILL IN]
- Motherboard: [FILL IN]
- Operating system and build: [FILL IN]
- Audio interface/device: [FILL IN]
- Audio device sample rate: [FILL IN]
- Display refresh rate: [FILL IN]
- Other relevant hardware: [FILL IN]

### Streaming / Receiver PC

- CPU: [FILL IN]
- GPU: [FILL IN]
- RAM: [FILL IN]
- Motherboard: [FILL IN]
- Operating system and build: [FILL IN]
- Audio interface/device: [FILL IN]
- OBS audio device sample rate: [FILL IN]
- Other relevant hardware: [FILL IN]

---

## 5. Software Versions

### Sender

- OBS Studio version: [FILL IN]
- DistroAV version / commit: [FILL IN]
- NDI Runtime version: [FILL IN]
- GPU driver version: [FILL IN]
- Relevant OBS plugins: [FILL IN]

### Receiver

- OBS Studio version: [FILL IN]
- DistroAV version / commit: [FILL IN]
- Receiver Clock Lab commit: [FILL IN]
- NDI Runtime version: [FILL IN]
- GPU driver version: [FILL IN]
- Relevant OBS plugins: [FILL IN]

### Build information

- Build method: [FILL IN: GITHUB ACTIONS / LOCAL CMAKE / OTHER]
- Compiler and version: [FILL IN]
- Build type: [FILL IN: RELEASE / RELWITHDEBINFO / DEBUG]
- Installer or portable build: [FILL IN]
- Exact DLL path used by OBS: [FILL IN]

---

## 6. OBS Configuration

### Sender OBS video settings

- Base canvas resolution: [FILL IN]
- Output resolution: [FILL IN]
- FPS numerator / denominator: [FILL IN, EXAMPLE: 60/1]
- Color format: [FILL IN]
- Color space: [FILL IN]
- Color range: [FILL IN]
- HDR or SDR: [FILL IN]
- Renderer: [FILL IN]
- Hardware acceleration settings: [FILL IN]

### Sender OBS audio settings

- OBS sample rate: [FILL IN, EXPECTED: 48 kHz]
- Channel layout: [FILL IN]
- Desktop audio device: [FILL IN]
- Microphone device: [FILL IN]
- Monitoring device: [FILL IN]
- Sync offsets configured in Advanced Audio Properties: [FILL IN]
- Audio filters: [FILL IN]

### Receiver OBS video settings

- Base canvas resolution: [FILL IN]
- Output resolution: [FILL IN]
- FPS numerator / denominator: [FILL IN, EXAMPLE: 60/1]
- Color format: [FILL IN]
- Color space: [FILL IN]
- Color range: [FILL IN]
- Renderer: [FILL IN]

### Receiver OBS audio settings

- OBS sample rate: [FILL IN, EXPECTED: 48 kHz]
- Channel layout: [FILL IN]
- Monitoring device: [FILL IN]
- Sync offsets configured in Advanced Audio Properties: [FILL IN]
- Audio filters: [FILL IN]

### Output used during the test

- OBS preview enabled: [FILL IN: YES / NO]
- Recording enabled: [FILL IN: YES / NO]
- Streaming enabled: [FILL IN: YES / NO]
- Encoder: [FILL IN]
- Rate control and quality settings: [FILL IN]
- Recording format: [FILL IN]
- Output resolution and FPS: [FILL IN]

---

## 7. NDI / DistroAV Configuration

### Sender output

- NDI output method: [FILL IN]
- NDI source name: [FILL IN]
- Bandwidth mode: [FILL IN]
- Video format: [FILL IN]
- Audio embedded with video: [FILL IN: YES / NO]
- Number of audio channels: [FILL IN]
- NDI groups: [FILL IN]
- Hardware acceleration: [FILL IN]
- Other sender options: [FILL IN]

### Receiver source

- DistroAV source name in OBS: [FILL IN]
- Selected NDI source: [FILL IN]
- Bandwidth mode: [FILL IN]
- Sync mode used for baseline: [FILL IN]
- Sync mode used for receiver-paced validation: **Receiver-Paced / OBS-Paced**
- Audio enabled: [FILL IN]
- Latency mode: [FILL IN]
- Hardware acceleration: [FILL IN]
- Other receiver options: [FILL IN]

---

## 8. Original Failure Behavior

### Initial condition

After fully restarting or rebuilding the NDI receiver:

- Initial perceived A/V offset: [FILL IN]
- Initial measured A/V offset: [FILL IN]
- Time allowed for stabilization before measurement: [FILL IN]

### Progressive failure

Previously observed behavior:

- Approximate drift: **~50 ms every ~25 minutes**
- Approximate drift rate: **~2 ms/minute**
- Direction of drift: [FILL IN: AUDIO EARLY / AUDIO LATE / VIDEO EARLY / VIDEO LATE]
- Whether the offset reset after restarting the NDI receiver: [FILL IN]
- Whether the offset reset after restarting OBS: [FILL IN]
- Whether the issue appeared in OBS preview: [FILL IN]
- Whether the issue appeared in OBS recordings: [FILL IN]
- Whether the issue appeared in NDI Studio Monitor: [FILL IN]
- Other repeatable observations: [FILL IN]

### Known variables already tested

Mark each item and describe the result.

- [ ] FrameSync enabled versus disabled  
  Result: [FILL IN]

- [ ] Hardware acceleration enabled versus disabled  
  Result: [FILL IN]

- [ ] Both systems set to 48 kHz  
  Result: [FILL IN]

- [ ] Different video resolutions or bandwidth modes  
  Result: [FILL IN]

- [ ] Recording enabled versus preview-only  
  Result: [FILL IN]

- [ ] Encoder load / encoding overload  
  Result: [FILL IN]

- [ ] Direct network connection versus network switch  
  Result: [FILL IN]

- [ ] Other: [FILL IN]  
  Result: [FILL IN]

---

## 9. Diagnostic Measurements

The Receiver Clock Lab records timing at several stages so that incoming NDI timing can be distinguished from the timestamps DistroAV ultimately delivers to OBS.

### Primary measurements

1. **Incoming NDI video minus incoming NDI audio**
   - Shows the relationship between timing arriving from the NDI receive path.
   - CSV field(s): [FILL IN EXACT COLUMN NAMES]

2. **DistroAV output video minus DistroAV output audio**
   - Shows the relationship between the timestamps DistroAV sends into OBS.
   - Primary field:
     - `output_video_minus_output_audio_projected_ns`

3. **Selected video minus filtered audio**
   - Shows a downstream comparison through the diagnostic probes.
   - Primary field:
     - `selected_video_minus_filtered_audio_projected_ns`

4. **Drift slope**
   - Calculated as the change in offset over elapsed time.
   - Reported in milliseconds per minute.
   - Analysis command or script: [FILL IN]

### Supporting measurements

- Receiver rebuild/reset events
- Empty audio pulls
- Empty video pulls
- Repeated video frames
- NDI-reported dropped audio frames
- NDI-reported dropped video frames
- Audio samples delivered
- Video ticks delivered
- Scheduler lateness / catch-up events
- [FILL IN OTHER RELEVANT COLUMNS]

### CSV location

Default live log directory:

```text
%APPDATA%\obs-studio\plugin_config\distroav\
```

Expected filename format:

```text
receiver-clock-lab-<source-id>.csv
```

Exact path used for these tests:

```text
[FILL IN]
```

---

## 10. Baseline Reproduction Procedure

Use this procedure with the existing or stock receive behavior.

1. Close OBS completely on both systems.
2. Confirm both OBS installations are configured with the intended sample rate.
3. Confirm the sender and receiver use the settings documented above.
4. Start OBS on the sender.
5. Start the NDI output.
6. Start OBS on the receiver.
7. Add or enable the DistroAV NDI source.
8. Select the baseline synchronization mode:
   - [FILL IN]
9. Fully rebuild or reset the NDI receiver.
10. Start Receiver Clock Lab logging.
11. Allow the source to stabilize for:
    - [FILL IN: SECONDS / MINUTES]
12. Create a clear synchronization reference:
    - [FILL IN: CLAP / FRAME-ACCURATE TEST VIDEO / FLASH AND TONE / OTHER]
13. Record the initial measured offset.
14. Leave the source running without resetting it for at least:
    - [FILL IN: RECOMMENDED 30–60 MINUTES]
15. At regular intervals, record:
    - Elapsed time
    - Perceived A/V offset
    - Measured output A/V offset
    - Drift slope
    - Dropped/empty pull counters
16. Export the CSV.
17. Save the OBS log from both systems.
18. Record whether restarting only the receiver returns synchronization to the initial state.

### Baseline acceptance result

The issue is considered reproduced when:

- The output A/V offset moves consistently away from its starting value.
- The movement is large enough to exceed normal callback jitter.
- The measured slope remains directionally consistent over time.
- A receiver reset or rebuild returns the source near its initial offset.

Baseline result:

```text
[FILL IN]
```

---

## 11. Receiver-Paced Implementation

The experimental implementation is primarily located in:

```text
src/ndi-source.cpp
```

### Core design

The receiver creates one local scheduling state containing:

- One receiver-owned epoch in `os_gettime_ns()` time.
- The OBS audio sample rate.
- The OBS video frame interval.
- The cumulative number of audio samples delivered.
- The cumulative number of receiver video ticks.

Audio and video timestamps are generated from that same epoch.

Conceptually:

```text
audio timestamp =
    receiver epoch
    + duration of all delivered audio samples

video timestamp =
    receiver epoch
    + duration of all elapsed OBS video ticks
```

### Scheduling behavior

- Audio is pulled according to receiver audio deadlines.
- The number of requested audio samples is derived from the OBS sample rate and elapsed scheduling time.
- Late audio pulls use bounded catch-up rather than allowing lateness to accumulate indefinitely.
- Video is pulled according to the OBS video interval.
- If the receiver misses one or more video deadlines, missed ticks are skipped so the scheduler does not remain permanently late.
- The shared receiver epoch is reset whenever the NDI receiver / FrameSync instance is rebuilt.

### Timestamp override

The media-processing functions accept an optional receiver-generated timestamp.

Relevant functions:

```text
ndi_source_thread_process_audio3(...)
ndi_source_thread_process_video2(...)
```

When Receiver-Paced mode is active, the locally generated timestamp is assigned to the OBS audio or video frame. In the comparison/reference modes, the original source timestamp remains in use.

### Exact commit / diff

- Branch: [FILL IN]
- Commit: [FILL IN]
- Comparison URL: [FILL IN]
- Main changed file(s): [FILL IN]
- Approximate synchronization-specific line count: [FILL IN]
- Approximate diagnostics-only line count: [FILL IN]

---

## 12. Receiver-Paced Validation Procedure

1. Close OBS completely on the receiver.
2. Install the Receiver Clock Lab build.
3. Confirm the expected `distroav.dll` is loaded from:
   - [FILL IN]
4. Start OBS on the sender and enable the NDI output.
5. Start OBS on the receiver.
6. Select the same NDI source and all settings used during the baseline test.
7. Select:
   - **Receiver-Paced / OBS-Paced**
8. Fully rebuild or reset the NDI receiver.
9. Start Receiver Clock Lab logging.
10. Allow the source to stabilize for:
    - [FILL IN]
11. Run the same synchronization reference used for the baseline.
12. Leave the test uninterrupted for at least:
    - [FILL IN: 30 MINUTES OR LONGER]
13. Do not manually reset, deactivate, or recreate the NDI source during the run.
14. Export the CSV.
15. Save the OBS logs from both systems.
16. Analyze:
    - Final output A/V offset
    - Median output A/V offset
    - 5th and 95th percentile output offsets
    - Drift slope in ms/minute
    - Empty pull counters
    - NDI drop counters
    - Receiver reset/rebuild events

---

## 13. Completed Validation Results

### Test A

- Duration: **approximately 4.4 minutes**
- Final output A/V offset: **approximately +0.28 ms**
- Median output offset: **approximately -0.05 ms**
- Measured output drift: **approximately -0.003 ms/minute**
- Result: Short confirmation that receiver output remained centered around zero.

### Test B

- Duration: **approximately 16 minutes**
- Final output A/V offset: **approximately -0.39 ms**
- Median output offset: **approximately -0.06 ms**
- Measured output drift: **approximately -0.0024 ms/minute**
- Empty pulls: **0**
- NDI-reported drops: **0**
- Result: The old drift would already have been visible, but no accumulating output offset appeared.

### Test C

- Duration: **approximately 28.3 minutes**
- Drift expected from previous behavior: **approximately 57 ms**
- Final output A/V offset: **approximately -0.35 ms**
- Median output offset: **approximately -0.07 ms**
- Approximate 90% range: **-1.19 ms to +1.01 ms**
- Measured output drift: **approximately -0.0014 ms/minute**
- Empty audio pulls: **0**
- Empty video pulls: **0**
- NDI-reported dropped audio frames: **0**
- NDI-reported dropped video frames: **0**
- Result: Conclusive pass for the accumulating A/V drift problem.

### Comparison table

| Test | Mode | Duration | Expected/previous drift | Final output offset | Measured slope |
|---|---|---:|---:|---:|---:|
| Baseline | [FILL IN] | [FILL IN] | ~50 ms per 25 min observed | [FILL IN] | ~2 ms/min |
| Test A | Receiver-Paced | 4.4 min | ~8.8 ms expected | +0.28 ms | -0.003 ms/min |
| Test B | Receiver-Paced | 16 min | ~32 ms expected | -0.39 ms | -0.0024 ms/min |
| Test C | Receiver-Paced | 28.3 min | ~57 ms expected | -0.35 ms | -0.0014 ms/min |

---

## 14. Pass / Fail Criteria

The receiver-paced implementation is considered successful when all of the following are true:

- The DistroAV output A/V offset remains bounded around its initial value.
- The output offset does not show the previous consistent multi-millisecond-per-minute slope.
- The final output offset remains within:
  - [FILL IN, SUGGESTED: ±2 ms]
- The measured drift slope remains below:
  - [FILL IN, SUGGESTED: ±0.05 ms/minute]
- No recurring empty audio or video pulls occur.
- No unexplained NDI drop counters increase.
- Receiver rebuilds reset the local epoch cleanly.
- Incoming NDI timing may vary without causing the output timing delivered to OBS to drift.

The completed 28.3-minute test met these criteria.

---

## 15. Interpretation

The successful test does not show that the incoming NDI audio and video timestamps are always identical. Instead, it shows that the receiver can prevent disagreement between sender timing, receiver timing, audio cadence, and video cadence from becoming progressive A/V drift inside OBS.

NDI FrameSync remains responsible for selecting or resampling the appropriate media. The receiver-paced scheduler determines when the selected audio and video exist on the OBS timeline.

The important proof point is:

> The incoming timing could still show an offset or variation, while the timestamps DistroAV delivered to OBS remained centered around zero with effectively no measurable drift.

This indicates that the original progressive desynchronization was caused by clock-domain handling in the receive-to-OBS timing path, rather than by a one-time static offset alone.

---

## 16. Known Limitations and Deferred Work

### Repeated video frames

The current receiver-paced implementation occasionally receives the same video image from NDI FrameSync on consecutive OBS ticks.

Latest observed result:

- Repeated video frames: **83**
- Test duration: **28.3 minutes**
- Approximate rate: **one repeated frame every 20 seconds**

This is being treated as a separate video-pacing quality issue. It did not cause the measured output A/V offset to drift and is intentionally outside the scope of this reproduction document.

### Diagnostic probe limitations

Some diagnostic callback anomaly counters may over-count expected high-frequency callback behavior. These counters should not be interpreted as visible failures without correlation to actual empty pulls, dropped frames, timestamp discontinuities, or recorded output.

### Additional tests recommended

- [ ] 60-minute uninterrupted validation
- [ ] 120-minute uninterrupted validation
- [ ] Multiple OBS FPS values
- [ ] 59.94 FPS validation
- [ ] Different OBS audio block/callback conditions
- [ ] Receiver source deactivate/reactivate
- [ ] NDI sender restart during an active receiver session
- [ ] Network interruption and recovery
- [ ] Different NDI bandwidth modes
- [ ] Different sender and receiver hardware
- [ ] Multiple simultaneous NDI sources
- [ ] Recording and streaming under heavy GPU/encoder load

---

## 17. Files to Attach

Attach the following to any issue, discussion, or pull request:

- [ ] This `REPRODUCTION.md`
- [ ] Baseline CSV
- [ ] Receiver-Paced Test A CSV
- [ ] Receiver-Paced Test B CSV
- [ ] Receiver-Paced Test C CSV
- [ ] Sender OBS log
- [ ] Receiver OBS log
- [ ] Crash log, if relevant
- [ ] Exact minimal source diff
- [ ] Screenshots of sender settings
- [ ] Screenshots of receiver settings
- [ ] Analysis script and command
- [ ] Short sample recording showing the original drift
- [ ] Short sample recording showing the receiver-paced result

File links:

- Baseline CSV: [FILL IN]
- Test A CSV: [FILL IN]
- Test B CSV: [FILL IN]
- Test C CSV: [FILL IN]
- Sender OBS log: [FILL IN]
- Receiver OBS log: [FILL IN]
- Minimal patch / commit: [FILL IN]

---

## 18. Initial AI Prompts and Development History

The following section is included to document how the experiment was directed and to make the development process easier to audit.

### Initial problem statement

```text
[FILL IN OR PASTE THE INITIAL PROMPT]
```

### Prompt used to request drift measurement

```text
[FILL IN OR PASTE PROMPT]
```

### Prompt used to isolate clock domains

```text
[FILL IN OR PASTE PROMPT]
```

### Prompt used to create the receiver-paced experiment

```text
[FILL IN OR PASTE PROMPT]
```

### Prompt used to add CSV diagnostics

```text
[FILL IN OR PASTE PROMPT]
```

### Human-directed constraints and corrections

Examples of important constraints provided during development:

- [FILL IN]
- [FILL IN]
- [FILL IN]

### Manual validation performed

- Code paths manually reviewed: [FILL IN]
- Builds manually installed and tested: [FILL IN]
- Results independently verified by: [FILL IN]
- Known unreviewed areas: [FILL IN]

---

## 19. Questions for DistroAV Maintainers

1. Does the clock-domain interpretation match the intended behavior of DistroAV’s current NDI FrameSync receive path?
2. Should receiver-paced timing be implemented as:
   - A new synchronization mode,
   - A replacement for the current FrameSync path, or
   - An internal behavior selected automatically?
3. Which existing DistroAV abstractions should own the receiver clock scheduler?
4. Should the OBS output timestamps be entirely receiver-generated in this mode, or should any NDI timing metadata remain authoritative?
5. What test coverage would be required for an upstream implementation?
6. Would the drift fields documented here fit into the planned DistroAV networking report?
7. What minimal diagnostics should remain in production builds?
8. Are there known NDI FrameSync timing guarantees that should change the scheduler design?

---

## 20. Formal Stock Control and 96-Minute Validation

The earlier 4.4, 16, and 28.3-minute tests established that the receiver-paced concept was promising. A later stock-control test and a 96-minute validation test provided a much stronger direct comparison.

### Stock DistroAV control

- Duration: **60.775 minutes**
- Metric: `selected_video_minus_filtered_audio_projected_ns`
- Start: **-54.893150 ms**
- End: **-164.433400 ms**
- End-to-end change: **-109.540250 ms**
- Linear slope: **-1.8024 ms/minute**
- Equivalent rate difference: **-30.040 ppm**

This independently reproduced the long-term behavior previously estimated from recordings as approximately 50 ms every 25 minutes.

### Receiver-Paced validation

- Duration: **96.079 minutes**
- Same selected-video-minus-filtered-audio metric:
  - Start: **-27.451104 ms**
  - End: **-27.541554 ms**
- End-to-end change: **-0.090450 ms**
- Linear slope: approximately **-0.00094 ms/minute**
- Equivalent rate difference: approximately **-0.016 ppm**

At the direct DistroAV output boundary:

- Output video minus output audio start: **-0.026388 ms**
- Output video minus output audio end: **-0.214438 ms**
- End-to-end change: **-0.188050 ms**
- Approximate slope: **-0.0020 ms/minute**

Additional observations:

- Incoming capture timing continued to move by approximately **+6.56 ms**.
- That incoming movement did not propagate into the receiver-paced OBS output timestamps.
- Empty audio pulls: **0**
- Empty video pulls: **0**
- NDI-reported dropped audio frames: **0**
- NDI-reported dropped video frames: **0**
- Audio catch-up events: **0**
- Video catch-up events: **0**

### Interpretation

The stock control allowed disagreement between the incoming clock relationships to become progressive downstream A/V movement. Receiver-Paced mode isolated OBS output timing from that disagreement by generating both streams from one receiver-owned timeline.

This is stronger evidence than merely observing a final offset near zero. The decisive comparison is that the incoming timing still changed while the DistroAV output timing stayed bounded.

---

## 21. Separate-Source Clock-Domain Regression

The first Receiver-Paced implementation gave each NDI source instance its own receiver epoch. This worked when video and embedded audio came from one source, but introduced a new failure when video, desktop audio, and microphone were represented by separate DistroAV source instances.

### Three-source test layout

1. NDI video-only source
2. NDI desktop-audio-only source
3. NDI microphone-audio-only source

### Observed result

Over approximately 14.5 minutes:

- Video moved approximately **66–76 ms** relative to both audio sources.
- Equivalent slope: approximately **4.6–5.2 ms/minute**.
- Desktop audio and microphone remained aligned within approximately **0.003 ms**.
- DistroAV-submitted video and OBS-selected video moved together.
- The selected-video-minus-submitted-video gap stayed near **22.6 ms** and changed by only approximately **0.001 ms**.
- Downstream OBS gap jumps: **0**
- NDI-reported dropped audio/video frames: **0**
- Repeat debt recovered to zero.

### Localization

Because both audio sources stayed mutually aligned while video moved relative to both, the audio clocks were not the source of the new disagreement.

Because DistroAV-submitted video and OBS-selected video moved together while their downstream separation stayed nearly constant, the movement was already present by the DistroAV video-submission boundary rather than accumulating in OBS's downstream queue during this test.

### Combined-source control

A control layout used:

1. One NDI source containing video plus embedded desktop audio
2. One separate NDI microphone source

Over approximately 4.7–4.9 minutes:

- Video versus embedded desktop audio stayed near zero.
- Source video/audio versus the separate microphone remained below approximately **0.1 ms**.
- The combined video and desktop audio did not reproduce the 4.6–5.2 ms/minute movement.

### Conclusion

The first receiver-paced implementation solved the original within-source clock drift but accidentally created multiple independent local receiver-clock domains. Separate source instances therefore behaved like separate watches rather than members of one OBS timeline.

---

## 22. Shared Process-Wide Receiver Epoch

The receiver scheduler was changed so every Receiver-Paced source instance uses one process-wide monotonic epoch.

Separate sources retain their own:

- NDI receiver instance
- NDI FrameSync instance
- media-selection state
- audio sample count
- video tick count

But they now generate OBS timestamps inside the same clock domain.

A newly created source does not replay time from the beginning of the process epoch. It joins at the next valid audio block or video tick at or after the current receiver time plus the startup lead.

Video timestamps were also changed from repeated addition of a truncated integer frame interval to exact rational frame-rate calculation:

```text
video timestamp =
    shared receiver epoch
    + video tick count × FPS denominator × 1,000,000,000
      / FPS numerator
```

This avoids accumulating nanosecond truncation error for rates such as 60000/1001.

### Initial shared-clock test

- Duration: approximately **5.5 minutes**
- All three sources reported the same epoch:
  - **55033763614600 ns**
- DistroAV output video versus desktop audio: approximately **+0.015 ms/minute**
- DistroAV output video versus microphone: approximately **+0.012 ms/minute**
- OBS-selected video versus desktop audio: approximately **+0.024 ms/minute**
- OBS-selected video versus microphone: approximately **+0.020 ms/minute**
- Desktop audio versus microphone: effectively zero
- Repeated video frames: **21**
- Recovered repeats: **21**
- Final repeat debt: **0**
- NDI-reported dropped frames: **0**

This reduced the previous 4.6–5.2 ms/minute separate-source movement by roughly two orders of magnitude immediately.

### 26.5-minute shared-clock validation

- DistroAV output video versus desktop audio: approximately **+0.0007 ms/minute**
- DistroAV output video versus microphone: approximately **-0.0004 ms/minute**
- Desktop audio versus microphone: approximately **-0.0011 ms/minute**
- OBS-selected video versus audio: approximately **+0.002 to +0.003 ms/minute**
- Repeated video frames: **93**
- Recovered repeats: **93**
- Final repeat debt: **0**
- NDI-reported dropped frames: **0**

Raw values moved slightly from sample to sample, but there was no sustained movement comparable to the earlier 4.6–5.2 ms/minute regression.

### Conclusion

The shared receiver epoch corrected the separate-source clock-domain regression. Video, desktop audio, and microphone could remain separate NDI source instances while participating in one receiver-owned OBS timeline.

---

## 23. OBS Async-Video Backlog and Unbuffered Validation

A later long test identified a separate failure after DistroAV had already submitted correctly timed video.

### 108-minute buffered test

For the first approximately **106.4 minutes**:

- OBS-selected video remained approximately **30–31 ms** behind DistroAV-submitted video.
- The downstream gap was stable.
- DistroAV output video stayed aligned with desktop audio at approximately **-0.0012 ms/minute**.
- DistroAV output video stayed aligned with microphone at approximately **+0.0025 ms/minute**.
- Audio sources stayed aligned.
- FrameSync repeat debt returned to zero.
- NDI-reported dropped frames remained zero.

At approximately **106.4 minutes**:

- OBS-selected video experienced a one-time downstream jump of approximately **350 ms**.
- Afterward, selected video remained approximately **381 ms behind** DistroAV-submitted video.
- The DistroAV output boundary itself did not show a matching A/V jump.

### Interpretation

This localized the persistent step change after `obs_source_output_video(...)`, inside OBS's asynchronous video buffering/selection path.

The event also matched the practical symptom in which the NDI feed could remain current outside OBS while the OBS preview and recording path fell behind.

### Lowest Latency behavior

DistroAV's Lowest Latency setting enables:

```cpp
obs_source_set_async_unbuffered(obs_source, true);
```

This tells OBS to favor the newest asynchronous frame rather than preserving a stale queue of frames.

Testing showed that this behavior prevented a temporary receiver stall from becoming permanent video latency. Receiver-Paced mode was therefore updated to enable OBS async-video unbuffering automatically, independently of the NDI decode/color-format latency selection.

### 22.7-minute unbuffered test

- Duration: **22.7 minutes**
- Downstream selected-video gap:
  - Start: approximately **15.44 ms**
  - End: approximately **15.63 ms**
- Linear trend: approximately **+0.002 ms/minute**
- Large persistent downstream jumps: **0**
- Repeated video frames: **41**
- Recovered repeats: **41**
- Final repeat debt: **0**

### 61.7-minute unbuffered stress test

The receiver was deliberately disturbed during the final portion of the run.

- Total duration: approximately **61.7 minutes**
- Normal downstream selected-video gap: approximately **15.4 ms**
- Long-term trend: approximately **+0.0025 ms/minute**
- Largest temporary disturbance:
  - occurred at approximately **54.82 minutes**
  - peak gap approximately **30.6 ms**
  - recovery approximately **0.27 seconds**
- Permanent added video delay: **0**
- Persistent downstream jump events: **0**
- Repeated video frames: **582**
- Recovered repeats: **582**
- Final repeat debt: **0**
- NDI-reported dropped video frames: **0**

The repeat count was concentrated during the deliberate stress period rather than spread uniformly through the entire run. Diagnostic samples commonly showed bursts of three to six repeats, with a maximum observed sampled burst of eight.

### Sender-overload control

The sender was also deliberately overloaded at 4K using NVENC P7:

- OBS rendering lag: approximately **10.4%**
- OBS encoding lag: approximately **18.1%**
- Hundreds of sender-side frame losses were reported.

Despite the overload, A/V timing recovered afterward. This falsified the simpler theory that every lost sender frame necessarily adds one permanent frame of receiver A/V delay.

### Final interpretation of repeats

A repeated FrameSync image means the same underlying NDI video identity was returned for more than one receiver video tick.

At 60 FPS, one repeated display interval is approximately **16.7 ms**. A repeat can therefore appear as a small motion hitch.

However, in the completed tests, repeats did not:

- accumulate into A/V drift,
- leave unrecovered repeat debt,
- create permanent downstream video delay,
- correspond one-for-one with permanent sender frame loss.

With OBS async-video unbuffered, a disturbance produced short repeat/drop activity and then returned to normal delay instead of preserving an old queued-video backlog.

---

## 24. Updated Pass / Fail Criteria

The final receiver-clock approach is considered successful when:

- Stock behavior reproduces a consistent multi-millisecond-per-minute output slope.
- Receiver-Paced output timing remains bounded around its starting relationship.
- Separate Receiver-Paced source instances share one epoch.
- Video, desktop audio, and microphone remain aligned when represented by separate NDI source instances.
- The direct DistroAV output slope remains below **±0.05 ms/minute**.
- OBS-selected video does not acquire a persistent downstream step after a disturbance.
- FrameSync repeat debt returns to zero.
- NDI drop counters do not increase without an explained external disturbance.
- Rebuilding the NDI receiver resets source-local scheduling state cleanly.
- A long recording remains visibly synchronized when checked against an external flash/tone or equivalent reference.

The completed stock, 96-minute, shared-clock, Lowest Latency, and stress tests met the timing-related criteria in this environment.

---

## 25. Updated Files to Attach

Attach the following to an upstream issue, discussion, or pull request when available:

- [ ] This complete `REPRODUCTION.md`
- [ ] Stock 60.775-minute CSV
- [ ] Receiver-Paced 96.079-minute CSV
- [ ] Separate-source regression CSV
- [ ] Combined-source control CSV
- [ ] Initial shared-clock CSV
- [ ] 26.5-minute shared-clock CSV
- [ ] 108-minute buffered downstream-jump CSV
- [ ] 22.7-minute Lowest Latency CSV
- [ ] 61.7-minute Lowest Latency stress CSV
- [ ] Sender-overload OBS log
- [ ] Receiver OBS logs
- [ ] Exact minimal source diff
- [ ] Analysis script and commands
- [ ] Screenshots of all sender and receiver source settings
- [ ] Short recording showing stock drift
- [ ] Long recording showing final behavior
- [ ] Commit hashes for both research and minimal branches

---

## 26. Updated Questions for DistroAV Maintainers

1. Is a process-wide receiver epoch the appropriate ownership level, or should DistroAV derive the epoch from an OBS video/audio timing service?
2. Should Receiver-Paced behavior become a new public source mode, an internal FrameSync implementation detail, or the default FrameSync behavior?
3. Are there NDI SDK guarantees about FrameSync phase and repeated identities that should change the bounded catch-up policy?
4. Should newly created source instances join the shared epoch on the next video tick/audio block as implemented, or use another alignment primitive?
5. Is automatically enabling `obs_source_set_async_unbuffered(..., true)` acceptable for this mode?
6. Should NDI's decode/color-format latency option remain separate from OBS async-video buffering, as in the current experiment?
7. What scheduler counters should remain in production after the research-only CSV probes are removed?
8. What additional platforms, frame rates, and sample rates should be included before considering upstream integration?
9. Should exact rational video timestamp math use OBS's configured FPS numerator/denominator directly everywhere in this path?
10. Would maintainers prefer the minimal patch to preserve selectable stock modes for comparison, or replace the affected FrameSync behavior internally?

---

## 27. Final Conclusion

The original system repeatedly accumulated approximately **50 ms of A/V drift every 25 minutes**. A formal stock capture measured **-109.540 ms over 60.775 minutes**, or **-1.802 ms/minute**.

The first Receiver-Paced implementation reduced the original output drift to approximately **-0.00094 ms/minute over 96.079 minutes**, but separate source instances exposed a new **4.6–5.2 ms/minute** clock-domain disagreement.

Changing Receiver-Paced sources to use one shared process-wide epoch reduced that separate-source movement to approximately **0.001 ms/minute or less** at the DistroAV output boundary.

A separate 108-minute test then localized one persistent approximately **350 ms** step to OBS's downstream asynchronous video path after DistroAV submission. Automatically enabling unbuffered async video for Receiver-Paced mode prevented that failure in subsequent tests. During the 61.7-minute stress run, the largest temporary delay recovered in approximately **0.27 seconds** and left no permanent added latency.

On this tested system, the final combination of:

- receiver-generated audio and video timestamps,
- one shared receiver epoch,
- exact rational video timing,
- bounded deadline catch-up,
- NDI FrameSync for media selection,
- and unbuffered OBS async video

appears to solve both the long-term A/V rate drift and the persistent OBS-side video backlog.

The remaining known behavior is occasional repeated video imagery during timing disturbances. It can produce a brief one-frame motion hitch, but every logged repeat recovered, final repeat debt returned to zero, and no completed test showed repeats accumulating into lasting A/V desynchronization.

The implementation remains experimental until it passes clean CI builds, additional multi-hour recordings, and review by DistroAV maintainers.
