# Build and test

## Build

Use the repository's normal Windows GitHub Actions workflow or local DistroAV build process. The experimental installer identifies itself as `DistroAV Receiver Clock Lab 6.2.1.2`.

A code change is not considered validated until the Windows build completes and the installer loads in OBS.

## Basic setup

For each NDI Source under test:

1. Select **Receiver Clock Lab: OBS-paced FrameSync**.
2. Enable **Capture receiver-clock diagnostics**.
3. Choose the intended NDI source and bandwidth.
4. The Receiver-Paced mode automatically uses unbuffered OBS async video. The Latency dropdown may still be changed to test the NDI color-format path.

Use separate sources when testing the shared domain:

- source 1: video, audio disabled.
- source 2: desktop audio-only.
- source 3: mic audio-only.

## Export

Open each source's properties and press **Export receiver-clock-lab.csv**. Rename each file immediately so the next export does not overwrite it.

Run:

```powershell
py .\tools\analyze-receiver-clock-log.py .\receiver-clock-lab.csv
```

## Pass criteria

A normal test should show:

- DistroAV output video versus both audio sources remaining flat.
- OBS-selected video versus DistroAV-submitted video remaining near a stable baseline.
- no persistent downstream gap step.
- zero NDI drops in a clean network test.
- repeat debt returning to zero after temporary repeats.

For a quick validation, run 15 to 30 minutes. For final confidence, run at least two hours.

## Stress test

To test recovery without waiting for a random jump, create several short receiver-side stalls, then leave OBS untouched for 20 to 30 seconds after each one. Examples include brief RDP interaction, scene switching, window resizing, or a short receiver GPU load.

Expected behavior:

```text
stable downstream gap -> temporary increase -> return to baseline
```

A gap that rises and remains elevated indicates that stale OBS video is still being retained.

## Known remaining behavior

NDI FrameSync can occasionally return the same source-frame identity on two receiver ticks. The logger records repeats, clusters, later source skips, and recovered debt. A recovered repeat does not accumulate A/V delay, but a dense burst may still look like a short video hitch.
