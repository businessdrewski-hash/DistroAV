#!/usr/bin/env python3
# Summarize Receiver Clock Lab timing, repeat recovery, and downstream OBS video jumps.

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return math.nan


def finite(values: list[float]) -> list[float]:
    return [value for value in values if math.isfinite(value)]


def median(values: list[float]) -> float:
    values = finite(values)
    return statistics.median(values) if values else math.nan


def robust_change_ms(
    rows: list[dict[str, str]], field: str, window: int
) -> tuple[float, float, float]:
    first = median([number(row, field) for row in rows[:window]]) / 1e6
    last = median([number(row, field) for row in rows[-window:]]) / 1e6
    return first, last, last - first


def counter_change(rows: list[dict[str, str]], field: str) -> float:
    if field not in rows[0]:
        return math.nan
    return number(rows[-1], field) - number(rows[0], field)


def final_value(rows: list[dict[str, str]], field: str) -> float:
    return number(rows[-1], field) if field in rows[0] else math.nan


def maximum(rows: list[dict[str, str]], field: str) -> float:
    if field not in rows[0]:
        return math.nan
    values = finite([number(row, field) for row in rows])
    return max(values) if values else math.nan


def minimum(rows: list[dict[str, str]], field: str) -> float:
    if field not in rows[0]:
        return math.nan
    values = finite([number(row, field) for row in rows])
    return min(values) if values else math.nan


def integer(value: float) -> str:
    return "not logged" if not math.isfinite(value) else f"{value:.0f}"


def milliseconds(value_ns: float) -> str:
    return "not logged" if not math.isfinite(value_ns) else f"{value_ns / 1e6:+.3f} ms"


