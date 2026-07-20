#include "receiver-clock-diagnostics.h"

#include <algorithm>
#include <cstdlib>
#include <limits>
#include <sstream>

namespace distroav::clocklab {

int64_t Diagnostics::signed_delta(uint64_t current, uint64_t previous) noexcept
{
	if (current >= previous) {
		const uint64_t delta = current - previous;
		return delta > static_cast<uint64_t>(std::numeric_limits<int64_t>::max())
			       ? std::numeric_limits<int64_t>::max()
			       : static_cast<int64_t>(delta);
	}
	const uint64_t delta = previous - current;
	return delta > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()) ? std::numeric_limits<int64_t>::min()
										  : -static_cast<int64_t>(delta);
}

const char *Diagnostics::event_name(Event event) noexcept
{
	switch (event) {
	case Event::None:
		return "";
	case Event::LoggingEnabled:
		return "logging_enabled";
	case Event::ReceiverReset:
		return "receiver_reset";
	case Event::ReceiverReady:
		return "receiver_ready";
	case Event::ModeChanged:
		return "mode_changed";
	case Event::DiagnosticsChanged:
		return "diagnostics_changed";
	}
	return "unknown";
}

void Diagnostics::clear_stage(StageAtomics &stage) noexcept
{
	stage.sequence.store(0, std::memory_order_relaxed);
	stage.ndi_timestamp_100ns.store(0, std::memory_order_relaxed);
	stage.ndi_timecode_100ns.store(0, std::memory_order_relaxed);
	stage.timestamp_ns.store(0, std::memory_order_relaxed);
	stage.wall_ns.store(0, std::memory_order_relaxed);
	stage.timestamp_delta_ns.store(0, std::memory_order_relaxed);
	stage.wall_delta_ns.store(0, std::memory_order_relaxed);
	stage.unit_a.store(0, std::memory_order_relaxed);
	stage.unit_b.store(0, std::memory_order_relaxed);
	stage.unit_c.store(0, std::memory_order_relaxed);
	stage.observations.store(0, std::memory_order_relaxed);
	stage.pacing_anomalies.store(0, std::memory_order_relaxed);
}

void Diagnostics::clear_downstream_video(DownstreamVideoAtomics &state) noexcept
{
	state.sequence.store(0, std::memory_order_relaxed);
	state.last_selected_timestamp_ns.store(0, std::memory_order_relaxed);
	state.expected_interval_ns.store(0, std::memory_order_relaxed);
	state.selected_timestamp_delta_ns.store(0, std::memory_order_relaxed);
	state.selected_unique_advances.store(0, std::memory_order_relaxed);
	state.selected_repeat_events.store(0, std::memory_order_relaxed);
	state.selected_skip_events.store(0, std::memory_order_relaxed);
	state.selected_skipped_frames.store(0, std::memory_order_relaxed);
	state.selected_backward_events.store(0, std::memory_order_relaxed);
	state.gap_observations.store(0, std::memory_order_relaxed);
	state.last_gap_ns.store(0, std::memory_order_relaxed);
	state.selected_minus_output_projected_ns.store(0, std::memory_order_relaxed);
	state.selected_minus_output_gap_delta_ns.store(0, std::memory_order_relaxed);
	state.gap_jump_threshold_ns.store(0, std::memory_order_relaxed);
	state.gap_jump_events.store(0, std::memory_order_relaxed);
	state.last_gap_jump_ns.store(0, std::memory_order_relaxed);
	state.max_abs_gap_jump_ns.store(0, std::memory_order_relaxed);
	state.min_gap_ns.store(0, std::memory_order_relaxed);
	state.max_gap_ns.store(0, std::memory_order_relaxed);
	state.last_gap_jump_wall_ns.store(0, std::memory_order_relaxed);
	state.last_gap_jump_selected_timestamp_ns.store(0, std::memory_order_relaxed);
	state.last_gap_jump_output_timestamp_ns.store(0, std::memory_order_relaxed);
}

