from __future__ import annotations

import shlex
import sys
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable, Optional

VENDOR_DIR = Path(__file__).resolve().parent / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from powers.message_handler import BotMessageHandler, BotResponse
from powers.utils.config import Config
from powers.utils.logger import (
    DEBUG_MODE,
    add_runtime_log_sink,
    disable_console_logging,
    enable_console_logging,
    remove_runtime_log_sink,
)

MAX_PANEL_LINES = 500


def cli_text(zh: str, en: str) -> str:
    language = str(Config.BOT_LANGUAGE).lower()
    if language == "zh":
        return zh
    if language == "bilingual":
        return f"{zh} / {en}"
    return en


def style_log_line(line: str) -> Text:
    parts = line.split(" | ", 3)
    if len(parts) != 4:
        return Text(line, style="white")

    timestamp, level, origin, message = parts
    level_style = {
        "DEBG": "bright_black",
        "INFO": "bright_green",
        "WARN": "bright_yellow",
        "ERRO": "bright_red",
    }.get(level, "white")

    styled = Text()
    styled.append(timestamp, style="green")
    styled.append(" | ", style="white")
    styled.append(level, style=level_style)
    styled.append(" | ", style="white")
    styled.append(origin, style="cyan")
    styled.append(" | ", style="white")
    styled.append(message, style=level_style)
    return styled


class ControlCliApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #0f172a;
    }

    #body {
        height: 1fr;
        layout: vertical;
    }

    .panel {
        border: round #64748b;
        margin: 0 1;
        padding: 0 1;
        background: #111827;
    }

    .panel_title {
        color: #cbd5e1;
        text-style: bold;
        margin: 0;
    }

    #log_panel {
        height: 4fr;
    }

    #output_panel {
        height: 4fr;
    }

    #log_view, #output_view {
        width: 100%;
        height: 1fr;
    }

    #input_panel {
        height: 2fr;
    }

    Input {
        width: 100%;
        height: 3;
        margin: 1 0 0 0;
        background: #020617;
        color: #f8fafc;
        border: heavy #38bdf8;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("tab", "focus_next", "Next"),
        ("shift+tab", "focus_previous", "Prev"),
        ("ctrl+l", "focus_input", "Input"),
    ]

    def __init__(
        self,
        runtime_starter: Optional[Callable[[], Any]] = None,
        runtime_stopper: Optional[Callable[[Any], None]] = None,
        enable_runtime: bool = True,
    ) -> None:
        super().__init__()
        self.runtime_starter = runtime_starter
        self.runtime_stopper = runtime_stopper
        self.enable_runtime = enable_runtime
        self.runtime = None
        self.message_handler = BotMessageHandler()
        self.log_queue: Queue[str] = Queue()
        self.log_sink_id: Optional[int] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="body"):
            with Vertical(classes="panel", id="log_panel"):
                yield Static("Runtime Logs", classes="panel_title")
                yield RichLog(
                    id="log_view",
                    max_lines=MAX_PANEL_LINES,
                    wrap=False,
                    highlight=False,
                    markup=False,
                    auto_scroll=True,
                )
            with Vertical(classes="panel", id="output_panel"):
                yield Static("Command Parsing / Response", classes="panel_title")
                yield RichLog(
                    id="output_view",
                    max_lines=MAX_PANEL_LINES,
                    wrap=False,
                    highlight=False,
                    markup=False,
                    auto_scroll=True,
                )
            with Vertical(classes="panel", id="input_panel"):
                yield Static("Command Input", classes="panel_title")
                yield Input(placeholder="state / settemp 28.5 / stats 24h / plot 6h / help / exit", id="command_input")
        yield Footer()

    def on_mount(self) -> None:
        output_view = self.query_one("#output_view", RichLog)
        if self.enable_runtime:
            starter = self.runtime_starter
            if starter is None:
                from controll import start_runtime

                starter = start_runtime
            self.runtime = starter()

        self.log_sink_id = add_runtime_log_sink(
            self.log_queue.put,
            level="DEBUG" if DEBUG_MODE else "INFO",
        )
        self.query_one("#command_input", Input).focus()

        log_view = self.query_one("#log_view", RichLog)
        log_view.show_horizontal_scrollbar = True
        log_view.show_vertical_scrollbar = True
        output_view.show_horizontal_scrollbar = True
        output_view.show_vertical_scrollbar = True

        output_view.write(Text(cli_text("控制台已就绪。", "AC control CLI ready."), style="bright_cyan"))
        output_view.write(
            Text(
                cli_text(
                    "可输入例如: state, scheduler, settemp 28.5, stats 24h, plot 6h, help, exit",
                    "Enter commands such as: state, scheduler, settemp 28.5, stats 24h, plot 6h, help, exit",
                ),
                style="white",
            )
        )
        output_view.write(
            Text(
                cli_text(
                    "聚焦后的面板可用方向键和滚动条滚动。",
                    "Focused panels use built-in arrow key and scrollbar scrolling.",
                ),
                style="bright_white",
            )
        )

        self.set_interval(0.1, self.flush_logs)

    def on_unmount(self) -> None:
        if self.log_sink_id is not None:
            remove_runtime_log_sink(self.log_sink_id)
            self.log_sink_id = None
        if self.runtime is not None:
            stopper = self.runtime_stopper
            if stopper is None:
                from controll import shutdown_runtime

                stopper = shutdown_runtime
            stopper(self.runtime)
            self.runtime = None

    def flush_logs(self) -> None:
        log_view = self.query_one("#log_view", RichLog)
        updated = False
        while True:
            try:
                message = self.log_queue.get_nowait()
            except Empty:
                break
            for line in message.splitlines() or [""]:
                log_view.write(style_log_line(line), scroll_end=True)
            updated = True
        if updated:
            log_view.refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip()
        event.input.value = ""
        if not raw:
            return

        output_view = self.query_one("#output_view", RichLog)
        parsed = self.normalize_command(raw)
        output_view.write(Text(f"> {raw}", style="bright_cyan"), scroll_end=True)

        if parsed in {"exit", "quit"}:
            output_view.write(Text(cli_text("正在关闭控制台。", "Shutting down control CLI."), style="bright_yellow"), scroll_end=True)
            self.exit()
            return
        if parsed == "clear":
            self.query_one("#log_view", RichLog).clear()
            output_view.clear()
            output_view.write(Text(cli_text("面板已清空。", "Panels cleared."), style="bright_yellow"), scroll_end=True)
            return
        if parsed == "help":
            help_response = self.message_handler.deal_message("/help", source="controll-cli")
            for line in help_response.text.splitlines() or [""]:
                output_view.write(Text(line), scroll_end=True)
            output_view.write(Text(""), scroll_end=True)
            output_view.write(
                Text(
                    cli_text("本地 CLI 指令: clear, exit, quit", "Local CLI commands: clear, exit, quit"),
                    style="bright_yellow",
                ),
                scroll_end=True,
            )
            return

        output_view.write(Text(cli_text(f"已解析: {parsed}", f"parsed: {parsed}"), style="bright_green"), scroll_end=True)
        output_view.write(Text(cli_text("处理中...", "processing..."), style="white"), scroll_end=True)
        worker = self.run_worker(
            lambda: self.message_handler.deal_message(parsed, source="controll-cli"),
            name="command-dispatch",
            group="command-dispatch",
            description=parsed,
            exit_on_error=False,
            thread=True,
        )
        self.watch_command_worker(worker, parsed)

    def action_focus_input(self) -> None:
        self.query_one("#command_input", Input).focus()

    @work(exit_on_error=False)
    async def watch_command_worker(self, worker, parsed: str) -> None:
        output_view = self.query_one("#output_view", RichLog)
        try:
            response: BotResponse = await worker.wait()
            for line in response.text.splitlines() or [""]:
                output_view.write(Text(line), scroll_end=True)
            if response.image_path is not None:
                output_view.write(Text(str(response.image_path), style="bright_cyan"), scroll_end=True)
        except Exception as exc:
            output_view.write(Text(cli_text(f"已解析: {parsed}", f"parsed: {parsed}"), style="bright_yellow"), scroll_end=True)
            output_view.write(
                Text(cli_text(f"失败: {type(exc).__name__}: {exc}", f"failed: {type(exc).__name__}: {exc}"), style="bright_red"),
                scroll_end=True,
            )

    @staticmethod
    def normalize_command(raw: str) -> str:
        text = raw.strip()
        lowered = text.lower()
        local_commands = {
            "exit": "exit",
            "/exit": "exit",
            "quit": "quit",
            "/quit": "quit",
            "clear": "clear",
            "/clear": "clear",
            "help": "help",
            "/help": "help",
        }
        if lowered in local_commands:
            return local_commands[lowered]
        if text.startswith("/"):
            return text

        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        if not parts:
            return text

        head = parts[0].lower()
        aliases = {
            "setlock": "/lock",
            "clearlock": "/lock clear",
            "switchon": "/switchOn",
            "switchoff": "/switchOff",
        }
        bot_commands = {spec["name"] for spec in BotMessageHandler.DISCORD_COMMAND_SPECS}
        if head in aliases:
            return f"{aliases[head]} {' '.join(parts[1:])}".strip()
        if head in bot_commands:
            return f"/{parts[0]} {' '.join(parts[1:])}".strip()
        return text


def main() -> None:
    disable_console_logging()
    try:
        ControlCliApp().run()
    finally:
        enable_console_logging()


if __name__ == "__main__":
    main()
