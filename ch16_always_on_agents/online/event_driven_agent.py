"""
event_driven_agent.py — Filesystem-event triggered Atlas agent.

Same logic as always_on_agent.py but with no sleep timer. Instead of polling
every N seconds, the OS notifies us the instant a .txt file appears in tasks/.

The trade-off vs. polling:
  + Zero latency between file creation and processing
  + No wasted CPU during idle periods
  - Requires the watchdog library
  - Misses files created while the observer isn't running (use polling for
    crash-recovery scenarios where you need to drain a backlog on startup)

This version drains any backlog in tasks/ at startup, then switches to
event-driven mode. Best of both worlds.

Usage:
    python event_driven_agent.py

Requires: pip install anthropic watchdog
"""

import logging
import signal
import time
from pathlib import Path

import anthropic
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

client = anthropic.Anthropic()

TASK_DIR = Path("tasks")
DONE_DIR = TASK_DIR / "done"
FAILED_DIR = TASK_DIR / "failed"

SYSTEM_PROMPT = """You are Atlas, a research assistant running as an always-on service.
Complete each task clearly and concisely. Do not add preamble."""

_running = True


def _handle_shutdown(signum, frame):
    global _running
    log.info("Shutdown signal received.")
    _running = False


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


def process_task(task_file: Path):
    """Process one task file. Moves it to done/ or failed/ when complete."""
    task = task_file.read_text().strip()
    if not task:
        task_file.unlink()
        return

    log.info(f"Processing: {task_file.name}")
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": task}],
            max_tokens=1024,
        )
        result = response.content[0].text
        (DONE_DIR / task_file.name).write_text(result)
        task_file.unlink()
        log.info(f"✅ {task_file.name} → done/")
    except Exception as e:
        log.error(f"❌ {task_file.name}: {e}")
        task_file.rename(FAILED_DIR / task_file.name)


class TaskHandler(FileSystemEventHandler):
    """Triggered by the OS when a file is created in the watched directory."""

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix != ".txt":
            return
        # Small delay: let the writer finish before we read
        time.sleep(0.1)
        if path.exists():
            process_task(path)


def drain_backlog():
    """Process any tasks that arrived while the agent was offline."""
    backlog = sorted(TASK_DIR.glob("*.txt"))
    if backlog:
        log.info(f"Draining {len(backlog)} backlog task(s)...")
        for f in backlog:
            process_task(f)


def main():
    for d in (TASK_DIR, DONE_DIR, FAILED_DIR):
        d.mkdir(parents=True, exist_ok=True)

    drain_backlog()

    observer = Observer()
    observer.schedule(TaskHandler(), path=str(TASK_DIR), recursive=False)
    observer.start()
    log.info(f"Event-driven agent started. Watching {TASK_DIR}/")

    try:
        while _running:
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    main()