void Diagnostics::publish(StageAtomics &stage, int64_t ndi_timestamp_100ns, int64_t ndi_timecode_100ns,
			  uint64_t timestamp_ns, uint64_t wall_ns, uint32_t unit_a, uint32_t unit_b,
			  uint32_t unit_c) noexcept
{
	const uint64_t previous_timestamp = stage.timestamp_ns.load(std::memory_order_relaxed);
	const uint64_t previous_wall = stage.wall_ns.load(std::memory_order_relaxed);
	const int64_t timestamp_delta = previous_timestamp ? signed_delta(timestamp_ns, previous_timestamp) : 0;
	const int64_t wall_delta = previous_wall ? signed_delta(wall_ns, previous_wall) : 0;

	stage.sequence.fetch_add(1, std::memory_order_acq_rel);
	stage.ndi_timestamp_100ns.store(ndi_timestamp_100ns, std::memory_order_relaxed);
	stage.ndi_timecode_100ns.store(ndi_timecode_100ns, std::memory_order_relaxed);
	stage.timestamp_ns.store(timestamp_ns, std::memory_order_relaxed);
	stage.wall_ns.store(wall_ns, std::memory_order_relaxed);
	stage.timestamp_delta_ns.store(timestamp_delta, std::memory_order_relaxed);
	stage.wall_delta_ns.store(wall_delta, std::memory_order_relaxed);
	stage.unit_a.store(unit_a, std::memory_order_relaxed);
	stage.unit_b.store(unit_b, std::memory_order_relaxed);
	stage.unit_c.store(unit_c, std::memory_order_relaxed);
	stage.observations.fetch_add(1, std::memory_order_relaxed);
	if (previous_timestamp && previous_wall &&
	    (std::llabs(timestamp_delta - wall_delta) > 2000000LL || timestamp_delta <= 0))
		stage.pacing_anomalies.fetch_add(1, std::memory_order_relaxed);
	stage.sequence.fetch_add(1, std::memory_order_release);
}

StageSnapshot Diagnostics::read_stage(const StageAtomics &stage) noexcept
{
	StageSnapshot result;
	for (int attempt = 0; attempt < 4; ++attempt) {
		const uint64_t before = stage.sequence.load(std::memory_order_acquire);
		if (before & 1ULL)
			continue;
		result.ndi_timestamp_100ns = stage.ndi_timestamp_100ns.load(std::memory_order_relaxed);
		result.ndi_timecode_100ns = stage.ndi_timecode_100ns.load(std::memory_order_relaxed);
		result.timestamp_ns = stage.timestamp_ns.load(std::memory_order_relaxed);
		result.wall_ns = stage.wall_ns.load(std::memory_order_relaxed);
		result.timestamp_delta_ns = stage.timestamp_delta_ns.load(std::memory_order_relaxed);
		result.wall_delta_ns = stage.wall_delta_ns.load(std::memory_order_relaxed);
		result.unit_a = stage.unit_a.load(std::memory_order_relaxed);
		result.unit_b = stage.unit_b.load(std::memory_order_relaxed);
		result.unit_c = stage.unit_c.load(std::memory_order_relaxed);
		result.observations = stage.observations.load(std::memory_order_relaxed);
		result.pacing_anomalies = stage.pacing_anomalies.load(std::memory_order_relaxed);
		const uint64_t after = stage.sequence.load(std::memory_order_acquire);
		if (before == after && !(after & 1ULL))
			break;
	}
	return result;
}

DownstreamVideoSnapshot Diagnostics::read_downstream_video() const noexcept
{
	DownstreamVideoSnapshot result;
	for (int attempt = 0; attempt < 4; ++attempt) {
		const uint64_t before = downstream_video_.sequence.load(std::memory_order_acquire);
		if (before & 1ULL)
			continue;
		result.expected_interval_ns =
			downstream_video_.expected_interval_ns.load(std::memory_order_relaxed);
		result.selected_timestamp_delta_ns =
			downstream_video_.selected_timestamp_delta_ns.load(std::memory_order_relaxed);
		result.selected_unique_advances =
			downstream_video_.selected_unique_advances.load(std::memory_order_relaxed);
		result.selected_repeat_events =
			downstream_video_.selected_repeat_events.load(std::memory_order_relaxed);
		result.selected_skip_events =
			downstream_video_.selected_skip_events.load(std::memory_order_relaxed);
		result.selected_skipped_frames =
			downstream_video_.selected_skipped_frames.load(std::memory_order_relaxed);
		result.selected_backward_events =
			downstream_video_.selected_backward_events.load(std::memory_order_relaxed);
		result.gap_observations = downstream_video_.gap_observations.load(std::memory_order_relaxed);
		result.selected_minus_output_projected_ns =
			downstream_video_.selected_minus_output_projected_ns.load(std::memory_order_relaxed);
		result.selected_minus_output_gap_delta_ns =
			downstream_video_.selected_minus_output_gap_delta_ns.load(std::memory_order_relaxed);
		result.gap_jump_threshold_ns =
			downstream_video_.gap_jump_threshold_ns.load(std::memory_order_relaxed);
		result.gap_jump_events = downstream_video_.gap_jump_events.load(std::memory_order_relaxed);
		result.last_gap_jump_ns = downstream_video_.last_gap_jump_ns.load(std::memory_order_relaxed);
		result.max_abs_gap_jump_ns =
			downstream_video_.max_abs_gap_jump_ns.load(std::memory_order_relaxed);
		result.min_gap_ns = downstream_video_.min_gap_ns.load(std::memory_order_relaxed);
		result.max_gap_ns = downstream_video_.max_gap_ns.load(std::memory_order_relaxed);
		result.last_gap_jump_wall_ns =
			downstream_video_.last_gap_jump_wall_ns.load(std::memory_order_relaxed);
		result.last_gap_jump_selected_timestamp_ns =
			downstream_video_.last_gap_jump_selected_timestamp_ns.load(std::memory_order_relaxed);
		result.last_gap_jump_output_timestamp_ns =
			downstream_video_.last_gap_jump_output_timestamp_ns.load(std::memory_order_relaxed);
		const uint64_t after = downstream_video_.sequence.load(std::memory_order_acquire);
		if (before == after && !(after & 1ULL))
			break;
	}
	return result;
}

