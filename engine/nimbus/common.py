"""Shared utilities — console output, prompts, logging, JSON transaction log.

Provider-agnostic utilities used across the Nimbus engine.
Providers and services should import from here, not duplicate these functions.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

# ---------------------------------------------------------------------------
# Console singleton
# ---------------------------------------------------------------------------
console = Console()

# ---------------------------------------------------------------------------
# Timestamp for log file naming
# ---------------------------------------------------------------------------
TIMESTAMP = datetime.now().strftime("%Y-%m-%d-%H%M%S")

# ---------------------------------------------------------------------------
# Display helpers (Rich equivalents of Bash colour functions)
# ---------------------------------------------------------------------------


def print_header(title: str) -> None:
    console.print()
    console.print(Panel(f"[bold]{title}[/bold]", border_style="blue", expand=True))
    console.print()


def print_step(msg: str) -> None:
    console.print(f"[bold cyan]▶ {msg}[/bold cyan]")


def print_info(msg: str) -> None:
    console.print(f"[blue]ℹ {msg}[/blue]")


def print_success(msg: str) -> None:
    console.print(f"[bold green]✔ {msg}[/bold green]")


def print_warning(msg: str) -> None:
    console.print(f"[bold yellow]⚠ {msg}[/bold yellow]")


def print_error(msg: str) -> None:
    console.print(f"[bold red]✖ {msg}[/bold red]")


def print_detail(msg: str) -> None:
    console.print(f"  {msg}")


def die(msg: str, code: int = 1) -> None:
    print_error(msg)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def confirm(msg: str, default: bool = False) -> bool:
    return Confirm.ask(f"[bold]{msg}[/bold]", default=default)


def prompt_input(msg: str, default: str = "") -> str:
    return Prompt.ask(f"[bold]{msg}[/bold]", default=default or None) or ""


def prompt_password(msg: str) -> str:
    return Prompt.ask(f"[bold]{msg}[/bold]", password=True) or ""


def prompt_selection(items: list[str], prompt_msg: str = "Select") -> int:
    """Display a numbered list and return the 0-based index of the selection."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("No.", style="cyan", width=4)
    table.add_column("Item")
    for i, item in enumerate(items, 1):
        table.add_row(str(i), item)
    console.print(table)
    while True:
        choice = prompt_input(f"{prompt_msg} [1-{len(items)}]")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return idx
        except ValueError:
            pass
        print_warning(f"Please enter a number between 1 and {len(items)}")


# ---------------------------------------------------------------------------
# File-based logging
# ---------------------------------------------------------------------------

_log_file: Optional[Path] = None
_logger: Optional[logging.Logger] = None


def init_logging(prefix: str = "nimbus", log_dir: Optional[Path] = None) -> Path:
    """Initialise file-based logging. Returns the log file path."""
    global _log_file, _logger

    if log_dir is None:
        from .config import settings
        log_dir = settings.local_dir / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = log_dir / f"{prefix}-{TIMESTAMP}.log"

    _logger = logging.getLogger("nimbus")
    _logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(_log_file)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(fh)
    return _log_file


def log(msg: str) -> None:
    if _logger:
        _logger.info(msg)


def log_quiet(msg: str) -> None:
    if _logger:
        _logger.debug(msg)


def get_log_file() -> Optional[Path]:
    return _log_file


# ---------------------------------------------------------------------------
# JSON transaction log
# ---------------------------------------------------------------------------


class TransactionLog:
    """Structured JSON log for tracking multi-step operations."""

    def __init__(self, operation: str, log_dir: Optional[Path] = None):
        self.operation = operation
        if log_dir is None:
            from .config import settings
            log_dir = settings.local_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"{operation}-{TIMESTAMP}.json"
        self._data: dict[str, Any] = {
            "operation": operation,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "in_progress",
            "steps": [],
        }
        self._current_step: Optional[dict[str, Any]] = None
        self._flush()

    def step(self, step_id: str, description: str) -> None:
        self._close_current_step("done")
        self._current_step = {
            "id": step_id,
            "description": description,
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._data["steps"].append(self._current_step)
        self._flush()

    def step_update(self, status: str = "done", detail: str = "") -> None:
        if self._current_step:
            self._current_step["status"] = status
            if detail:
                self._current_step["detail"] = detail
            self._current_step["ended_at"] = datetime.now(timezone.utc).isoformat()
        self._flush()

    def finalize(self, status: str = "success", message: str = "") -> None:
        self._close_current_step("done")
        self._data["status"] = status
        self._data["ended_at"] = datetime.now(timezone.utc).isoformat()
        if message:
            self._data["message"] = message
        self._flush()

    def _close_current_step(self, default_status: str) -> None:
        if self._current_step and self._current_step["status"] == "in_progress":
            self._current_step["status"] = default_status
            self._current_step["ended_at"] = datetime.now(timezone.utc).isoformat()

    def _flush(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------


def check_command(cmd: str) -> bool:
    """Return True if *cmd* is available on PATH."""
    try:
        subprocess.run(["which", cmd], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_dependencies(*cmds: str) -> None:
    missing = [c for c in cmds if not check_command(c)]
    if missing:
        die(f"Missing required commands: {', '.join(missing)}")