def downstream_jump_rows(
    rows: list[dict[str, str]], first_wall_ns: float
) -> list[tuple[float, float, float, float]]:
    field = "selected_output_gap_jump_events"
    if field not in rows[0]:
        return []

    events: list[tuple[float, float, float, float]] = []
    previous = number(rows[0], field)
    for row in rows[1:]:
        current = number(row, field)
        if math.isfinite(current) and math.isfinite(previous) and current > previous:
            wall = number(row, "selected_output_last_gap_jump_wall_ns")
            elapsed = (wall - first_wall_ns) / 1e9 if math.isfinite(wall) else math.nan
            events.append(
                (
                    elapsed,
                    number(row, "selected_output_last_gap_jump_ns") / 1e6,
                    number(row, "selected_minus_output_live_projected_ns") / 1e6,
                    current - previous,
                )
            )
        previous = current
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--window", type=int, default=120)
    parser.add_argument("--warmup-seconds", type=float, default=10.0)
    args = parser.parse_args()

    with args.csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("CSV contains no samples")

    required = {
        "sample_wall_ns",
        "mode",
        "selected_video_minus_filtered_audio_projected_ns",
        "ndi_dropped_audio_frames",
        "ndi_dropped_video_frames",
    }
    missing = sorted(required - rows[0].keys())
    if missing:
        raise SystemExit(
            "Not a Receiver Clock Lab CSV; missing fields: " + ", ".join(missing)
        )

    original_first_wall = number(rows[0], "sample_wall_ns")
    cutoff = original_first_wall + args.warmup_seconds * 1e9
    warmed = [
        row for row in rows if number(row, "sample_wall_ns") >= cutoff
    ]
    if len(warmed) >= 8:
        rows = warmed

    first_wall = number(rows[0], "sample_wall_ns")
    duration = (number(rows[-1], "sample_wall_ns") - first_wall) / 1e9
    mode = rows[-1].get("mode", "unknown")
    mode_name = {
        "0": "stock-direct",
        "1": "stock-framesync",
        "2": "receiver-paced",
    }.get(mode, "unknown")
    print(f"rows={len(rows)} duration_s={duration:.3f} mode={mode} ({mode_name})")

    relation_fields = [
        "capture_video_minus_capture_audio_projected_ns",
        "output_video_minus_output_audio_projected_ns",
        "selected_video_minus_output_video_projected_ns",
        "filtered_audio_minus_output_audio_projected_ns",
        "selected_video_minus_filtered_audio_projected_ns",
    ]
    window = min(args.window, max(1, len(rows) // 4))
    for field in relation_fields:
        first, last, change = robust_change_ms(rows, field, window)
        slope_ppm = change * 1000.0 / duration if duration > 0 else math.nan
        print(
            f"{field}: {first:.6f} -> {last:.6f} ms; "
            f"change={change:+.6f} ms; slope={slope_ppm:+.3f} ppm"
        )

    print("receiver / FrameSync counters:")
    for field in [
        "ndi_dropped_audio_frames",
        "ndi_dropped_video_frames",
        "audio_catchups",
        "video_catchups",
        "repeated_video_frames",
        "recovered_video_repeats",
        "source_video_skipped_frames",
        "empty_audio_pulls",
        "empty_video_pulls",
    ]:
        print(f"  {field}={integer(counter_change(rows, field))}")

    repeat_debt = final_value(rows, "video_repeat_debt_frames")
    repeat_peak = maximum(rows, "max_video_repeat_debt_frames")
    nominal_step_100ns = final_value(rows, "nominal_video_step_100ns")
    print("FrameSync repeat recovery:")
    print(f"  final_unrecovered_repeat_debt_frames={integer(repeat_debt)}")
    print(f"  max_unrecovered_repeat_debt_frames={integer(repeat_peak)}")
    if math.isfinite(repeat_debt) and repeat_debt > 0:
        estimated_ms = (
            repeat_debt * nominal_step_100ns / 10000.0
            if math.isfinite(nominal_step_100ns) and nominal_step_100ns > 0
            else math.nan
        )
        suffix = f" (~{estimated_ms:.1f} ms)" if math.isfinite(estimated_ms) else ""
        print(
            f"  WARNING: video ended with {repeat_debt:.0f} "
            f"unrecovered FrameSync repeats{suffix}."
        )
    elif math.isfinite(repeat_debt):
        print("  Repeat classification ended with no unrecovered FrameSync debt.")
    else:
        print("  This CSV predates the repeat-recovery fields.")

    downstream_field = "selected_output_gap_jump_events"
    if downstream_field not in rows[0]:
        print("Downstream OBS selection: not logged by this build.")
        return

    print("Downstream OBS asynchronous-video selection:")
    for field in [
        "selected_video_repeat_events",
        "selected_video_skip_events",
        "selected_video_skipped_frames",
        "selected_video_backward_events",
        "selected_output_gap_jump_events",
    ]:
        print(f"  {field}={integer(counter_change(rows, field))}")

    final_gap = final_value(rows, "selected_minus_output_live_projected_ns")
    min_gap = minimum(rows, "selected_output_min_gap_ns")
    max_gap = maximum(rows, "selected_output_max_gap_ns")
    max_jump = maximum(rows, "selected_output_max_abs_gap_jump_ns")
    last_jump = final_value(rows, "selected_output_last_gap_jump_ns")
    expected = final_value(rows, "selected_video_expected_interval_ns")
    print(f"  expected_video_interval={milliseconds(expected)}")
    print(f"  final_selected_minus_output_gap={milliseconds(final_gap)}")
    print(f"  minimum_selected_minus_output_gap={milliseconds(min_gap)}")
    print(f"  maximum_selected_minus_output_gap={milliseconds(max_gap)}")
    print(f"  maximum_absolute_single_gap_change={milliseconds(max_jump)}")
    print(f"  last_classified_gap_jump={milliseconds(last_jump)}")

    events = downstream_jump_rows(rows, first_wall)
    if events:
        print("  classified downstream gap jumps:")
        for elapsed, jump_ms, resulting_gap_ms, count_change in events[:12]:
            time_text = (
                f"{elapsed / 60.0:.3f} min"
                if math.isfinite(elapsed)
                else "unknown time"
            )
            print(
                f"    at {time_text}: jump={jump_ms:+.3f} ms, "
                f"resulting_gap={resulting_gap_ms:+.3f} ms, "
                f"events_added={count_change:.0f}"
            )
        if len(events) > 12:
            print(f"    ... {len(events) - 12} more sampled jump rows")

    downstream_jumps = counter_change(rows, downstream_field)
    if math.isfinite(downstream_jumps) and downstream_jumps > 0:
        print(
            "WARNING: OBS's selected-video relationship made one or more sudden "
            "changes of at least 25 ms / 1.5 frames."
        )
        if math.isfinite(repeat_debt) and repeat_debt == 0:
            print(
                "The test ended without FrameSync repeat debt, so a persistent "
                "gap is more consistent with a downstream OBS async-video "
                "selection/queue event than stale FrameSync content."
            )
    elif math.isfinite(downstream_jumps):
        print("No classified downstream OBS selected-video gap jump occurred.")


if __name__ == "__main__":
    main()