void Diagnostics::set_enabled(bool enabled, uint64_t wall_ns)
{
	if (enabled == enabled_.load(std::memory_order_acquire))
		return;
	enabled_.store(false, std::memory_order_release);
	if (!enabled) {
		std::lock_guard<std::mutex> lock(ring_mutex_);
		if (live_output_) {
			live_output_.flush();
			live_output_.close();
		}
		return;
	}

	clear_stage(capture_audio_);
	clear_stage(capture_video_);
	clear_stage(output_audio_);
	clear_stage(output_video_);
	clear_stage(filtered_audio_);
	clear_stage(selected_video_);
	clear_downstream_video(downstream_video_);
	{
		std::lock_guard<std::mutex> lock(ring_mutex_);
		ring_.assign(kCapacity, Sample{});
		write_index_ = 0;
		count_ = 0;
		overwritten_ = 0;
		sampled_event_generation_ = 0;
		live_rows_since_flush_ = 0;
		if (live_output_.is_open())
			live_output_.close();
		if (!live_output_path_.empty()) {
			live_output_.open(live_output_path_, std::ios::binary | std::ios::trunc);
			if (live_output_)
				write_csv_header(live_output_);
		}
	}
	session_.fetch_add(1, std::memory_order_acq_rel);
	last_event_.store(static_cast<uint8_t>(Event::LoggingEnabled), std::memory_order_relaxed);
	last_event_wall_ns_.store(wall_ns, std::memory_order_relaxed);
	event_generation_.fetch_add(1, std::memory_order_acq_rel);
	enabled_.store(true, std::memory_order_release);
}

void Diagnostics::set_live_output_path(std::string path)
{
	std::lock_guard<std::mutex> lock(ring_mutex_);
	live_output_path_ = std::move(path);
}

void Diagnostics::mark_event(Event event, uint64_t wall_ns) noexcept
{
	if (!enabled() || event == Event::None)
		return;
	last_event_.store(static_cast<uint8_t>(event), std::memory_order_relaxed);
	last_event_wall_ns_.store(wall_ns, std::memory_order_relaxed);
	event_generation_.fetch_add(1, std::memory_order_acq_rel);
}

void Diagnostics::observe_capture_audio(int64_t ndi_timestamp_100ns, int64_t ndi_timecode_100ns, uint64_t timestamp_ns,
					uint64_t wall_ns, uint32_t frames, uint32_t sample_rate,
					uint32_t channels) noexcept
{
	if (enabled())
		publish(capture_audio_, ndi_timestamp_100ns, ndi_timecode_100ns, timestamp_ns, wall_ns, frames,
			sample_rate, channels);
}

void Diagnostics::observe_capture_video(int64_t ndi_timestamp_100ns, int64_t ndi_timecode_100ns, uint64_t timestamp_ns,
					uint64_t wall_ns, uint32_t width, uint32_t height) noexcept
{
	if (enabled())
		publish(capture_video_, ndi_timestamp_100ns, ndi_timecode_100ns, timestamp_ns, wall_ns, width, height,
			0);
}

void Diagnostics::observe_output_audio(uint64_t timestamp_ns, uint64_t wall_ns, uint32_t frames, uint32_t sample_rate,
				       uint32_t channels) noexcept
{
	if (enabled())
		publish(output_audio_, 0, 0, timestamp_ns, wall_ns, frames, sample_rate, channels);
}

