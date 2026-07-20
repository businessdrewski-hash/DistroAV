# DistroAV A/V Drift Reproduction

> \\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\*Test author:\\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\* \\\\\\\\ Andrew Carriker 
> \\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\*Date:\\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\* \\\\\\\\ 7/19/26 
> \\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\*Repository / branch:\\\\\\\\\\\\\\\*\\\\\\\\\\\\\\\* \\\\\\\\ https://github.com/businessdrewski-hash/DistroAV/tree/receiver-clock-lab

## Summary

This test reproduces progressive A/V drift in a two-PC OBS setup using DistroAV, then validates an experimental receiver-paced timing change.

Previously observed behavior:

* Approximately **50 ms of A/V drift every 25 minutes**
* Approximately **2 ms/minute**
* Restarting or rebuilding the NDI receiver returned the source close to sync

The longest receiver-paced validation ran for **96.08 minutes**. At the previous drift rate, approximately **192 ms** of visible desynchronization should have accumulated. Instead:

* Output A/V offset started at **-0.026 ms** and ended at **-0.214 ms**
* Total movement over the entire test: **-0.188 ms**
* Measured drift slope: **-0.033 ppm**, or approximately **-0.0020 ms/minute**
* Median output offset: **approximately -0.110 ms**
* 90% of samples remained between **-1.163 ms and +1.062 ms**
* Empty audio pulls: **0**
* Empty video pulls: **0**
* NDI-reported dropped audio/video frames: **0**
* Audio/video catch-ups: **0**

The incoming capture relationship still moved by approximately **+6.56 ms**, while the timestamps DistroAV delivered to OBS remained effectively locked. This is the clearest evidence that the receiver-paced timing change prevented the original accumulating drift.

\---

## Test Setup

### Sender PC

* CPU: AMD 9950X3d
* GPU: RTX 5090
* RAM: 64GB DDR5
* Windows version: Win11 Pro 10.0.26200 Build 26200
* OBS version: 32.1.2
* DistroAV version: 6.2.1
* NDI Runtime version: 6.3.2.0
* Audio device/interface: Steinburg UR22 MKII
* Audio sample rate: 48khz

### Receiver PC

* CPU: Intel 12600kf
* GPU: RTX 5060
* RAM: 32GB DDR4
* Windows version: Win11 Pro 10.0.26200 Build 26200
* OBS version: 32.1.2
* DistroAV test build / commit: DistroAV Receiver Clock Lab 6.2.1.1
* NDI Runtime version: 6.3.2.0
* OBS audio sample rate: 48khz

### Network

* Connection type: Ethernet
* Link speed: 1Gbps
* Switch/router: Deco X55
* Sender NIC:  Realtek(R) PCI(e) Ethernet Controller
* Receiver NIC: Realtek Gaming 2.5GbE Family Controller

\---

## OBS and NDI Settings

### Sender

* Canvas/output resolution: 3840x2160
* FPS: 60
* Color format / space / range: NV12, Rec 709, Limited
* HDR or SDR: HDR downmixed to SDR output
* OBS audio sample rate: \[FILL IN]
* NDI source name: DrewskiGame
* NDI bandwidth mode: Highest
* Audio embedded with video: Yes
* Hardware acceleration: No

### Receiver

* Canvas/output resolution: 3840x2160
* FPS: 60
* OBS audio sample rate: 48khz
* Selected NDI source: DrewskiGame
* Baseline sync mode: Standard DistroAV receive mode — FrameSync disabled
* Validation sync mode: **Receiver-Paced / OBS-Paced**
* Hardware acceleration: No
* Recording/streaming active during test: Yes (to reference A/V sync after and confirm logged shift in Adobe Premiere.)

\---

## Original Failure

After a fresh OBS or NDI receiver restart, A/V sync began close to baseline. Over time, the output gradually moved out of sync at approximately:

```text
50 ms every 25 minutes
```

Additional observations:

* Drift direction: Audio ahead of video \~50ms/25mins
* Visible in OBS preview: No (No live ability to monitor A/V sync)
* Visible in recordings: No, but as drift continues over time, yes. Noticeable at \~30mins.
* Visible in NDI Studio Monitor: No (No live ability to monitor A/V sync)
* Receiver restart reset the offset: Always Yes
* Attempted fixes: 48 kHz on both systems. Framesync on/off. HWX on/off. Source/Network Timing. Bandwidth High/low. Color Ranges.

