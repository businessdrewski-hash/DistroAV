# Reproducing DistroAV Receiver A/V Drift

> **Test author:** Andrew Carriker  
> **Original test date:** July 19, 2026  
> **Document update:** July 20, 2026  
> **Research repository:** https://github.com/businessdrewski-hash/DistroAV  
> **Research branch:** `receiver-clock-lab`  
> **Upstream repository:** https://github.com/DistroAV/DistroAV  
> **Stock base commit:** `038d9d6bf8bff36018ffac8ddc3d15f3bb3ef9e8`  
> **Final research build:** DistroAV Receiver Clock Lab `6.2.1.2`

## Purpose

This document describes how to reproduce and measure the original progressive NDI A/V drift in a two-PC OBS setup.

It intentionally focuses on:

- the tested hardware and software environment.
- the exact sender and receiver configuration.
- the minimum reproduction procedure.
- the measurements that distinguish progressive drift from a static offset.
- the files and analyzer output needed for a useful report.

Implementation details are documented in [IMPLEMENTATION.md](IMPLEMENTATION.md).

The complete experiment history and validation results are documented in [VALIDATION.md](VALIDATION.md).

## Reproduced failure

After a fresh OBS launch or NDI receiver rebuild, A/V sync began close to its baseline. Audio then progressively moved ahead of video at approximately:

```text
50 ms every 25 minutes
```

Equivalent rate:

```text
approximately 2 ms/minute
```

A formal stock DistroAV control measured:

- duration: **60.775 minutes**
- starting offset: **-54.893150 ms**
- final offset: **-164.433400 ms**
- total movement: **-109.540250 ms**
- linear slope: **-30.040 ppm**
- equivalent drift: **-1.8024 ms/minute**

Rebuilding only the receiver returned the relationship close to its original baseline.

A one-time static A/V offset does not demonstrate this bug. The defining evidence is a sustained slope over time that resets after receiver reconstruction.

## 1. Test environment

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
- Stock baseline: DistroAV 6.2.1
- Experimental logging build: DistroAV Receiver Clock Lab 6.2.1.1 or later
- NDI Runtime: 6.3.2.0
- OBS audio sample rate: 48 kHz

### 1.3 Network

- Connection: Ethernet
- Negotiated link speed: 1 Gbps
- Router/switch: TP-Link Deco X55
- Sender NIC: Realtek PCIe Ethernet Controller
- Receiver NIC: Realtek Gaming 2.5GbE Family Controller

## 2. OBS and NDI settings

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
- Selected NDI source: `DrewskiGame`
- Baseline timing mode: stock DistroAV direct receive
- FrameSync: disabled for the primary stock control
- DistroAV hardware acceleration: Off
- Recording active during tests: Yes
- Final recordings checked in Adobe Premiere against the synchronization reference

The original drift was also observed while varying FrameSync, hardware acceleration, source timing, bandwidth, and color settings. None of those changes removed the long-term slope.

## 3. Synchronization reference

Use a repeatable flash-and-tone reference that provides a visual event and an audio event at the same intended instant.

The reference used in these tests was:

```text
https://www.youtube.com/watch?v=YyZq_lEJZ2U&t=2002s
```

Small differences are difficult to judge reliably from the live OBS preview alone. Record the reference near both the beginning and end of the test and inspect the recording frame-by-frame when possible.

## 4. Basic reproduction procedure

1. Close OBS on both systems.
2. Confirm that sender and receiver OBS audio are both configured for 48 kHz.
3. Start OBS on the sender.
4. Enable the normal DistroAV NDI output on the sender.
5. Confirm the sender is transmitting `DrewskiGame`.
6. Start OBS on the receiver.
7. Add or enable the DistroAV NDI Source.
8. Select `DrewskiGame`.
9. Select the stock direct receive path.
10. Disable FrameSync for the primary baseline control.
11. Disable DistroAV hardware acceleration.
12. Fully rebuild the receiver by recreating the source, changing the source away and back, or restarting receiver OBS.
13. Enable Receiver Clock Lab diagnostics if using the instrumented build.
14. Play and record the flash-and-tone reference.
15. Note the initial A/V relationship.
16. Leave the source running continuously for at least 25–30 minutes.
17. Prefer a 60–120 minute run for a strong slope measurement.
18. Do not reset the NDI source, restart OBS, or change receiver timing settings during the run.
19. Play and record the same flash-and-tone reference again.
20. Export the Receiver Clock Lab CSV.
21. Save sender and receiver OBS logs.
22. Record the final manually observed A/V relationship.
23. Calculate the measured slope from the CSV rather than relying only on the final sample.
24. Rebuild only the receiver.
25. Confirm whether the A/V relationship returns close to its original baseline.

The issue is reproduced when:

- the measured A/V relationship moves consistently in one direction.
- the movement is substantially larger than normal sample-to-sample jitter.
- the fitted slope remains present over a long interval.
- rebuilding only the receiver restores the relationship close to baseline.

## 5. Diagnostic export

Receiver Clock Lab writes the CSV to:

```text
%APPDATA%\obs-studio\plugin_config\distroav\receiver-clock-lab.csv
```

Open the DistroAV source properties and press:

```text
Export receiver-clock-lab.csv
```

Rename the file immediately after each source export so another export does not overwrite it.

For a single stock source, a useful filename is:

```text
stock-direct-60min.csv
```

For separate-source tests, identify the source represented by each file:

```text
receiver-paced-video.csv
receiver-paced-desktop-audio.csv
receiver-paced-mic.csv
```

## 6. Primary measurements

### 6.1 DistroAV output relationship

```text
output_video_minus_output_audio_projected_ns
```

This compares the video and audio timestamps DistroAV submits to OBS after projecting both observations to a common current-time domain.

Use this metric to determine whether progressive movement is already present at the DistroAV output boundary.

### 6.2 Downstream OBS relationship

```text
selected_video_minus_filtered_audio_projected_ns
```

This compares video selected by OBS's asynchronous video path against audio observed after the OBS audio filter/mixer boundary.

Use this metric to determine whether timing is stable at DistroAV output but becomes delayed later inside OBS.

### 6.3 Submitted-to-selected video gap

The diagnostics also compare:

```text
OBS-selected video timestamp
minus
DistroAV-submitted video timestamp
```

A stable nonzero value can represent normal fixed buffering.

A sudden increase that remains elevated indicates a persistent downstream OBS video backlog rather than gradual clock-rate drift.

## 7. Additional fields to retain

The logger records:

- incoming NDI audio and video timestamp/timecode.
- DistroAV output audio and video timestamps.
- OBS-selected video timestamps.
- OBS-filtered audio timestamps.
- receiver epoch.
- cumulative audio sample count.
- cumulative video tick count.
- audio and video deadline error.
- audio and video catch-up counters.
- empty audio and video pulls.
- repeated video identities.
- consecutive repeats.
- recovered repeats.
- current and maximum repeat debt.
- skipped source-video identities.
- NDI receive queue depth.
- NDI total and dropped frame counters.
- submitted-to-selected downstream video gap.
- large downstream gap-step events.

Do not use one counter alone as proof of the failure. The most useful report includes the fitted timing slopes, queue/drop state, and any discrete gap-step events.

## 8. CSV analysis

The repository includes:

```text
tools/analyze-receiver-clock-log.py
```

Run it from the repository root:

```powershell
python .\tools\analyze-receiver-clock-log.py "C:\path\to\receiver-clock-lab.csv"
```

Example:

```powershell
python .\tools\analyze-receiver-clock-log.py "$env:APPDATA\obs-studio\plugin_config\distroav\receiver-clock-lab.csv"
```

The analyzer reports:

- test duration.
- selected timing mode.
- starting and final A/V offset.
- total offset movement.
- linear drift slope.
- ppm.
- empty pulls.
- audio and video catch-ups.
- repeated frames and recovery.
- NDI-reported drops.
- maximum queued frames.
- downstream video gap.
- large or persistent downstream jumps.

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
-30.040 ppm × 0.06 = -1.8024 ms/minute
```

Attach both the raw CSV and the analyzer summary. Do not rely only on a manually inspected final row.

## 9. Expected stock result

On the documented system, a successful stock reproduction should resemble:

- duration of at least 25–30 minutes.
- audio progressively moving ahead of video.
- slope near **-1.8 to -2.0 ms/minute** in the tested configuration.
- no requirement for NDI-reported packet or frame drops.
- a relationship that returns near baseline after receiver reconstruction.

The exact static starting offset may differ between systems. The important value is the change over time.

A different machine may reproduce the same class of bug at a different rate. Report the fitted slope rather than requiring an exact match to **-1.8024 ms/minute**.

## 10. Controls that did not remove the original slope

The original investigation tested:

- FrameSync enabled and disabled.
- DistroAV hardware acceleration enabled and disabled.
- NDI timestamp and source-timecode timing choices.
- bandwidth and color-format changes.
- both systems configured for 48 kHz.
- receiver reconstruction.

Only receiver reconstruction consistently returned the relationship close to its original baseline. The other variables did not eliminate the progressive movement.

## 11. What to submit with a reproduction report

Include:

1. Sender and receiver hardware.
2. Windows, OBS, DistroAV, and NDI Runtime versions.
3. OBS video and audio settings on both systems.
4. Exact DistroAV sender and receiver settings.
5. Test duration.
6. Initial and final flash/tone observations.
7. Raw diagnostic CSV.
8. Analyzer summary.
9. Sender and receiver OBS logs.
10. Whether receiver reconstruction restored baseline.
11. Whether DistroAV output drifted, OBS downstream drifted, or both.
12. Whether NDI drop or queue counters changed.
13. Any scene changes, RDP use, window resizing, GPU overload, or other disturbances during the run.

## 12. Reproduction limitations

The documented reproduction environment does not establish that the same rate will occur:

- at every supported frame rate.
- at sample rates other than 48 kHz.
- on macOS or Linux.
- with every NDI bandwidth or color format.
- with every sender, receiver, NIC, switch, or router.
- under every CPU, GPU, network, or OBS load.

A clean failure to reproduce should include the same measurements. “It looked synchronized” is not enough to disprove a slow drift that may require a long run and fitted slope to detect.
