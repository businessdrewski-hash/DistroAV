# DistroAV A/V Drift Reproduction and Validation

> **Test author:** Andrew Carriker  
> **Original test date:** July 19, 2026  
> **Final document update:** July 20, 2026  
> **Research repository:** https://github.com/businessdrewski-hash/DistroAV  
> **Research branch:** `receiver-clock-lab`  
> **Upstream repository:** https://github.com/DistroAV/DistroAV  
> **Stock base commit:** `038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8`  
> **Final research build:** DistroAV Receiver Clock Lab `6.2.1.2`

## Executive Summary

This document records the reproduction, diagnosis, implementation, and validation of progressive NDI A/V desynchronization in a two-PC OBS setup.

The original system repeatedly accumulated approximately:

- **50 ms of A/V drift every 25 minutes**
- approximately **2 ms/minute**
- audio progressively ahead of video
- near-baseline sync again after the NDI receiver was rebuilt

A formal stock DistroAV control later measured **-109.540 ms of movement over 60.775 minutes**, equivalent to **-1.802 ms/minute** or approximately **-30.040 ppm**.

The investigation produced three receiver-side changes:

1. **Receiver-Paced timestamps**  
   Audio and video timestamps delivered to OBS are generated from a receiver-owned monotonic timeline instead of remaining dependent on sender-derived timing.

2. **A shared process-wide receiver epoch**  
   Separate Receiver-Paced DistroAV source instances use one common clock domain instead of creating independent local clocks.

3. **Automatic unbuffered OBS async video**  
   Receiver-Paced mode enables `obs_source_set_async_unbuffered(..., true)` so a temporary OBS video backlog cannot become permanent added delay.

The strongest completed results were:

| Test | Duration | Result |
|---|---:|---|
| Stock Direct control | 60.775 min | **-1.802 ms/min** drift |
| Receiver-Paced long test | 96.079 min | approximately **-0.0020 ms/min** at DistroAV output |
| Separate-source regression before shared epoch | ~14.5 min | approximately **4.6–5.2 ms/min** |
| Shared-epoch validation | 26.5 min | approximately **0.001 ms/min or less** at DistroAV output |
| Unbuffered normal test | 22.7 min | no persistent downstream jump |
| Unbuffered stress test | 61.7 min | largest disturbance recovered in approximately **0.27 seconds** |

On this tested system, the final build appears to solve both:

- long-term audio/video clock drift, and
- persistent OBS-side asynchronous video backlog.

The remaining known behavior is occasional repeated FrameSync video imagery during timing disturbances. Every instrumented repeat recovered, final repeat debt returned to zero, and the repeats did not accumulate into lasting A/V desynchronization.

---

## 1. Test Environment

### 1.1 Sender PC

- CPU: AMD Ryzen 9 9950X3D
- GPU: NVIDIA GeForce RTX 5090
- RAM: 64 GB DDR5
- Windows: Windows 11 Pro, build 26200
- OBS Studio: 32.1.2
- DistroAV: 6.2.1
- NDI Runtime: 6.3.2.0
- Audio interface: Steinberg UR22mkII
- Audio sample rate: 48 kHz

### 1.2 Receiver PC

- CPU: Intel Core i5-12600KF
- GPU: NVIDIA GeForce RTX 5060
- RAM: 32 GB DDR4
- Windows: Windows 11 Pro, build 26200
- OBS Studio: 32.1.2
- Initial Receiver Clock Lab build: 6.2.1.1
- Final shared-clock/unbuffered build: 6.2.1.2
- NDI Runtime: 6.3.2.0
- OBS audio sample rate: 48 kHz

### 1.3 Network

- Connection: Ethernet
- Negotiated link speed: 1 Gbps
- Router/switch: TP-Link Deco X55
- Sender NIC: Realtek PCIe Ethernet Controller
- Receiver NIC: Realtek Gaming 2.5GbE Family Controller

---

## 2. OBS and NDI Settings

### 2.1 Sender

