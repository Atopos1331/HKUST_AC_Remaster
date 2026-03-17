import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib.dates as mdates
from matplotlib.figure import Figure

from powers.utils.config import Config, Recorder
from powers.utils.logger import log

DB_PATH = Recorder.DB_PATH
FIGURE_DIR = Path(Config.FIGURE_DIR)


@dataclass(frozen=True)
class MetricSpec:
    label: str
    unit: str
    color: str


METRIC_SPECS: Dict[str, MetricSpec] = {
    "temperature": MetricSpec("Indoor Temperature", "C", "#D97706"),
    "outdoor_temp": MetricSpec("Outdoor Temperature", "C", "#DC2626"),
    "heat_index_c": MetricSpec("Indoor Heat Index", "C", "#92400E"),
    "outdoor_heat_index_c": MetricSpec("Outdoor Heat Index", "C", "#7F1D1D"),
    "humidity": MetricSpec("Indoor Humidity", "%", "#0284C7"),
    "outdoor_humidity": MetricSpec("Outdoor Humidity", "%", "#0EA5E9"),
    "ac_power_w": MetricSpec("AC Power", "W", "#6D28D9"),
    "ac_energy_wh": MetricSpec("Energy", "Wh", "#0F766E"),
    "balance_min": MetricSpec("Balance", "min", "#D97706"),
    "ac_on": MetricSpec("AC State", "state", "#111827"),
}


POWER_ON_THRESHOLD_W = 20.0


DEFAULT_METRICS = [
    "temperature",
    "heat_index_c",
    "humidity",
    "outdoor_temp",
    "outdoor_heat_index_c",
    "outdoor_humidity",
    "ac_power_w",
    "ac_energy_wh",
    "balance_min",
]


PLOT_GROUPS: List[Tuple[str, List[str]]] = [
    ("Indoor Climate", ["temperature", "humidity", "heat_index_c"]),
    ("Outdoor Climate", ["outdoor_temp", "outdoor_humidity", "outdoor_heat_index_c"]),
    ("AC Power", ["ac_power_w"]),
    ("Energy and Balance", ["ac_energy_wh", "balance_min"]),
]


HIDDEN_METRICS = {"ac_voltage", "ac_current"}

TIME_RANGE_PRESETS: Dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def safe_mean(values: Iterable[float]) -> Optional[float]:
    values_list = list(values)
    if not values_list:
        return None
    return sum(values_list) / len(values_list)


def fmt_value(value: Optional[float], suffix: str = "", precision: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{precision}f}{suffix}"


def fmt_count(value: Optional[int]) -> str:
    if value is None:
        return "0"
    return str(value)


