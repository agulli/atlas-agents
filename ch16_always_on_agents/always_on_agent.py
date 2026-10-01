"""
Atlas v0.16 — Always-On Directory Monitor
==========================================
Chapter 16 Project: A daemon agent that watches a tasks/ directory,
processes each .txt file through Claude, and routes results to done/
or failed/. Writes a heartbeat file every loop so a watchdog can
detect crashes and stuck states.

Usage:
    python always_on_agent.py [--task-dir tasks] [--interval 10]

    # In another terminal, drop tasks in:
    echo "What is the capital of France?" > tasks/q001.txt

    # Stop cleanly:
    kill -TERM <pid>

Requires: pip install anthropic
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

import anthropic


sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are Atlas, a research assistant running as an always-on service.
Complete each task clearly and concisely. Do not add preamble."""

# ── Shutdown flag ──────────────────────────────────────────────────────

_running = True


def _handle_shutdown(signum, frame):
    global _running
    log.info("Shutdown signal received — finishing current task, then stopping.")
    _running = False


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


# ── Core logic ─────────────────────────────────────────────────────────

def process_task(task_file: Path) -> str:
    """Send the task to Claude and return the response text."""
    task = task_file.read_text().strip()
    if not task:
        raise ValueError("Task file is empty")

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": task}],
        max_tokens=1024,
    )
    return response.content[0].text


def write_heartbeat(path: Path):
    """Write current epoch timestamp. Watchdogs check this for staleness."""
    path.write_text(str(time.time()))


# ── Poll loop ──────────────────────────────────────────────────────────

def run(task_dir: Path, interval_s: int):
    done_dir = task_dir / "done"
    failed_dir = task_dir / "failed"
    heartbeat_file = task_dir.parent / "heartbeat.txt"

    for d in (task_dir, done_dir, failed_dir):
        d.mkdir(parents=True, exist_ok=True)

    log.info(f"Atlas Monitor started. Watching {task_dir}/ every {interval_s}s")
    log.info(f"Heartbeat: {heartbeat_file}")
    log.info("Send SIGTERM or Ctrl-C for graceful shutdown.")

    while _running:
        write_heartbeat(heartbeat_file)

        tasks = sorted(task_dir.glob("*.txt"))
        if not tasks:
            time.sleep(interval_s)
            continue

        for task_file in tasks:
            if not _running:
                break

            log.info(f"Processing: {task_file.name}")
            try:
                result = process_task(task_file)
                output = done_dir / task_file.name
                output.write_text(result)
                task_file.unlink()
                log.info(f"✅ {task_file.name} → done/")
            except Exception as e:
                log.error(f"❌ {task_file.name}: {e}")
                task_file.rename(failed_dir / task_file.name)

        time.sleep(interval_s)

    log.info("Shutdown complete.")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Atlas always-on directory monitor")
    parser.add_argument("--task-dir", default="tasks", help="Directory to watch")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval in seconds")
    args = parser.parse_args()

    run(Path(args.task_dir), args.interval)


if __name__ == "__main__":
    main()
