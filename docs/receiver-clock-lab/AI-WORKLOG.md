# AI-assisted investigation worklog

This experiment was developed through an AI-assisted, evidence-first workflow over an extended period of testing and iteration. The human operator supplied the real two-computer OBS/NDI environment, repeated long-duration observations, controlled single-variable tests, recordings, and exported timing captures. The AI assisted with source review, implementation ideas, instrumentation design, statistical analysis, and translating the observed behavior into testable hypotheses.

The investigation did not begin with the receiver-clock solution. The first goal was simply to counter the visible drift well enough to keep long recordings synchronized.

## Early corrective experiments

The first experimental plugins treated the drift as something that had already happened and needed to be corrected downstream.

One approach measured the changing A/V offset and adjusted the audio rate by small PPM amounts. If audio appeared to be moving ahead, the plugin could slightly slow or speed the delivered audio so the offset moved back toward its learned baseline.

A later approach also experimented with video-side timing adjustments. The working questions at that stage were practical:

- Is it better to correct the audio clock or the video clock?
- How do we know whether audio is rushing or video is falling behind?
- What clock are we treating as real time?
- Why does resetting the NDI receiver immediately bring sync back close to normal?

These plugins were useful because they proved that the offset could be measured and influenced, but they were still reacting to drift after it accumulated. They did not yet explain where the drift originated.

## Moving from correction to measurement

The next step was to stop relying only on visual judgment and build ways to track the offset over time.

The test tools began recording the video and audio timestamps OBS exposed through its source and audio callbacks, along with `os_gettime_ns()` observations. The measurements were projected into a common local time domain so the video-minus-audio relationship could be graphed over long captures.

This produced practical questions such as:

- Is the offset moving steadily, or is it changing in occasional jumps?
- Does the measured slope match the visible drift in the recording?
- Does changing FrameSync, hardware acceleration, source timing, network timing, or bandwidth change the slope?
- Is the plugin measuring actual media drift, OBS buffering, or callback scheduling jitter?
- When the receiver is rebuilt, which timing state needs to be cleared?

The operator repeatedly ran long-duration tests, changed one variable at a time, and compared the measured slope with the recorded A/V result. Through that process, the measurement tools became more important than the original correction logic.

## Testing each boundary of the pipeline

Once the drift could be measured reliably, the investigation shifted from “how do we correct this?” to “at exactly which boundary does the offset begin changing?”

Custom DistroAV test builds were created to observe the pipeline at multiple points:

1. Incoming NDI audio and video timing
2. DistroAV-captured audio and video timing
3. Timestamps passed through `obs_source_output_audio` and `obs_source_output_video`
4. Video timing selected downstream by OBS
5. Filtered OBS mixer-audio timing
6. Queue depth, repeated frames, empty pulls, dropped frames, and scheduling catch-ups

Representative questions included:

- If both streams begin close to synchronized after a receiver rebuild, where does the offset start accumulating?
- Does the drift already exist in the incoming NDI timestamps, or does it appear between DistroAV output and OBS-selected video?
- Is audio actually running fast, is video being selected late, or are the streams following different clocks?
- Is FrameSync controlling output cadence, or is it only selecting and resampling the media returned to DistroAV?
- Would changing only the video timestamp work, or must the receive loop itself be paced from a receiver-owned clock?
- Can the root receiver problem be fixed instead of applying downstream PPM correction or periodic resets?

The important methodological correction was to stop treating a near-zero calculated “corrected deviation” as proof. The long capture was decomposed at every observable boundary. That showed the audio handoff remained stable while the dominant accumulating offset appeared in the video path between DistroAV output and OBS-selected timing.

The Stock Direct Receive control later confirmed this result. Its filtered audio relationship changed by essentially zero, while OBS-selected video moved by more than 100 ms relative to the video timing DistroAV emitted.

## Finding the core issue

The key finding was that the problem was not simply “audio running too fast” or “video needing a timestamp correction.”

The incoming NDI A/V relationship moved only slightly. The DistroAV audio handoff into OBS remained stable. The large accumulating error appeared after DistroAV emitted video and before OBS selected that video for presentation.

That meant the system was allowing two different timing authorities to interact:

- NDI sender-derived timestamps described when the media existed on the sending system.
- OBS on the receiving system selected and presented video according to its own local cadence.
- Audio was consumed according to the receiver’s audio clock.
- Video did not have an equivalent receiver-owned scheduler that kept its output cadence tied to that same local timeline.

The result was a small clock mismatch that did not appear as a single obvious failure. Instead, it accumulated gradually as OBS continued consuming audio and selecting video according to receiver-side timing while the outgoing media timestamps still reflected sender-side timing.

This also explained several observations that had seemed disconnected earlier:

- Restarting the receiver restored sync because the receive path and timing relationship were rebuilt from a fresh starting point.
- Matching both systems to 48 kHz did not solve the issue because nominal sample-rate settings do not make two independent hardware clocks identical.
- Audio PPM correction could counter the symptom because it altered one stream to chase the accumulating error, but it did not remove the underlying mixed-clock design.
- Changing only a video timestamp was insufficient if the receive loop itself continued to pull and schedule frames from the wrong cadence.
- FrameSync could select or resample media without necessarily becoming the clock that governed when OBS received each frame.

## How that led to the receiver-clock design

Once the failing relationship was isolated, the design changed from a feedback controller into a scheduling fix.

Instead of measuring drift after it appeared and then correcting audio or video, the new design establishes one receiver-owned timeline at ingestion.

A single local epoch is created from `os_gettime_ns()` when the NDI receiver and FrameSync objects are built. Both media streams then derive their OBS timestamps from that same epoch:

```text
audio timestamp =
    receiver epoch
    + duration of cumulative delivered audio samples

video timestamp =
    receiver epoch
    + duration of elapsed OBS video ticks
```

The receiver also owns the delivery cadence:

- Audio is pulled according to OBS audio deadlines.
- Audio time advances from the actual number of samples delivered at the OBS sample rate.
- Video is pulled according to OBS frame deadlines.
- Video time advances from receiver-side video ticks.
- Late audio work can use bounded catch-up.
- Missed video ticks are skipped so scheduler lateness does not become permanent accumulated delay.
- The shared epoch resets whenever the NDI receiver is rebuilt.

NDI FrameSync still performs the work it is suited for: selecting source media and converting audio samples between independent clocks. But it no longer acts as the timestamp authority for OBS output. DistroAV owns the receiver-side scheduler and generates timestamps that match the clock OBS is actually using.

This is the core distinction between the earlier plugins and the final design:

- The earlier plugins measured a growing downstream error and tried to steer it back toward zero.
- The receiver-clock design prevents the error from accumulating by putting both streams onto one receiver-owned timeline before they enter OBS.

## Validating the core fix

The Stock Direct Receive control and Receiver-Paced validation were designed to test that exact theory.

In the control:

- The incoming capture relationship moved by only a few milliseconds.
- The audio handoff remained effectively unchanged.
- OBS-selected video accumulated more than 100 ms of movement relative to DistroAV video output.
- End-to-end drift measured approximately 1.8 ms/minute.

In Receiver-Paced mode:

- The incoming capture relationship still moved by a similar amount.
- DistroAV output timing remained nearly fixed.
- OBS-selected video remained aligned with DistroAV video output.
- The end-to-end relationship moved by only a fraction of a millisecond over a longer test.

That result matters because the receiver-clock design did not merely hide the incoming clock movement. It prevented that movement from becoming progressive A/V desynchronization inside OBS.

The control and validation therefore support the full chain of reasoning:

1. The drift was real and repeatable.
2. It was not caused by the OBS audio handoff.
3. The dominant accumulation occurred in the downstream video timing relationship.
4. Stock DistroAV allowed sender timing and receiver timing to remain mixed.
5. A shared receiver-owned scheduler removed the accumulating error.
6. The fix worked without downstream audio PPM correction, periodic source resets, or a feedback controller chasing the drift.

## Human and AI collaboration

I began this project without knowing how to code and with no prior OBS plugin-development experience. I was also unfamiliar with DistroAV’s receive path, FrameSync, clock domains, and how audio and video timestamps moved through OBS.

I relied heavily on AI to write most of the code, review the existing source, build the instrumentation, analyze captures, and propose implementation changes. I did not independently author or fully understand every line of the experimental code as it was first produced.

My role was to identify the real-world problem, suggest what should be tested, run the builds in the actual two-PC environment, change one variable at a time, and report what happened. I supplied the repeated drift observations, receiver-reset behavior, recordings, CSV captures, and comparisons with NDI Studio Monitor. I also challenged explanations that did not match the real system and directed the investigation toward measuring each stage of the pipeline separately.

The earlier plugins were not the final fix, but their correction logic, logging, and reset behavior led to the receiver-clock design. The final result came from combining AI-assisted coding and source analysis with repeated hands-on testing and evidence from the real setup.

## Purpose of this branch

This branch is intentionally implemented as conventional DistroAV source code. The earlier plugins are part of the investigation history, but maintainers do not need to understand or integrate them to review this change.

The final branch is intended to provide:

- A reproducible Stock Direct Receive control
- A receiver-paced comparison mode
- Boundary-by-boundary CSV diagnostics
- A repeatable analysis script
- A focused implementation that can be reduced to a production-sized DistroAV change

The goal is not to preserve every experimental idea. The goal is to show how the investigation moved from compensating for drift, to measuring it, to isolating it, and finally to fixing the core receiver scheduling problem that allowed it to accumulate.