void Diagnostics::observe_output_video(uint64_t timestamp_ns, uint64_t wall_ns, uint32_t width,
				       uint32_t height) noexcept
{
	if (enabled())
		publish(output_video_, 0, 0, timestamp_ns, wall_ns, width, height, 0);
}

void Diagnostics::observe_filtered_audio(uint64_t timestamp_ns, uint64_t wall_ns, uint32_t frames) noexcept
{
	if (enabled())
		publish(filtered_audio_, 0, 0, timestamp_ns, wall_ns, frames, 0, 0);
}

void Diagnostics::observe_selected_video(uint64_t timestamp_ns, uint64_t wall_ns) noexcept
{
	if (!enabled())
		return;

	const StageSnapshot output = read_stage(output_video_);
	publish(selected_video_, 0, 0, timestamp_ns, wall_ns, 0, 0, 0);

	const int64_t nominal_step_100ns =
		scheduler_.nominal_video_step_100ns.load(std::memory_order_relaxed);
	uint64_t expected_interval_ns =
		nominal_step_100ns > 0 ? static_cast<uint64_t>(nominal_step_100ns) * 100ULL : 0;
	if (!expected_interval_ns && output.timestamp_delta_ns > 0)
		expected_interval_ns = static_cast<uint64_t>(output.timestamp_delta_ns);

	auto &state = downstream_video_;
	const uint64_t previous_selected =
		state.last_selected_timestamp_ns.load(std::memory_order_relaxed);
	const int64_t selected_delta =
		previous_selected ? signed_delta(timestamp_ns, previous_selected) : 0;
	const uint64_t previous_gap_observations =
		state.gap_observations.load(std::memory_order_relaxed);

	const bool gap_valid = output.timestamp_ns && output.wall_ns;
	int64_t gap_ns = 0;
	int64_t gap_delta_ns = 0;
	if (gap_valid) {
		gap_ns = signed_delta(timestamp_ns, output.timestamp_ns) +
			 signed_delta(output.wall_ns, wall_ns);
		if (previous_gap_observations)
			gap_delta_ns = gap_ns - state.last_gap_ns.load(std::memory_order_relaxed);
	}

	const uint64_t jump_threshold_ns =
		std::max<uint64_t>(25000000ULL, expected_interval_ns + expected_interval_ns / 2ULL);

	state.sequence.fetch_add(1, std::memory_order_acq_rel);
	state.expected_interval_ns.store(expected_interval_ns, std::memory_order_relaxed);
	state.selected_timestamp_delta_ns.store(selected_delta, std::memory_order_relaxed);

	if (previous_selected) {
		if (selected_delta == 0) {
			state.selected_repeat_events.fetch_add(1, std::memory_order_relaxed);
		} else if (selected_delta < 0) {
			state.selected_backward_events.fetch_add(1, std::memory_order_relaxed);
		} else {
			state.selected_unique_advances.fetch_add(1, std::memory_order_relaxed);
			if (expected_interval_ns &&
			    static_cast<uint64_t>(selected_delta) >
				    expected_interval_ns + expected_interval_ns / 2ULL) {
				const uint64_t advanced_frames =
					(static_cast<uint64_t>(selected_delta) + expected_interval_ns / 2ULL) /
					expected_interval_ns;
				if (advanced_frames > 1) {
					state.selected_skip_events.fetch_add(1, std::memory_order_relaxed);
					state.selected_skipped_frames.fetch_add(advanced_frames - 1,
									 std::memory_order_relaxed);
				}
			}
		}
	}

	if (gap_valid) {
		state.selected_minus_output_projected_ns.store(gap_ns, std::memory_order_relaxed);
		state.selected_minus_output_gap_delta_ns.store(gap_delta_ns, std::memory_order_relaxed);
		state.gap_jump_threshold_ns.store(jump_threshold_ns, std::memory_order_relaxed);

		if (!previous_gap_observations) {
			state.min_gap_ns.store(gap_ns, std::memory_order_relaxed);
			state.max_gap_ns.store(gap_ns, std::memory_order_relaxed);
		} else {
			state.min_gap_ns.store(
				std::min(gap_ns, state.min_gap_ns.load(std::memory_order_relaxed)),
				std::memory_order_relaxed);
			state.max_gap_ns.store(
				std::max(gap_ns, state.max_gap_ns.load(std::memory_order_relaxed)),
				std::memory_order_relaxed);
		}

		const int64_t absolute_gap_delta = std::llabs(gap_delta_ns);
		if (absolute_gap_delta >
		    state.max_abs_gap_jump_ns.load(std::memory_order_relaxed))
			state.max_abs_gap_jump_ns.store(absolute_gap_delta, std::memory_order_relaxed);

		if (previous_gap_observations &&
		    static_cast<uint64_t>(absolute_gap_delta) >= jump_threshold_ns) {
			state.gap_jump_events.fetch_add(1, std::memory_order_relaxed);
			state.last_gap_jump_ns.store(gap_delta_ns, std::memory_order_relaxed);
			state.last_gap_jump_wall_ns.store(wall_ns, std::memory_order_relaxed);
			state.last_gap_jump_selected_timestamp_ns.store(timestamp_ns,
									    std::memory_order_relaxed);
			state.last_gap_jump_output_timestamp_ns.store(output.timestamp_ns,
									  std::memory_order_relaxed);
		}

		state.last_gap_ns.store(gap_ns, std::memory_order_relaxed);
		state.gap_observations.fetch_add(1, std::memory_order_relaxed);
	}

	state.last_selected_timestamp_ns.store(timestamp_ns, std::memory_order_relaxed);
	state.sequence.fetch_add(1, std::memory_order_release);
}

