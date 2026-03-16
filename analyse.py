import argparse
import cmd
import shlex
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from powers.data.analysis import (
    DEFAULT_METRICS,
    HIDDEN_METRICS,
    METRIC_SPECS,
    ACAnalysisService,
    fmt_value,
    parse_range_text,
)
from powers.data.settings import get_settings_manager
from powers.utils.logger import log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AC analysis CLI")
    subparsers = parser.add_subparsers(dest="command")

    metrics_parser = subparsers.add_parser("metrics", help="List available metrics")
    metrics_parser.set_defaults(func=run_metrics)

    summary_parser = subparsers.add_parser("summary", help="Print analysis summary")
    add_range_argument(summary_parser)
    summary_parser.set_defaults(func=run_summary)

    prompt_parser = subparsers.add_parser("prompt", help="Generate AI prompt")
    add_range_argument(prompt_parser)
    prompt_parser.set_defaults(func=run_prompt)

    plot_parser = subparsers.add_parser("plot", help="Export analysis figure")
    add_range_argument(plot_parser)
    plot_parser.add_argument("--metrics", nargs="*", help="Metrics to plot")
    plot_parser.add_argument("--output", type=Path, help="Output file path")
    plot_parser.add_argument("--stem", default="cli", help="Figure stem when output is not provided")
    plot_parser.set_defaults(func=run_plot)

    shell_parser = subparsers.add_parser("shell", help="Start interactive CLI shell")
    shell_parser.set_defaults(func=run_shell)

    return parser


def add_range_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--range",
        dest="range_text",
        default="6h",
        help="Preset like 6h/24h/3d or 'YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM'",
    )


def resolve_metrics(service: ACAnalysisService, requested: Optional[Iterable[str]]) -> list[str]:
    available = set(service.get_available_metrics())
    metrics = list(requested or DEFAULT_METRICS)
    filtered = [metric for metric in metrics if metric in available and metric not in HIDDEN_METRICS]
    if not filtered:
        raise ValueError("No valid metrics selected.")
    return filtered