- Canvas/output resolution: 3840 × 2160
- Frame rate: 60 FPS
- Color format: NV12
- Color space: Rec. 709
- Range: Limited
- Source content: HDR, converted to SDR output
- OBS audio sample rate: 48 kHz
- NDI source name: `DrewskiGame`
- NDI bandwidth: Highest
- Audio embedded with video: Yes
- DistroAV hardware acceleration: Off

### 2.2 Receiver

- Canvas/output resolution: 3840 × 2160
- Frame rate: 60 FPS
- OBS audio sample rate: 48 kHz
- Selected source: `DrewskiGame`
- Stock baseline mode: standard DistroAV direct receive path with FrameSync disabled
- Experimental mode: **Receiver-Paced / OBS-Paced**
- DistroAV hardware acceleration: Off
- Recording active during tests: Yes
- Final recordings checked in Adobe Premiere against the synchronization reference

---

## 3. Original Failure

After a fresh OBS launch or NDI receiver rebuild, A/V sync began close to baseline. Over time, audio progressively moved ahead of video at approximately:

```text
50 ms every 25 minutes
```

Equivalent rate:

```text
approximately 2 ms/minute
```

Additional observations:

- The offset became noticeable in recordings after roughly 30 minutes.
- There was no permanent live flash/tone reference in the OBS preview, so small drift could not be judged reliably by eye during the run.
- NDI Studio Monitor did not provide a permanent live reference either.
- Rebuilding the receiver consistently returned the system close to its original sync.
- The problem occurred with both 48 kHz systems.
- Testing FrameSync on/off did not remove the long-term drift.
- Testing hardware acceleration on/off did not remove it.
- Testing source/network timing options did not remove it.
- Testing different bandwidth and color settings did not remove it.

The repeatable reset after receiver reconstruction suggested that accumulated receiver-side timing or buffering state was involved.

---

## 4. Basic Reproduction Procedure

1. Close OBS on both systems.
2. Confirm both systems are configured for 48 kHz audio.
3. Start OBS and DistroAV NDI output on the sender.
4. Start OBS on the receiver.
5. Add or enable the DistroAV NDI source.
6. Select the stock baseline timing mode.
7. Fully rebuild the NDI receiver.
8. Start Receiver Clock Lab CSV diagnostics.
9. Play a flash-and-tone synchronization reference. The reference used in these tests was:  
   https://www.youtube.com/watch?v=YyZq_lEJZ2U&t=2002s
10. Record the initial A/V offset.
11. Leave the source running for at least 25–30 minutes. Longer tests are strongly preferred.
12. Export the CSV from the DistroAV source properties.
13. Save the sender and receiver OBS logs.
14. Record the final A/V offset and calculated slope.
15. Rebuild only the receiver and confirm whether the offset returns close to baseline.

CSV output directory:

```text
%APPDATA%\obs-studio\plugin_config\distroav\
```

The issue is reproduced when the measured output offset moves consistently in one direction and then returns close to baseline after receiver reconstruction.

A one-time static offset is not sufficient to demonstrate the bug. The important evidence is a sustained slope over time.

---

## 5. Diagnostic Measurements

### 5.1 Primary DistroAV output metric

```text
output_video_minus_output_audio_projected_ns
```

This compares the video and audio timestamps DistroAV actually submits to OBS after projecting both to a common current-time domain.

### 5.2 Downstream OBS metric

```text
selected_video_minus_filtered_audio_projected_ns
```

This compares the video selected by OBS's asynchronous video path against audio observed after the OBS audio filter/mixer boundary.

### 5.3 Other important fields

The research logger also records:

- incoming NDI audio/video timing
- DistroAV audio/video output timestamps
- OBS-selected video timestamps
- OBS-filtered audio timestamps
- receiver epoch
- audio sample count
- video tick count
- audio and video deadline error
- bounded catch-up counters
- repeated video identities
- consecutive repeats
- recovered repeats
- current and maximum repeat debt
- skipped source-video identities
- NDI receive queue depth
- NDI total and dropped frame counters
- downstream selected-video gap
- downstream jump events

The distinction between DistroAV output and OBS-selected output was essential. A/V timing could be correct when submitted by DistroAV but later become delayed inside OBS's asynchronous video path.