\---

## Reproduction Steps

1. Close OBS on both systems.
2. Confirm both systems use the documented audio sample rate.
3. Start OBS and NDI output on the sender.
4. Start OBS on the receiver.
5. Add or enable the DistroAV NDI source.
6. Select the baseline synchronization mode.
7. Restart the NDI receiver.
8. Start CSV diagnostics.
9. Create a synchronization reference using https://www.youtube.com/watch?v=YyZq\_lEJZ2U\&t=2002s
10. Record the initial A/V offset.
11. Leave the source running for at least 25–30 minutes.
12. Export the CSV in the properties of the main NDI source. (AppData\\Roaming\\obs-studio\\plugin\_config\\distroav)
13. Record the final offset and drift slope.
14. Restart only the NDI receiver (hide/unhide), export another CSV, observe and confirm whether the offset returns close to baseline.

The issue is reproduced when the measured output offset moves consistently in one direction over time and resets after rebuilding the receiver.

\---

## What Was Changed

The experimental change is primarily in:

```text
src/ndi-source.cpp
```

The existing receive path allowed audio and video timing to remain influenced by different clock domains. NDI FrameSync could select appropriate media, but the timestamps delivered to OBS were not necessarily generated from one shared receiver timeline.

The receiver-paced implementation adds one local scheduling state containing:

* A receiver-owned epoch based on `os\\\\\\\\\\\\\\\_gettime\\\\\\\\\\\\\\\_ns()`
* The OBS audio sample rate
* The OBS video frame interval
* Total audio samples delivered
* Total receiver video ticks

Audio and video timestamps are then generated from the same epoch:

```text
audio timestamp =
    receiver epoch
    + duration of delivered audio samples

video timestamp =
    receiver epoch
    + duration of elapsed OBS video ticks
```

The main processing functions changed are:

```text
ndi\\\\\\\\\\\\\\\_source\\\\\\\\\\\\\\\_thread\\\\\\\\\\\\\\\_process\\\\\\\\\\\\\\\_audio3(...)
ndi\\\\\\\\\\\\\\\_source\\\\\\\\\\\\\\\_thread\\\\\\\\\\\\\\\_process\\\\\\\\\\\\\\\_video2(...)
```

When Receiver-Paced mode is active, these functions use the locally generated receiver timestamp instead of the incoming source timestamp.

The receive loop was also changed so:

* Audio is pulled according to OBS audio deadlines
* Video is pulled according to the OBS frame interval
* Late audio pulls use bounded catch-up
* Missed video scheduling ticks are skipped rather than allowed to accumulate
* The local epoch resets whenever the NDI receiver is rebuilt

Exact branch / commit: receiver-clock-lab / 496819c54309c8a56811a2edd959c4a17e7e4181

Approximate synchronization-specific lines changed: Approximately 150 lines in src/ndi-source.cpp, excluding CSV diagnostics, test code, and startup-crash hardening

Comparison URL: Not currently available because the experimental branch does not share Git history with the stock DistroAV repository

## Upstream DistroAV repository: https://github.com/DistroAV/DistroAV

## Measurements

The most important CSV field is:

```text
output\\\\\\\\\\\\\\\_video\\\\\\\\\\\\\\\_minus\\\\\\\\\\\\\\\_output\\\\\\\\\\\\\\\_audio\\\\\\\\\\\\\\\_projected\\\\\\\\\\\\\\\_ns
```

This measures the relationship between the video and audio timestamps DistroAV actually delivers to OBS.

Also useful:

```text
selected\\\\\\\\\\\\\\\_video\\\\\\\\\\\\\\\_minus\\\\\\\\\\\\\\\_filtered\\\\\\\\\\\\\\\_audio\\\\\\\\\\\\\\\_projected\\\\\\\\\\\\\\\_ns
```

This provides a downstream comparison through the diagnostic probes.

CSV directory:

```text
%APPDATA%\\\\\\\\\\\\\\\\obs-studio\\\\\\\\\\\\\\\\plugin\\\\\\\\\\\\\\\_config\\\\\\\\\\\\\\\\distroav\\\\\\\\\\\\\\\\
```

