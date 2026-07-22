#include "receiver-clock-diagnostics-dock.h"

#include "plugin-main.h"
#include "receiver-clock-diagnostics.h"

#include <obs-frontend-api.h>
#include <util/platform.h>

#include <QApplication>
#include <QClipboard>
#include <QComboBox>
#include <QDesktopServices>
#include <QDockWidget>
#include <QFont>
#include <QGridLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QMainWindow>
#include <QPointer>
#include <QPushButton>
#include <QSignalBlocker>
#include <QStringList>
#include <QTimer>
#include <QUrl>
#include <QVariant>
#include <QVBoxLayout>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <vector>

namespace {

constexpr const char *kDockId = "distroav_receiver_clock_health";
constexpr const char *kDockTitle = "DistroAV Receiver Clock Health";
constexpr double kGoodOffsetMs = 40.0;
constexpr double kWarningOffsetMs = 80.0;
constexpr double kGrowingRateMsPerMinute = 0.50;

QPointer<QWidget> dock_widget;

double ns_to_ms(int64_t ns)
{
	return static_cast<double>(ns) / 1000000.0;
}

QString signed_number(double value, int decimals)
{
	return (value >= 0.0 ? QStringLiteral("+") : QString()) + QString::number(value, 'f', decimals);
}

QString signed_ms(int64_t ns)
{
	return QStringLiteral("%1 ms").arg(signed_number(ns_to_ms(ns), 1));
}

QString signed_rate(double rate)
{
	if (!std::isfinite(rate))
		return QStringLiteral("Collecting history…");
	return QStringLiteral("%1 ms/min").arg(signed_number(rate, 3));
}

QString data_age_text(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (!snapshot.latest_observation_wall_ns || snapshot.wall_ns < snapshot.latest_observation_wall_ns)
		return QStringLiteral("No live frames yet");
	const double age_ms = static_cast<double>(snapshot.wall_ns - snapshot.latest_observation_wall_ns) / 1000000.0;
	return QStringLiteral("%1 ms").arg(age_ms, 0, 'f', 0);
}

double active_final_trend(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (snapshot.has_trend_10m)
		return snapshot.final_av_trend_10m_ms_per_min;
	if (snapshot.has_trend_60s)
		return snapshot.final_av_trend_60s_ms_per_min;
	return std::numeric_limits<double>::quiet_NaN();
}

double active_output_trend(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (snapshot.has_trend_10m)
		return snapshot.output_av_trend_10m_ms_per_min;
	if (snapshot.has_trend_60s)
		return snapshot.output_av_trend_60s_ms_per_min;
	return std::numeric_limits<double>::quiet_NaN();
}

double active_video_path_trend(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (snapshot.has_trend_10m)
		return snapshot.video_path_trend_10m_ms_per_min;
	if (snapshot.has_trend_60s)
		return snapshot.video_path_trend_60s_ms_per_min;
	return std::numeric_limits<double>::quiet_NaN();
}

double active_audio_path_trend(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (snapshot.has_trend_10m)
		return snapshot.audio_path_trend_10m_ms_per_min;
	if (snapshot.has_trend_60s)
		return snapshot.audio_path_trend_60s_ms_per_min;
	return std::numeric_limits<double>::quiet_NaN();
}

QString status_name(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (!snapshot.enabled)
		return QStringLiteral("DIAGNOSTICS OFF");
	if (!snapshot.selected_video.observations || !snapshot.filtered_audio.observations)
		return QStringLiteral("WAITING FOR A/V");
	if (snapshot.latest_observation_wall_ns && snapshot.wall_ns > snapshot.latest_observation_wall_ns + 3000000000ULL)
		return QStringLiteral("DATA STALE");

	const double offset = std::abs(ns_to_ms(snapshot.final_av_ns));
	const double trend = std::abs(active_final_trend(snapshot));
	if (offset <= kGoodOffsetMs && (!std::isfinite(trend) || trend < 0.25))
		return QStringLiteral("GOOD");
	if (offset <= kWarningOffsetMs && (!std::isfinite(trend) || trend < 1.0))
		return QStringLiteral("WATCH");
	return QStringLiteral("WARNING");
}

QString status_style(const QString &status)
{
	if (status == QStringLiteral("GOOD"))
		return QStringLiteral("QLabel { background: #176b36; color: white; border-radius: 5px; padding: 8px; }");
	if (status == QStringLiteral("WATCH"))
		return QStringLiteral("QLabel { background: #8a6500; color: white; border-radius: 5px; padding: 8px; }");
	if (status == QStringLiteral("WARNING") || status == QStringLiteral("DATA STALE"))
		return QStringLiteral("QLabel { background: #8b2525; color: white; border-radius: 5px; padding: 8px; }");
	return QStringLiteral("QLabel { background: #4b4b4b; color: white; border-radius: 5px; padding: 8px; }");
}

QString av_explanation(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (!snapshot.enabled)
		return QStringLiteral("Enable Receiver Clock diagnostics in this NDI source's properties.");
	if (!snapshot.selected_video.observations || !snapshot.filtered_audio.observations)
		return QStringLiteral("Waiting for both OBS-selected video and post-filter audio observations.");

	const double final_ms = ns_to_ms(snapshot.final_av_ns);
	const double absolute_ms = std::abs(final_ms);
	if (absolute_ms <= kGoodOffsetMs)
		return QStringLiteral("Audio and video are currently close enough that no obvious sync problem is indicated.");
	if (final_ms > 0.0)
		return QStringLiteral("Audio appears late relative to video by about %1 ms.").arg(absolute_ms, 0, 'f', 1);
	return QStringLiteral("Video appears late relative to audio by about %1 ms.").arg(absolute_ms, 0, 'f', 1);
}

QString likely_cause(const distroav::clocklab::LiveSnapshot &snapshot)
{
	if (!snapshot.enabled)
		return QStringLiteral("Diagnostics are disabled; no diagnosis is possible yet.");
	if (!snapshot.selected_video.observations || !snapshot.filtered_audio.observations)
		return QStringLiteral("No complete downstream A/V measurement yet.");
	if (snapshot.latest_observation_wall_ns && snapshot.wall_ns > snapshot.latest_observation_wall_ns + 3000000000ULL)
		return QStringLiteral("The receiver stopped producing fresh diagnostic observations.");

	const double final_trend = active_final_trend(snapshot);
	const double output_trend = active_output_trend(snapshot);
	const double video_trend = active_video_path_trend(snapshot);
	const double audio_trend = active_audio_path_trend(snapshot);

	const double abs_output = std::isfinite(output_trend) ? std::abs(output_trend) : 0.0;
	const double abs_video = std::isfinite(video_trend) ? std::abs(video_trend) : 0.0;
	const double abs_audio = std::isfinite(audio_trend) ? std::abs(audio_trend) : 0.0;

	if ((snapshot.scheduler.ndi_queued_audio_frames > 4 || snapshot.scheduler.ndi_queued_video_frames > 4) &&
	    (snapshot.scheduler.ndi_dropped_audio_frames > 0 || snapshot.scheduler.ndi_dropped_video_frames > 0))
		return QStringLiteral("NDI receive pressure is visible: queued media and dropped frames were both reported.");

	if (abs_audio >= kGrowingRateMsPerMinute && abs_audio >= abs_video && abs_audio >= abs_output)
		return QStringLiteral("Most movement is appearing after DistroAV in the OBS audio/filter path. This fits growing audio buffering or mixer latency.");
	if (abs_video >= kGrowingRateMsPerMinute && abs_video >= abs_audio && abs_video >= abs_output)
		return QStringLiteral("Most movement is appearing after DistroAV in OBS's video selection path. This fits a growing async-video queue.");
	if (abs_output >= kGrowingRateMsPerMinute && abs_output >= abs_audio && abs_output >= abs_video)
		return QStringLiteral("The A/V relationship is already moving at DistroAV's output boundary, before downstream OBS buffering.");
	if (std::isfinite(final_trend) && std::abs(final_trend) >= kGrowingRateMsPerMinute)
		return QStringLiteral("A real downstream A/V trend is present, but no single measured queue currently dominates it.");
	if (std::abs(ns_to_ms(snapshot.final_av_ns)) > kWarningOffsetMs)
		return QStringLiteral("The offset is large but presently looks mostly static, not progressively growing.");
	return QStringLiteral("No meaningful growing queue or clock-path movement is visible right now.");
}

class ReceiverClockDiagnosticsDock final : public QWidget {
public:
	explicit ReceiverClockDiagnosticsDock(QWidget *parent) : QWidget(parent)
	{
		auto *root = new QVBoxLayout(this);
		root->setContentsMargins(10, 10, 10, 10);
		root->setSpacing(8);

		auto *title = new QLabel(QStringLiteral("Receiver Clock Health"), this);
		QFont title_font = title->font();
		title_font.setPointSize(title_font.pointSize() + 3);
		title_font.setBold(true);
		title->setFont(title_font);
		root->addWidget(title);

		auto *source_row = new QHBoxLayout();
		source_row->addWidget(new QLabel(QStringLiteral("NDI source:"), this));
		source_combo_ = new QComboBox(this);
		source_combo_->setSizeAdjustPolicy(QComboBox::AdjustToContents);
		source_row->addWidget(source_combo_, 1);
		root->addLayout(source_row);

		status_label_ = new QLabel(QStringLiteral("WAITING"), this);
		status_label_->setAlignment(Qt::AlignCenter);
		QFont status_font = status_label_->font();
		status_font.setPointSize(status_font.pointSize() + 4);
		status_font.setBold(true);
		status_label_->setFont(status_font);
		root->addWidget(status_label_);

		summary_label_ = new QLabel(QStringLiteral("Waiting for an instrumented NDI source."), this);
		summary_label_->setWordWrap(true);
		root->addWidget(summary_label_);

		auto *metrics_box = new QGroupBox(QStringLiteral("Live measurements"), this);
		auto *metrics = new QGridLayout(metrics_box);
		metrics->setColumnStretch(1, 1);

		int row = 0;
		final_av_value_ = add_metric(metrics, row++, QStringLiteral("Final A/V difference"),
					   QStringLiteral("Positive means audio is late relative to video. Negative means video is late relative to audio."));
		trend_value_ = add_metric(metrics, row++, QStringLiteral("A/V movement"),
					QStringLiteral("Uses a ten-minute history when available, otherwise a one-minute history."));
		output_av_value_ = add_metric(metrics, row++, QStringLiteral("At DistroAV output"),
					    QStringLiteral("A/V difference at the plugin output boundary, before downstream OBS filtering and selection."));
		video_path_value_ = add_metric(metrics, row++, QStringLiteral("OBS video path"),
					     QStringLiteral("Submitted-to-selected video relationship. Persistent growth points to an OBS async-video backlog."));
		audio_path_value_ = add_metric(metrics, row++, QStringLiteral("OBS audio path"),
					     QStringLiteral("DistroAV-output to post-filter audio relationship. Persistent growth points to downstream audio buffering."));
		ndi_queue_value_ = add_metric(metrics, row++, QStringLiteral("NDI receive queue"),
					    QStringLiteral("Queued audio and video frames reported by the NDI receiver."));
		ndi_drop_value_ = add_metric(metrics, row++, QStringLiteral("NDI dropped frames"),
					   QStringLiteral("Cumulative audio and video drops reported by NDI for this receiver session."));
		deadline_value_ = add_metric(metrics, row++, QStringLiteral("Clock deadline error"),
					   QStringLiteral("How late the receiver-paced audio and video schedules were at the latest sample."));
		catchup_value_ = add_metric(metrics, row++, QStringLiteral("Clock catch-ups"),
					  QStringLiteral("Cumulative schedule catch-ups. These are timing recovery events, not PPM correction."));
		repeat_value_ = add_metric(metrics, row++, QStringLiteral("Video repeat debt"),
					 QStringLiteral("Current and maximum count of repeated FrameSync video identities waiting to recover."));
		age_value_ = add_metric(metrics, row++, QStringLiteral("Latest data age"),
				      QStringLiteral("Time since the newest audio or video observation."));
		root->addWidget(metrics_box);

		auto *cause_box = new QGroupBox(QStringLiteral("Most likely location"), this);
		auto *cause_layout = new QVBoxLayout(cause_box);
		cause_label_ = new QLabel(QStringLiteral("Waiting for data."), cause_box);
		cause_label_->setWordWrap(true);
		cause_layout->addWidget(cause_label_);
		root->addWidget(cause_box);

		auto *note = new QLabel(
			QStringLiteral("This dock only observes timestamps, queue behavior, and timing history. It does not apply PPM correction or change the receiver clock fix."),
			this);
		note->setWordWrap(true);
		note->setStyleSheet(QStringLiteral("QLabel { color: palette(mid); font-style: italic; }"));
		root->addWidget(note);

		auto *buttons = new QHBoxLayout();
		auto *open_folder = new QPushButton(QStringLiteral("Open diagnostics folder"), this);
		auto *copy_summary = new QPushButton(QStringLiteral("Copy summary"), this);
		buttons->addWidget(open_folder);
		buttons->addWidget(copy_summary);
		root->addLayout(buttons);
		root->addStretch(1);

		connect(source_combo_, &QComboBox::currentIndexChanged, this, [this](int) {
			selected_token_ = source_combo_->currentData().toULongLong();
			refresh();
		});
		connect(open_folder, &QPushButton::clicked, this, [] {
			char *path = obs_module_config_path("");
			if (!path)
				return;
			QDesktopServices::openUrl(QUrl::fromLocalFile(QString::fromUtf8(path)));
			bfree(path);
		});
		connect(copy_summary, &QPushButton::clicked, this, [this] {
			QApplication::clipboard()->setText(last_summary_);
		});

		timer_ = new QTimer(this);
		timer_->setInterval(1000);
		connect(timer_, &QTimer::timeout, this, [this] { refresh(); });
		timer_->start();
		refresh();
	}

private:
	static QLabel *add_metric(QGridLayout *layout, int row, const QString &name, const QString &tooltip)
	{
		auto *name_label = new QLabel(name);
		auto *value_label = new QLabel(QStringLiteral("—"));
		value_label->setTextInteractionFlags(Qt::TextSelectableByMouse);
		name_label->setToolTip(tooltip);
		value_label->setToolTip(tooltip);
		layout->addWidget(name_label, row, 0);
		layout->addWidget(value_label, row, 1, Qt::AlignRight);
		return value_label;
	}

