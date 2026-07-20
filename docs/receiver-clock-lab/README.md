# DistroAV Receiver Clock Lab

This branch is an experimental DistroAV 6.2.1 fork for testing NDI A/V clock behavior inside OBS. It does not combine audio tracks and does not alter DistroAV output features.

## What it changes

Receiver-Paced mode uses NDI FrameSync for frame selection, but replaces incoming sender timestamps with timestamps generated from OBS's local monotonic clock.

All Receiver-Paced source instances share one process-wide clock origin. A video-only source, desktop-audio source, and mic source therefore write timestamps onto the same receiver timeline instead of starting three private clocks.

Receiver-Paced video is also always submitted to OBS as unbuffered async video. This prevents OBS's second video queue from slowly accumulating delay or remaining late after a system hitch. The normal Latency dropdown still controls the NDI receiver color-format choice; Receiver-Paced mode only forces the OBS unbuffered behavior.

## Modes

- **Stock DistroAV: direct receive** - unchanged DistroAV direct capture path.
- **Stock DistroAV: existing FrameSync** - unchanged DistroAV FrameSync reference path.
- **Receiver Clock Lab: OBS-paced FrameSync** - shared receiver clock, receiver-generated timestamps, bounded catch-up, and unbuffered OBS video.

## Measured results

| Test | Measured drift |
|---|---:|
| Stock single-source DistroAV | about 1.8 to 2.0 ms/min |
| First receiver-paced single-source test | about 0.001 ms/min |
| Separate receiver-paced sources before shared clock | about 4.6 to 5.2 ms/min |
| Separate sources after shared clock | about 0.0004 to 0.0007 ms/min at DistroAV output |
| Lowest-latency OBS-selected video tests | about 0.002 to 0.0025 ms/min, with no persistent jumps |

The remaining repeat counter describes temporary FrameSync reuse of a source frame. Recovered repeat debt does not create long-term delay, though a clustered burst can still appear as a short motion hitch.

## Files

- [IMPLEMENTATION.md](IMPLEMENTATION.md) - every source-code and project change from stock DistroAV 6.2.1.
- [TESTING.md](TESTING.md) - build, setup, logging, and validation procedure.