Analysis script / command: `tools/analyze-receiver-clock-log.py` / `python .\\\\\\\\tools\\\\\\\\analyze-receiver-clock-log.py "$env:APPDATA\\\\\\\\obs-studio\\\\\\\\plugin\\\\\\\_config\\\\\\\\distroav\\\\\\\\receiver-clock-lab-<source-id>.csv"` Run the command from the repository’s root folder. Replace <source-id> with the actual CSV filename.

\---

## How to Analyze the CSV

The source repository includes:

```text
tools/analyze-receiver-clock-log.py
```

Install Python 3 if it is not already installed, then open PowerShell in the repository folder and run:

```powershell
python .\\\\\\\\\\\\\\\\tools\\\\\\\\\\\\\\\\analyze-receiver-clock-log.py "C:\\\\\\\\\\\\\\\\path\\\\\\\\\\\\\\\\to\\\\\\\\\\\\\\\\receiver-clock-lab.csv"
```

Example:

```powershell
python .\\\\\\\\\\\\\\\\tools\\\\\\\\\\\\\\\\analyze-receiver-clock-log.py "$env:APPDATA\\\\\\\\\\\\\\\\obs-studio\\\\\\\\\\\\\\\\plugin\\\\\\\\\\\\\\\_config\\\\\\\\\\\\\\\\distroav\\\\\\\\\\\\\\\\receiver-clock-lab.csv"
```

I personally threw the file into \\tools in my install and then ran py .\\analyze-receiver-clock-log.py .\\receiver-clock-lab.csv



The script summarizes the full test rather than requiring manual interpretation of individual CSV rows. Record the following results:

* Test duration and timing mode
* Starting and final output A/V offset
* Total offset change
* Drift slope
* Empty audio and video pulls
* Repeated video frames
* NDI-reported dropped frames
* Audio/video catch-up counters
* Maximum queued audio/video frames

The primary synchronization field is:

```text
output\\\\\\\\\\\\\\\_video\\\\\\\\\\\\\\\_minus\\\\\\\\\\\\\\\_output\\\\\\\\\\\\\\\_audio\\\\\\\\\\\\\\\_projected\\\\\\\\\\\\\\\_ns
```

The script reports drift rate in **ppm**. For an offset changing over time:

```text
1 ppm = 0.06 ms/minute
```

Convert the reported value with:

```text
drift in ms/minute = reported ppm × 0.06
```

Example from the 96.08-minute validation:

```text
-0.033 ppm × 0.06 = approximately -0.0020 ms/minute
```

Attach the raw CSV and paste the script summary into the test report. The tester is not expected to decode the unlabelled final CSV row manually.

\---

## Validation Results

|Test|Duration|Drift expected from old behavior|Final output offset|Measured slope|
|-|-:|-:|-:|-:|
|Test A|4.4 min|\~8.8 ms|+0.28 ms|-0.003 ms/min|
|Test B|16 min|\~32 ms|-0.39 ms|-0.0024 ms/min|
|Test C|28.3 min|\~57 ms|-0.35 ms|-0.0014 ms/min|
|Test D|96.08 min|\~192 ms|-0.214 ms|-0.0020 ms/min|

For the 96.08-minute test:

* Starting output offset: **-0.026 ms**
* Final output offset: **-0.214 ms**
* Total change: **-0.188 ms**
* Median output offset: **approximately -0.110 ms**
* Approximate 90% range: **-1.163 ms to +1.062 ms**
* Incoming capture relationship changed by: **+6.564 ms**
* Empty audio pulls: **0**
* Empty video pulls: **0**
* NDI-reported dropped audio frames: **0**
* NDI-reported dropped video frames: **0**
* Audio catch-ups: **0**
* Video catch-ups: **0**

The conclusive result is that incoming timing continued to move, while the timestamps DistroAV delivered to OBS remained essentially unchanged for more than 96 minutes.

\---

## Pass Criteria

The fix is considered successful when:

* Output A/V offset stays bounded around its starting value
* Drift slope remains near zero
* Final offset remains within \[FILL IN, suggested: ±2 ms]
* Drift slope remains below \[FILL IN, suggested: ±0.05 ms/min]
* No recurring empty pulls occur
* No unexplained NDI drop counters increase
* Rebuilding the receiver resets the local scheduler cleanly