void Diagnostics::update_scheduler(const SchedulerSnapshot &snapshot) noexcept
{
	scheduler_.mode.store(snapshot.mode, std::memory_order_relaxed);
	scheduler_.receiver_epoch_ns.store(snapshot.receiver_epoch_ns, std::memory_order_relaxed);
	scheduler_.next_audio_deadline_ns.store(snapshot.next_audio_deadline_ns, std::memory_order_relaxed);
	scheduler_.next_video_deadline_ns.store(snapshot.next_video_deadline_ns, std::memory_order_relaxed);
	scheduler_.cumulative_audio_frames.store(snapshot.cumulative_audio_frames, std::memory_order_relaxed);
	scheduler_.video_ticks.store(snapshot.video_ticks, std::memory_order_relaxed);
	scheduler_.audio_deadline_error_ns.store(snapshot.audio_deadline_error_ns, std::memory_order_relaxed);
	scheduler_.video_deadline_error_ns.store(snapshot.video_deadline_error_ns, std::memory_order_relaxed);
	scheduler_.audio_catchups.store(snapshot.audio_catchups, std::memory_order_relaxed);
	scheduler_.video_catchups.store(snapshot.video_catchups, std::memory_order_relaxed);
	scheduler_.repeated_video_frames.store(snapshot.repeated_video_frames, std::memory_order_relaxed);
	scheduler_.consecutive_video_repeats.store(snapshot.consecutive_video_repeats, std::memory_order_relaxed);
	scheduler_.recovered_video_repeats.store(snapshot.recovered_video_repeats, std::memory_order_relaxed);
	scheduler_.video_repeat_debt_frames.store(snapshot.video_repeat_debt_frames, std::memory_order_relaxed);
	scheduler_.max_video_repeat_debt_frames.store(snapshot.max_video_repeat_debt_frames, std::memory_order_relaxed);
	scheduler_.source_video_skipped_frames.store(snapshot.source_video_skipped_frames, std::memory_order_relaxed);
	scheduler_.last_video_ndi_timestamp_100ns.store(snapshot.last_video_ndi_timestamp_100ns, std::memory_order_relaxed);
	scheduler_.last_video_ndi_timecode_100ns.store(snapshot.last_video_ndi_timecode_100ns, std::memory_order_relaxed);
	scheduler_.source_video_identity_delta_100ns.store(snapshot.source_video_identity_delta_100ns, std::memory_order_relaxed);
	scheduler_.nominal_video_step_100ns.store(snapshot.nominal_video_step_100ns, std::memory_order_relaxed);
	scheduler_.empty_audio_pulls.store(snapshot.empty_audio_pulls, std::memory_order_relaxed);
	scheduler_.empty_video_pulls.store(snapshot.empty_video_pulls, std::memory_order_relaxed);
	scheduler_.ndi_total_audio_frames.store(snapshot.ndi_total_audio_frames, std::memory_order_relaxed);
	scheduler_.ndi_total_video_frames.store(snapshot.ndi_total_video_frames, std::memory_order_relaxed);
	scheduler_.ndi_dropped_audio_frames.store(snapshot.ndi_dropped_audio_frames, std::memory_order_relaxed);
	scheduler_.ndi_dropped_video_frames.store(snapshot.ndi_dropped_video_frames, std::memory_order_relaxed);
	scheduler_.ndi_queued_audio_frames.store(snapshot.ndi_queued_audio_frames, std::memory_order_relaxed);
	scheduler_.ndi_queued_video_frames.store(snapshot.ndi_queued_video_frames, std::memory_order_relaxed);
}