class ACDataAnalyzer:
    """Query and analyze time-series measurements stored in SQLite."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = None
        return conn

    @staticmethod
    def parse_datetime(dt_str: str) -> datetime:
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

    def get_data(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: List[str],
    ) -> Dict[str, List[Tuple[datetime, float]]]:
        result: Dict[str, List[Tuple[datetime, float]]] = {metric: [] for metric in metrics}
        if not metrics:
            log.warning("[analysis] get_data called without metrics.")
            return result

        placeholders = ",".join("?" for _ in metrics)
        query = f"""
            SELECT ts, metric, value
            FROM measurements
            WHERE metric IN ({placeholders}) AND ts BETWEEN ? AND ?
            ORDER BY ts
        """
        params = [*metrics, start_time.isoformat(), end_time.isoformat()]

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        for ts_str, metric, value in cursor.fetchall():
            try:
                ts = self.parse_datetime(ts_str) if isinstance(ts_str, str) else ts_str
                result[metric].append((ts, float(value)))
            except (ValueError, TypeError):
                continue
        conn.close()
        sample_count = sum(len(values) for values in result.values())
        log.detail(
            f"[analysis] Loaded {sample_count} samples for metrics={metrics} "
            f"range={start_time.isoformat()} -> {end_time.isoformat()}"
        )
        return result

    def get_available_metrics(self) -> List[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT metric FROM measurements ORDER BY metric")
        metrics = [row[0] for row in cursor.fetchall()]
        conn.close()
        return metrics

    def analyze_ac_efficiency(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        data = self.get_data(
            start_time,
            end_time,
            [
                "temperature",
                "humidity",
                "heat_index_c",
                "outdoor_temp",
                "outdoor_humidity",
                "ac_on",
                "ac_power_w",
                "balance_min",
            ],
        )
        analysis: Dict[str, Any] = {
            "total_runtime_hours": 0.0,
            "avg_indoor_temp": None,
            "avg_indoor_humidity": None,
            "avg_indoor_heat_index": None,
            "avg_outdoor_temp": None,
            "avg_outdoor_humidity": None,
            "avg_power_w": None,
            "cooling_cycles": 0,
            "avg_cycle_duration": 0.0,
        }

        ac_on_data = data.get("ac_on", [])
        on_periods = infer_on_periods(data, end_time=end_time)
        if on_periods:
            total_runtime = sum((end - start).total_seconds() for start, end in on_periods)
            analysis["total_runtime_hours"] = total_runtime / 3600
            analysis["cooling_cycles"] = len(on_periods)
            if on_periods:
                analysis["avg_cycle_duration"] = total_runtime / len(on_periods) / 60

        analysis["avg_indoor_temp"] = safe_mean(value for _, value in data.get("temperature", []))
        analysis["avg_indoor_humidity"] = safe_mean(value for _, value in data.get("humidity", []))
        analysis["avg_indoor_heat_index"] = safe_mean(value for _, value in data.get("heat_index_c", []))
        analysis["avg_outdoor_temp"] = safe_mean(value for _, value in data.get("outdoor_temp", []))
        analysis["avg_outdoor_humidity"] = safe_mean(value for _, value in data.get("outdoor_humidity", []))
        analysis["avg_power_w"] = safe_mean(value for _, value in data.get("ac_power_w", []))
        return analysis

    def build_range_stats(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        metrics = [
            "temperature",
            "humidity",
            "heat_index_c",
            "outdoor_temp",
            "outdoor_humidity",
            "outdoor_heat_index_c",
            "ac_power_w",
            "ac_energy_wh",
            "balance_min",
            "ac_on",
        ]
        data = self.get_data(start_time, end_time, metrics)
        on_periods = infer_on_periods(data, end_time=end_time)
        total_runtime_seconds = sum((end - start).total_seconds() for start, end in on_periods)
        return {
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": (end_time - start_time).total_seconds() / 3600,
            "cooling_cycles": len(on_periods),
            "runtime_hours": total_runtime_seconds / 3600,
            "runtime_ratio": (total_runtime_seconds / max((end_time - start_time).total_seconds(), 1)) * 100,
            "avg_indoor_temp": safe_mean(value for _, value in data.get("temperature", [])),
            "avg_indoor_humidity": safe_mean(value for _, value in data.get("humidity", [])),
            "avg_indoor_heat_index": safe_mean(value for _, value in data.get("heat_index_c", [])),
            "avg_outdoor_temp": safe_mean(value for _, value in data.get("outdoor_temp", [])),
            "avg_outdoor_humidity": safe_mean(value for _, value in data.get("outdoor_humidity", [])),
            "avg_outdoor_heat_index": safe_mean(value for _, value in data.get("outdoor_heat_index_c", [])),
            "avg_power_w": safe_mean(value for _, value in data.get("ac_power_w", [])),
            "max_power_w": max((value for _, value in data.get("ac_power_w", [])), default=None),
            "energy_wh_delta": self._estimate_energy_delta(data.get("ac_energy_wh", [])),
            "min_balance": min((value for _, value in data.get("balance_min", [])), default=None),
            "latest_balance": data.get("balance_min", [])[-1][1] if data.get("balance_min") else None,
            "sample_counts": {metric: len(values) for metric, values in data.items()},
        }

    @staticmethod
    def _estimate_energy_delta(samples: List[Tuple[datetime, float]]) -> Optional[float]:
        if len(samples) < 2:
            return None
        return samples[-1][1] - samples[0][1]

    def build_hourly_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: List[str],
    ) -> List[Dict[str, Any]]:
        data = self.get_data(start_time, end_time, metrics)
        buckets: Dict[datetime, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for metric, samples in data.items():
            for ts, value in samples:
                bucket = ts.replace(minute=0, second=0, microsecond=0)
                buckets[bucket][metric].append(value)

        rows: List[Dict[str, Any]] = []
        for bucket in sorted(buckets):
            row: Dict[str, Any] = {"hour": bucket}
            for metric in metrics:
                metric_values = buckets[bucket].get(metric, [])
                row[metric] = safe_mean(metric_values)
                row[f"{metric}__count"] = len(metric_values)
            rows.append(row)
        return rows

    def build_hour_of_day_profile(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: List[str],
    ) -> List[Dict[str, Any]]:
        data = self.get_data(start_time, end_time, metrics)
        buckets: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for metric, samples in data.items():
            for ts, value in samples:
                buckets[ts.hour][metric].append(value)

        rows: List[Dict[str, Any]] = []
        for hour in range(24):
            row: Dict[str, Any] = {"hour": hour}
            for metric in metrics:
                metric_values = buckets[hour].get(metric, [])
                row[metric] = safe_mean(metric_values)
                row[f"{metric}__count"] = len(metric_values)
            rows.append(row)
        return rows

    def format_hourly_summary(self, rows: List[Dict[str, Any]], hour_of_day: bool = False) -> str:
        if not rows:
            return "No hourly summary available."

        lines: List[str] = []
        for row in rows:
            prefix = (
                f"{int(row['hour']):02d}:00-{int(row['hour']):02d}:59 averaged across all matching days"
                if hour_of_day
                else (
                    f"{row['hour'].strftime('%Y-%m-%d %H:00')} to "
                    f"{(row['hour'] + timedelta(hours=1) - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')}"
                )
            )
            parts = [f"Window={prefix}", "Values are bucket averages over the full window, not a single timestamp"]
            for metric in [
                "temperature",
                "humidity",
                "heat_index_c",
                "outdoor_temp",
                "outdoor_humidity",
                "ac_power_w",
                "ac_on",
            ]:
                value = row.get(metric)
                if value is None:
                    continue
                count = row.get(f"{metric}__count")
                spec = METRIC_SPECS.get(metric, MetricSpec(metric, "", "#111827"))
                if spec.unit == "state":
                    parts.append(f"{spec.label}={value * 100:.0f}% on (samples={fmt_count(count)})")
                elif spec.unit == "%":
                    parts.append(f"{spec.label}={value:.1f}% (samples={fmt_count(count)})")
                else:
                    parts.append(f"{spec.label}={value:.1f} {spec.unit} (samples={fmt_count(count)})")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def generate_ai_prompt(
        self,
        start_time: datetime,
        end_time: datetime,
        settings: Dict[str, Any],
    ) -> str:
        analysis = self.analyze_ac_efficiency(start_time, end_time)
        summary_metrics = [
            "temperature",
            "humidity",
            "heat_index_c",
            "outdoor_temp",
            "outdoor_humidity",
            "ac_power_w",
            "ac_on",
        ]
        hourly_rows = self.build_hourly_summary(start_time, end_time, summary_metrics)
        if len(hourly_rows) <= 48:
            hourly_block = self.format_hourly_summary(hourly_rows)
            hourly_mode = (
                "Per-hour bucket summary across the selected range. "
                "Each row represents the mean over a full one-hour interval, not a single reading."
            )
        else:
            hourly_block = self.format_hourly_summary(
                self.build_hour_of_day_profile(start_time, end_time, summary_metrics),
                hour_of_day=True,
            )
            hourly_mode = (
                "Average hour-of-day profile across the selected range. "
                "Each row aggregates all samples observed in that hour slot across multiple days."
            )

        return f"""You are reviewing historical air-conditioner control data for one dorm room and must recommend better operating parameters.
