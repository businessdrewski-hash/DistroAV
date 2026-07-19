# DistroAV A/V Drift Reproduction and Receiver-Paced Validation

> **Test author:** Andrew Carriker  
> **Date:** July 19, 2026  
> **Review repository / branch:** https://github.com/businessdrewski-hash/DistroAV/tree/receiver-clock-lab  
> **Comparison against stock DistroAV 6.2.1:** https://github.com/businessdrewski-hash/DistroAV/compare/6.2.1...receiver-clock-lab  
> **Test build:** DistroAV Receiver Clock Lab 6.2.1.1  
> **Review-branch commit:** Add the current commit SHA after the branch is pushed

## Summary

This report compares two tests performed in the same two-computer OBS/NDI environment:

1. **Control:** Stock DistroAV Direct Receive, with FrameSync disabled.
2. **Validation:** The experimental Receiver-Paced / OBS-Paced receive mode.

The Stock Direct Receive control reproduced the previously observed progressive A/V drift. During the **60.78-minute control**, the downstream OBS-selected video-minus-audio relationship moved by **-109.540 ms**, equivalent to approximately **-1.802 ms/minute**. The negative movement means audio became increasingly early relative to video.

During the **96.08-minute Receiver-Paced validation**, the same downstream relationship moved by only **-0.090 ms**, equivalent to approximately **-0.00094 ms/minute**.

### Primary control-versus-validation result

| Test | Receive mode | Duration | Starting downstream offset | Final downstream offset | Total movement | Drift rate |
|---|---|---:|---:|---:|---:|---:|
| **Control** | Stock DistroAV Direct Receive | 60.78 min | -54.893 ms | -164.433 ms | **-109.540 ms** | **-1.802 ms/min** |
| **Validation** | Receiver-Paced / OBS-Paced | 96.08 min | -27.451 ms | -27.542 ms | **-0.090 ms** | **-0.00094 ms/min** |

The formal control closely matches the earlier real-world observation of approximately **50 ms every 25 minutes**, or about **2 ms/minute**. The Receiver-Paced test reduced the measured downstream drift rate from approximately **1.80 ms/minute** to effectively zero in this test environment.

### Boundary-by-boundary comparison

| Measured relationship | Stock Direct control change | Receiver-Paced change | Interpretation |
|---|---:|---:|---|
| Incoming capture video minus capture audio | +5.969 ms | +6.564 ms | The incoming relationship moved by a similar amount in both tests |
| DistroAV output video minus output audio | +5.968 ms | -0.188 ms | Stock Direct passed the incoming timing movement downstream; Receiver-Paced held output timing nearly fixed |
| OBS-selected video minus DistroAV output video | **-115.662 ms** | +0.056 ms | The dominant control drift appeared in downstream video selection |
| Filtered OBS mixer audio minus DistroAV output audio | -0.0002 ms | +0.0004 ms | The audio handoff remained stable in both tests |
| OBS-selected video minus filtered OBS mixer audio | **-109.540 ms** | **-0.090 ms** | End-to-end control drift was reproduced and did not accumulate under Receiver-Paced timing |

This decomposition is important. The control test did not show a comparable error in the audio handoff. The dominant changing offset appeared between the video DistroAV emitted and the video timing selected downstream by OBS. The Receiver-Paced mode prevented that offset from accumulating.

---

## Test Setup

### Sender PC

- CPU: AMD Ryzen 9 9950X3D
- GPU: NVIDIA GeForce RTX 5090
- RAM: 64 GB DDR5
- Windows version: Windows 11 Pro 10.0.26200, build 26200
- OBS version: 32.1.2
- DistroAV version: 6.2.1
- NDI Runtime version: 6.3.2.0
- Audio interface: Steinberg UR22mkII
- Audio sample rate: 48 kHz

### Receiver PC

- CPU: Intel Core i5-12600KF
- GPU: NVIDIA GeForce RTX 5060
- RAM: 32 GB DDR4
- Windows version: Windows 11 Pro 10.0.26200, build 26200
- OBS version: 32.1.2
- DistroAV test build: DistroAV Receiver Clock Lab 6.2.1.1
- NDI Runtime version: 6.3.2.0
- OBS audio sample rate: 48 kHz

### Network

- Connection type: Ethernet
- Link speed: 1 Gbps
- Switch/router: TP-Link Deco X55
- Sender NIC: Realtek PCIe Ethernet Controller
- Receiver NIC: Realtek Gaming 2.5GbE Family Controller

---

## OBS and NDI Settings

### Sender