The 96.08-minute test passed these criteria.

\---

## Known Limitation

The receiver-paced test occasionally received the same NDI video image on consecutive OBS ticks.

Latest result:

* Repeated frames: **262**
* Duration: **96.08 minutes**
* Approximate rate: **one every 22 seconds**

This remains a separate video-pacing issue from the resolved A/V drift. It did not cause the measured A/V offset to drift. I will attempt to phase-align the video pull timing to the incoming NDI cadence and skip/retime late OBS ticks instead of accepting the same frame twice. It cannot prevent repeats caused by a genuinely missing sender/network frame, but 262 regular pacing repeats over 90mins should be reducible.

\---

## Conclusion

The original setup repeatedly accumulated approximately **50 ms of A/V drift every 25 minutes**. The receiver-paced implementation moved both streams onto one receiver-owned OBS timeline.

In the **96.08-minute** validation test, approximately **192 ms** of drift should have appeared based on the old behavior. Instead, the output moved by only **-0.188 ms** from start to finish and ended at **-0.214 ms**, with a measured slope of approximately **-0.0020 ms/minute**. There were no empty pulls, NDI-reported dropped frames, or catch-up events.

Meanwhile, the incoming capture relationship moved by approximately **+6.56 ms**. The fact that this movement did not propagate into DistroAV's OBS output is conclusive evidence that the receiver-paced timing approach prevented the previously observed accumulating A/V drift in this test environment.

\---

## Additional Validation: Formal Stock Control

A later stock DistroAV control provided a direct measured baseline for the original issue.

* Duration: **60.775 minutes**
* Metric: `selected_video_minus_filtered_audio_projected_ns`
* Starting offset: **-54.893 ms**
* Final offset: **-164.433 ms**
* Total change: **-109.540 ms**
* Measured slope: **-30.040 ppm**
* Equivalent drift: **approximately -1.802 ms/minute**

This closely matched the original real-world observation of approximately **50 ms every 25 minutes**.

The stock control established that the original problem was not only a visual estimate from recordings. The output timing moved consistently in one direction over a long run and at a rate large enough to become clearly visible.

\---

## Separate-Source Regression Found After the First Fix

The first Receiver-Paced implementation used one local receiver epoch per DistroAV source instance.

That worked well when video and embedded desktop audio came through the same NDI source, but a new problem appeared when video, desktop audio, and microphone were split into three separate DistroAV source instances.

### Test layout

1. NDI video-only source
2. NDI desktop-audio-only source
3. NDI microphone-audio-only source

### Result

Over approximately **14.5 minutes**:

* Video moved approximately **66–76 ms** relative to both audio sources
* Equivalent drift: approximately **4.6–5.2 ms/minute**
* Desktop audio and microphone stayed aligned within approximately **0.003 ms**
* DistroAV-submitted video and OBS-selected video moved together
* The selected-video-minus-submitted-video gap stayed near **22.6 ms**
* That downstream gap changed by only approximately **0.001 ms**
* Downstream OBS jump events: **0**
* NDI-reported dropped frames: **0**
* Repeat debt recovered to zero

### Interpretation

Because the two audio sources stayed aligned while video moved relative to both, the new error was not caused by one audio stream running at a different rate.

Because DistroAV-submitted video and OBS-selected video moved together while their separation stayed nearly constant, the drift was already present by the DistroAV video-output boundary rather than being created later in OBS during this test.

The first Receiver-Paced implementation had therefore solved the original within-source drift but created independent receiver-clock domains for separate source instances.

\---

## Combined-Source Control

A control test used:

1. One NDI source containing video plus embedded desktop audio
2. One separate NDI microphone source

Over approximately **4.7–4.9 minutes**:

* Video versus embedded desktop audio stayed near zero
* Video/desktop versus the separate microphone remained below approximately **0.1 ms**
* The previous **4.6–5.2 ms/minute** video drift did not appear

This confirmed that the new regression was caused by separate Receiver-Paced source clocks rather than the microphone, desktop audio, sender, or network.

\---

## Shared Process-Wide Receiver Epoch

The Receiver-Paced implementation was changed so every Receiver-Paced source instance uses one shared process-wide monotonic epoch.

Each source still has its own:

* NDI receiver
* NDI FrameSync instance
* audio sample counter
* video tick counter
* media-selection state

But all OBS output timestamps now exist inside one common receiver clock domain.

A newly created source joins the current shared timeline at the next valid audio block or video tick instead of starting a new independent local clock.

Video timestamps were also changed to use exact rational frame-rate math rather than repeatedly adding a truncated integer nanosecond interval.

```text
video timestamp =
    shared receiver epoch
    + video tick count × FPS denominator × 1,000,000,000
      / FPS numerator
```

This prevents tiny accumulated timing error at fractional rates such as 60000/1001.

\---

## Shared-Clock Validation

### Initial shared-clock test

* Duration: approximately **5.5 minutes**
* All three sources reported the same epoch:
  * **55033763614600 ns**
* DistroAV output video versus desktop audio: approximately **+0.015 ms/minute**
* DistroAV output video versus microphone: approximately **+0.012 ms/minute**
* OBS-selected video versus desktop audio: approximately **+0.024 ms/minute**
* OBS-selected video versus microphone: approximately **+0.020 ms/minute**
* Desktop audio versus microphone: effectively zero
* Repeated video frames: **21**
* Recovered repeats: **21**
* Final repeat debt: **0**
* NDI-reported dropped frames: **0**

This already reduced the previous **4.6–5.2 ms/minute** separate-source drift by roughly two orders of magnitude.

### 26.5-minute shared-clock test

* DistroAV output video versus desktop audio: approximately **+0.0007 ms/minute**
* DistroAV output video versus microphone: approximately **-0.0004 ms/minute**
* Desktop audio versus microphone: approximately **-0.0011 ms/minute**
* OBS-selected video versus audio: approximately **+0.002 to +0.003 ms/minute**
* Repeated video frames: **93**
* Recovered repeats: **93**
* Final repeat debt: **0**
* NDI-reported dropped frames: **0**

The raw values moved slightly between samples, but no sustained movement comparable to the earlier **4.6–5.2 ms/minute** regression remained.

### Shared-clock result

The shared process-wide receiver epoch corrected the separate-source clock-domain problem. Video, desktop audio, and microphone could remain separate DistroAV source instances while staying on one receiver-owned OBS timeline.

\---

## Long Buffered Test: OBS Downstream Video Jump

A later long run showed that DistroAV's submitted audio and video remained aligned, but OBS-selected video experienced a one-time downstream delay increase.

### 108-minute test

For approximately the first **106.4 minutes**:

* OBS-selected video stayed approximately **30–31 ms** behind DistroAV-submitted video
* The downstream gap remained stable
* DistroAV output video versus desktop audio: approximately **-0.0012 ms/minute**
* DistroAV output video versus microphone: approximately **+0.0025 ms/minute**
* Desktop audio and microphone remained aligned
* Repeat debt returned to zero
* NDI-reported dropped frames remained zero

At approximately **106.4 minutes**:

* OBS-selected video suddenly moved approximately **350 ms** farther behind
* Selected video then remained approximately **381 ms behind** DistroAV-submitted video
* The DistroAV output boundary itself did not show a matching A/V jump

### Interpretation

This localized the persistent jump after `obs_source_output_video(...)`, inside OBS's asynchronous video buffering and selection path.

It also matched the practical observation that the NDI feed could remain current outside OBS while the OBS preview or recording path fell behind.

\---

## Automatic Unbuffered OBS Video

DistroAV's Lowest Latency mode already enables:

```cpp
obs_source_set_async_unbuffered(obs_source, true);
```

Testing showed that this prevents OBS from keeping a stale queue of old asynchronous video frames after a receiver stall.

Receiver-Paced mode was therefore updated so OBS async-video unbuffering is enabled automatically whenever Receiver-Paced mode is active.

This is separate from the NDI decode/color-format latency option. Receiver-Paced mode forces unbuffered OBS video without necessarily forcing all other Lowest Latency decode behavior.

The intended failure behavior changes from:

```text
receiver disturbance
→ stale OBS video backlog
→ permanent added delay
```

to:

```text
receiver disturbance
→ temporary repeat/drop activity
→ return to normal video delay
```

\---

## Lowest Latency Validation

### 22.7-minute normal test