SchedulerSnapshot Diagnostics::read_scheduler() const noexcept
{
	SchedulerSnapshot result;
	result.mode = scheduler_.mode.load(std::memory_order_relaxed);
	result.receiver_epoch_ns = scheduler_.receiver_epoch_ns.load(std::memory_order_relaxed);
	result.next_audio_deadline_ns = scheduler_.next_audio_deadline_ns.load(std::memory_order_relaxed);
	result.next_video_deadline_ns = scheduler_.next_video_deadline_ns.load(std::memory_order_relaxed);
	result.cumulative_audio_frames = scheduler_.cumulative_audio_frames.load(std::memory_order_relaxed);
	result.video_ticks = scheduler_.video_ticks.load(std::memory_order_relaxed);
	result.audio_deadline_error_ns = scheduler_.audio_deadline_error_ns.load(std::memory_order_relaxed);
	result.video_deadline_error_ns = scheduler_.video_deadline_error_ns.load(std::memory_order_relaxed);
	result.audio_catchups = scheduler_.audio_catchups.load(std::memory_order_relaxed);
	result.video_catchups = scheduler_.video_catchups.load(std::memory_order_relaxed);
	result.repeated_video_frames = scheduler_.repeated_video_frames.load(std::memory_order_relaxed);
	result.consecutive_video_repeats = scheduler_.consecutive_video_repeats.load(std::memory_order_relaxed);
	result.recovered_video_repeats = scheduler_.recovered_video_repeats.load(std::memory_order_relaxed);
	result.video_repeat_debt_frames = scheduler_.video_repeat_debt_frames.load(std::memory_order_relaxed);
	result.max_video_repeat_debt_frames = scheduler_.max_video_repeat_debt_frames.load(std::memory_order_relaxed);
	result.source_video_skipped_frames = scheduler_.source_video_skipped_frames.load(std::memory_order_relaxed);
	result.last_video_ndi_timestamp_100ns = scheduler_.last_video_ndi_timestamp_100ns.load(std::memory_order_relaxed);
	result.last_video_ndi_timecode_100ns = scheduler_.last_video_ndi_timecode_100ns.load(std::memory_order_relaxed);
	result.source_video_identity_delta_100ns = scheduler_.source_video_identity_delta_100ns.load(std::memory_order_relaxed);
	result.nominal_video_step_100ns = scheduler_.nominal_video_step_100ns.load(std::memory_order_relaxed);
	result.empty_audio_pulls = scheduler_.empty_audio_pulls.load(std::memory_order_relaxed);
	result.empty_video_pulls = scheduler_.empty_video_pulls.load(std::memory_order_relaxed);
	result.ndi_total_audio_frames = scheduler_.ndi_total_audio_frames.load(std::memory_order_relaxed);
	result.ndi_total_video_frames = scheduler_.ndi_total_video_frames.load(std::memory_order_relaxed);
	result.ndi_dropped_audio_frames = scheduler_.ndi_dropped_audio_frames.load(std::memory_order_relaxed);
	result.ndi_dropped_video_frames = scheduler_.ndi_dropped_video_frames.load(std::memory_order_relaxed);
	result.ndi_queued_audio_frames = scheduler_.ndi_queued_audio_frames.load(std::memory_order_relaxed);
	result.ndi_queued_video_frames = scheduler_.ndi_queued_video_frames.load(std::memory_order_relaxed);
	return result;
}

void Diagnostics::sample(uint64_t wall_ns)
{
	if (!enabled())
		return;
	Sample row;
	row.wall_ns = wall_ns;
	row.session = session_.load(std::memory_order_relaxed);
	row.event_generation = event_generation_.load(std::memory_order_acquire);
	row.capture_audio = read_stage(capture_audio_);
	row.capture_video = read_stage(capture_video_);
	row.output_audio = read_stage(output_audio_);
	row.output_video = read_stage(output_video_);
	row.filtered_audio = read_stage(filtered_audio_);
	row.selected_video = read_stage(selected_video_);
	row.downstream_video = read_downstream_video();
	row.scheduler = read_scheduler();

	std::lock_guard<std::mutex> lock(ring_mutex_);
	if (ring_.empty())
		return;
	if (row.event_generation != sampled_event_generation_) {
		row.event = static_cast<Event>(last_event_.load(std::memory_order_relaxed));
		row.event_wall_ns = last_event_wall_ns_.load(std::memory_order_relaxed);
		sampled_event_generation_ = row.event_generation;
	}
	row.overwritten_at_capture = overwritten_;
	ring_[write_index_] = row;
	write_index_ = (write_index_ + 1) % ring_.size();
	if (count_ < ring_.size())
		++count_;
	else
		++overwritten_;
	if (live_output_) {
		write_csv_row(live_output_, row);
		if (++live_rows_since_flush_ >= 16) {
			live_output_.flush();
			live_rows_since_flush_ = 0;
		}
	}
}