def parse_range(range_text: str) -> tuple[datetime, datetime, str]:
    start_time, end_time, label = parse_range_text(range_text)
    log.info(
        f"[cli] Parsed range={range_text!r} => "
        f"{start_time.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return start_time, end_time, label


def run_metrics(_: argparse.Namespace) -> int:
    service = ACAnalysisService()
    for metric in service.get_available_metrics():
        if metric in HIDDEN_METRICS:
            continue
        spec = METRIC_SPECS.get(metric)
        label = spec.label if spec else metric
        unit = spec.unit if spec else ""
        print(f"{metric:24} {label} [{unit}]")
    return 0


def run_summary(args: argparse.Namespace) -> int:
    service = ACAnalysisService()
    start_time, end_time, _ = parse_range(args.range_text)
    analysis = service.analyze_ac_efficiency(start_time, end_time)
    print(f"Range: {start_time:%Y-%m-%d %H:%M:%S} -> {end_time:%Y-%m-%d %H:%M:%S}")
    print(f"Runtime: {fmt_value(analysis['total_runtime_hours'], ' h', 2)}")
    print(f"Cooling cycles: {analysis['cooling_cycles']}")
    print(f"Average cycle: {fmt_value(analysis['avg_cycle_duration'], ' min', 1)}")
    print(f"Indoor temperature: {fmt_value(analysis['avg_indoor_temp'], ' C', 1)}")
    print(f"Indoor humidity: {fmt_value(analysis['avg_indoor_humidity'], '%', 1)}")
    print(f"Indoor heat index: {fmt_value(analysis['avg_indoor_heat_index'], ' C', 1)}")
    print(f"Outdoor temperature: {fmt_value(analysis['avg_outdoor_temp'], ' C', 1)}")
    print(f"Outdoor humidity: {fmt_value(analysis['avg_outdoor_humidity'], '%', 1)}")
    print(f"Average power: {fmt_value(analysis['avg_power_w'], ' W', 0)}")
    return 0


def run_prompt(args: argparse.Namespace) -> int:
    service = ACAnalysisService()
    settings = get_settings_manager().load_settings()
    start_time, end_time, _ = parse_range(args.range_text)
    prompt = service.generate_ai_prompt(start_time, end_time, settings)
    print(prompt)
    return 0


def run_plot(args: argparse.Namespace) -> int:
    service = ACAnalysisService()
    start_time, end_time, label = parse_range(args.range_text)
    metrics = resolve_metrics(service, args.metrics)
    output_path = service.export_figure(
        start_time,
        end_time,
        metrics=metrics,
        output_path=args.output,
        stem=f"{args.stem}_{label}",
    )
    if output_path is None:
        print("No plottable data was found in the requested range.")
        return 1
    print(output_path)
    return 0


class AnalysisShell(cmd.Cmd):
    intro = (
        "AC analysis shell\n"
        "\n"
        "Inspect historical AC measurements, summaries, prompts, and plots.\n"
        "\n"
        "Quick start:\n"
        "  metrics\n"
        "      List all plottable metrics currently present in the database.\n"
        "\n"
        "  summary [range]\n"
        "      Print a compact operational summary for a time window.\n"
        "      Example: summary 24h\n"
        "\n"
        "  prompt [range]\n"
        "      Generate the full AI-analysis prompt from current settings and history.\n"
        "      Example: prompt 3d\n"
        "\n"
        "  plot [range] [metric...]\n"
        "      Export a figure. If metrics are omitted, the default metric set is used.\n"
        "      Example: plot 6h temperature humidity ac_power_w\n"
        "\n"
        "Range formats:\n"
        "  Presets: 1h, 2h, 6h, 12h, 24h, 3d, 7d, 30d\n"
        "  Custom : \"YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM\"\n"
        "           Use quotes when the range contains spaces.\n"
        "\n"
        "Other commands:\n"
        "  help, ?, exit, quit\n"
        "\n"
        "Type 'help <command>' for command-specific usage.\n"
    )
    prompt = "ac> "

    def __init__(self) -> None:
        super().__init__()
        self.analysis_service = ACAnalysisService()

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> bool:
        text = line.strip()
        if not text:
            return False
        command = text.split()[0]
        print(f"Unknown command: {command}")
        print("Type 'help' to see available commands.")
        return False

    def do_metrics(self, arg: str) -> bool:
        _ = arg
        run_metrics(argparse.Namespace())
        return False

    def help_metrics(self) -> None:
        print("Usage: metrics")
        print("List all metrics currently available in the database.")
        print("Hidden internal metrics are omitted from this view.")

    def do_summary(self, arg: str) -> bool:
        range_text = arg.strip() or "6h"
        try:
            run_summary(argparse.Namespace(range_text=range_text))
        except Exception as exc:
            log.error(f"[cli] summary failed: {type(exc).__name__}: {exc}")
            print(f"summary failed: {exc}")
        return False

    def help_summary(self) -> None:
        print("Usage: summary [range]")
        print("Print runtime, cycle count, average indoor/outdoor conditions, and power.")
        print("Default range: 6h")
        print("Examples:")
        print("  summary")
        print("  summary 24h")
        print('  summary "2026-03-15 00:00, 2026-03-16 00:00"')

    def do_prompt(self, arg: str) -> bool:
        range_text = arg.strip() or "6h"
        try:
            run_prompt(argparse.Namespace(range_text=range_text))
        except Exception as exc:
            log.error(f"[cli] prompt failed: {type(exc).__name__}: {exc}")
            print(f"prompt failed: {exc}")
        return False

    def help_prompt(self) -> None:
        print("Usage: prompt [range]")
        print("Generate the AI prompt that combines controller settings with historical data.")
        print("Default range: 6h")
        print("Examples:")
        print("  prompt")
        print("  prompt 3d")

    def do_plot(self, arg: str) -> bool:
        try:
            tokens = shlex.split(arg)
            range_text = "6h"
            metrics: Optional[list[str]] = None
            if tokens:
                range_text = tokens[0]
            if len(tokens) > 1:
                metrics = tokens[1:]
            run_plot(
                argparse.Namespace(
                    range_text=range_text,
                    metrics=metrics,
                    output=None,
                    stem="shell",
                )
            )
        except Exception as exc:
            log.error(f"[cli] plot failed: {type(exc).__name__}: {exc}")
            print(f"plot failed: {exc}")
        return False

    def help_plot(self) -> None:
        print("Usage: plot [range] [metric ...]")
        print("Export a figure to the configured figure directory.")
        print("Default range: 6h")
        print("If no metrics are provided, the default plot metric set is used.")
        print("Examples:")
        print("  plot")
        print("  plot 24h")
        print("  plot 6h temperature humidity ac_power_w")
        print('  plot "2026-03-15 18:00, 2026-03-16 06:00" temperature')
        print("Use 'metrics' first if you are unsure which metric names are valid.")

    def do_help(self, arg: str) -> bool:
        topic = arg.strip()
        if not topic:
            print(self.intro)
            return False
        return super().do_help(arg)

    def do_exit(self, arg: str) -> bool:
        _ = arg
        return True

    def help_exit(self) -> None:
        print("Usage: exit")
        print("Leave the interactive shell.")

    def do_quit(self, arg: str) -> bool:
        return self.do_exit(arg)

    def help_quit(self) -> None:
        print("Usage: quit")
        print("Alias for exit.")

    def do_EOF(self, arg: str) -> bool:
        print()
        return self.do_exit(arg)


def run_shell(_: argparse.Namespace) -> int:
    AnalysisShell().cmdloop()
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        args = parser.parse_args(["shell"])
    try:
        return args.func(args)
    except Exception as exc:
        log.error(f"[cli] command failed: {type(exc).__name__}: {exc}")
        print(f"Command failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