You must reason like a controls engineer, not like a generic comfort advisor.

Current control settings:
- Control mode: {settings.get('control_mode', 'N/A')}
- Temperature-mode basis: {settings.get('temperature_control_basis', 'temperature')}
- Shared target metric setpoint: {settings.get('target_temp', 'N/A')} C
- Lower hysteresis threshold: {settings.get('temp_threshold_low', 'N/A')} C
- Upper hysteresis threshold: {settings.get('temp_threshold_high', 'N/A')} C
- Cooldown between state changes: {settings.get('cooldown_time', 'N/A')} seconds

Observed performance:
- Analysis window: {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}
- Total AC runtime: {fmt_value(analysis['total_runtime_hours'], ' h', 2)}
- Cooling cycles: {analysis['cooling_cycles']}
- Average cycle duration: {fmt_value(analysis['avg_cycle_duration'], ' min', 1)}
- Average indoor temperature: {fmt_value(analysis['avg_indoor_temp'], ' C', 1)}
- Average indoor humidity: {fmt_value(analysis['avg_indoor_humidity'], '%', 1)}
- Average indoor heat index: {fmt_value(analysis['avg_indoor_heat_index'], ' C', 1)}
- Average outdoor temperature: {fmt_value(analysis['avg_outdoor_temp'], ' C', 1)}
- Average outdoor humidity: {fmt_value(analysis['avg_outdoor_humidity'], '%', 1)}
- Average AC power draw: {fmt_value(analysis['avg_power_w'], ' W', 0)}

