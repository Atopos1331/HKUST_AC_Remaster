from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from powers.auth.ac_api import get_ac_api
from powers.data.analysis import ACAnalysisService, fmt_value, parse_range_text
from powers.data.global_state import (
    read_ac_is_on,
    read_indoor_climate,
    read_last_switch,
    read_recent_applied,
    read_recent_decisions,
)
from powers.data.settings import get_settings_manager
from powers.utils.config import Config
from powers.utils.logger import log


@dataclass(frozen=True)
class BotResponse:
    text: str
    image_path: Optional[Path] = None


def _get_api():
    return get_ac_api()


def _datetime_from_iso(iso_string: str, default: datetime = datetime(1970, 1, 1)) -> datetime:
    try:
        return datetime.fromisoformat(iso_string)
    except Exception:
        return default


class BotMessageHandler:
    """Shared command handler used by QQ, Discord, and CLI."""

    DISCORD_COMMAND_SPECS = [
        {"name": "state", "description": "Show current controller status"},
        {"name": "settemp", "description": "Set target temperature", "options": {"temperature": "Target temperature, 16-35"}},
        {"name": "setbasis", "description": "Set temperature basis", "options": {"basis": "temperature or heatindex"}},
        {
            "name": "settime",
            "description": "Set scheduler on-off durations",
            "options": {"on_seconds": "On duration in seconds", "off_seconds": "Off duration in seconds"},
        },
        {"name": "setmode", "description": "Switch control mode", "options": {"mode": "temperature or scheduler"}},
        {"name": "timer", "description": "Show device off-timer"},
        {"name": "scheduler", "description": "Show scheduler status"},
        {"name": "lock", "description": "Show temporary lock status"},
        {"name": "setlock", "description": "Configure temporary lock", "options": {"state": "ON or OFF", "duration": "Lock duration in seconds"}},
        {"name": "clearlock", "description": "Clear temporary lock"},
        {"name": "log", "description": "Show recent logs"},
        {"name": "switchon", "description": "Turn master switch on"},
        {"name": "switchoff", "description": "Turn master switch off"},
        {"name": "stats", "description": "Show data statistics", "options": {"range_text": "1h/2h/6h/12h/24h/3d/7d/30d or start,end"}},
        {"name": "plot", "description": "Generate an analysis figure", "options": {"range_text": "1h/2h/6h/12h/24h/3d/7d/30d or start,end"}},
        {"name": "help", "description": "Show help menu"},
    ]

    def __init__(self) -> None:
        self.settings_manager = get_settings_manager()
        self.analysis_service = ACAnalysisService()
        self.language = str(Config.BOT_LANGUAGE).lower()

    def get_discord_command_specs(self) -> list[dict]:
        return self.DISCORD_COMMAND_SPECS

    def deal_message(self, content: str, source: str = "unknown") -> BotResponse:
        content = content.strip()
        preview = content if len(content) <= 160 else f"{content[:157]}..."
        lowered = content.lower()

        commands = [
            ("/state", self._handle_state_command),
            ("/setbasis", lambda: self._handle_setbasis_command(content)),
            ("/settime", lambda: self._handle_settime_command(content)),
            ("/settemp", lambda: self._handle_settemp_command(content)),
            ("/setmode", lambda: self._handle_setmode_command(content)),
            ("/timer", self._handle_timer_command),
            ("/scheduler", self._handle_scheduler_command),
            ("/lock", lambda: self._handle_lock_command(content)),
            ("/log", self._handle_log_command),
            ("/switchon", lambda: self._handle_switch_command(True)),
            ("/switchoff", lambda: self._handle_switch_command(False)),
            ("/stats", lambda: self._handle_stats_command(content)),
            ("/plot", lambda: self._handle_plot_command(content)),
            ("/help", self._handle_help_command),
        ]
        for prefix, handler in commands:
            if lowered.startswith(prefix):
                response = handler()
                log.info(f"[command] source={source} handled={preview}")
                return response

        log.warning(f"[command] source={source} unknown command: {preview}")
        return BotResponse(self._msg("❌ 未知指令。使用 /help 查看可用命令。", "❌ Unknown command. Use /help to see the available commands."))

    def _msg(self, zh: str, en: str) -> str:
        if self.language == "zh":
            return zh
        if self.language == "bilingual":
            return f"{zh}\n{en}"
        return en

    def _na(self) -> str:
        return self._msg("暂无", "N/A")

    def _state_text(self, is_on: bool) -> str:
        return self._msg("开启", "ON") if is_on else self._msg("关闭", "OFF")

    def _basis_text(self, basis: str) -> str:
        return {
            "temperature": self._msg("温度", "temperature"),
            "heat_index": self._msg("体感温度", "heat index"),
        }.get(basis, basis)

    def _mode_text(self, mode: str) -> str:
        return {
            "temperature": self._msg("温控", "temperature"),
            "scheduler": self._msg("定时", "scheduler"),
        }.get(mode, mode)

    def _fmt_optional(self, value: Optional[float], unit: str, precision: int = 2) -> str:
        if value is None:
            return self._na()
        return f"{value:.{precision}f} {unit}"

    def _syntax_line(self, syntax: str, example: Optional[str] = None) -> str:
        zh = f"📌 语法: {syntax}"
        en = f"📌 Syntax: {syntax}"
        if example:
            zh = f"{zh} | eg: {example}"
            en = f"{en} | eg: {example}"
        return self._msg(zh, en)

    @staticmethod
    def _fmt_duration(seconds: int) -> str:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        parts: list[str] = []
        if h:
            parts.append(f"{h}h")
        if m:
            parts.append(f"{m}m")
        if s or not parts:
            parts.append(f"{s}s")
        return " ".join(parts)

    def _handle_state_command(self) -> BotResponse:
        try:
            settings = self.settings_manager.load_settings()
            control_mode = settings.get("control_mode", "temperature")
            control_basis = settings.get("temperature_control_basis", "temperature")
            switch = settings.get("switch", 1)
            target_temp = settings.get("target_temp", 29.5)
            climate = read_indoor_climate()
            ac_on = read_ac_is_on()
            balance = _get_api().get_balance()[0]

            lines = [
                self._msg("📋 系统状态", "📋 System Status"),
                self._msg(f"🎛️ 总开关: {self._state_text(switch == 1)}", f"🎛️ Master switch: {self._state_text(switch == 1)}"),
                self._msg(f"💰 余额: {balance} 分钟", f"💰 Balance: {balance} min"),
                self._msg(f"🌡️ 当前温度: {self._fmt_optional(climate.temperature, 'C')}", f"🌡️ Current temperature: {self._fmt_optional(climate.temperature, 'C')}"),
                self._msg(f"💧 当前湿度: {self._fmt_optional(climate.humidity, '%')}", f"💧 Current humidity: {self._fmt_optional(climate.humidity, '%')}"),
                self._msg(f"🥵 当前体感温度: {self._fmt_optional(climate.heat_index, 'C')}", f"🥵 Current heat index: {self._fmt_optional(climate.heat_index, 'C')}"),
                self._msg(f"🎯 目标指标: {target_temp:.1f} C", f"🎯 Target metric: {target_temp:.1f} C"),
                self._msg(f"❄️ 空调状态: {self._state_text(ac_on)}", f"❄️ AC state: {self._state_text(ac_on)}"),
                self._msg(f"🧭 控制模式: {self._mode_text(control_mode)}", f"🧭 Control mode: {self._mode_text(control_mode)}"),
                self._msg(f"📏 温控依据: {self._basis_text(control_basis)}", f"📏 Temperature basis: {self._basis_text(control_basis)}"),
            ]
            return BotResponse("\n".join(lines))
        except Exception as exc:
            log.error(f"State command failed: {exc}")
            return BotResponse(self._msg(f"❌ 获取状态失败：{exc}", f"❌ Failed to retrieve status: {exc}"))

    def _handle_settime_command(self, content: str) -> BotResponse:
        try:
            parts = content.split()
            if len(parts) != 3:
                return BotResponse(self._syntax_line("/settime <on_seconds> <off_seconds>", "/settime 300 1200"))
            ontime, offtime = int(parts[1]), int(parts[2])
            if ontime <= 0 or offtime <= 0:
                return BotResponse(self._msg("❌ 两个时长都必须大于 0。", "❌ Both durations must be greater than 0."))
            if ontime > 3600 or offtime > 7200:
                return BotResponse(
                    self._msg(
                        "❌ 超出允许范围：on_seconds 必须 <= 3600，off_seconds 必须 <= 7200。",
                        "❌ Value out of range: on_seconds must be <= 3600 and off_seconds must be <= 7200.",
                    )
                )
            self.settings_manager.update_multiple_settings({"ontime": ontime, "offtime": offtime})
            return BotResponse(
                self._msg(
                    f"✅ 定时模式已更新：开启 {ontime}s，关闭 {offtime}s。",
                    f"✅ Scheduler updated: on for {ontime}s, off for {offtime}s.",
                )
            )
        except Exception as exc:
            log.error(f"settime command failed: {exc}")
            return BotResponse(self._msg(f"❌ 设置定时周期失败：{exc}", f"❌ Failed to set scheduler durations: {exc}"))

    def _handle_settemp_command(self, content: str) -> BotResponse:
        try:
            parts = content.split()
            if len(parts) != 2:
                return BotResponse(self._syntax_line("/settemp <temperature>", "/settemp 28.5"))
            temp = float(parts[1])
            if not (16.0 <= temp <= 35.0):
                return BotResponse(self._msg("❌ 温度必须在 16 到 35 C 之间。", "❌ Temperature must be between 16 and 35 C."))
            self.settings_manager.set_setting("target_temp", temp)
            return BotResponse(self._msg(f"✅ 目标温度已设为 {temp:.1f} C。", f"✅ Target temperature set to {temp:.1f} C."))
        except Exception as exc:
            log.error(f"settemp command failed: {exc}")
            return BotResponse(self._msg(f"❌ 设置温度失败：{exc}", f"❌ Failed to set temperature: {exc}"))

    def _handle_setbasis_command(self, content: str) -> BotResponse:
        try:
            parts = content.split()
            if len(parts) != 2:
                return BotResponse(self._syntax_line("/setbasis <temperature|heatindex>", "/setbasis temperature"))
            basis = parts[1].lower()
            basis_map = {
                "t": "temperature",
                "temp": "temperature",
                "temperature": "temperature",
                "hi": "heat_index",
                "heatindex": "heat_index",
                "heat_index": "heat_index",
            }
            resolved = basis_map.get(basis)
            if resolved is None:
                return BotResponse(self._msg("❌ 无效依据，可选 temperature 或 heatindex。", "❌ Invalid basis. Choose either temperature or heatindex."))
            self.settings_manager.set_setting("temperature_control_basis", resolved)
            return BotResponse(
                self._msg(
                    f"✅ 温控依据已切换为：{self._basis_text(resolved)}。",
                    f"✅ Temperature control basis switched to: {self._basis_text(resolved)}.",
                )
            )
        except Exception as exc:
            log.error(f"setbasis command failed: {exc}")
            return BotResponse(self._msg(f"❌ 设置依据失败：{exc}", f"❌ Failed to set basis: {exc}"))

    def _handle_setmode_command(self, content: str) -> BotResponse:
        try:
            parts = content.split()
            if len(parts) != 2:
                return BotResponse(self._syntax_line("/setmode <temperature|scheduler>", "/setmode scheduler"))
            mode = parts[1].lower()
            if mode not in ("temperature", "t", "scheduler", "s"):
                return BotResponse(self._msg("❌ 模式无效，可选 temperature (t) 或 scheduler (s)。", "❌ Invalid mode. Choose temperature (t) or scheduler (s)."))
            mode = {"t": "temperature", "s": "scheduler"}.get(mode, mode)
            self.settings_manager.set_setting("control_mode", mode)
            return BotResponse(
                self._msg(
                    f"✅ 控制模式已切换为：{self._mode_text(mode)}。",
                    f"✅ Control mode switched to: {self._mode_text(mode)}.",
                )
            )
        except Exception as exc:
            log.error(f"setmode command failed: {exc}")
            return BotResponse(self._msg(f"❌ 设置模式失败：{exc}", f"❌ Failed to set mode: {exc}"))

    def _handle_timer_command(self) -> BotResponse:
        try:
            timer = _get_api().get_timer()
            if timer:
                return BotResponse(self._msg(f"⏲️ 设备关机定时：{timer:%Y-%m-%d %H:%M:%S}", f"⏲️ Device off-timer: {timer:%Y-%m-%d %H:%M:%S}"))
            return BotResponse(self._msg("⏲️ 设备关机定时：未设置", "⏲️ Device off-timer: not set"))
        except Exception as exc:
            log.error(f"timer command failed: {exc}")
            return BotResponse(self._msg(f"❌ 获取定时失败：{exc}", f"❌ Failed to get timer: {exc}"))

    def _handle_scheduler_command(self) -> BotResponse:
        try:
            settings = self.settings_manager.load_settings()
            if settings.get("control_mode", "temperature") != "scheduler":
                return BotResponse(self._msg("ℹ️ 当前不是定时模式，请先使用 /setmode scheduler。", "ℹ️ Scheduler mode is not active. Use /setmode scheduler first."))

            ontime = settings.get("ontime", Config.DEFAULT_ONTIME)
            offtime = settings.get("offtime", Config.DEFAULT_OFFTIME)
            ac_on = read_ac_is_on()
            last_switch = read_last_switch()
            now = datetime.now()
            end = last_switch + timedelta(seconds=ontime if ac_on else offtime)
            remaining = max(0, int((end - now).total_seconds()))
            lines = [
                self._msg("🕒 定时模式状态", "🕒 Scheduler Status"),
                self._msg(f"🔌 当前状态: {self._state_text(ac_on)}", f"🔌 Current state: {self._state_text(ac_on)}"),
                self._msg(f"▶️ 开启时长: {self._fmt_duration(ontime)} ({ontime}s)", f"▶️ On duration: {self._fmt_duration(ontime)} ({ontime}s)"),
                self._msg(f"⏸️ 关闭时长: {self._fmt_duration(offtime)} ({offtime}s)", f"⏸️ Off duration: {self._fmt_duration(offtime)} ({offtime}s)"),
                self._msg(f"🕘 上次切换: {last_switch:%Y-%m-%d %H:%M:%S}", f"🕘 Last switch: {last_switch:%Y-%m-%d %H:%M:%S}"),
                self._msg(f"⏲️ 预计下次切换: {end:%Y-%m-%d %H:%M:%S}", f"⏲️ Expected next switch: {end:%Y-%m-%d %H:%M:%S}"),
                self._msg(f"⌛ 剩余时间: {self._fmt_duration(remaining)}", f"⌛ Remaining: {self._fmt_duration(remaining)}"),
            ]
            return BotResponse("\n".join(lines))
        except Exception as exc:
            log.error(f"scheduler command failed: {exc}")
            return BotResponse(self._msg(f"❌ 获取定时状态失败：{exc}", f"❌ Failed to get scheduler info: {exc}"))

    def _handle_lock_command(self, content: str) -> BotResponse:
        try:
            parts = content.split()
            if len(parts) == 1:
                settings = self.settings_manager.load_settings()
                end = _datetime_from_iso(settings.get("lock_end_time", datetime(1970, 1, 1).isoformat()))
                if datetime.now() >= end:
                    return BotResponse(self._msg("🔓 当前没有临时锁定。", "🔓 There is no active temporary lock."))
                lock = settings.get("lock_status", False)
                remaining = int((end - datetime.now()).total_seconds())
                return BotResponse(
                    "\n".join(
                        [
                            self._msg("🔒 临时锁定状态", "🔒 Temporary Lock Status"),
                            self._msg(f"🎯 目标状态: {self._state_text(lock)}", f"🎯 Target state: {self._state_text(lock)}"),
                            self._msg(f"⌛ 剩余时间: {self._fmt_duration(remaining)}", f"⌛ Remaining: {self._fmt_duration(remaining)}"),
                            self._msg(f"⏲️ 结束时间: {end:%Y-%m-%d %H:%M:%S}", f"⏲️ Until: {end:%Y-%m-%d %H:%M:%S}"),
                        ]
                    )
                )
            if len(parts) == 2 and parts[1].lower() == "clear":
                settings = self.settings_manager.load_settings()
                settings["lock_status"] = False
                settings["lock_end_time"] = datetime(1970, 1, 1).isoformat()
                self.settings_manager.save_settings(settings)
                return BotResponse(self._msg("✅ 临时锁定已清除。", "✅ Temporary lock cleared."))
            if len(parts) == 3:
                state = parts[1].upper()
                duration = int(parts[2])
                if state not in ("ON", "OFF"):
                    return BotResponse(self._msg("❌ 锁定状态只能是 ON 或 OFF。", "❌ Lock state must be either ON or OFF."))
                end_time = datetime.now() + timedelta(seconds=duration)
                self.settings_manager.update_multiple_settings({"lock_status": state == "ON", "lock_end_time": end_time.isoformat()})
                return BotResponse(
                    self._msg(
                        f"✅ 临时锁定已配置\n🎯 目标状态: {state}\n⌛ 时长: {self._fmt_duration(duration)}\n⏲️ 结束时间: {end_time:%Y-%m-%d %H:%M:%S}",
                        f"✅ Temporary lock configured\n🎯 Target state: {state}\n⌛ Duration: {self._fmt_duration(duration)}\n⏲️ Until: {end_time:%Y-%m-%d %H:%M:%S}",
                    )
                )
            return BotResponse(
                "\n".join(
                    [
                        self._syntax_line("/lock"),
                        self._syntax_line("/lock <ON|OFF> <seconds>", "/lock ON 1800"),
                        self._syntax_line("/lock clear"),
                    ]
                )
            )
        except Exception as exc:
            log.error(f"lock command failed: {exc}")
            return BotResponse(self._msg(f"❌ 处理锁定指令失败：{exc}", f"❌ Failed to process lock command: {exc}"))

    def _handle_switch_command(self, switch_on: bool) -> BotResponse:
        try:
            self.settings_manager.set_setting("switch", 1 if switch_on else 0)
            return BotResponse(self._msg(f"✅ 总开关已设为 {self._state_text(switch_on)}。", f"✅ Master switch turned {self._state_text(switch_on)}."))
        except Exception as exc:
            log.error(f"switch command failed: {exc}")
            return BotResponse(self._msg(f"❌ 切换总开关失败：{exc}", f"❌ Failed to change master switch: {exc}"))

    def _handle_log_command(self) -> BotResponse:
        try:
            lines: list[str] = []
            applied = read_recent_applied()
            if applied:
                lines.append(self._msg("🛠️ 最近执行动作", "🛠️ Recent Applied Actions"))
                for entry in reversed(applied):
                    entry_time = entry["time"].strftime("%Y-%m-%d %H:%M:%S")
                    action = entry["action"]
                    next_time = entry["next_time"].strftime("%H:%M:%S") if entry["next_time"] else self._na()
                    reason = entry["info"].get("reason", self._na())
                    lines.append(f"{entry_time} | action: {action} | next: {next_time} | reason: {reason}")

            decisions = read_recent_decisions()
            if decisions:
                if lines:
                    lines.append("")
                lines.append(self._msg("🧭 最近决策", "🧭 Recent Decisions"))
                for entry in reversed(decisions):
                    entry_time = entry["time"].strftime("%Y-%m-%d %H:%M:%S")
                    action = entry["action"]
                    next_time = entry["next_time"].strftime("%H:%M:%S") if entry["next_time"] else self._na()
                    reason = entry["info"].get("reason", self._na())
                    lines.append(f"{entry_time} | action: {action} | next: {next_time} | reason: {reason}")

            if not lines:
                return BotResponse(self._msg("📑 还没有日志记录。", "📑 No log entries are available yet."))
            return BotResponse("\n".join(lines))
        except Exception as exc:
            log.error(f"log command failed: {exc}")
            return BotResponse(self._msg(f"❌ 获取日志失败：{exc}", f"❌ Failed to retrieve log: {exc}"))

    def _handle_stats_command(self, content: str = "/stats") -> BotResponse:
        parts = content.split(maxsplit=1)
        range_text = parts[1] if len(parts) == 2 else "24h"
        try:
            start_time, end_time, _ = parse_range_text(range_text)
            stats = self.analysis_service.build_range_stats(start_time, end_time)
            sample_counts = ", ".join(f"{metric}={count}" for metric, count in sorted(stats["sample_counts"].items()))
            lines = [
                self._msg("📊 数据统计", "📊 Data Statistics"),
                self._msg(f"⏱️ 时间范围: {start_time:%Y-%m-%d %H:%M} -> {end_time:%Y-%m-%d %H:%M}", f"⏱️ Range: {start_time:%Y-%m-%d %H:%M} -> {end_time:%Y-%m-%d %H:%M}"),
                self._msg(f"🕰️ 区间时长: {stats['duration_hours']:.2f} 小时", f"🕰️ Duration: {stats['duration_hours']:.2f} h"),
                self._msg(f"❄️ 空调累计运行: {stats['runtime_hours']:.2f} 小时 ({stats['runtime_ratio']:.1f}%)", f"❄️ AC runtime: {stats['runtime_hours']:.2f} h ({stats['runtime_ratio']:.1f}%)"),
                self._msg(f"🔁 制冷周期数: {stats['cooling_cycles']}", f"🔁 Cooling cycles: {stats['cooling_cycles']}"),
                self._msg(
                    f"🌡️ 室内均温: {fmt_value(stats['avg_indoor_temp'], ' C', 1)} | 💧 室内均湿: {fmt_value(stats['avg_indoor_humidity'], '%', 1)}",
                    f"🌡️ Avg indoor temperature: {fmt_value(stats['avg_indoor_temp'], ' C', 1)} | 💧 Avg indoor humidity: {fmt_value(stats['avg_indoor_humidity'], '%', 1)}",
                ),
                self._msg(f"🥵 室内平均体感: {fmt_value(stats['avg_indoor_heat_index'], ' C', 1)}", f"🥵 Avg indoor heat index: {fmt_value(stats['avg_indoor_heat_index'], ' C', 1)}"),
                self._msg(
                    f"🌤️ 室外均温: {fmt_value(stats['avg_outdoor_temp'], ' C', 1)} | 💦 室外均湿: {fmt_value(stats['avg_outdoor_humidity'], '%', 1)}",
                    f"🌤️ Avg outdoor temperature: {fmt_value(stats['avg_outdoor_temp'], ' C', 1)} | 💦 Avg outdoor humidity: {fmt_value(stats['avg_outdoor_humidity'], '%', 1)}",
                ),
                self._msg(f"🥵 室外平均体感: {fmt_value(stats['avg_outdoor_heat_index'], ' C', 1)}", f"🥵 Avg outdoor heat index: {fmt_value(stats['avg_outdoor_heat_index'], ' C', 1)}"),
                self._msg(
                    f"⚡ 平均功率: {fmt_value(stats['avg_power_w'], ' W', 0)} | 峰值功率: {fmt_value(stats['max_power_w'], ' W', 0)}",
                    f"⚡ Avg power: {fmt_value(stats['avg_power_w'], ' W', 0)} | Peak power: {fmt_value(stats['max_power_w'], ' W', 0)}",
                ),
                self._msg(f"🔋 区间电量增量: {fmt_value(stats['energy_wh_delta'], ' Wh', 1)}", f"🔋 Energy delta over range: {fmt_value(stats['energy_wh_delta'], ' Wh', 1)}"),
                self._msg(
                    f"💰 最低余额: {fmt_value(stats['min_balance'], ' min', 1)} | 最新余额: {fmt_value(stats['latest_balance'], ' min', 1)}",
                    f"💰 Min balance: {fmt_value(stats['min_balance'], ' min', 1)} | Latest balance: {fmt_value(stats['latest_balance'], ' min', 1)}",
                ),
                self._msg(f"🧪 样本数: {sample_counts}", f"🧪 Sample counts: {sample_counts}"),
            ]
            return BotResponse("\n".join(lines))
        except Exception as exc:
            log.error(f"stats command failed: {exc}")
            return BotResponse(
                f"{self._msg(f'❌ 获取统计失败：{exc}', f'❌ Failed to build stats: {exc}')}\n"
                f"{self._syntax_line('/stats <range>', '/stats 24h')}"
            )

    def _handle_plot_command(self, content: str) -> BotResponse:
        parts = content.split(maxsplit=1)
        if len(parts) != 2:
            return BotResponse(
                "\n".join(
                    [
                        self._syntax_line("/plot <range>", "/plot 6h"),
                        self._syntax_line(
                            "/plot <YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM>",
                            "/plot 2026-03-16 00:00, 2026-03-16 12:00",
                        ),
                    ]
                )
            )
        try:
            start_time, end_time, range_label = parse_range_text(parts[1])
            figure_path = self.analysis_service.export_figure(start_time, end_time, stem=f"bot_{range_label}")
            if figure_path is None:
                return BotResponse(self._msg("📈 所选时间范围内没有可绘制的数据。", "📈 No plottable data was found in the requested range."))
            return BotResponse(
                self._msg(
                    f"🖼️ 图像已生成\n{start_time:%Y-%m-%d %H:%M} -> {end_time:%Y-%m-%d %H:%M}",
                    f"🖼️ Figure generated\n{start_time:%Y-%m-%d %H:%M} -> {end_time:%Y-%m-%d %H:%M}",
                ),
                image_path=figure_path,
            )
        except Exception as exc:
            log.error(f"plot command failed: {exc}")
            return BotResponse(self._msg(f"❌ 生成图像失败：{exc}", f"❌ Failed to generate figure: {exc}"))

    def _handle_help_command(self) -> BotResponse:
        return BotResponse(
            "\n".join(
                [
                    self._msg("🤖 空调控制机器人", "🤖 AC Controller Bot"),
                    self._msg("📎 信息类指令", "📎 Information Commands"),
                    self._msg("/state  查看当前系统状态", "/state  Show current system status"),
                    self._msg("/scheduler  查看定时模式详情", "/scheduler  Show scheduler details"),
                    self._msg("/timer  查看设备关机定时", "/timer  Show the device off-timer"),
                    self._msg("/lock  查看临时锁定状态", "/lock  Show temporary lock status"),
                    self._msg("/log  查看最近日志", "/log  Show recent logs"),
                    self._msg("/stats <range>  查看某段时间统计 | eg: /stats 24h", "/stats <range>  Show statistical summary for a range | eg: /stats 24h"),
                    self._msg("/plot <range>  生成数据图像 | eg: /plot 6h", "/plot <range>  Generate a data figure | eg: /plot 6h"),
                    self._msg(
                        "/plot <YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM>  按绝对时间范围生成图像 | eg: /plot 2026-03-16 00:00, 2026-03-16 12:00",
                        "/plot <YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM>  Generate a figure for an absolute time range | eg: /plot 2026-03-16 00:00, 2026-03-16 12:00",
                    ),
                    "",
                    self._msg("🛠️ 控制类指令", "🛠️ Control Commands"),
                    self._msg("/settemp <temperature>  设置目标温度 | eg: /settemp 28.5", "/settemp <temperature>  Set the target temperature | eg: /settemp 28.5"),
                    self._msg("/setbasis <temperature|heatindex>  设置温控依据 | eg: /setbasis temperature", "/setbasis <temperature|heatindex>  Set the control basis | eg: /setbasis temperature"),
                    self._msg("/settime <on_seconds> <off_seconds>  设置定时周期 | eg: /settime 300 1200", "/settime <on_seconds> <off_seconds>  Configure the scheduler cycle | eg: /settime 300 1200"),
                    self._msg("/setmode <temperature|scheduler>  切换控制模式 | eg: /setmode scheduler", "/setmode <temperature|scheduler>  Switch control mode | eg: /setmode scheduler"),
                    self._msg("/lock <ON|OFF> <seconds>  设置临时锁定 | eg: /lock ON 1800", "/lock <ON|OFF> <seconds>  Set a temporary lock | eg: /lock ON 1800"),
                    self._msg("/lock clear  清除临时锁定", "/lock clear  Clear the temporary lock"),
                    self._msg("/switchOn / /switchOff  打开或关闭总开关", "/switchOn / /switchOff  Turn master switch on or off"),
                ]
            )
        )