---

## 6. CSV Analysis

The repository includes:

```text
tools/analyze-receiver-clock-log.py
```

Run from the repository root:

```powershell
python .\tools\analyze-receiver-clock-log.py "C:\path\to\receiver-clock-lab.csv"
```

Example:

```powershell
python .\tools\analyze-receiver-clock-log.py "$env:APPDATA\obs-studio\plugin_config\distroav\receiver-clock-lab.csv"
```

The script reports:

- test duration
- selected timing mode
- starting and final A/V offset
- total offset movement
- linear drift slope
- ppm
- empty pulls
- audio/video catch-ups
- repeated frames and recovery
- NDI-reported drops
- maximum queued frames
- downstream video gap and jumps

Conversion:

```text
1 ppm = 0.06 ms/minute
```

Therefore:

```text
drift in ms/minute = reported ppm × 0.06
```

Example:

```text
-0.033 ppm × 0.06 = approximately -0.0020 ms/minute
```

Attach the raw CSV and the analyzer summary. Do not rely only on a manually inspected final row.

---

## 7. First Implementation: Receiver-Paced Timestamps

The primary implementation is in:

```text
src/ndi-source.cpp
```

The stock direct and existing FrameSync paths allowed outgoing OBS timing to remain influenced by sender-provided timestamps. NDI FrameSync could select or resample appropriate media, but the final OBS audio and video timestamps were not necessarily generated from one receiver-owned timeline.

Receiver-Paced mode adds scheduler state containing:

- a receiver-owned epoch based on `os_gettime_ns()`
- the OBS audio sample rate
- the OBS video FPS numerator and denominator
- cumulative audio frames delivered
- cumulative receiver video ticks
- next audio deadline
- next video deadline

Audio timestamp:

```text
receiver epoch
+ cumulative delivered audio frames × 1,000,000,000
  / audio sample rate
```

Video timestamp:

```text
receiver epoch
+ video tick count × FPS denominator × 1,000,000,000
  / FPS numerator
```

The main media-output functions use these locally generated timestamps in Receiver-Paced mode:

```text
ndi_source_thread_process_audio3(...)
ndi_source_thread_process_video2(...)
```

The receiver loop was also changed so:

- audio is pulled according to receiver audio deadlines
- video is pulled according to receiver video deadlines
- late audio may use bounded catch-up pulls
- missed video ticks are advanced rather than allowed to create permanent scheduling debt
- NDI FrameSync remains responsible for media selection and sample conversion
- sender timestamps remain available for diagnostics but are not the final OBS timestamp authority in Receiver-Paced mode

### 7.1 First-version reset behavior

The first version used one source-local receiver epoch. Rebuilding that source reset its epoch and scheduler counters.

This solved the original within-source drift but later created a new problem when several separate source instances each created their own independent epoch.

---

## 8. Early Receiver-Paced Validation

| Test | Duration | Drift expected from old behavior | Final DistroAV output offset | Measured slope |
|---|---:|---:|---:|---:|
| Test A | 4.4 min | ~8.8 ms | +0.28 ms | -0.003 ms/min |
| Test B | 16 min | ~32 ms | -0.39 ms | -0.0024 ms/min |
| Test C | 28.3 min | ~57 ms | -0.35 ms | -0.0014 ms/min |
| Test D | 96.079 min | ~192 ms | -0.214 ms | approximately -0.0020 ms/min |

These tests showed that receiver-generated output timestamps prevented the original approximately 2 ms/minute drift from propagating into DistroAV's OBS output.

---

## 9. Formal Stock DistroAV Control

A long stock-control capture provided a measured baseline.

- Duration: **60.775 minutes**
- Mode: Stock Direct
- Metric: `selected_video_minus_filtered_audio_projected_ns`
- Starting offset: **-54.893150 ms**
- Final offset: **-164.433400 ms**
- Total movement: **-109.540250 ms**
- Linear slope: **-30.040 ppm**
- Equivalent drift: **-1.8024 ms/minute**

This independently reproduced the original real-world estimate of approximately 50 ms every 25 minutes.

---

## 10. Formal 96-Minute Receiver-Paced Validation