namespace {
void write_stage_header(std::ostream &out, const char *prefix, const char *unit_a, const char *unit_b,
			const char *unit_c)
{
	out << ',' << prefix << "_timestamp_ns," << prefix << "_wall_ns," << prefix << "_timestamp_delta_ns," << prefix
	    << "_wall_delta_ns," << prefix << "_ndi_timestamp_100ns," << prefix << "_ndi_timecode_100ns," << prefix
	    << '_' << unit_a << ',' << prefix << '_' << unit_b << ',' << prefix << '_' << unit_c << ',' << prefix
	    << "_observations," << prefix << "_pacing_anomalies";
}

void write_stage(std::ostream &out, const StageSnapshot &stage)
{
	out << ',' << stage.timestamp_ns << ',' << stage.wall_ns << ',' << stage.timestamp_delta_ns << ','
	    << stage.wall_delta_ns << ',' << stage.ndi_timestamp_100ns << ',' << stage.ndi_timecode_100ns << ','
	    << stage.unit_a << ',' << stage.unit_b << ',' << stage.unit_c << ',' << stage.observations << ','
	    << stage.pacing_anomalies;
}

int64_t projected_relation(const StageSnapshot &a, const StageSnapshot &b)
{
	if (!a.timestamp_ns || !a.wall_ns || !b.timestamp_ns || !b.wall_ns)
		return 0;
	auto delta = [](uint64_t current, uint64_t previous) {
		if (current >= previous)
			return static_cast<int64_t>(std::min<uint64_t>(current - previous, INT64_MAX));
		return -static_cast<int64_t>(std::min<uint64_t>(previous - current, INT64_MAX));
	};
	return delta(a.timestamp_ns, b.timestamp_ns) + delta(b.wall_ns, a.wall_ns);
}
} // namespace

void Diagnostics::write_csv_header(std::ostream &out)
{
	out << "sample_wall_ns,session,event,event_generation,event_wall_ns,overwritten_samples";
	write_stage_header(out, "capture_audio", "frames", "sample_rate", "channels");
	write_stage_header(out, "capture_video", "width", "height", "unused");
	write_stage_header(out, "output_audio", "frames", "sample_rate", "channels");
	write_stage_header(out, "output_video", "width", "height", "unused");
	write_stage_header(out, "filtered_audio", "frames", "unused_a", "unused_b");
	write_stage_header(out, "selected_video", "unused_a", "unused_b", "unused_c");
	out << ",selected_video_expected_interval_ns,selected_video_timestamp_delta_ns"
	       ",selected_video_unique_advances,selected_video_repeat_events,selected_video_skip_events"
	       ",selected_video_skipped_frames,selected_video_backward_events,selected_output_gap_observations"
	       ",selected_minus_output_live_projected_ns,selected_minus_output_live_gap_delta_ns"
	       ",selected_output_gap_jump_threshold_ns,selected_output_gap_jump_events"
	       ",selected_output_last_gap_jump_ns,selected_output_max_abs_gap_jump_ns"
	       ",selected_output_min_gap_ns,selected_output_max_gap_ns"
	       ",selected_output_last_gap_jump_wall_ns"
	       ",selected_output_last_gap_jump_selected_timestamp_ns"
	       ",selected_output_last_gap_jump_output_timestamp_ns";
	out << ",mode,receiver_epoch_ns,next_audio_deadline_ns,next_video_deadline_ns,cumulative_audio_frames,video_ticks"
	       ",audio_deadline_error_ns,video_deadline_error_ns,audio_catchups,video_catchups,repeated_video_frames"
	       ",consecutive_video_repeats,recovered_video_repeats,video_repeat_debt_frames"
	       ",max_video_repeat_debt_frames,source_video_skipped_frames,last_video_ndi_timestamp_100ns"
	       ",last_video_ndi_timecode_100ns,source_video_identity_delta_100ns,nominal_video_step_100ns"
	       ",empty_audio_pulls,empty_video_pulls,ndi_total_audio_frames,ndi_total_video_frames"
	       ",ndi_dropped_audio_frames,ndi_dropped_video_frames,ndi_queued_audio_frames,ndi_queued_video_frames"
	       ",capture_video_minus_capture_audio_projected_ns"
	       ",output_video_minus_output_audio_projected_ns,selected_video_minus_output_video_projected_ns"
	       ",filtered_audio_minus_output_audio_projected_ns,selected_video_minus_filtered_audio_projected_ns\n";
}

