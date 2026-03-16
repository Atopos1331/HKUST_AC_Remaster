from __future__ import annotations

from dataclasses import dataclass, field
import shlex
from typing import Any, Callable, Iterable, Mapping, Sequence


_MISSING = object()


@dataclass(frozen=True, slots=True)
class CommandOptionSpec:
    name: str
    description: str
    value_type: type = str
    choices: tuple[str, ...] = ()
    default: Any = _MISSING
    consume_rest: bool = False

    @property
    def required(self) -> bool:
        return self.default is _MISSING


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str
    handler_name: str
    options: tuple[CommandOptionSpec, ...] = ()
    slash_names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    formatter: Callable[[Mapping[str, Any]], str] = field(default=lambda _: "", repr=False)

    def build_message(self, args: Mapping[str, Any] | None = None) -> str:
        return self.formatter(args or {})

    def build_message_from_tokens(self, tokens: Sequence[str]) -> str:
        args: dict[str, Any] = {}
        remaining = list(tokens)
        for index, option in enumerate(self.options):
            if remaining:
                if option.consume_rest or index == len(self.options) - 1 and option.consume_rest:
                    args[option.name] = " ".join(remaining).strip()
                    remaining.clear()
                else:
                    args[option.name] = remaining.pop(0)
            elif option.default is not _MISSING:
                args[option.name] = option.default
        return self.build_message(args)

    def to_discord_spec(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.options:
            payload["options"] = {option.name: option.description for option in self.options}
        return payload


def _default_formatter(command_name: str) -> Callable[[Mapping[str, Any]], str]:
    return lambda _: f"/{command_name}"


def _format_with_single_arg(command_name: str, option_name: str) -> Callable[[Mapping[str, Any]], str]:
    def formatter(args: Mapping[str, Any]) -> str:
        value = args.get(option_name)
        return f"/{command_name} {value}".strip() if value not in (None, "") else f"/{command_name}"

    return formatter


def _format_with_two_args(command_name: str, first_option: str, second_option: str) -> Callable[[Mapping[str, Any]], str]:
    def formatter(args: Mapping[str, Any]) -> str:
        parts = [f"/{command_name}"]
        first = args.get(first_option)
        second = args.get(second_option)
        if first not in (None, ""):
            parts.append(str(first))
        if second not in (None, ""):
            parts.append(str(second))
        return " ".join(parts)

    return formatter


def _format_lock_command(args: Mapping[str, Any]) -> str:
    parts = ["/lock"]
    state = args.get("state")
    duration = args.get("duration")
    if state not in (None, ""):
        parts.append(str(state))
    if duration not in (None, ""):
        parts.append(str(duration))
    return " ".join(parts)


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="state",
        description="Show current controller status",
        handler_name="_handle_state_command",
        slash_names=("state",),
        formatter=_default_formatter("state"),
    ),
    CommandSpec(
        name="settemp",
        description="Set target temperature",
        handler_name="_handle_settemp_command",
        options=(CommandOptionSpec("temperature", "Target temperature, 16-35", float),),
        slash_names=("settemp",),
        formatter=_format_with_single_arg("settemp", "temperature"),
    ),
    CommandSpec(
        name="setbasis",
        description="Set temperature basis",
        handler_name="_handle_setbasis_command",
        options=(
            CommandOptionSpec(
                "basis",
                "temperature or heatindex",
                str,
                choices=("temperature", "heatindex"),
            ),
        ),
        slash_names=("setbasis",),
        formatter=_format_with_single_arg("setbasis", "basis"),
    ),
    CommandSpec(
        name="settime",
        description="Set scheduler on-off durations",
        handler_name="_handle_settime_command",
        options=(
            CommandOptionSpec("on_seconds", "On duration in seconds", int),
            CommandOptionSpec("off_seconds", "Off duration in seconds", int),
        ),
        slash_names=("settime",),
        formatter=_format_with_two_args("settime", "on_seconds", "off_seconds"),
    ),
    CommandSpec(
        name="setmode",
        description="Switch control mode",
        handler_name="_handle_setmode_command",
        options=(
            CommandOptionSpec(
                "mode",
                "temperature or scheduler",
                str,
                choices=("temperature", "scheduler"),
            ),
        ),
        slash_names=("setmode",),
        formatter=_format_with_single_arg("setmode", "mode"),
    ),
    CommandSpec(
        name="timer",
        description="Show device off-timer",
        handler_name="_handle_timer_command",
        slash_names=("timer",),
        formatter=_default_formatter("timer"),
    ),
    CommandSpec(
        name="scheduler",
        description="Show scheduler status",
        handler_name="_handle_scheduler_command",
        slash_names=("scheduler",),
        formatter=_default_formatter("scheduler"),
    ),
    CommandSpec(
        name="lock",
        description="Show temporary lock status",
        handler_name="_handle_lock_command",
        slash_names=("lock",),
        formatter=_default_formatter("lock"),
    ),
    CommandSpec(
        name="setlock",
        description="Configure temporary lock",
        handler_name="_handle_lock_command",
        options=(
            CommandOptionSpec("state", "ON or OFF", str, choices=("ON", "OFF")),
            CommandOptionSpec("duration", "Lock duration in seconds", int),
        ),
        slash_names=("setlock",),
        formatter=_format_lock_command,
    ),
    CommandSpec(
        name="clearlock",
        description="Clear temporary lock",
        handler_name="_handle_lock_command",
        slash_names=("clearlock",),
        formatter=lambda _: "/lock clear",
    ),
    CommandSpec(
        name="log",
        description="Show recent logs",
        handler_name="_handle_log_command",
        slash_names=("log",),
        formatter=_default_formatter("log"),
    ),
    CommandSpec(
        name="switchon",
        description="Turn master switch on",
        handler_name="_handle_switch_command",
        slash_names=("switchon", "switchOn"),
        formatter=lambda _: "/switchOn",
    ),
    CommandSpec(
        name="switchoff",
        description="Turn master switch off",
        handler_name="_handle_switch_command",
        slash_names=("switchoff", "switchOff"),
        formatter=lambda _: "/switchOff",
    ),
    CommandSpec(
        name="stats",
        description="Show data statistics",
        handler_name="_handle_stats_command",
        options=(
            CommandOptionSpec(
                "range_text",
                "1h/2h/6h/12h/24h/3d/7d/30d or start,end",
                str,
                default="24h",
                consume_rest=True,
            ),
        ),
        slash_names=("stats",),
        formatter=_format_with_single_arg("stats", "range_text"),
    ),
    CommandSpec(
        name="plot",
        description="Generate an analysis figure",
        handler_name="_handle_plot_command",
        options=(
            CommandOptionSpec(
                "range_text",
                "1h/2h/6h/12h/24h/3d/7d/30d or start,end",
                str,
                consume_rest=True,
            ),
        ),
        slash_names=("plot",),
        formatter=_format_with_single_arg("plot", "range_text"),
    ),
    CommandSpec(
        name="help",
        description="Show help menu",
        handler_name="_handle_help_command",
        slash_names=("help",),
        formatter=_default_formatter("help"),
    ),
)


COMMANDS_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}
SLASH_COMMAND_LOOKUP = {
    alias.lower(): spec
    for spec in COMMAND_SPECS
    for alias in (spec.slash_names or (spec.name,))
}


def get_discord_command_specs() -> list[dict[str, Any]]:
    return [spec.to_discord_spec() for spec in COMMAND_SPECS]


def iter_command_specs() -> Iterable[CommandSpec]:
    return COMMAND_SPECS


def parse_command_spec(content: str) -> CommandSpec | None:
    text = content.strip()
    if not text.startswith("/"):
        return None
    head = text[1:].split(maxsplit=1)[0].lower()
    return SLASH_COMMAND_LOOKUP.get(head)


def normalize_user_command(raw: str) -> str:
    text = raw.strip()
    if not text or text.startswith("/"):
        return text

    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    if not tokens:
        return text

    spec = COMMANDS_BY_NAME.get(tokens[0].lower())
    if spec is None:
        return text
    return spec.build_message_from_tokens(tokens[1:])