### 10.1 DistroAV output boundary

- Duration: **96.079 minutes**
- Metric: `output_video_minus_output_audio_projected_ns`
- Starting offset: **-0.026388 ms**
- Final offset: **-0.214438 ms**
- Total movement: **-0.188050 ms**
- Approximate slope: **-0.0020 ms/minute**
- Median output offset: approximately **-0.110 ms**
- Approximate 90% range: **-1.163 ms to +1.062 ms**

### 10.2 Downstream selected-video boundary

- Metric: `selected_video_minus_filtered_audio_projected_ns`
- Starting offset: **-27.451104 ms**
- Final offset: **-27.541554 ms**
- Total movement: **-0.090450 ms**
- Linear slope: approximately **-0.00094 ms/minute**
- Equivalent rate difference: approximately **-0.016 ppm**

### 10.3 Additional counters

- Incoming capture relationship movement: approximately **+6.564 ms**
- Empty audio pulls: **0**
- Empty video pulls: **0**
- NDI-reported dropped audio frames: **0**
- NDI-reported dropped video frames: **0**
- Audio catch-ups: **0**
- Video catch-ups: **0**
- Repeated video frames: **262**
- Approximate repeat rate: one every **22 seconds**

### 10.4 Interpretation

The incoming capture relationship continued to move, but the timestamps delivered by DistroAV and selected by OBS remained essentially bounded for more than 96 minutes.

This is the strongest evidence that the receiver-paced output timeline prevented the original accumulating drift. A near-zero final value by itself would not be sufficient; the important result is that incoming timing movement did not propagate into progressive output movement.

---

## 11. Separate-Source Clock-Domain Regression

The first Receiver-Paced implementation used one local receiver epoch per DistroAV source instance.

This worked when video and embedded desktop audio came through the same NDI source. A new failure appeared when video, desktop audio, and microphone were represented by three separate source instances.

### 11.1 Test layout

1. NDI video-only source
2. NDI desktop-audio-only source
3. NDI microphone-audio-only source

### 11.2 Result

Over approximately **14.5 minutes**:

- video moved approximately **66–76 ms** relative to both audio sources
- equivalent slope: approximately **4.6–5.2 ms/minute**
- desktop audio and microphone stayed aligned within approximately **0.003 ms**
- DistroAV-submitted video and OBS-selected video moved together
- the selected-video-minus-submitted-video gap stayed near **22.6 ms**
- that downstream gap changed by only approximately **0.001 ms**
- downstream OBS jump events: **0**
- NDI-reported dropped frames: **0**
- repeat debt recovered to zero

### 11.3 Localization

Because both audio sources stayed aligned while video moved relative to both, the new error was not caused by either audio stream.

Because DistroAV-submitted video and OBS-selected video moved together while their downstream separation stayed constant, the movement was already present by the DistroAV video-submission boundary during this test.

The first Receiver-Paced implementation solved the original within-source drift but created independent local clock domains across separate source instances.

---

## 12. Combined-Source Control

A control layout used:

1. one NDI source containing video plus embedded desktop audio
2. one separate NDI microphone source

Over approximately **4.7–4.9 minutes**:

- video versus embedded desktop audio stayed near zero
- video/desktop versus the separate microphone remained below approximately **0.1 ms**
- the previous **4.6–5.2 ms/minute** video movement did not appear

This confirmed that the new regression was caused by independent Receiver-Paced source clocks rather than the microphone, desktop audio, sender, or network.

---

## 13. Final Clock Design: Shared Process-Wide Epoch

All Receiver-Paced source instances were changed to use one process-wide monotonic epoch.

Each source still owns its own:

- NDI receiver
- NDI FrameSync instance
- audio sample count
- video tick count
- media-selection state
- local deadlines

But all generated OBS timestamps exist inside one common clock domain.

### 13.1 Shared epoch initialization

The first Receiver-Paced source establishes the process-wide epoch with a short startup lead based on `os_gettime_ns()`.

### 13.2 Joining an existing timeline

A source created later does not replay time from the original epoch. It joins at the next valid audio block or video tick at or after the current receiver time plus the startup lead.

