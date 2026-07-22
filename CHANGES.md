# Implementation summary

## Suspected failure path instrumented

The strongest current hypothesis is not a second clock-rate divergence. It is growing latency after the receiver-owned timestamps are generated. The new build therefore measures three boundaries independently:

1. DistroAV output video versus DistroAV output audio.
2. OBS-selected video versus DistroAV-submitted video.
3. OBS post-filter audio versus DistroAV-submitted audio.

The final OBS-side relationship is then measured as OBS-selected video versus post-filter audio. Ten-minute history identifies which boundary is actually moving.

## No timing behavior added

The patch does not alter receiver-paced timestamp generation, audio sample accounting, rational video tick generation, the shared process epoch, or OBS async-unbuffered behavior. All new code is observation, presentation, logging, registry access, or diagnostic-filter lifecycle repair.

## Sampling and retention

The existing 250 ms recorder is changed to one second because the requested test is several hours long and sub-second diagnostic resolution is unnecessary. The existing 43,200-row capacity therefore retains approximately twelve hours instead of three hours.
