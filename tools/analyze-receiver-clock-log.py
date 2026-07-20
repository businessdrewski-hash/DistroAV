#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, math, statistics
from pathlib import Path

def n(r,k):
    try: return float(r[k])
    except (KeyError,TypeError,ValueError): return math.nan
def med(v):
    x=[a for a in v if math.isfinite(a)]; return statistics.median(x) if x else math.nan
def change(rows,k,w):
    a=med([n(r,k) for r in rows[:w]])/1e6; b=med([n(r,k) for r in rows[-w:]])/1e6; return a,b,b-a
def delta(rows,k): return n(rows[-1],k)-n(rows[0],k) if k in rows[0] else math.nan
def final(rows,k): return n(rows[-1],k) if k in rows[0] else math.nan
def maximum(rows,k):
    x=[n(r,k) for r in rows if k in r and math.isfinite(n(r,k))]; return max(x) if x else math.nan
def f(x): return "not logged" if not math.isfinite(x) else f"{x:.0f}"

def main():
    p=argparse.ArgumentParser(); p.add_argument("csv_path",type=Path); p.add_argument("--window",type=int,default=120); p.add_argument("--warmup-seconds",type=float,default=10.0); a=p.parse_args()
    with a.csv_path.open(newline="",encoding="utf-8-sig") as h: rows=list(csv.DictReader(h))
    if not rows: raise SystemExit("CSV contains no samples")
    cutoff=n(rows[0],"sample_wall_ns")+a.warmup_seconds*1e9; warmed=[r for r in rows if n(r,"sample_wall_ns")>=cutoff]
    if len(warmed)>=8: rows=warmed
    duration=(n(rows[-1],"sample_wall_ns")-n(rows[0],"sample_wall_ns"))/1e9; mode=rows[-1].get("mode","unknown")
    print(f"rows={len(rows)} duration_s={duration:.3f} mode={mode}")
    fields=["capture_video_minus_capture_audio_projected_ns","output_video_minus_output_audio_projected_ns","selected_video_minus_output_video_projected_ns","filtered_audio_minus_output_audio_projected_ns","selected_video_minus_filtered_audio_projected_ns"]
    w=min(a.window,max(1,len(rows)//4))
    for k in fields:
        x,y,d=change(rows,k,w); ppm=d*1000/duration if duration>0 else math.nan; print(f"{k}: {x:.6f} -> {y:.6f} ms; change={d:+.6f} ms; slope={ppm:+.3f} ppm")
    print("counters:")
    for k in ["ndi_dropped_audio_frames","ndi_dropped_video_frames","audio_catchups","video_catchups","repeated_video_frames","recovered_video_repeats","source_video_skipped_frames","empty_audio_pulls","empty_video_pulls"]: print(f"  {k}={f(delta(rows,k))}")
    debt=final(rows,"video_repeat_debt_frames"); peak=maximum(rows,"max_video_repeat_debt_frames"); step=final(rows,"nominal_video_step_100ns")
    print("repeat recovery:"); print(f"  final_unrecovered_repeat_debt_frames={f(debt)}"); print(f"  max_unrecovered_repeat_debt_frames={f(peak)}")
    if math.isfinite(debt) and debt>0:
        ms=debt*step/10000 if math.isfinite(step) and step>0 else math.nan; extra=f" (~{ms:.1f} ms)" if math.isfinite(ms) else ""; print(f"WARNING: video ended with {debt:.0f} unrecovered repeated frames{extra}.")
    elif math.isfinite(debt): print("Repeat classification ended with no unrecovered frame debt.")
    else: print("This CSV predates the repeat-recovery logger fields.")
if __name__=="__main__": main()