### 13.3 Receiver rebuild behavior

Rebuilding one source:

- recreates that source's NDI receiver and FrameSync instance
- resets that source's local sample/tick counters and deadline state
- rejoins the existing process-wide timeline

It does **not** create an unrelated new clock domain while other Receiver-Paced sources are active.

### 13.4 Exact rational video timing

Video timestamps are calculated directly from the FPS numerator and denominator rather than repeatedly adding a truncated integer nanosecond interval.

This avoids accumulated truncation error at rates such as 60000/1001.

---

## 14. Shared-Clock Validation

### 14.1 Initial shared-clock test

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

This reduced the previous 4.6–5.2 ms/minute separate-source regression by roughly two orders of magnitude.

### 14.2 26.5-minute shared-clock test

- DistroAV output video versus desktop audio: approximately **+0.0007 ms/minute**
- DistroAV output video versus microphone: approximately **-0.0004 ms/minute**
- Desktop audio versus microphone: approximately **-0.0011 ms/minute**
- OBS-selected video versus audio: approximately **+0.002 to +0.003 ms/minute**
- Repeated frames: **93**
- Recovered repeats: **93**
- Final repeat debt: **0**
- NDI-reported dropped frames: **0**

The raw offsets moved slightly from sample to sample, but no sustained movement comparable to the earlier 4.6–5.2 ms/minute regression remained.

### 14.3 Result

The shared epoch corrected the separate-source clock-domain problem. Video, desktop audio, and microphone could remain separate DistroAV source instances while participating in one receiver-owned OBS timeline.

---

## 15. Long Buffered Test: OBS Downstream Video Jump

A later long run showed that DistroAV's submitted audio and video remained aligned, but OBS-selected video experienced a one-time downstream delay increase.

### 15.1 First 106.4 minutes

- OBS-selected video remained approximately **30–31 ms** behind DistroAV-submitted video
- the downstream gap was stable
- DistroAV output video versus desktop audio: approximately **-0.0012 ms/minute**
- DistroAV output video versus microphone: approximately **+0.0025 ms/minute**
- desktop audio and microphone remained aligned
- repeat debt returned to zero
- NDI-reported dropped frames remained zero

### 15.2 Jump event

At approximately **106.4 minutes**:

- OBS-selected video suddenly moved approximately **350 ms** farther behind
- selected video then remained approximately **381 ms behind** DistroAV-submitted video
- DistroAV's direct output boundary did not show a matching A/V jump
- repeat debt returned to zero
- NDI-reported drop counters did not explain the persistent step

### 15.3 Localization

This localized the permanent step after `obs_source_output_video(...)`, inside OBS's asynchronous video buffering/selection path.

It matched the practical observation that the NDI feed could remain current outside OBS while the OBS preview and recording path fell behind.

---

## 16. Automatic Unbuffered OBS Async Video

DistroAV's Lowest Latency setting already enables:

```cpp
obs_source_set_async_unbuffered(obs_source, true);
```

Testing showed that this prevents OBS from preserving a stale queue of asynchronous video frames after a receiver stall.

Receiver-Paced mode was therefore updated so OBS async-video unbuffering is enabled automatically whenever Receiver-Paced mode is active.

This is intentionally separate from DistroAV's NDI decode/color-format latency option. Receiver-Paced mode forces OBS async-video unbuffering without necessarily forcing every other Lowest Latency decode behavior.

Expected behavior changes from:

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

---

## 17. Unbuffered Validation

### 17.1 22.7-minute normal test

- Duration: **22.7 minutes**
- Downstream selected-video gap at start: approximately **15.44 ms**
- Downstream selected-video gap at end: approximately **15.63 ms**
- Long-term trend: approximately **+0.002 ms/minute**
- Large persistent downstream jumps: **0**
- Repeated frames: **41**
- Recovered repeats: **41**
- Final repeat debt: **0**

No measurable OBS-selected-video drift developed relative to DistroAV-submitted video.

### 17.2 61.7-minute stress test

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