* Duration: **22.7 minutes**
* Downstream selected-video gap at start: approximately **15.44 ms**
* Downstream selected-video gap at end: approximately **15.63 ms**
* Long-term trend: approximately **+0.002 ms/minute**
* Large persistent downstream jumps: **0**
* Repeated video frames: **41**
* Recovered repeats: **41**
* Final repeat debt: **0**

No measurable OBS-preview drift developed relative to DistroAV's submitted video.

### 61.7-minute stress test

The receiver was deliberately disturbed during the final portion of the run.

* Total duration: approximately **61.7 minutes**
* Normal downstream selected-video gap: approximately **15.4 ms**
* Long-term trend: approximately **+0.0025 ms/minute**
* Largest temporary disturbance:
  * Occurred at approximately **54.82 minutes**
  * Peak gap: approximately **30.6 ms**
  * Recovery time: approximately **0.27 seconds**
* Permanent added video delay: **0**
* Persistent downstream jump events: **0**
* Repeated video frames: **582**
* Recovered repeats: **582**
* Final repeat debt: **0**
* NDI-reported dropped video frames: **0**

The repeats were concentrated mainly during the deliberate stress period. They occurred in bursts rather than as a constant repeat rate.

Diagnostic samples commonly showed bursts of three to six repeats, with a maximum observed sampled burst of eight.

\---

## Sender-Overload Control

The sender was deliberately overloaded at 4K using NVENC P7.

Observed sender-side stress included:

* OBS rendering lag: approximately **10.4%**
* OBS encoding lag: approximately **18.1%**
* Hundreds of reported sender-side frame losses

Despite the overload, A/V timing recovered afterward.

This falsified the simpler theory that every missing sender frame necessarily creates one permanent frame of receiver-side A/V delay.

\---

## Updated Interpretation of Repeated Frames

A repeated FrameSync video image means the same underlying NDI video identity was returned for more than one receiver video tick.

At 60 FPS, one repeated display interval is approximately:

```text
16.7 ms
```

A repeat can therefore produce a small visible motion hitch.

However, in the completed tests, repeated images did not:

* Accumulate into long-term A/V drift
* Leave unrecovered repeat debt
* Create permanent downstream video delay
* Correspond one-for-one with permanently lost sender frames

With OBS async video unbuffered, disturbances produced temporary repeat/drop activity and then returned to the normal delay instead of preserving a stale queue.

\---

## Updated Validation Summary

|Test|Mode|Duration|Primary result|
|-|-|-:|-|
|Stock control|Stock Direct|60.775 min|-109.540 ms total movement, approximately -1.802 ms/min|
|Receiver-Paced long test|Receiver-Paced|96.079 min|-0.188 ms output movement, approximately -0.0020 ms/min|
|Separate-source regression|Independent Receiver-Paced clocks|~14.5 min|Video drifted approximately 4.6–5.2 ms/min relative to both audio sources|
|Combined-source control|Video + embedded desktop audio|~4.8 min|Video/audio remained near zero; separate mic stayed within ~0.1 ms|
|Initial shared clock|Shared Receiver-Paced epoch|~5.5 min|All sources used one epoch; drift reduced by roughly two orders of magnitude|
|Shared-clock validation|Shared Receiver-Paced epoch|26.5 min|DistroAV output relationships remained around 0.001 ms/min or less|
|Buffered downstream test|Shared clock, buffered OBS video|~108 min|One permanent ~350 ms OBS-selected-video jump after ~106.4 min|
|Unbuffered normal test|Shared clock + unbuffered OBS video|22.7 min|No persistent jump; downstream gap remained near 15.5 ms|
|Unbuffered stress test|Shared clock + unbuffered OBS video|61.7 min|Largest temporary disturbance recovered in ~0.27 s with no permanent delay|

\---

## Updated Pass Criteria

The final receiver-clock implementation is considered successful when:

* Stock behavior reproduces a consistent multi-millisecond-per-minute drift slope
* Receiver-Paced output timing stays bounded around its initial relationship
* Separate Receiver-Paced source instances report and use one shared epoch
* Video, desktop audio, and microphone remain aligned as separate source instances
* Direct DistroAV output drift remains below **±0.05 ms/minute**
* OBS-selected video does not gain a persistent downstream delay after a disturbance
* FrameSync repeat debt returns to zero
* NDI drop counters remain zero unless an external disturbance is intentionally introduced
* Rebuilding the NDI receiver resets source-local scheduler state cleanly
* A long recording remains visibly synchronized when checked against an external flash/tone reference