	void refresh_source_list(const std::vector<distroav::clocklab::RegisteredLiveSnapshot> &sources)
	{
		bool changed = source_combo_->count() != static_cast<int>(sources.size());
		if (!changed) {
			for (int i = 0; i < source_combo_->count(); ++i) {
				if (source_combo_->itemData(i).toULongLong() != sources[static_cast<size_t>(i)].token ||
				    source_combo_->itemText(i) != QString::fromStdString(sources[static_cast<size_t>(i)].source_name)) {
					changed = true;
					break;
				}
			}
		}
		if (!changed)
			return;

		const QSignalBlocker blocker(source_combo_);
		source_combo_->clear();
		for (const auto &source : sources)
			source_combo_->addItem(QString::fromStdString(source.source_name), QVariant::fromValue<qulonglong>(source.token));

		int selected_index = -1;
		for (int i = 0; i < source_combo_->count(); ++i) {
			if (source_combo_->itemData(i).toULongLong() == selected_token_) {
				selected_index = i;
				break;
			}
		}
		if (selected_index < 0 && source_combo_->count())
			selected_index = 0;
		source_combo_->setCurrentIndex(selected_index);
		selected_token_ = selected_index >= 0 ? source_combo_->itemData(selected_index).toULongLong() : 0;
	}