The repeats were concentrated during the deliberate stress period and occurred in bursts rather than at a constant rate. Diagnostic samples commonly showed bursts of three to six repeats, with a maximum sampled burst of eight.

### 17.3 Result

Unbuffered async video prevented receiver disturbances from becoming permanent OBS-side latency in these tests.

---

## 18. Sender-Overload Control

The sender was deliberately overloaded at 4K using NVENC P7.

Observed stress:

- OBS rendering lag: approximately **10.4%**
- OBS encoding lag: approximately **18.1%**
- hundreds of sender-side frame losses

Despite the overload, A/V timing recovered afterward.

This falsified the simpler theory that every missing sender frame necessarily creates one permanent frame of receiver-side A/V delay.

---

## 19. Repeated-Frame Interpretation

A repeated FrameSync image means the same underlying NDI video identity was returned for more than one receiver video tick.

At 60 FPS:

```text
one display interval ≈ 16.7 ms
```

A repeat can therefore appear as a small motion hitch.

In the completed tests, repeats did not:

- accumulate into long-term A/V drift
- leave unrecovered repeat debt
- create permanent downstream video latency
- correspond one-for-one with permanently lost sender frames

The 582-repeat stress result should not be interpreted as 582 permanently lost video frames. The repeats were mostly clustered during deliberate disturbances, and every logged repeat was recovered.

This remains a motion-smoothness issue worth improving, but it is separate from the resolved accumulating A/V-sync problem.

---

## 20. Complete Validation Summary

| Test | Mode | Duration | Primary result |
|---|---|---:|---|
| Early Test A | Receiver-Paced | 4.4 min | +0.28 ms final output offset; -0.003 ms/min |
| Early Test B | Receiver-Paced | 16 min | -0.39 ms final output offset; -0.0024 ms/min |
| Early Test C | Receiver-Paced | 28.3 min | -0.35 ms final output offset; -0.0014 ms/min |
| Stock control | Stock Direct | 60.775 min | -109.540 ms movement; -1.802 ms/min |
| Receiver-Paced long test | Source-local Receiver-Paced | 96.079 min | -0.188 ms DistroAV output movement; ~-0.0020 ms/min |
| Separate-source regression | Independent source-local clocks | ~14.5 min | video moved ~4.6–5.2 ms/min relative to both audio sources |
| Combined-source control | Video + embedded desktop audio | ~4.8 min | combined video/audio near zero; separate mic within ~0.1 ms |
| Initial shared-clock test | Shared Receiver-Paced epoch | ~5.5 min | common epoch confirmed; large regression removed |
| Shared-clock validation | Shared Receiver-Paced epoch | 26.5 min | DistroAV output relationships ~0.001 ms/min or less |
| Buffered downstream test | Shared clock, buffered OBS video | ~108 min | one persistent ~350 ms downstream jump after ~106.4 min |
| Unbuffered normal test | Shared clock + unbuffered video | 22.7 min | gap stayed near 15.5 ms; no persistent jump |
| Unbuffered stress test | Shared clock + unbuffered video | 61.7 min | largest disturbance recovered in ~0.27 s; no permanent delay |
| Sender-overload control | 4K NVENC P7 overload | stress segment | timing recovered despite rendering/encoding losses |

---

## 21. Final Pass Criteria

The final receiver-clock implementation is considered successful when:

- stock behavior reproduces a sustained multi-millisecond-per-minute slope
- Receiver-Paced output timing remains bounded around its starting relationship
- direct DistroAV output drift remains below **±0.05 ms/minute**
- separate Receiver-Paced source instances use one shared epoch
- separate video, desktop-audio, and microphone sources remain aligned
- OBS-selected video does not acquire a persistent downstream step after a disturbance
- repeat debt returns to zero
- unexplained NDI drop counters do not increase
- source reconstruction cleanly rejoins the shared timeline
- a long recording remains visibly synchronized against an external reference

The completed stock, 96-minute, shared-clock, unbuffered, and stress tests met the timing-related criteria in this environment.

---

## 22. Known Limitations

The completed tests do not yet prove:

- correct behavior at every supported frame rate
- correct behavior at sample rates other than 48 kHz
- correct behavior on macOS or Linux
- correct behavior with every NDI bandwidth and color-format setting
- correct behavior under every GPU, CPU, network, or OBS overload scenario
- whether OBS async-video unbuffering should become the upstream default for this mode
- whether the shared epoch should ultimately be process-wide, OBS-instance-wide, or owned by a more formal synchronization service
- whether repeat frequency can be reduced further without compromising clock stability

The implementation remains experimental until it receives clean CI results, additional long recordings, and maintainer review.

---

## 23. Files to Attach for Maintainer Review

- [ ] This `REPRODUCTION.md`
- [ ] Stock 60.775-minute CSV
- [ ] Receiver-Paced 96.079-minute CSV
- [ ] Separate-source regression CSV
- [ ] Combined-source control CSV
- [ ] Initial shared-clock CSV
- [ ] 26.5-minute shared-clock CSV
- [ ] 108-minute buffered downstream-jump CSV
- [ ] 22.7-minute unbuffered CSV
- [ ] 61.7-minute unbuffered stress CSV
- [ ] Sender-overload OBS log
- [ ] Receiver OBS logs
- [ ] Exact minimal source diff
- [ ] Analyzer script and command
- [ ] Sender and receiver settings screenshots
- [ ] Short recording showing stock drift
- [ ] Long recording showing final behavior
- [ ] Research branch commit SHA
- [ ] Minimal branch commit SHA after its build passes

Suggested comparison:

```text
stock base:
038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8

research branch:
receiver-clock-lab
```

---

## 24. Questions for DistroAV Maintainers

1. Is a process-wide shared receiver epoch the correct ownership level for separate DistroAV source instances?
2. Should Receiver-Paced behavior remain a selectable public mode, become an internal FrameSync implementation detail, or replace the affected path?
3. Are there NDI FrameSync timing guarantees that should change the bounded catch-up or repeated-frame policy?
4. Should newly created Receiver-Paced sources join at the next audio block/video tick as implemented?
5. Is automatically enabling `obs_source_set_async_unbuffered(..., true)` appropriate for Receiver-Paced mode?
6. Should the NDI decode/color-format latency option remain independent from OBS async-video buffering?
7. Should exact rational FPS timing use OBS's numerator and denominator directly throughout this receive path?
8. Which diagnostics should remain in a production implementation after the research probes are removed?
9. Which frame rates, sample rates, operating systems, and source layouts should be tested before upstream integration?
10. Would maintainers prefer the minimal two-file patch or the larger research branch with selectable modes and diagnostics?

---

## 25. Final Conclusion

The original setup repeatedly accumulated approximately **50 ms of A/V drift every 25 minutes**. A formal stock capture measured **-109.540 ms over 60.775 minutes**, equivalent to approximately **-1.802 ms/minute**.

The first Receiver-Paced implementation reduced the original output drift to approximately **-0.0020 ms/minute over 96.079 minutes**. That implementation then exposed a new **4.6–5.2 ms/minute** disagreement when separate source instances used independent local receiver clocks.

Changing all Receiver-Paced source instances to one shared process-wide epoch reduced the separate-source movement to approximately **0.001 ms/minute or less** at the DistroAV output boundary.

A later 108-minute test localized one persistent approximately **350 ms** step to OBS's asynchronous video path after DistroAV had already submitted correctly timed video.

Automatically enabling unbuffered OBS async video for Receiver-Paced mode prevented that failure in subsequent tests. During the 61.7-minute stress run, the largest temporary delay recovered in approximately **0.27 seconds** and left no permanent added latency.

On this system, the final combination of:

- receiver-generated audio and video timestamps
- one shared receiver epoch
- exact rational video timing
- bounded deadline catch-up
- NDI FrameSync for media selection
- automatic unbuffered OBS async video

appears to solve both the long-term A/V rate drift and the persistent OBS-side video-backlog problem.

The remaining known issue is occasional repeated video imagery during timing disturbances. It may create a brief one-frame motion hitch, but every logged repeat recovered, final repeat debt returned to zero, and no completed test showed repeats accumulating into lasting A/V desynchronization.