void Diagnostics::write_csv_row(std::ostream &out, const Sample &row)
{
	out << row.wall_ns << ',' << row.session << ',' << event_name(row.event) << ',' << row.event_generation << ','
	    << row.event_wall_ns << ',' << row.overwritten_at_capture;
	write_stage(out, row.capture_audio);
	write_stage(out, row.capture_video);
	write_stage(out, row.output_audio);
	write_stage(out, row.output_video);
	write_stage(out, row.filtered_audio);
	write_stage(out, row.selected_video);
	const auto &d = row.downstream_video;
	out << ',' << d.expected_interval_ns << ',' << d.selected_timestamp_delta_ns << ','
	    << d.selected_unique_advances << ',' << d.selected_repeat_events << ',' << d.selected_skip_events << ','
	    << d.selected_skipped_frames << ',' << d.selected_backward_events << ',' << d.gap_observations << ','
	    << d.selected_minus_output_projected_ns << ',' << d.selected_minus_output_gap_delta_ns << ','
	    << d.gap_jump_threshold_ns << ',' << d.gap_jump_events << ',' << d.last_gap_jump_ns << ','
	    << d.max_abs_gap_jump_ns << ',' << d.min_gap_ns << ',' << d.max_gap_ns << ','
	    << d.last_gap_jump_wall_ns << ',' << d.last_gap_jump_selected_timestamp_ns << ','
	    << d.last_gap_jump_output_timestamp_ns;
	const auto &s = row.scheduler;
	out << ',' << s.mode << ',' << s.receiver_epoch_ns << ',' << s.next_audio_deadline_ns << ','
	    << s.next_video_deadline_ns << ',' << s.cumulative_audio_frames << ',' << s.video_ticks << ','
	    << s.audio_deadline_error_ns << ',' << s.video_deadline_error_ns << ',' << s.audio_catchups << ','
	    << s.video_catchups << ',' << s.repeated_video_frames << ',' << s.consecutive_video_repeats << ','
	    << s.recovered_video_repeats << ',' << s.video_repeat_debt_frames << ','
	    << s.max_video_repeat_debt_frames << ',' << s.source_video_skipped_frames << ','
	    << s.last_video_ndi_timestamp_100ns << ',' << s.last_video_ndi_timecode_100ns << ','
	    << s.source_video_identity_delta_100ns << ',' << s.nominal_video_step_100ns << ','
	    << s.empty_audio_pulls << ',' << s.empty_video_pulls << ',' << s.ndi_total_audio_frames << ','
	    << s.ndi_total_video_frames << ','
	    << s.ndi_dropped_audio_frames << ',' << s.ndi_dropped_video_frames << ',' << s.ndi_queued_audio_frames
	    << ',' << s.ndi_queued_video_frames << ',' << projected_relation(row.capture_video, row.capture_audio)
	    << ',' << projected_relation(row.output_video, row.output_audio) << ','
	    << projected_relation(row.selected_video, row.output_video) << ','
	    << projected_relation(row.filtered_audio, row.output_audio) << ','
	    << projected_relation(row.selected_video, row.filtered_audio) << '\n';
}

std::string Diagnostics::csv() const
{
	std::lock_guard<std::mutex> lock(ring_mutex_);
	std::ostringstream out;
	write_csv_header(out);
	if (ring_.empty() || !count_)
		return out.str();
	const size_t first = count_ == ring_.size() ? write_index_ : 0;
	for (size_t offset = 0; offset < count_; ++offset)
		write_csv_row(out, ring_[(first + offset) % ring_.size()]);
	return out.str();
}

size_t Diagnostics::sample_count() const
{
	std::lock_guard<std::mutex> lock(ring_mutex_);
	return count_;
}

uint64_t Diagnostics::overwritten_samples() const
{
	std::lock_guard<std::mutex> lock(ring_mutex_);
	return overwritten_;
}

} // namespace distroav::clocklab