	void show_empty()
	{
		status_label_->setText(QStringLiteral("NO SOURCE"));
		status_label_->setStyleSheet(status_style(QStringLiteral("NO SOURCE")));
		summary_label_->setText(QStringLiteral("No Receiver Clock Lab NDI source is currently registered."));
		cause_label_->setText(QStringLiteral("Add or load an NDI source from the diagnostics build."));
		for (QLabel *label : {final_av_value_, trend_value_, output_av_value_, video_path_value_, audio_path_value_,
				      ndi_queue_value_, ndi_drop_value_, deadline_value_, catchup_value_, repeat_value_, age_value_})
			label->setText(QStringLiteral("—"));
		last_summary_ = QStringLiteral("DistroAV Receiver Clock Health: no registered source.");
	}

	void refresh()
	{
		const auto sources = distroav::clocklab::registered_live_snapshots(os_gettime_ns());
		refresh_source_list(sources);
		if (sources.empty()) {
			show_empty();
			return;
		}

		const auto it = std::find_if(sources.begin(), sources.end(), [this](const auto &source) {
			return source.token == selected_token_;
		});
		const auto &source = it != sources.end() ? *it : sources.front();
		selected_token_ = source.token;
		const auto &snapshot = source.diagnostics;

		const QString status = status_name(snapshot);
		status_label_->setText(status);
		status_label_->setStyleSheet(status_style(status));
		summary_label_->setText(av_explanation(snapshot));
		cause_label_->setText(likely_cause(snapshot));

		final_av_value_->setText(signed_ms(snapshot.final_av_ns));
		trend_value_->setText(signed_rate(active_final_trend(snapshot)));
		output_av_value_->setText(QStringLiteral("%1  (%2)")
					    .arg(signed_ms(snapshot.output_av_ns), signed_rate(active_output_trend(snapshot))));
		video_path_value_->setText(QStringLiteral("%1  (%2)")
					     .arg(signed_ms(snapshot.video_path_ns), signed_rate(active_video_path_trend(snapshot))));
		audio_path_value_->setText(QStringLiteral("%1  (%2)")
					     .arg(signed_ms(snapshot.audio_path_ns), signed_rate(active_audio_path_trend(snapshot))));
		ndi_queue_value_->setText(QStringLiteral("Audio %1  |  Video %2")
					    .arg(snapshot.scheduler.ndi_queued_audio_frames)
					    .arg(snapshot.scheduler.ndi_queued_video_frames));
		ndi_drop_value_->setText(QStringLiteral("Audio %1  |  Video %2")
					   .arg(snapshot.scheduler.ndi_dropped_audio_frames)
					   .arg(snapshot.scheduler.ndi_dropped_video_frames));
		deadline_value_->setText(QStringLiteral("Audio %1 ms  |  Video %2 ms")
					   .arg(signed_number(ns_to_ms(snapshot.scheduler.audio_deadline_error_ns), 2))
					   .arg(signed_number(ns_to_ms(snapshot.scheduler.video_deadline_error_ns), 2)));
		catchup_value_->setText(QStringLiteral("Audio %1  |  Video %2")
					  .arg(snapshot.scheduler.audio_catchups)
					  .arg(snapshot.scheduler.video_catchups));
		repeat_value_->setText(QStringLiteral("Current %1  |  Max %2")
					 .arg(snapshot.scheduler.video_repeat_debt_frames)
					 .arg(snapshot.scheduler.max_video_repeat_debt_frames));
		age_value_->setText(data_age_text(snapshot));

		last_summary_ = QStringList{
			QStringLiteral("DistroAV Receiver Clock Health"),
			QStringLiteral("Source: %1").arg(QString::fromStdString(source.source_name)),
			QStringLiteral("Status: %1").arg(status),
			QStringLiteral("Final A/V difference: %1").arg(signed_ms(snapshot.final_av_ns)),
			QStringLiteral("A/V movement: %1").arg(signed_rate(active_final_trend(snapshot))),
			QStringLiteral("DistroAV output A/V: %1").arg(signed_ms(snapshot.output_av_ns)),
			QStringLiteral("OBS video path: %1").arg(signed_ms(snapshot.video_path_ns)),
			QStringLiteral("OBS audio path: %1").arg(signed_ms(snapshot.audio_path_ns)),
			QStringLiteral("NDI queue: audio %1, video %2")
				.arg(snapshot.scheduler.ndi_queued_audio_frames)
				.arg(snapshot.scheduler.ndi_queued_video_frames),
			QStringLiteral("NDI dropped: audio %1, video %2")
				.arg(snapshot.scheduler.ndi_dropped_audio_frames)
				.arg(snapshot.scheduler.ndi_dropped_video_frames),
			QStringLiteral("Likely location: %1").arg(likely_cause(snapshot)),
		}.join(QLatin1Char('\n'));
	}

