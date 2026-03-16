from __future__ import annotations

import argparse
from datetime import datetime
import subprocess
import sys
import time
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restart the main controller automatically when it exits."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Seconds to wait before restarting after an exit. Default: 5",
    )
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=0,
        help="Maximum restart count. 0 means unlimited. Default: 0",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run. Default: python control_cli.py",
    )
    return parser


def resolve_command(command_args: Sequence[str]) -> list[str]:
    if not command_args:
        return [sys.executable, "control_cli.py"]
    if command_args[0] == "--":
        return list(command_args[1:]) or [sys.executable, "control_cli.py"]
    return list(command_args)


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[run_forever] {timestamp} | {message}", flush=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    command = resolve_command(args.command)

    restart_count = 0
    while True:
        log(f"starting: {' '.join(command)}")
        try:
            exit_code = subprocess.call(command)
        except KeyboardInterrupt:
            log("interrupted by user, stopping wrapper")
            return 130
        except Exception as exc:
            exit_code = 1
            log(f"failed to start child process: {type(exc).__name__}: {exc}")

        log(f"child exited with code {exit_code}")

        if args.max_restarts > 0 and restart_count >= args.max_restarts:
            log("max restarts reached, stopping wrapper")
            return exit_code

        restart_count += 1
        if args.delay > 0:
            log(f"restarting in {args.delay:.1f}s")
            try:
                time.sleep(args.delay)
            except KeyboardInterrupt:
                log("interrupted during restart delay, stopping wrapper")
                return 130


if __name__ == "__main__":
    raise SystemExit(main())