The completed stock, 96-minute, shared-clock, Lowest Latency, and stress tests met the timing-related criteria in this environment.

\---

## Updated Known Limitations

The final build still occasionally repeats an NDI video image on consecutive OBS ticks.

This appears to be a motion-smoothness issue rather than an accumulating A/V-sync issue.

The completed tests do not yet prove:

* Correct behavior on every supported frame rate
* Correct behavior at sample rates other than 48 kHz
* Correct behavior on macOS or Linux
* Correct behavior with every NDI bandwidth and color-format setting
* Correct behavior under every GPU, network, or OBS overload scenario
* Whether OBS async unbuffering should become the upstream default for this mode
* Whether the shared receiver epoch should be process-wide, OBS-instance-wide, or owned by a more formal synchronization service

\---

## Updated Files to Attach

* This `REPRODUCTION.md`
* Stock 60.775-minute CSV
* Receiver-Paced 96.079-minute CSV
* Separate-source regression CSV
* Combined-source control CSV
* Initial shared-clock CSV
* 26.5-minute shared-clock CSV
* 108-minute buffered downstream-jump CSV
* 22.7-minute Lowest Latency CSV
* 61.7-minute Lowest Latency stress CSV
* Sender-overload OBS log
* Receiver OBS logs
* Exact minimal source diff
* Analysis script and commands
* Screenshots of sender and receiver source settings
* Short recording showing stock drift
* Long recording showing final behavior
* Commit hashes for the research and minimal branches

\---

## Updated Questions for DistroAV Maintainers

1. Is a process-wide shared receiver epoch the correct ownership level for separate DistroAV source instances?
2. Should Receiver-Paced mode remain a selectable public mode, become an internal FrameSync implementation detail, or replace the affected path?
3. Are there NDI FrameSync timing guarantees that should change the bounded catch-up and repeated-frame policy?
4. Should newly created Receiver-Paced sources join at the next audio block/video tick as implemented?
5. Is automatically enabling `obs_source_set_async_unbuffered(..., true)` appropriate for Receiver-Paced mode?
6. Should NDI decode/color-format latency remain independent from OBS async-video buffering?
7. Should exact rational FPS timing use the OBS numerator and denominator directly throughout this path?
8. Which diagnostics should remain in a production implementation after the research probes are removed?
9. Which frame rates, sample rates, operating systems, and source layouts should be tested before upstream integration?
10. Would maintainers prefer a minimal patch containing only the fix, or the larger research branch with selectable controls and diagnostics?

\---

## Updated Final Conclusion

The original setup repeatedly accumulated approximately **50 ms of A/V drift every 25 minutes**. A formal stock capture later measured **-109.540 ms over 60.775 minutes**, or approximately **-1.802 ms/minute**.

The first Receiver-Paced implementation reduced the original output drift to approximately **-0.0020 ms/minute over 96.079 minutes**, but separate source instances exposed a new **4.6–5.2 ms/minute** disagreement because they used independent local receiver clocks.

Changing all Receiver-Paced source instances to one shared process-wide epoch reduced that separate-source movement to approximately **0.001 ms/minute or less** at the DistroAV output boundary.

A later 108-minute test localized one persistent approximately **350 ms** jump to OBS's downstream asynchronous video path after DistroAV had already submitted correctly timed video.

Automatically enabling unbuffered OBS async video for Receiver-Paced mode prevented that failure in later tests. During the **61.7-minute stress run**, the largest temporary downstream delay recovered in approximately **0.27 seconds** and left no permanent added latency.

On this tested system, the final combination of:

* Receiver-generated audio and video timestamps
* One shared process-wide receiver epoch
* Exact rational video timing
* Bounded deadline catch-up
* NDI FrameSync for media selection
* Automatic unbuffered OBS async video

appears to solve both the long-term A/V rate drift and the persistent OBS-side video-backlog problem.

The remaining known issue is occasional repeated video imagery during timing disturbances. It may create a brief one-frame motion hitch, but every logged repeat recovered, final repeat debt returned to zero, and no completed test showed repeats accumulating into lasting A/V desynchronization.