- Canvas/output resolution: 3840 × 2160
- Frame rate: 60 FPS
- Color format / space / range: NV12, Rec. 709, Limited
- Source format: HDR converted to SDR output
- OBS audio sample rate: 48 kHz
- NDI source name: `DrewskiGame`
- NDI bandwidth mode: Highest
- Audio embedded with video: Yes
- Hardware acceleration: Disabled

### Receiver

- Canvas/output resolution: 3840 × 2160
- Frame rate: 60 FPS
- OBS audio sample rate: 48 kHz
- Selected NDI source: `DrewskiGame`
- Control mode: **Stock DistroAV Direct Receive, FrameSync disabled**
- Validation mode: **Receiver-Paced / OBS-Paced**
- Hardware acceleration: Disabled
- Recording active during tests: Yes
- Recorded files were checked in Adobe Premiere to confirm the measured A/V movement

---

## Original Failure

After a fresh OBS start or NDI receiver rebuild, A/V sync began close to its normal baseline. Audio then gradually moved ahead of video.

Previously observed rate:

```text
Approximately 50 ms every 25 minutes
Approximately 2 ms/minute
```

The new Stock Direct Receive control formally reproduced the issue:

```text
Duration: 60.78 minutes
End-to-end movement: -109.540 ms
Measured drift rate: -1.802 ms/minute
```

Additional observations:

- Drift direction: Audio increasingly ahead of video
- Visible in recordings: Yes, generally noticeable after approximately 30 minutes
- OBS preview: No practical live method was available to judge the exact sync offset
- NDI Studio Monitor: No equivalent accumulating drift was observed
- Rebuilding or restarting the receiver returned the offset close to baseline
- Receiver reset behavior was repeatable
- Attempted fixes included matching both systems to 48 kHz, FrameSync enabled and disabled, hardware acceleration enabled and disabled, Source Timing, Network Timing, high and low bandwidth modes, and different color settings

---

## Test Definitions

### Control test: Stock DistroAV Direct Receive

The control used the ordinary DistroAV direct receive path:

```text
mode=0 (stock-direct)
FrameSync disabled
Receiver-Paced scheduling disabled
```

This test establishes the failure behavior without the experimental synchronization change.

### Validation test: Receiver-Paced / OBS-Paced

The validation used:

```text
mode=2 (receiver-paced)
NDI FrameSync used for media selection and audio resampling
One receiver-owned OBS clock used for scheduling and outgoing timestamps
```

This test measures whether the receiver-owned scheduler prevents the control drift.

---

## Reproduction Procedure

Use the same OBS scene, NDI sender, receiver source, resolution, frame rate, audio sample rate, and network path for both tests.

### A. Run the Stock Direct control

1. Close OBS on both systems.
2. Confirm both systems use 48 kHz audio.
3. Start OBS and NDI output on the sender.
4. Start OBS on the receiver.
5. Add or enable the DistroAV NDI source.
6. Select **Stock DistroAV Direct Receive** with FrameSync disabled.
7. Rebuild the NDI receiver by hiding and unhiding the source.
8. Start CSV diagnostics.
9. Create an initial synchronization reference using:
   https://www.youtube.com/watch?v=YyZq_lEJZ2U&t=2002s
10. Begin the receiver recording.
11. Leave the source running for at least 60 minutes.
12. Export or locate the diagnostic CSV.
13. Analyze the CSV and record the starting offset, final offset, total movement, drift slope, and counters.
14. Confirm the recorded A/V offset independently in an editor.

### B. Run the Receiver-Paced validation

1. Rebuild the receiver to clear the previous timing state.
2. Select **Receiver-Paced / OBS-Paced** mode.
3. Start a new CSV capture and receiver recording.
4. Use the same synchronization reference and test conditions.
5. Leave the test running for at least as long as the control.
6. Analyze the CSV using the same script and fields.
7. Compare the validation results directly with the Stock Direct control.

The issue is reproduced when the Stock Direct control moves consistently in one direction over time and returns close to its starting relationship after the receiver is rebuilt.

---

## What Was Changed

The primary synchronization implementation is in:

```text
src/ndi-source.cpp
```

Stock DistroAV allowed audio and video timing to remain influenced by sender-derived timing and separate receive/output scheduling behavior. NDI FrameSync could select or resample media, but that did not provide one receiver-owned scheduling timeline for both streams.

The Receiver-Paced implementation adds one local scheduling state containing:

- A receiver-owned epoch based on `os_gettime_ns()`
- The OBS audio sample rate
- The OBS video frame interval
- Total audio samples delivered
- Total receiver video ticks

Audio and video timestamps are generated from the same epoch:

```text
audio timestamp =
    receiver epoch
    + duration of cumulative delivered audio samples

video timestamp =
    receiver epoch
    + duration of elapsed OBS video ticks
```