	QComboBox *source_combo_ = nullptr;
	QLabel *status_label_ = nullptr;
	QLabel *summary_label_ = nullptr;
	QLabel *final_av_value_ = nullptr;
	QLabel *trend_value_ = nullptr;
	QLabel *output_av_value_ = nullptr;
	QLabel *video_path_value_ = nullptr;
	QLabel *audio_path_value_ = nullptr;
	QLabel *ndi_queue_value_ = nullptr;
	QLabel *ndi_drop_value_ = nullptr;
	QLabel *deadline_value_ = nullptr;
	QLabel *catchup_value_ = nullptr;
	QLabel *repeat_value_ = nullptr;
	QLabel *age_value_ = nullptr;
	QLabel *cause_label_ = nullptr;
	QTimer *timer_ = nullptr;
	qulonglong selected_token_ = 0;
	QString last_summary_;
};

} // namespace

void receiver_clock_diagnostics_dock_init(QMainWindow *main_window)
{
	if (!main_window) {
		obs_log(LOG_WARNING, "[receiver-clock-lab] Could not register diagnostics dock: no OBS main window");
		return;
	}
	if (dock_widget) {
		receiver_clock_diagnostics_dock_show();
		return;
	}

	auto *widget = new ReceiverClockDiagnosticsDock(main_window);
	bool added = obs_frontend_add_dock_by_id(kDockId, kDockTitle, widget);
	if (!added) {
		// Recover from a stale id left by an earlier in-process test build. The id is
		// plugin-specific, so removing it cannot target an unrelated OBS dock.
		obs_log(LOG_WARNING, "[receiver-clock-lab] Diagnostics dock id already existed; removing stale dock and retrying");
		obs_frontend_remove_dock(kDockId);
		added = obs_frontend_add_dock_by_id(kDockId, kDockTitle, widget);
	}
	if (!added) {
		delete widget;
		obs_log(LOG_ERROR, "[receiver-clock-lab] Could not add diagnostics dock after retry");
		return;
	}

	dock_widget = widget;
	obs_log(LOG_INFO, "[receiver-clock-lab] Live diagnostics dock registered and available in Docks menu");
	receiver_clock_diagnostics_dock_show();
}

void receiver_clock_diagnostics_dock_show()
{
	if (!dock_widget)
		return;

	for (QWidget *ancestor = dock_widget->parentWidget(); ancestor; ancestor = ancestor->parentWidget()) {
		if (auto *dock = qobject_cast<QDockWidget *>(ancestor)) {
			dock->show();
			dock->raise();
			dock->activateWindow();
			return;
		}
	}

	// Defensive fallback if OBS changes the wrapper hierarchy.
	dock_widget->show();
	dock_widget->raise();
}

void receiver_clock_diagnostics_dock_deinit()
{
	if (!dock_widget)
		return;
	QPointer<QWidget> widget = dock_widget;
	dock_widget.clear();
	obs_frontend_remove_dock(kDockId);
	if (widget)
		widget->deleteLater();
}