Technical interpretation rules:
- Temperature mode means the controller compares a live comfort metric against one shared setpoint plus two hysteresis offsets:
  `turn ON when metric > target + high_threshold`, `turn OFF when metric < target - low_threshold`.
- In temperature mode, the cooldown is a hard lockout between state changes. A poor cooldown can cause short-cycling even if thresholds are reasonable.
- Scheduler mode ignores direct temperature feedback during each on/off segment and instead alternates fixed ON and OFF durations.
- Scheduler mode can be superior when room thermal inertia is stable and the measured comfort metric is noisy; it can be worse when outdoor load varies rapidly.
- The selected basis changes the control signal:
  `temperature` reacts only to dry-bulb temperature,
  `heat_index` reacts to combined temperature-humidity discomfort and may justify different thresholds and cycle lengths.
- When reviewing hourly summaries below, treat every row as an averaged time bucket with sample counts. Do not interpret a row as a single instantaneous reading.

{hourly_mode}:
{hourly_block}

Goals:
1. Reduce short-cycling and unnecessary switching.
2. Keep comfort stable.
3. Improve the temperature-mode strategy if that is still the right mode.

Tasks:
1. Decide whether temperature mode or scheduler mode is more appropriate.
2. If temperature mode is best, recommend a setpoint, low threshold, high threshold, and cooldown.
3. If scheduler mode is best, recommend explicit ON and OFF durations and explain why fixed cycling is better than threshold control here.
4. Decide whether the basis should stay on temperature or switch to heat index, and explain the technical tradeoff.
5. Explain the most important hourly and operational patterns driving your recommendation, including evidence from runtime, humidity, outdoor load, and power draw.
6. Call out any indication of short-cycling, weak hysteresis, overly aggressive cooldown, or poor comfort stability.
7. Give specific numeric recommendations, not generic advice.

