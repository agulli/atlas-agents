# Chapter 16 — Always-On Agents: Daemons, Watchdogs, and Recovery

> **Atlas v0.16** — a **daemon** agent that watches a task folder, processes each task, writes a **heartbeat**, shuts down cleanly on signals, and runs under a **watchdog** that restarts it.

## TL;DR

A long-running agent *will* crash, hang, or be killed mid-task. Design for it:

- **Loop**: poll (or subscribe to) a queue: `tasks/*.txt` → process → `done/` or `failed/`.
- **Heartbeat**: write a timestamp every iteration so an outside process can tell "alive" from "stuck".
- **Graceful shutdown**: on SIGTERM/SIGINT, finish the current task, then exit.
- **Supervisor**: restart on crash *or* stale heartbeat with exponential backoff, and give up after N tries.

```
watchdog_supervisor ──spawns──▶ always_on_agent ──every loop──▶ heartbeat.txt
      │  checks: process exited? heartbeat stale?                 tasks/ → done/ | failed/
      └──▶ kill + backoff + restart (max N) ──▶ CRITICAL alert
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Filesystem queue** | The directory *is* the queue, and moving files makes state visible. | `run()` |
| **Poison-message handling** | A failing task goes to `failed/` so it can't block the queue. | `run()` except-branch |
| **Heartbeat** | Epoch timestamp file, checked for staleness from outside. | `write_heartbeat()` |
| **Signal handling** | A flag set by SIGTERM/SIGINT so the loop exits between tasks, not mid-write. | `_handle_shutdown()` |
| **Crash vs. hang** | Crash means the process exited. Hang means it's alive but the heartbeat is stale. Handle both. | `online/watchdog_supervisor.py` |
| **Exponential backoff** | Wait longer between restarts to avoid tight crash loops. | `supervise()` |
| **Event-driven mode** | OS file events instead of polling, with a backlog drain at startup for crash recovery. | `online/event_driven_agent.py` |
| **HTTP health** | `GET /health` → 200 / 503 for load balancers, plus an external checker that alerts. | `online/heartbeat_monitor.py` |

## Files

| File | What it shows |
|---|---|
| `always_on_agent.py` | The chapter project: polling daemon with heartbeat and graceful shutdown. |
| `online/watchdog_supervisor.py` | Runs the agent as a child and restarts it on crash or hang. |
| `online/event_driven_agent.py` | `watchdog`-library file events plus backlog drain. |
| `online/heartbeat_monitor.py` | FastAPI health endpoint and a staleness checker. |

## What needs to be done

- [ ] `pip install anthropic` (plus `watchdog`, `fastapi`, `uvicorn`, `httpx` for the extras).
- [ ] Start the agent, drop a few `.txt` tasks into `tasks/`, and watch them move to `done/`.
- [ ] Drop an empty file and confirm it lands in `failed/`.
- [ ] `kill -TERM <pid>` mid-run and confirm it finishes the current task first.
- [ ] Run under `watchdog_supervisor.py`, then `kill -9` the agent and watch the restart and backoff.
- [ ] Simulate a hang (add a long `sleep` in `process_task`) and confirm the stale heartbeat triggers a restart.

## Run it

```bash
cd ch16_always_on_agents
python always_on_agent.py --task-dir tasks --interval 10
echo "What is the capital of France?" > tasks/q001.txt

python online/watchdog_supervisor.py --agent always_on_agent.py --max-restarts 5
python online/heartbeat_monitor.py --mode server   # + --mode checker in another terminal
```

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Fully local.** This is the best chapter to run on Ollama: a daemon that runs all day costs nothing per call locally.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=gemma4-longctx`.

```bash
pip install anthropic python-dotenv watchdog fastapi uvicorn httpx
```

Keep the model loaded between tasks, so each task doesn't pay the load time:

```bash
export OLLAMA_KEEP_ALIVE=24h     # set before starting `ollama serve` (or in the desktop app's environment)
```

### Commands

```bash
# Terminal 1: the agent under its watchdog
cd ch16_always_on_agents
python online/watchdog_supervisor.py --agent always_on_agent.py --max-restarts 5

# Terminal 2: feed it tasks
cd ch16_always_on_agents
echo "Summarize the CAP theorem in 3 bullets" > tasks/q001.txt
echo "" > tasks/empty.txt                       # → tasks/failed/
ls tasks/done tasks/failed; cat tasks/done/q001.txt
```

Event-driven variant and HTTP health:

```bash
python ch16_always_on_agents/online/event_driven_agent.py
python ch16_always_on_agents/online/heartbeat_monitor.py --mode server     # + --mode checker in another terminal
```

### What to expect on Gemma 4

- **Hang detection matters more locally.** A local generation can take a long time on CPU, which can look like a stuck process. The heartbeat is written between tasks, so if the watchdog restarts the agent mid-task, raise `HEARTBEAT_TIMEOUT_S` (60 s) in `watchdog_supervisor.py` above your slowest task.
- Stop Ollama (`ollama stop gemma4-longctx` or quit it) while tasks are queued: tasks move to `failed/` with a connection error, and the daemon keeps running. That's the poison-message handling at work.

### Troubleshooting

- **The first task is slow, later ones fast**: model load time. `OLLAMA_KEEP_ALIVE` keeps it in memory.

## Production notes

- Make task processing **idempotent**, because a crash can leave a task half-done and it will be retried.
- Replace the log line in the checker with a real alert (PagerDuty, Slack, SNS).
- In containers, use the HTTP health endpoint for liveness probes.
- Chapter 17 shows how managed platforms take this whole layer off your hands.

## Takeaways

1. Assume the agent will crash or hang.
2. Heartbeat + supervisor + backoff is the basic reliability setup for any long-running process.
3. Graceful shutdown and poison-message handling keep failures from spreading.

**Prev:** [Ch. 15](../ch15_agent_harness/README.md) · **Next:** [Chapter 17 — Managed Agents](../ch17_managed_agents/README.md)