The primary processing functions changed are:

```text
ndi_source_thread_process_audio3(...)
ndi_source_thread_process_video2(...)
```

When Receiver-Paced mode is active:

- Audio is pulled according to OBS audio deadlines
- Video is pulled according to OBS frame deadlines
- Audio timestamps advance from cumulative delivered samples
- Video timestamps advance from receiver video ticks
- Late audio pulls can use bounded catch-up
- Missed video ticks are skipped instead of allowing scheduler lateness to accumulate
- The shared receiver epoch resets whenever the NDI receiver is rebuilt
- Stock Direct and Stock FrameSync modes retain their reference behavior

Approximate synchronization-specific change:

```text
Approximately 150 lines in src/ndi-source.cpp
```

This estimate excludes CSV diagnostics, test code, documentation, and startup-crash hardening.

---

## Measurement Fields

### End-to-end synchronization field

```text
selected_video_minus_filtered_audio_projected_ns
```

This compares the OBS-selected video timing with the filtered OBS mixer-audio timing. It is the primary field used for the side-by-side control and validation result.

### DistroAV output field

```text
output_video_minus_output_audio_projected_ns
```

This compares the video and audio timestamps DistroAV directly delivers to OBS.

### Video-selection field

```text
selected_video_minus_output_video_projected_ns
```

This isolates movement between DistroAV video output and the timing selected downstream by OBS.

### Audio-handoff field

```text
filtered_audio_minus_output_audio_projected_ns
```

This isolates movement between DistroAV audio output and the filtered OBS mixer-audio probe.

### Sign convention

For video-minus-audio fields:

- A value becoming more negative means audio is moving further ahead of video.
- A value becoming more positive means video is moving further ahead of audio.
- The important drift measurement is the change over time, not the static starting offset.

CSV directory:

```text
%APPDATA%\obs-studio\plugin_config\distroav\
```

Typical CSV filename:

```text
receiver-clock-lab-<source-id>.csv
```

---

## CSV Analysis

The repository includes:

```text
tools/analyze-receiver-clock-log.py
```

From the repository root, run:

```powershell
python .\tools\analyze-receiver-clock-log.py "$env:APPDATA\obs-studio\plugin_config\distroav\receiver-clock-lab-<source-id>.csv"
```

Replace `<source-id>` with the actual CSV filename.

The script uses robust medians from the beginning and end of the test after a short warm-up. It reports:

- Test duration
- Timing mode
- Starting and final relationships
- Total relationship change
- Drift slope in ppm
- Empty pulls
- Repeated video frames
- NDI-reported dropped frames
- Catch-up counters
- Maximum queued audio and video frames

Conversion:

```text
1 ppm = 0.06 ms/minute
drift in ms/minute = reported ppm × 0.06
```

---

## Control Test Results

### Stock DistroAV Direct Receive

Source CSV:

```text
receiver-clock-lab(4).csv
```

Analyzer summary:

```text
rows=14253
duration_s=3646.520
duration_min=60.775
mode=0 (stock-direct)

capture_video_minus_capture_audio_projected_ns:
  -22.185300 -> -16.216700 ms
  change=+5.968600 ms
  slope=+1.637 ppm

output_video_minus_output_audio_projected_ns:
  -22.185450 -> -16.217250 ms
  change=+5.968200 ms
  slope=+1.637 ppm

selected_video_minus_output_video_projected_ns:
  -32.578800 -> -148.241000 ms
  change=-115.662200 ms
  slope=-31.719 ppm

filtered_audio_minus_output_audio_projected_ns:
  -0.002600 -> -0.002800 ms
  change=-0.000200 ms
  slope=-0.000 ppm

selected_video_minus_filtered_audio_projected_ns:
  -54.893150 -> -164.433400 ms
  change=-109.540250 ms
  slope=-30.040 ppm
```

Converted end-to-end drift rate:

```text
-30.040 ppm × 0.06 = approximately -1.802 ms/minute
```

Control counters:

```text
NDI dropped audio frames: 0
NDI dropped video frames: 0
Audio catch-ups: 0
Video catch-ups: 0
Repeated video frames: 0
Empty audio pulls: 0
Empty video pulls: 0
Maximum queued audio frames: 2
Maximum queued video frames: 1
```

### Control interpretation

The control reproduced the progressive desynchronization without empty pulls, NDI-reported frame drops, or audio-handoff drift.

The incoming and direct-output A/V relationships moved by approximately **+5.97 ms**, but OBS-selected video moved by approximately **-115.66 ms** relative to DistroAV video output. Because the filtered audio relationship changed by only **-0.0002 ms**, the dominant accumulating control error appeared in the downstream video path rather than the audio handoff.

---