Answer in detailed English bullet points with explicit numeric settings and technical reasoning.
"""


class PlotExporter:
    """Render grouped plots to image files."""

    def __init__(self) -> None:
        self.fig = Figure(figsize=(32.5, 13.5), dpi=120, facecolor="#FCFCFD")

    def export_grouped_metrics(
        self,
        data: Dict[str, List[Tuple[datetime, float]]],
        title: str,
        output_path: Path,
    ) -> Optional[Path]:
        self.fig.clear()
        active_data = {metric: values for metric, values in data.items() if values}
        visible_data = {metric: values for metric, values in active_data.items() if metric not in HIDDEN_METRICS}
        plotted_metrics = {metric: values for metric, values in visible_data.items() if metric != "ac_on"}
        if not plotted_metrics:
            return None

        axes = self.fig.subplots(2, 2, sharex=False)
        flat_axes = list(axes.flatten())
        on_periods = infer_on_periods(active_data)
        gap_windows = self._build_global_gap_windows(list(plotted_metrics.values()))

        for axis, (group_title, metrics) in zip(flat_axes, PLOT_GROUPS):
            group_metrics = [metric for metric in metrics if metric in plotted_metrics]
            self._style_axis(axis)
            self._shade_on_periods(axis, on_periods)
            axis.set_title(group_title, fontsize=14, fontweight="bold", color="#1F2937", loc="left", pad=14)
            if not group_metrics:
                axis.set_visible(False)
                continue

            unit_axes: Dict[str, Any] = {}
            handles = []
            labels = []
            for metric in group_metrics:
                spec = METRIC_SPECS.get(metric, MetricSpec(metric, "", "#111827"))
                unit = spec.unit or metric
                metric_axis = unit_axes.get(unit)
                if metric_axis is None:
                    metric_axis = axis if not unit_axes else axis.twinx()
                    if metric_axis is not axis:
                        metric_axis.spines["top"].set_visible(False)
                        metric_axis.spines["right"].set_position(("outward", 54 * (len(unit_axes) - 1)))
                        metric_axis.spines["right"].set_color("#CBD5E1")
                        metric_axis.tick_params(colors="#475569", labelsize=10)
                    unit_axes[unit] = metric_axis

                times, values, bridge_segments = self._build_line_with_gap_bridges(
                    plotted_metrics[metric],
                    gap_windows=gap_windows,
                )
                line = metric_axis.plot(
                    times,
                    values,
                    label=spec.label,
                    color=spec.color,
                    linewidth=1.9,
                    alpha=0.96,
                )[0]
                for bridge_start, bridge_end, bridge_start_value, bridge_end_value in bridge_segments:
                    metric_axis.plot(
                        [bridge_start, bridge_end],
                        [bridge_start_value, bridge_end_value],
                        color="#94A3B8",
                        linewidth=1.4,
                        linestyle="--",
                        alpha=0.95,
                        zorder=line.get_zorder() - 0.1,
                    )
                handles.append(line)
                labels.append(spec.label)
                metric_axis.set_ylabel(unit, fontsize=10, color=spec.color, labelpad=10)
                metric_axis.tick_params(axis="y", colors=spec.color, labelsize=10)

            axis.legend(
                handles,
                labels,
                loc="upper left",
                bbox_to_anchor=(1.14, 1.02),
                frameon=False,
                fontsize=10,
                handlelength=2.8,
                borderaxespad=0.0,
            )
            axis.text(
                0.0,
                -0.34,
                self._build_group_footer(group_metrics, plotted_metrics),
                transform=axis.transAxes,
                fontsize=9,
                color="#475569",
                va="top",
                ha="left",
                clip_on=False,
                linespacing=1.35,
            )

        for axis in flat_axes:
            if not axis.get_visible():
                continue
            axis.set_xlabel("Time", fontsize=11, color="#334155", labelpad=12)
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
            axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
            axis.margins(x=0.02)

        self.fig.suptitle(title, fontsize=18, fontweight="bold", color="#0F172A", y=0.985)
        self.fig.subplots_adjust(left=0.045, right=0.77, top=0.915, bottom=0.02, hspace=0.7, wspace=0.42)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor=self.fig.get_facecolor())
        return output_path

    def _style_axis(self, axis: Any) -> None:
        axis.set_facecolor("#FFFFFF")
        axis.set_axisbelow(True)
        axis.grid(True, color="#E2E8F0", linewidth=0.9, alpha=0.85)
        axis.spines["left"].set_color("#CBD5E1")
        axis.spines["bottom"].set_color("#CBD5E1")
        axis.spines["right"].set_color("#CBD5E1")
        axis.spines["top"].set_color("#CBD5E1")
        for spine in axis.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(1.3)
        axis.tick_params(colors="#475569", labelsize=10)
        axis.patch.set_edgecolor("#CBD5E1")
        axis.patch.set_linewidth(1.2)

    def _shade_on_periods(self, axis: Any, on_periods: List[Tuple[datetime, datetime]]) -> None:
        for start, end in on_periods:
            axis.axvspan(start, end, color="#86EFAC", alpha=0.58, zorder=0)

    def _build_group_footer(
        self,
        group_metrics: List[str],
        plotted_metrics: Dict[str, List[Tuple[datetime, float]]],
    ) -> str:
        lines: List[str] = []
        for metric in group_metrics:
            spec = METRIC_SPECS.get(metric, MetricSpec(metric, "", "#111827"))
            values = [value for _, value in plotted_metrics[metric]]
            latest = values[-1]
            average = safe_mean(values)
            lines.append(
                f"{spec.label}: n={len(values)} | avg={fmt_value(average, f' {spec.unit}'.rstrip(), 1)}"
                f" | min={fmt_value(min(values), f' {spec.unit}'.rstrip(), 1)}"
                f" | max={fmt_value(max(values), f' {spec.unit}'.rstrip(), 1)}"
                f" | last={fmt_value(latest, f' {spec.unit}'.rstrip(), 1)}"
            )
        return "\n".join(lines)

    def _build_line_with_gap_bridges(
        self,
        samples: List[Tuple[datetime, float]],
        gap_windows: Optional[List[Tuple[datetime, datetime]]] = None,
    ) -> Tuple[List[datetime], List[float], List[Tuple[datetime, datetime, float, float]]]:
        if len(samples) < 2:
            return [ts for ts, _ in samples], [value for _, value in samples], []

        times: List[datetime] = []
        values: List[float] = []
        bridge_segments: List[Tuple[datetime, datetime, float, float]] = []
        previous_ts: Optional[datetime] = None
        previous_value: Optional[float] = None

        for ts, value in samples:
            if previous_ts is not None:
                bridging_gap = self._find_crossed_gap(previous_ts, ts, gap_windows or [])
                if bridging_gap is not None and previous_value is not None:
                    bridge_start, bridge_end = bridging_gap
                    bridge_segments.append((previous_ts, ts, previous_value, value))
                    midpoint = bridge_start + (bridge_end - bridge_start) / 2
                    times.append(midpoint)
                    values.append(math.nan)
            times.append(ts)
            values.append(value)
            previous_ts = ts
            previous_value = value

        return times, values, bridge_segments

    def _build_global_gap_windows(
        self,
        sample_groups: List[List[Tuple[datetime, float]]],
    ) -> List[Tuple[datetime, datetime]]:
        timeline = sorted({ts for samples in sample_groups for ts, _ in samples})
        if len(timeline) < 3:
            return []

        deltas = [
            (curr_ts - prev_ts).total_seconds()
            for prev_ts, curr_ts in zip(timeline, timeline[1:])
            if curr_ts > prev_ts
        ]
        if len(deltas) < 2:
            return []

        sorted_deltas = sorted(deltas)
        median_delta = sorted_deltas[len(sorted_deltas) // 2]
        gap_threshold = max(median_delta * 2.5, 60.0)
        return [
            (prev_ts, curr_ts)
            for prev_ts, curr_ts in zip(timeline, timeline[1:])
            if (curr_ts - prev_ts).total_seconds() > gap_threshold
        ]

    @staticmethod
    def _find_crossed_gap(
        start_ts: datetime,
        end_ts: datetime,
        gap_windows: List[Tuple[datetime, datetime]],
    ) -> Optional[Tuple[datetime, datetime]]:
        for gap_start, gap_end in gap_windows:
            if start_ts <= gap_start and end_ts >= gap_end:
                return gap_start, gap_end
        return None


def extract_on_periods(
    ac_on_samples: List[Tuple[datetime, float]],
    end_time: Optional[datetime] = None,
) -> List[Tuple[datetime, datetime]]:
    on_periods: List[Tuple[datetime, datetime]] = []
    last_on_time: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None
    for ts, value in ac_on_samples:
        last_timestamp = ts
        if value >= 0.5 and last_on_time is None:
            last_on_time = ts
        elif value < 0.5 and last_on_time is not None:
            on_periods.append((last_on_time, ts))
            last_on_time = None
    if last_on_time is not None:
        closing_time = end_time or last_timestamp
        if closing_time is not None:
            on_periods.append((last_on_time, closing_time))
    return on_periods


def infer_on_periods(
    data: Dict[str, List[Tuple[datetime, float]]],
    end_time: Optional[datetime] = None,
) -> List[Tuple[datetime, datetime]]:
    power_samples = data.get("ac_power_w", [])
    if power_samples:
        power_state_samples = [(ts, 1.0 if value > POWER_ON_THRESHOLD_W else 0.0) for ts, value in power_samples]
        power_periods = extract_on_periods(power_state_samples, end_time=end_time)
        if power_periods:
            balance_periods = extract_balance_drop_periods(data.get("balance_min", []))
            return merge_periods([*power_periods, *balance_periods])

    balance_periods = extract_balance_drop_periods(data.get("balance_min", []))
    if balance_periods:
        return balance_periods

    return extract_on_periods(data.get("ac_on", []), end_time=end_time)


def extract_balance_drop_periods(
    balance_samples: List[Tuple[datetime, float]],
) -> List[Tuple[datetime, datetime]]:
    if len(balance_samples) < 2:
        return []

    periods: List[Tuple[datetime, datetime]] = []
    previous_ts, previous_balance = balance_samples[0]
    for ts, balance in balance_samples[1:]:
        if balance < previous_balance:
            periods.append((previous_ts, ts))
        previous_ts, previous_balance = ts, balance
    return merge_periods(periods)


def merge_periods(
    periods: List[Tuple[datetime, datetime]],
    max_gap: timedelta = timedelta(seconds=90),
) -> List[Tuple[datetime, datetime]]:
    normalized = sorted((start, end) for start, end in periods if start < end)
    if not normalized:
        return []

    merged: List[Tuple[datetime, datetime]] = []
    current_start, current_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= current_end + max_gap:
            if end > current_end:
                current_end = end
            continue
        merged.append((current_start, current_end))
        current_start, current_end = start, end
    merged.append((current_start, current_end))
    return merged


def build_figure_path(end_time: datetime, stem: str = "ac_timeline") -> Path:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = end_time.strftime("%Y%m%d_%H%M%S")
    return FIGURE_DIR / f"{stem}_{timestamp}.png"


def parse_range_text(range_text: str, now: Optional[datetime] = None) -> Tuple[datetime, datetime, str]:
    now = now or datetime.now()
    text = range_text.strip().lower()
    if text in TIME_RANGE_PRESETS:
        return now - TIME_RANGE_PRESETS[text], now, text

    if "," in range_text:
        start_text, end_text = [part.strip() for part in range_text.split(",", 1)]
        start_time = parse_user_datetime(start_text)
        end_time = parse_user_datetime(end_text)
        if start_time >= end_time:
            raise ValueError("Start time must be earlier than end time.")
        return start_time, end_time, "custom"

    raise ValueError("Range must be a preset like 6h/3d or 'YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM'.")


def parse_user_datetime(value: str) -> datetime:
    for fmt in [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(value)


class ACAnalysisService:
    """High-level facade used by CLI and bot integrations."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.analyzer = ACDataAnalyzer(db_path)
        self.plot_exporter = PlotExporter()

    def get_available_metrics(self) -> List[str]:
        return self.analyzer.get_available_metrics()

    def analyze_ac_efficiency(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        return self.analyzer.analyze_ac_efficiency(start_time, end_time)

    def build_range_stats(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        return self.analyzer.build_range_stats(start_time, end_time)

    def generate_ai_prompt(self, start_time: datetime, end_time: datetime, settings: Dict[str, Any]) -> str:
        return self.analyzer.generate_ai_prompt(start_time, end_time, settings)

    def export_figure(
        self,
        start_time: datetime,
        end_time: datetime,
        metrics: Optional[List[str]] = None,
        output_path: Optional[Path] = None,
        title: Optional[str] = None,
        stem: str = "ac_timeline",
    ) -> Optional[Path]:
        requested_metrics = list(dict.fromkeys([*(metrics or DEFAULT_METRICS), "ac_on"]))
        log.info(
            f"[analysis] Export figure requested: metrics={requested_metrics} "
            f"range={start_time.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        data = self.analyzer.get_data(start_time, end_time, requested_metrics)
        target_path = output_path or build_figure_path(end_time, stem=stem)
        plot_title = title or f"AC Timeline  |  {start_time.strftime('%Y-%m-%d %H:%M')} -> {end_time.strftime('%Y-%m-%d %H:%M')}"
        figure_path = self.plot_exporter.export_grouped_metrics(data, plot_title, target_path)
        if figure_path is None:
            log.warning("[analysis] Figure export skipped because no plottable data was found.")
            return None
        log.info(f"[analysis] Figure exported to {figure_path}")
        return figure_path
