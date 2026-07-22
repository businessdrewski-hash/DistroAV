#!/usr/bin/env python3
"""Apply the Receiver Clock Lab live diagnostics extension.

This patcher is intentionally strict: it only modifies the known
receiver-clock-lab 6.2.1.1/6.2.1.2 source layout, and it is idempotent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PatchError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_regex_once(text: str, pattern: str, new: str, label: str) -> str:
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE | re.DOTALL))
    if len(matches) != 1:
        raise PatchError(f"{label}: expected exactly one regex anchor, found {len(matches)}")
    return re.sub(pattern, lambda _match: new, text, count=1, flags=re.MULTILINE | re.DOTALL)


def prepare_modify(path: Path, marker: str, transform) -> tuple[bool, str]:
    if not path.exists():
        raise PatchError(f"Missing required file: {path}")
    original = path.read_text(encoding="utf-8")
    if marker in original:
        return False, original
    updated = transform(original)
    if updated == original:
        raise PatchError(f"No changes produced for {path}")
    return True, updated


def patch_header(text: str) -> str:
    text = replace_once(
        text,
        "static constexpr size_t kCapacity = 43200; // three hours at 250 ms",
        "static constexpr size_t kCapacity = 43200; // twelve hours at one-second sampling",
        "diagnostics capacity",
    )

    insertion = r'''struct LiveSnapshot {
	bool enabled = false;
	uint64_t wall_ns = 0;
	uint64_t session = 0;
	uint64_t sample_count = 0;
	uint64_t overwritten_samples = 0;
	Event last_event = Event::None;
	uint64_t last_event_wall_ns = 0;
	StageSnapshot capture_audio;
	StageSnapshot capture_video;
	StageSnapshot output_audio;
	StageSnapshot output_video;
	StageSnapshot filtered_audio;
	StageSnapshot selected_video;
	DownstreamVideoSnapshot downstream_video;
	SchedulerSnapshot scheduler;
	int64_t capture_av_ns = 0;
	int64_t output_av_ns = 0;
	int64_t video_path_ns = 0;
	int64_t audio_path_ns = 0;
	int64_t final_av_ns = 0;
	uint64_t latest_observation_wall_ns = 0;
	bool has_trend_60s = false;
	bool has_trend_10m = false;
	double final_av_trend_60s_ms_per_min = 0.0;
	double output_av_trend_60s_ms_per_min = 0.0;
	double video_path_trend_60s_ms_per_min = 0.0;
	double audio_path_trend_60s_ms_per_min = 0.0;
	double final_av_trend_10m_ms_per_min = 0.0;
	double output_av_trend_10m_ms_per_min = 0.0;
	double video_path_trend_10m_ms_per_min = 0.0;
	double audio_path_trend_10m_ms_per_min = 0.0;
};

struct RegisteredLiveSnapshot {
	uint64_t token = 0;
	std::string source_name;
	LiveSnapshot diagnostics;
};

'''
    text = replace_once(
        text,
        "// Callback-facing observations only publish atomics. A compact 250 ms flight\n",
        insertion + "// Callback-facing observations only publish atomics. A compact one-second flight\n",
        "live snapshot declarations",
    )
    text = replace_once(
        text,
        "\tvoid sample(uint64_t wall_ns);\n\n\tstd::string csv() const;",
        "\tvoid sample(uint64_t wall_ns);\n\tLiveSnapshot live_snapshot(uint64_t wall_ns) const;\n\n\tstd::string csv() const;",
        "live snapshot method",
    )
    text = replace_once(
        text,
        "};\n\n} // namespace distroav::clocklab\n",
        "};\n\n// Implemented by the NDI source registry so the OBS dock can safely read all live sources.\n"
        "std::vector<RegisteredLiveSnapshot> registered_live_snapshots(uint64_t wall_ns);\n\n"
        "} // namespace distroav::clocklab\n",
        "registry declaration",
    )
    return text


def patch_diagnostics_cpp(text: str) -> str:
    method = r'''LiveSnapshot Diagnostics::live_snapshot(uint64_t wall_ns) const
{
	LiveSnapshot result;
	result.enabled = enabled();
	result.wall_ns = wall_ns;
	result.session = session_.load(std::memory_order_relaxed);
	result.last_event = static_cast<Event>(last_event_.load(std::memory_order_relaxed));
	result.last_event_wall_ns = last_event_wall_ns_.load(std::memory_order_relaxed);
	result.capture_audio = read_stage(capture_audio_);
	result.capture_video = read_stage(capture_video_);
	result.output_audio = read_stage(output_audio_);
	result.output_video = read_stage(output_video_);
	result.filtered_audio = read_stage(filtered_audio_);
	result.selected_video = read_stage(selected_video_);
	result.downstream_video = read_downstream_video();
	result.scheduler = read_scheduler();

	auto relation = [](const StageSnapshot &a, const StageSnapshot &b) -> int64_t {
		if (!a.timestamp_ns || !a.wall_ns || !b.timestamp_ns || !b.wall_ns)
			return 0;
		return signed_delta(a.timestamp_ns, b.timestamp_ns) + signed_delta(b.wall_ns, a.wall_ns);
	};

	result.capture_av_ns = relation(result.capture_video, result.capture_audio);
	result.output_av_ns = relation(result.output_video, result.output_audio);
	result.video_path_ns = relation(result.selected_video, result.output_video);
	result.audio_path_ns = relation(result.filtered_audio, result.output_audio);
	result.final_av_ns = relation(result.selected_video, result.filtered_audio);
	result.latest_observation_wall_ns = std::max(
		{result.capture_audio.wall_ns, result.capture_video.wall_ns, result.output_audio.wall_ns,
		 result.output_video.wall_ns, result.filtered_audio.wall_ns, result.selected_video.wall_ns});

	std::lock_guard<std::mutex> lock(ring_mutex_);
	result.sample_count = count_;
	result.overwritten_samples = overwritten_;
	if (ring_.empty() || !count_)
		return result;

	const size_t newest_index = (write_index_ + ring_.size() - 1) % ring_.size();
	const Sample &newest = ring_[newest_index];
	auto sample_relation = [&relation](const Sample &row, StageSnapshot Sample::*a,
					      StageSnapshot Sample::*b) -> int64_t {
		return relation(row.*a, row.*b);
	};
	auto find_reference = [&](uint64_t lookback_ns) -> const Sample * {
		for (size_t offset = 1; offset < count_; ++offset) {
			const size_t index = (newest_index + ring_.size() - offset) % ring_.size();
			const Sample &candidate = ring_[index];
			if (candidate.session != newest.session)
				break;
			if (newest.wall_ns > candidate.wall_ns && newest.wall_ns - candidate.wall_ns >= lookback_ns)
				return &candidate;
		}
		return nullptr;
	};
	auto calculate_trends = [&](const Sample *reference, bool &available, double &final_rate,
				     double &output_rate, double &video_rate, double &audio_rate) {
		if (!reference || newest.wall_ns <= reference->wall_ns)
			return;
		const double elapsed_minutes =
			static_cast<double>(newest.wall_ns - reference->wall_ns) / 60000000000.0;
		if (elapsed_minutes <= 0.0)
			return;
		auto rate = [elapsed_minutes](int64_t current, int64_t previous) {
			return (static_cast<double>(current - previous) / 1000000.0) / elapsed_minutes;
		};
		final_rate = rate(sample_relation(newest, &Sample::selected_video, &Sample::filtered_audio),
				  sample_relation(*reference, &Sample::selected_video, &Sample::filtered_audio));
		output_rate = rate(sample_relation(newest, &Sample::output_video, &Sample::output_audio),
				   sample_relation(*reference, &Sample::output_video, &Sample::output_audio));
		video_rate = rate(sample_relation(newest, &Sample::selected_video, &Sample::output_video),
				  sample_relation(*reference, &Sample::selected_video, &Sample::output_video));
		audio_rate = rate(sample_relation(newest, &Sample::filtered_audio, &Sample::output_audio),
				  sample_relation(*reference, &Sample::filtered_audio, &Sample::output_audio));
		available = true;
	};

	calculate_trends(find_reference(60000000000ULL), result.has_trend_60s,
			 result.final_av_trend_60s_ms_per_min, result.output_av_trend_60s_ms_per_min,
			 result.video_path_trend_60s_ms_per_min, result.audio_path_trend_60s_ms_per_min);
	calculate_trends(find_reference(600000000000ULL), result.has_trend_10m,
			 result.final_av_trend_10m_ms_per_min, result.output_av_trend_10m_ms_per_min,
			 result.video_path_trend_10m_ms_per_min, result.audio_path_trend_10m_ms_per_min);
	return result;
}

'''
    text = replace_once(
        text,
        "void Diagnostics::sample(uint64_t wall_ns)\n{",
        method + "void Diagnostics::sample(uint64_t wall_ns)\n{",
        "live snapshot implementation",
    )
    text = replace_once(
        text,
        "if (++live_rows_since_flush_ >= 16)",
        "if (++live_rows_since_flush_ >= 4)",
        "live CSV flush cadence",
    )
    return text


def patch_ndi_source(text: str) -> str:
    text = replace_once(
        text,
        "#include <QDesktopServices>\n#include <QUrl>\n",
        "#include <QCoreApplication>\n#include <QDesktopServices>\n#include <QTimer>\n#include <QUrl>\n",
        "Qt probe lifecycle includes",
    )
    text = replace_once(
        text,
        "#include <unordered_map>\n",
        "#include <unordered_map>\n#include <vector>\n",
        "vector include",
    )
    text = replace_once(
        text,
        "\tobs_source_t *clock_video_probe;\n\tobs_source_t *clock_audio_probe;\n",
        "\tobs_source_t *clock_video_probe;\n"
        "\tobs_source_t *clock_audio_probe;\n"
        "\tbool clock_probe_lifecycle_ready;\n",
        "probe lifecycle state",
    )
    text = replace_once(
        text,
        "std::mutex clocklab_registry_mutex;\n"
        "std::unordered_map<uint64_t, std::shared_ptr<distroav::clocklab::Diagnostics>> clocklab_registry;\n"
        "std::atomic<uint64_t> clocklab_next_token{1};",
        "struct ClocklabRegistryEntry {\n"
        "\tstd::shared_ptr<distroav::clocklab::Diagnostics> diagnostics;\n"
        "\tstd::string source_name;\n"
        "};\n\n"
        "std::mutex clocklab_registry_mutex;\n"
        "std::unordered_map<uint64_t, ClocklabRegistryEntry> clocklab_registry;\n"
        "std::atomic<uint64_t> clocklab_next_token{1};",
        "diagnostics registry entry",
    )

    old_registry = r'''uint64_t register_clocklab_diagnostics(const std::shared_ptr<distroav::clocklab::Diagnostics> &diagnostics)
{
	const uint64_t token = clocklab_next_token.fetch_add(1, std::memory_order_relaxed);
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	clocklab_registry[token] = diagnostics;
	return token;
}

std::shared_ptr<distroav::clocklab::Diagnostics> acquire_clocklab_diagnostics(uint64_t token)
{
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	auto it = clocklab_registry.find(token);
	return it != clocklab_registry.end() ? it->second : nullptr;
}

void unregister_clocklab_diagnostics(uint64_t token)
{
	if (!token)
		return;
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	clocklab_registry.erase(token);
}
} // namespace
'''
    new_registry = r'''uint64_t register_clocklab_diagnostics(const std::shared_ptr<distroav::clocklab::Diagnostics> &diagnostics,
				       const char *source_name)
{
	const uint64_t token = clocklab_next_token.fetch_add(1, std::memory_order_relaxed);
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	clocklab_registry[token] = ClocklabRegistryEntry{diagnostics, source_name ? source_name : ""};
	return token;
}

std::shared_ptr<distroav::clocklab::Diagnostics> acquire_clocklab_diagnostics(uint64_t token)
{
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	auto it = clocklab_registry.find(token);
	return it != clocklab_registry.end() ? it->second.diagnostics : nullptr;
}

void update_clocklab_diagnostics_name(uint64_t token, const char *source_name)
{
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	auto it = clocklab_registry.find(token);
	if (it != clocklab_registry.end())
		it->second.source_name = source_name ? source_name : "";
}

void unregister_clocklab_diagnostics(uint64_t token)
{
	if (!token)
		return;
	std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
	clocklab_registry.erase(token);
}
} // namespace

namespace distroav::clocklab {
std::vector<RegisteredLiveSnapshot> registered_live_snapshots(uint64_t wall_ns)
{
	struct PendingSnapshot {
		uint64_t token;
		std::string source_name;
		std::shared_ptr<Diagnostics> diagnostics;
	};
	std::vector<PendingSnapshot> pending;
	{
		std::lock_guard<std::mutex> lock(clocklab_registry_mutex);
		pending.reserve(clocklab_registry.size());
		for (const auto &[token, entry] : clocklab_registry)
			pending.push_back(PendingSnapshot{token, entry.source_name, entry.diagnostics});
	}
	std::sort(pending.begin(), pending.end(), [](const auto &a, const auto &b) {
		return a.source_name < b.source_name;
	});
	std::vector<RegisteredLiveSnapshot> result;
	result.reserve(pending.size());
	for (const auto &entry : pending) {
		if (entry.diagnostics)
			result.push_back(RegisteredLiveSnapshot{entry.token, entry.source_name,
							 entry.diagnostics->live_snapshot(wall_ns)});
	}
	return result;
}
} // namespace distroav::clocklab
'''
    text = replace_once(text, old_registry, new_registry, "diagnostics registry functions")

    probe_helpers = r'''
static size_t remove_clocklab_probes_by_id(obs_source_t *parent, const char *id)
{
	if (!parent || !id)
		return 0;
	struct ProbeList {
		const char *id;
		std::vector<obs_source_t *> filters;
	} list{id, {}};
	obs_source_enum_filters(
		parent,
		[](obs_source_t *, obs_source_t *filter, void *param) {
			auto *list_ = static_cast<ProbeList *>(param);
			const char *filter_id = obs_source_get_id(filter);
			if (filter_id && strcmp(filter_id, list_->id) == 0) {
				obs_source_get_ref(filter);
				list_->filters.push_back(filter);
			}
		},
		&list);
	for (obs_source_t *filter : list.filters) {
		obs_source_filter_remove(parent, filter);
		obs_source_release(filter);
	}
	return list.filters.size();
}

static bool add_clocklab_probe(obs_source_t *parent, const char *id, const char *name, uint64_t token)
{
	obs_source_t *filter = install_clocklab_probe(parent, id, name, token);
	if (!filter)
		return false;
	// The parent owns the attached-filter reference. Do not retain a second
	// source-owned reference that can survive resets or be released twice.
	obs_source_release(filter);
	return true;
}

static void reconcile_clocklab_probes(obs_source_t *parent, uint64_t token, bool enabled, const char *reason)
{
	if (!parent)
		return;

	// Always collapse every persisted or stale copy first. Receiver resets do
	// not call this function; only create/load and a diagnostics on/off change do.
	const size_t removed_video = remove_clocklab_probes_by_id(parent, CLOCKLAB_VIDEO_PROBE_ID);
	const size_t removed_audio = remove_clocklab_probes_by_id(parent, CLOCKLAB_AUDIO_PROBE_ID);

	bool video_ready = false;
	bool audio_ready = false;
	if (enabled && token) {
		video_ready = add_clocklab_probe(parent, CLOCKLAB_VIDEO_PROBE_ID,
					   "DistroAV Receiver Clock Video Probe", token);
		audio_ready = add_clocklab_probe(parent, CLOCKLAB_AUDIO_PROBE_ID,
					   "DistroAV Receiver Clock Audio Probe", token);
	}

	obs_log(LOG_INFO,
		"[receiver-clock-lab] Probe reconcile source='%s' reason=%s enabled=%s removed_video=%zu removed_audio=%zu video=%s audio=%s",
		obs_source_get_name(parent), reason ? reason : "unknown", enabled ? "true" : "false",
		removed_video, removed_audio, video_ready ? "ready" : (enabled ? "failed" : "off"),
		audio_ready ? "ready" : (enabled ? "failed" : "off"));
}

static void schedule_clocklab_probe_reconcile(obs_source_t *parent, uint64_t token, bool enabled,
					      const char *reason)
{
	if (!parent)
		return;

	obs_weak_source_t *weak = obs_source_get_weak_source(parent);
	if (!weak)
		return;
	const std::string reason_copy = reason ? reason : "scheduled";
	QCoreApplication *app = QCoreApplication::instance();
	if (!app) {
		reconcile_clocklab_probes(parent, token, enabled, reason_copy.c_str());
		obs_weak_source_release(weak);
		return;
	}

	// Defer until the UI event loop so OBS has finished restoring any saved
	// filters. A weak source prevents a queued callback from touching a source
	// that was deleted before it ran.
	QTimer::singleShot(0, app, [weak, token, enabled, reason_copy] {
		obs_source_t *strong = obs_weak_source_get_source(weak);
		if (strong) {
			reconcile_clocklab_probes(strong, token, enabled, reason_copy.c_str());
			obs_source_release(strong);
		}
		obs_weak_source_release(weak);
	});
}
'''
    text = replace_once(
        text,
        "static bool export_clocklab_diagnostics(ndi_source_t *source)\n{",
        probe_helpers + "\nstatic bool export_clocklab_diagnostics(ndi_source_t *source)\n{",
        "probe deduplication helpers",
    )

    logging_helpers = r'''static double clocklab_ns_to_ms(int64_t value)
{
	return static_cast<double>(value) / 1000000.0;
}

static double clocklab_active_trend(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (snapshot.has_trend_10m)
		return snapshot.final_av_trend_10m_ms_per_min;
	if (snapshot.has_trend_60s)
		return snapshot.final_av_trend_60s_ms_per_min;
	return 0.0;
}

static const char *clocklab_status(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (!snapshot.selected_video.observations || !snapshot.filtered_audio.observations)
		return "waiting";
	if (snapshot.latest_observation_wall_ns && snapshot.wall_ns > snapshot.latest_observation_wall_ns + 3000000000ULL)
		return "stale";
	const double offset_ms = std::abs(clocklab_ns_to_ms(snapshot.final_av_ns));
	const double trend = std::abs(clocklab_active_trend(snapshot));
	if (offset_ms <= 40.0 && trend < 0.25)
		return "good";
	if (offset_ms <= 80.0 && trend < 1.0)
		return "watch";
	return "warning";
}

static const char *clocklab_direction(const distroav::clocklab::LiveSnapshot &snapshot)
{
	const double offset_ms = clocklab_ns_to_ms(snapshot.final_av_ns);
	if (std::abs(offset_ms) <= 40.0)
		return "near-sync";
	return offset_ms > 0.0 ? "audio-late" : "video-late";
}

static const char *clocklab_likely_cause(const distroav::clocklab::LiveSnapshot &snapshot)
{
	const double output = snapshot.has_trend_10m ? snapshot.output_av_trend_10m_ms_per_min
						      : snapshot.output_av_trend_60s_ms_per_min;
	const double video = snapshot.has_trend_10m ? snapshot.video_path_trend_10m_ms_per_min
						     : snapshot.video_path_trend_60s_ms_per_min;
	const double audio = snapshot.has_trend_10m ? snapshot.audio_path_trend_10m_ms_per_min
						     : snapshot.audio_path_trend_60s_ms_per_min;
	if ((snapshot.scheduler.ndi_queued_audio_frames > 4 || snapshot.scheduler.ndi_queued_video_frames > 4) &&
	    (snapshot.scheduler.ndi_dropped_audio_frames > 0 || snapshot.scheduler.ndi_dropped_video_frames > 0))
		return "ndi-receive-pressure";
	if (std::abs(audio) >= 0.5 && std::abs(audio) >= std::abs(video) && std::abs(audio) >= std::abs(output))
		return "obs-audio-path-growth";
	if (std::abs(video) >= 0.5 && std::abs(video) >= std::abs(audio) && std::abs(video) >= std::abs(output))
		return "obs-video-queue-growth";
	if (std::abs(output) >= 0.5 && std::abs(output) >= std::abs(audio) && std::abs(output) >= std::abs(video))
		return "distroav-output-movement";
	if (std::abs(clocklab_ns_to_ms(snapshot.final_av_ns)) > 80.0)
		return "large-static-offset";
	return "stable-or-undetermined";
}

'''
    text = replace_once(
        text,
        "void *ndi_source_thread(void *data)\n{",
        logging_helpers + "void *ndi_source_thread(void *data)\n{",
        "diagnostics logging helpers",
    )

    text = replace_once(
        text,
        "\tuint64_t last_diagnostic_sample_ns = 0;",
        "\tuint64_t last_diagnostic_sample_ns = 0;\n"
        "\tuint64_t last_logged_gap_jump_events = 0;\n"
        "\tint64_t last_logged_dropped_audio_frames = 0;\n"
        "\tint64_t last_logged_dropped_video_frames = 0;\n"
        "\tuint64_t last_logged_max_repeat_debt = 0;\n"
        "\tint last_logged_health_level = -1;\n"
        "\tbool last_logged_queue_pressure = false;",
        "diagnostic event state",
    )
    text = replace_once(
        text,
        "\t\tlast_diagnostic_sample_ns = 0;",
        "\t\tlast_diagnostic_sample_ns = 0;\n"
        "\t\tlast_logged_gap_jump_events = 0;\n"
        "\t\tlast_logged_dropped_audio_frames = 0;\n"
        "\t\tlast_logged_dropped_video_frames = 0;\n"
        "\t\tlast_logged_max_repeat_debt = 0;\n"
        "\t\tlast_logged_health_level = -1;\n"
        "\t\tlast_logged_queue_pressure = false;",
        "diagnostic event reset",
    )

    text = replace_once(
        text,
        "now_ns - receiver_clock.last_diagnostic_sample_ns < 250000000ULL",
        "now_ns - receiver_clock.last_diagnostic_sample_ns < 1000000000ULL",
        "one-second sample cadence",
    )

    old_sample_end = r'''		s->clock_diagnostics->update_scheduler(snapshot);
		s->clock_diagnostics->sample(now_ns);
	};'''
    new_sample_end = r'''		s->clock_diagnostics->update_scheduler(snapshot);
		s->clock_diagnostics->sample(now_ns);
		const auto live = s->clock_diagnostics->live_snapshot(now_ns);
		const char *health_status = clocklab_status(live);
		const double data_age_ms = live.latest_observation_wall_ns && now_ns >= live.latest_observation_wall_ns
						   ? static_cast<double>(now_ns - live.latest_observation_wall_ns) / 1000000.0
						   : -1.0;
		obs_log(LOG_INFO,
			"[receiver-clock-lab] source='%s' status=%s direction=%s final_av_ms=%+.3f final_trend_ms_per_min=%+.4f trend_window=%s output_av_ms=%+.3f output_trend_ms_per_min=%+.4f obs_video_path_ms=%+.3f video_path_trend_ms_per_min=%+.4f obs_audio_path_ms=%+.3f audio_path_trend_ms_per_min=%+.4f ndi_total_audio=%lld ndi_total_video=%lld ndi_queue_audio=%d ndi_queue_video=%d ndi_dropped_audio=%lld ndi_dropped_video=%lld empty_audio_pulls=%llu empty_video_pulls=%llu audio_deadline_error_ms=%+.3f video_deadline_error_ms=%+.3f audio_catchups=%llu video_catchups=%llu repeated_video_frames=%llu recovered_video_repeats=%llu source_video_skipped_frames=%llu video_repeat_debt=%llu max_video_repeat_debt=%llu selected_gap_jump_events=%llu output_audio_pacing_anomalies=%llu output_video_pacing_anomalies=%llu selected_video_observations=%llu filtered_audio_observations=%llu samples=%llu overwritten=%llu data_age_ms=%.1f likely_cause=%s",
			obs_source_name, health_status, clocklab_direction(live),
			clocklab_ns_to_ms(live.final_av_ns), clocklab_active_trend(live),
			live.has_trend_10m ? "10m" : (live.has_trend_60s ? "60s" : "warming"),
			clocklab_ns_to_ms(live.output_av_ns),
			live.has_trend_10m ? live.output_av_trend_10m_ms_per_min : live.output_av_trend_60s_ms_per_min,
			clocklab_ns_to_ms(live.video_path_ns),
			live.has_trend_10m ? live.video_path_trend_10m_ms_per_min : live.video_path_trend_60s_ms_per_min,
			clocklab_ns_to_ms(live.audio_path_ns),
			live.has_trend_10m ? live.audio_path_trend_10m_ms_per_min : live.audio_path_trend_60s_ms_per_min,
			static_cast<long long>(live.scheduler.ndi_total_audio_frames),
			static_cast<long long>(live.scheduler.ndi_total_video_frames),
			live.scheduler.ndi_queued_audio_frames, live.scheduler.ndi_queued_video_frames,
			static_cast<long long>(live.scheduler.ndi_dropped_audio_frames),
			static_cast<long long>(live.scheduler.ndi_dropped_video_frames),
			static_cast<unsigned long long>(live.scheduler.empty_audio_pulls),
			static_cast<unsigned long long>(live.scheduler.empty_video_pulls),
			clocklab_ns_to_ms(live.scheduler.audio_deadline_error_ns),
			clocklab_ns_to_ms(live.scheduler.video_deadline_error_ns),
			static_cast<unsigned long long>(live.scheduler.audio_catchups),
			static_cast<unsigned long long>(live.scheduler.video_catchups),
			static_cast<unsigned long long>(live.scheduler.repeated_video_frames),
			static_cast<unsigned long long>(live.scheduler.recovered_video_repeats),
			static_cast<unsigned long long>(live.scheduler.source_video_skipped_frames),
			static_cast<unsigned long long>(live.scheduler.video_repeat_debt_frames),
			static_cast<unsigned long long>(live.scheduler.max_video_repeat_debt_frames),
			static_cast<unsigned long long>(live.downstream_video.gap_jump_events),
			static_cast<unsigned long long>(live.output_audio.pacing_anomalies),
			static_cast<unsigned long long>(live.output_video.pacing_anomalies),
			static_cast<unsigned long long>(live.selected_video.observations),
			static_cast<unsigned long long>(live.filtered_audio.observations),
			static_cast<unsigned long long>(live.sample_count),
			static_cast<unsigned long long>(live.overwritten_samples), data_age_ms,
			clocklab_likely_cause(live));

		const int health_level = strcmp(health_status, "warning") == 0 || strcmp(health_status, "stale") == 0
					 ? 2
					 : (strcmp(health_status, "watch") == 0 ? 1
											 : (strcmp(health_status, "good") == 0 ? 0 : -1));
		if (health_level >= 0 && receiver_clock.last_logged_health_level >= 0 &&
		    health_level != receiver_clock.last_logged_health_level) {
			obs_log(health_level > receiver_clock.last_logged_health_level ? LOG_WARNING : LOG_INFO,
				"[receiver-clock-lab] event=health-transition source='%s' previous_level=%d current_level=%d status=%s final_av_ms=%+.3f trend_ms_per_min=%+.4f likely_cause=%s",
				obs_source_name, receiver_clock.last_logged_health_level, health_level, health_status,
				clocklab_ns_to_ms(live.final_av_ns), clocklab_active_trend(live),
				clocklab_likely_cause(live));
		}
		if (health_level >= 0)
			receiver_clock.last_logged_health_level = health_level;

		const bool queue_pressure = live.scheduler.ndi_queued_audio_frames > 4 ||
					    live.scheduler.ndi_queued_video_frames > 4;
		if (queue_pressure != receiver_clock.last_logged_queue_pressure) {
			obs_log(queue_pressure ? LOG_WARNING : LOG_INFO,
				"[receiver-clock-lab] event=ndi-queue-pressure source='%s' active=%s queued_audio=%d queued_video=%d",
				obs_source_name, queue_pressure ? "true" : "false",
				live.scheduler.ndi_queued_audio_frames, live.scheduler.ndi_queued_video_frames);
			receiver_clock.last_logged_queue_pressure = queue_pressure;
		}

		if (live.scheduler.ndi_dropped_audio_frames > receiver_clock.last_logged_dropped_audio_frames ||
		    live.scheduler.ndi_dropped_video_frames > receiver_clock.last_logged_dropped_video_frames) {
			obs_log(LOG_WARNING,
				"[receiver-clock-lab] event=ndi-drops-increased source='%s' audio_previous=%lld audio_current=%lld video_previous=%lld video_current=%lld",
				obs_source_name,
				static_cast<long long>(receiver_clock.last_logged_dropped_audio_frames),
				static_cast<long long>(live.scheduler.ndi_dropped_audio_frames),
				static_cast<long long>(receiver_clock.last_logged_dropped_video_frames),
				static_cast<long long>(live.scheduler.ndi_dropped_video_frames));
		}
		receiver_clock.last_logged_dropped_audio_frames = live.scheduler.ndi_dropped_audio_frames;
		receiver_clock.last_logged_dropped_video_frames = live.scheduler.ndi_dropped_video_frames;

		if (live.downstream_video.gap_jump_events > receiver_clock.last_logged_gap_jump_events) {
			obs_log(LOG_WARNING,
				"[receiver-clock-lab] event=downstream-video-gap-jump source='%s' previous_events=%llu current_events=%llu last_jump_ms=%+.3f max_abs_jump_ms=%.3f current_video_path_ms=%+.3f",
				obs_source_name,
				static_cast<unsigned long long>(receiver_clock.last_logged_gap_jump_events),
				static_cast<unsigned long long>(live.downstream_video.gap_jump_events),
				clocklab_ns_to_ms(live.downstream_video.last_gap_jump_ns),
				clocklab_ns_to_ms(live.downstream_video.max_abs_gap_jump_ns),
				clocklab_ns_to_ms(live.video_path_ns));
		}
		receiver_clock.last_logged_gap_jump_events = live.downstream_video.gap_jump_events;

		if (live.scheduler.max_video_repeat_debt_frames > receiver_clock.last_logged_max_repeat_debt) {
			obs_log(LOG_WARNING,
				"[receiver-clock-lab] event=video-repeat-debt-high-water source='%s' previous_max=%llu current_max=%llu current_debt=%llu recovered=%llu skipped_source_frames=%llu",
				obs_source_name,
				static_cast<unsigned long long>(receiver_clock.last_logged_max_repeat_debt),
				static_cast<unsigned long long>(live.scheduler.max_video_repeat_debt_frames),
				static_cast<unsigned long long>(live.scheduler.video_repeat_debt_frames),
				static_cast<unsigned long long>(live.scheduler.recovered_video_repeats),
				static_cast<unsigned long long>(live.scheduler.source_video_skipped_frames));
		}
		receiver_clock.last_logged_max_repeat_debt = live.scheduler.max_video_repeat_debt_frames;
	};'''
    text = replace_once(text, old_sample_end, new_sample_end, "one-second summary logging")

    text = replace_once(
        text,
        "\tconst bool diagnostics_enabled = obs_data_get_bool(settings, PROP_CLOCK_DIAGNOSTICS);\n"
        "\tif (s->clock_diagnostics) {\n"
        "\t\ts->clock_diagnostics->set_enabled(diagnostics_enabled, os_gettime_ns());\n"
        "\t\tif (old_receiver_clock_mode != new_receiver_clock_mode)\n"
        "\t\t\ts->clock_diagnostics->mark_event(distroav::clocklab::Event::ModeChanged, os_gettime_ns());\n"
        "\t}\n"
        "\ts->config.clock_diagnostics_enabled = diagnostics_enabled;",
        "\tconst bool old_diagnostics_enabled = s->config.clock_diagnostics_enabled;\n"
        "\tconst bool diagnostics_enabled = obs_data_get_bool(settings, PROP_CLOCK_DIAGNOSTICS);\n"
        "\tif (s->clock_diagnostics) {\n"
        "\t\ts->clock_diagnostics->set_enabled(diagnostics_enabled, os_gettime_ns());\n"
        "\t\tif (old_receiver_clock_mode != new_receiver_clock_mode)\n"
        "\t\t\ts->clock_diagnostics->mark_event(distroav::clocklab::Event::ModeChanged, os_gettime_ns());\n"
        "\t}\n"
        "\ts->config.clock_diagnostics_enabled = diagnostics_enabled;\n"
        "\tif (s->clock_probe_lifecycle_ready && old_diagnostics_enabled != diagnostics_enabled)\n"
        "\t\tschedule_clocklab_probe_reconcile(s->obs_source, s->clock_diagnostics_token, diagnostics_enabled,\n"
        "\t\t\t\t\t  \"diagnostics-toggle\");",
        "diagnostics toggle probe lifecycle",
    )

    text = replace_once(
        text,
        "s->clock_diagnostics_token = register_clocklab_diagnostics(*s->clock_diagnostics_owner);",
        "s->clock_diagnostics_token = register_clocklab_diagnostics(*s->clock_diagnostics_owner, obs_source_name);",
        "registry source name",
    )
    text = replace_once(
        text,
        "\tnew_ndi_receiver_name(obs_source_name, &(s->config.ndi_receiver_name));\n\ts->config.reset_ndi_receiver = true;",
        "\tnew_ndi_receiver_name(obs_source_name, &(s->config.ndi_receiver_name));\n"
        "\tupdate_clocklab_diagnostics_name(s->clock_diagnostics_token, obs_source_name);\n"
        "\ts->config.reset_ndi_receiver = true;",
        "registry rename update",
    )

    new_install = r'''	ndi_source_update(s, settings);
	s->clock_probe_lifecycle_ready = true;
	schedule_clocklab_probe_reconcile(s->obs_source, s->clock_diagnostics_token,
					  s->config.clock_diagnostics_enabled, "source-create");
'''
    text = replace_regex_once(
        text,
        r"\tndi_source_update\(s, settings\);\n"
        r"\ts->clock_video_probe = install_clocklab_probe\(obs_source, CLOCKLAB_VIDEO_PROBE_ID,.*?"
        r"\ts->clock_audio_probe = install_clocklab_probe\(obs_source, CLOCKLAB_AUDIO_PROBE_ID,.*?"
        r"\s*s->clock_diagnostics_token\);\n",
        new_install,
        "single probe installation",
    )

    text = replace_once(
        text,
        "void ndi_source_destroy(void *data)\n{",
        "void ndi_source_load(void *data, obs_data_t *)\n{\n"
        "\tauto *source = static_cast<ndi_source_t *>(data);\n"
        "\tschedule_clocklab_probe_reconcile(source->obs_source, source->clock_diagnostics_token,\n"
        "\t\t\t\t\t  source->config.clock_diagnostics_enabled, \"source-load\");\n"
        "}\n\n"
        "void ndi_source_destroy(void *data)\n{",
        "source load repair",
    )
    text = replace_once(
        text,
        "\tndi_source_thread_stop(s);\n"
        "\tremove_clocklab_probe(s->obs_source, s->clock_video_probe);\n"
        "\tremove_clocklab_probe(s->obs_source, s->clock_audio_probe);\n"
        "\ts->clock_video_probe = nullptr;\n"
        "\ts->clock_audio_probe = nullptr;",
        "\tndi_source_thread_stop(s);\n"
        "\ts->clock_probe_lifecycle_ready = false;\n"
        "\tconst size_t removed_video_probes = remove_clocklab_probes_by_id(s->obs_source, CLOCKLAB_VIDEO_PROBE_ID);\n"
        "\tconst size_t removed_audio_probes = remove_clocklab_probes_by_id(s->obs_source, CLOCKLAB_AUDIO_PROBE_ID);\n"
        "\ts->clock_video_probe = nullptr;\n"
        "\ts->clock_audio_probe = nullptr;\n"
        "\tobs_log(LOG_INFO,\n"
        "\t\t\"[receiver-clock-lab] Probe destroy cleanup source='%s' removed_video=%zu removed_audio=%zu\",\n"
        "\t\tobs_source_name, removed_video_probes, removed_audio_probes);",
        "destroy probe cleanup",
    )

    text = replace_once(
        text,
        "\tndi_source_info.update = ndi_source_update;\n\tndi_source_info.hide = ndi_source_hidden;",
        "\tndi_source_info.update = ndi_source_update;\n"
        "\tndi_source_info.load = ndi_source_load;\n"
        "\tndi_source_info.hide = ndi_source_hidden;",
        "source load callback",
    )
    return text


def patch_plugin_main(text: str) -> str:
    text = replace_once(
        text,
        '#include "preview-output.h"\n',
        '#include "preview-output.h"\n#include "receiver-clock-diagnostics-dock.h"\n',
        "dock include",
    )
    text = replace_once(
        text,
        "static bool plugin_features_registered = false;\n",
        "static bool plugin_features_registered = false;\n\n"
        "static void queue_receiver_clock_diagnostics_dock(QMainWindow *main_window)\n"
        "{\n"
        "\tif (!main_window) {\n"
        "\t\tobs_log(LOG_WARNING, \"[receiver-clock-lab] Diagnostics dock registration skipped: no OBS main window\");\n"
        "\t\treturn;\n"
        "\t}\n"
        "\tQMetaObject::invokeMethod(\n"
        "\t\tmain_window, [main_window] { receiver_clock_diagnostics_dock_init(main_window); },\n"
        "\t\tQt::QueuedConnection);\n"
        "}\n",
        "dock queue helper",
    )
    text = replace_once(
        text,
        "\tif (main_window) {\n\t\tauto menu_action = static_cast<QAction *>(",
        "\tif (main_window) {\n"
        "\t\t// Register immediately and retry after OBS reports finished loading. The dock is\n"
        "\t\t// diagnostic UI and must not depend on the NDI runtime feature-registration path.\n"
        "\t\tqueue_receiver_clock_diagnostics_dock(main_window);\n\n"
        "\t\tauto menu_action = static_cast<QAction *>(",
        "immediate dock registration",
    )
    text = replace_once(
        text,
        "\t\tmenu_action->connect(menu_action, &QAction::triggered, menu_cb);\n\n"
        "\t\tobs_frontend_add_event_callback(",
        "\t\tmenu_action->connect(menu_action, &QAction::triggered, menu_cb);\n\n"
        "\t\tauto diagnostics_menu_action = static_cast<QAction *>(\n"
        "\t\t\tobs_frontend_add_tools_menu_qaction(\"DistroAV Receiver Clock Health\"));\n"
        "\t\tif (diagnostics_menu_action) {\n"
        "\t\t\tdiagnostics_menu_action->connect(\n"
        "\t\t\t\tdiagnostics_menu_action, &QAction::triggered, [main_window] {\n"
        "\t\t\t\t\treceiver_clock_diagnostics_dock_init(main_window);\n"
        "\t\t\t\t\treceiver_clock_diagnostics_dock_show();\n"
        "\t\t\t\t});\n"
        "\t\t}\n\n"
        "\t\tobs_frontend_add_event_callback(",
        "diagnostics tools menu fallback",
    )
    text = replace_once(
        text,
        "\t\t\t\tif (event == OBS_FRONTEND_EVENT_FINISHED_LOADING) {\n"
        "\t\t\t\t\tif (!plugin_features_registered) {",
        "\t\t\t\tif (event == OBS_FRONTEND_EVENT_FINISHED_LOADING) {\n"
        "\t\t\t\t\tauto main_window = static_cast<QMainWindow *>(obs_frontend_get_main_window());\n"
        "\t\t\t\t\tqueue_receiver_clock_diagnostics_dock(main_window);\n"
        "\t\t\t\t\tif (!plugin_features_registered) {",
        "finished-loading dock retry",
    )
    text = replace_once(
        text,
        "\n\t\t\t\t\tauto main_window = static_cast<QMainWindow *>(obs_frontend_get_main_window());\n"
        "\t\t\t\t\tQMetaObject::invokeMethod(",
        "\n\t\t\t\t\tQMetaObject::invokeMethod(",
        "remove duplicate main-window lookup",
    )
    text = replace_once(
        text,
        "\t\t\t\t} else if (event == OBS_FRONTEND_EVENT_EXIT) {\n"
        "\t\t\t\t\t// Unknown why putting this in obs_module_unload causes a crash when closing OBS\n"
        "\t\t\t\t\tmain_output_deinit();",
        "\t\t\t\t} else if (event == OBS_FRONTEND_EVENT_EXIT) {\n"
        "\t\t\t\t\treceiver_clock_diagnostics_dock_deinit();\n"
        "\t\t\t\t\t// Unknown why putting this in obs_module_unload causes a crash when closing OBS\n"
        "\t\t\t\t\tmain_output_deinit();",
        "dock shutdown event",
    )
    text = replace_once(
        text,
        "void obs_module_unload(void)\n{\n\tobs_log(LOG_DEBUG, \"+obs_module_unload()\");\n\n\tupdateCheckStop();",
        "void obs_module_unload(void)\n{\n"
        "\tobs_log(LOG_DEBUG, \"+obs_module_unload()\");\n\n"
        "\treceiver_clock_diagnostics_dock_deinit();\n"
        "\tupdateCheckStop();",
        "dock unload safety",
    )
    return text


def patch_cmake(text: str) -> str:
    return replace_once(
        text,
        "    src/receiver-clock-diagnostics.cpp\n    src/receiver-clock-diagnostics.h\n",
        "    src/receiver-clock-diagnostics.cpp\n"
        "    src/receiver-clock-diagnostics.h\n"
        "    src/receiver-clock-diagnostics-dock.cpp\n"
        "    src/receiver-clock-diagnostics-dock.h\n",
        "CMake dock sources",
    )


def patch_buildspec(text: str) -> str:
    if '"version": "6.2.1.4"' in text:
        return text
    matches = list(re.finditer(r'"version"\s*:\s*"6\.2\.1\.(?:1|2|3)"', text))
    if len(matches) != 1:
        raise PatchError(
            f"diagnostics build version: expected exactly one 6.2.1.1, 6.2.1.2, or 6.2.1.3 anchor, found {len(matches)}"
        )
    return re.sub(
        r'"version"\s*:\s*"6\.2\.1\.(?:1|2|3)"',
        '"version": "6.2.1.4"',
        text,
        count=1,
    )


def check_applied(root: Path) -> list[str]:
    checks = {
        root / "src/receiver-clock-diagnostics.h": "struct LiveSnapshot",
        root / "src/receiver-clock-diagnostics.cpp": "LiveSnapshot Diagnostics::live_snapshot",
        root / "src/ndi-source.cpp": "schedule_clocklab_probe_reconcile",
        root / "src/plugin-main.cpp": "queue_receiver_clock_diagnostics_dock",
        root / "CMakeLists.txt": "src/receiver-clock-diagnostics-dock.cpp",
        root / "buildspec.json": '"version": "6.2.1.4"',
        root / "src/receiver-clock-diagnostics-dock.cpp": "receiver_clock_diagnostics_dock_show",
        root / "src/receiver-clock-diagnostics-dock.h": "receiver_clock_diagnostics_dock_show",
    }
    missing: list[str] = []
    for path, marker in checks.items():
        if not path.exists() or marker not in path.read_text(encoding="utf-8"):
            missing.append(f"{path.relative_to(root)}: missing {marker!r}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None, help="Repository root; defaults to script parent/..")
    parser.add_argument("--check", action="store_true", help="Only verify that the patch is applied")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    if args.check:
        missing = check_applied(root)
        if missing:
            print("Receiver Clock live diagnostics patch is NOT fully applied:", file=sys.stderr)
            for item in missing:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("Receiver Clock live diagnostics patch is fully applied.")
        return 0

    required_new = [
        root / "src/receiver-clock-diagnostics-dock.cpp",
        root / "src/receiver-clock-diagnostics-dock.h",
    ]
    for path in required_new:
        if not path.exists():
            raise PatchError(f"Copy the packaged file into the repository first: {path}")

    changed: list[str] = []
    operations = [
        (root / "src/receiver-clock-diagnostics.h", "struct LiveSnapshot", patch_header),
        (root / "src/receiver-clock-diagnostics.cpp", "LiveSnapshot Diagnostics::live_snapshot", patch_diagnostics_cpp),
        (root / "src/ndi-source.cpp", "schedule_clocklab_probe_reconcile", patch_ndi_source),
        (root / "src/plugin-main.cpp", "queue_receiver_clock_diagnostics_dock", patch_plugin_main),
        (root / "CMakeLists.txt", "src/receiver-clock-diagnostics-dock.cpp", patch_cmake),
        (root / "buildspec.json", '"version": "6.2.1.4"', patch_buildspec),
    ]
    prepared: list[tuple[Path, str]] = []
    for path, marker, transform in operations:
        did_change, updated = prepare_modify(path, marker, transform)
        if did_change:
            prepared.append((path, updated))
            changed.append(str(path.relative_to(root)))

    # Write only after every source file has passed all strict anchor checks.
    for path, updated in prepared:
        path.write_text(updated, encoding="utf-8", newline="\n")

    missing = check_applied(root)
    if missing:
        raise PatchError("Post-apply verification failed:\n" + "\n".join(missing))

    if changed:
        print("Applied Receiver Clock live diagnostics changes:")
        for path in changed:
            print(f"  - {path}")
    else:
        print("Receiver Clock live diagnostics changes were already applied.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