## Receiver-Paced Validation Results

Source CSV:

```text
receiver-clock-lab(3).csv
```

Analyzer summary:

```text
rows=22544
duration_s=5764.715
duration_min=96.079
mode=2 (receiver-paced)

capture_video_minus_capture_audio_projected_ns:
  29.383400 -> 35.947050 ms
  change=+6.563650 ms
  slope=+1.139 ppm

output_video_minus_output_audio_projected_ns:
  -0.026388 -> -0.214438 ms
  change=-0.188050 ms
  slope=-0.033 ppm

selected_video_minus_output_video_projected_ns:
  -27.396849 -> -27.340632 ms
  change=+0.056217 ms
  slope=+0.010 ppm

filtered_audio_minus_output_audio_projected_ns:
  -0.002100 -> -0.001700 ms
  change=+0.000400 ms
  slope=+0.000 ppm

selected_video_minus_filtered_audio_projected_ns:
  -27.451104 -> -27.541554 ms
  change=-0.090450 ms
  slope=-0.016 ppm
```

Converted end-to-end drift rate:

```text
-0.016 ppm × 0.06 = approximately -0.00094 ms/minute
```

Validation counters:

```text
NDI dropped audio frames: 0
NDI dropped video frames: 0
Audio catch-ups: 0
Video catch-ups: 0
Repeated video frames: 262
Empty audio pulls: 0
Empty video pulls: 0
Maximum queued audio frames: 1
Maximum queued video frames: 1
```

### Validation interpretation

The incoming capture relationship still moved by **+6.564 ms**, similar to the **+5.969 ms** movement observed in the control. Under Receiver-Paced timing, that movement did not propagate into DistroAV output or into the downstream OBS-selected video-minus-audio relationship.

The end-to-end relationship moved by only **-0.090 ms** during a longer **96.08-minute** test.

---

## Additional Receiver-Paced Runs

| Test | Duration | Drift expected from historical behavior | Final DistroAV output offset | Measured output drift |
|---|---:|---:|---:|---:|
| Test A | 4.4 min | ~8.8 ms | +0.28 ms | -0.003 ms/min |
| Test B | 16 min | ~32 ms | -0.39 ms | -0.0024 ms/min |
| Test C | 28.3 min | ~57 ms | -0.35 ms | -0.0014 ms/min |
| Test D | 96.08 min | ~192 ms | -0.214 ms | -0.0020 ms/min |

These shorter tests support the longer validation but are not substitutes for the formal Stock Direct control.

---

## Pass Criteria

The Receiver-Paced test is considered successful when:

- The end-to-end offset remains bounded around its starting value
- The final end-to-end offset remains within ±2 ms of its starting value
- The absolute end-to-end drift rate remains below 0.05 ms/minute
- DistroAV output A/V timing remains bounded
- No recurring empty audio or video pulls occur
- No unexplained NDI drop counters increase
- Rebuilding the receiver resets the local scheduler cleanly
- The result is materially better than the Stock Direct control under the same conditions

The 96.08-minute Receiver-Paced validation passed these criteria.

---

## Known Limitation

The Receiver-Paced test occasionally received the same NDI video image on consecutive OBS ticks.

Latest result:

- Repeated video frames: 262
- Duration: 96.08 minutes
- Approximate rate: One repeat every 22 seconds
- Approximate share at 60 FPS: 0.076%, or about one in every 1,320 frames

A single repeated frame at 60 FPS produces an approximately 16.7 ms hold and is likely to appear as a subtle micro-stutter during smooth motion. This remains a separate video-pacing issue from the resolved progressive A/V drift.

Future work can phase-align video pull timing with the incoming NDI cadence and skip or retime late OBS ticks rather than accepting the same image twice. Repeats caused by a genuinely missing sender or network frame cannot be prevented by receiver scheduling alone.

---

## Conclusion

The **Stock DistroAV Direct Receive control** formally reproduced the original issue:

```text
60.78 minutes
-109.540 ms end-to-end movement
approximately -1.802 ms/minute
```

The **Receiver-Paced / OBS-Paced validation** produced:

```text
96.08 minutes
-0.090 ms end-to-end movement
approximately -0.00094 ms/minute
```

The control and validation experienced similar incoming capture movement, approximately **+5.97 ms** and **+6.56 ms** respectively. The control then accumulated approximately **-115.66 ms** between DistroAV video output and OBS-selected video, while its audio handoff remained effectively unchanged. The Receiver-Paced implementation held both the output and downstream relationships essentially stable.

This side-by-side result is strong evidence that a shared receiver-owned OBS scheduling timeline prevents the progressive A/V drift observed with Stock DistroAV Direct Receive in this test environment.
