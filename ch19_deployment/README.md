# Chapter 19 — Deployment, Async Agents, and Security

> **Atlas v0.19** — wrap the agent in a **FastAPI service** with three execution modes (sync, streaming, async queue), run it with Docker Compose, and add agent-specific monitoring.

## TL;DR

Agents are slow (seconds to minutes) and unpredictable in cost, so one request/response endpoint isn't enough. Offer three modes:

| Mode | Endpoint | Use when |
|---|---|---|
| **Sync** | `POST /agent/run` | Short tasks and the caller can wait. |
| **Stream** | `POST /agent/stream` (SSE) | Chat UIs, where users should see tokens as they arrive. |
| **Async** | `POST /agent/async` → `GET /agent/status/{task_id}` | Long tasks. A Celery worker processes them from a Redis queue with retry + backoff. |

Then monitor **agent** signals (tool calls per task, token-budget overruns, retry rate, cost per session) alongside the usual HTTP metrics.

```
client ─▶ agent-api (FastAPI) ─┬─ sync / SSE ─▶ Claude
                               └─ enqueue ─▶ Redis ─▶ agent-worker (Celery, retries) ─▶ Claude
                                                        │
             Postgres (checkpoints, trajectories)  ◀────┘      Prometheus ◀── /metrics
```

## Key concepts

| Concept | What it means | Where to see it |
|---|---|---|
| **Pydantic contracts** | `AgentRequest` / `AgentResponse` / `AsyncTaskResponse` validate the API boundary. | `api.py` |
| **Server-Sent Events** | Stream tokens over HTTP, which is simpler than WebSockets for one-way output. | `stream_agent()` |
| **Task queue** | Celery + Redis. The API returns a `task_id` immediately and workers do the work. | `async_agent()`, `process_agent_task()` |
| **Retry with backoff** | `max_retries=3`, `countdown = 2 ** retries`. | `process_agent_task()` |
| **Health checks** | `GET /health`, used by Docker healthchecks and load balancers. | `health()`, `docker-compose.yml` |
| **Compose stack** | `agent-api`, `agent-worker`, `redis`, `postgres`, `prometheus` with health-gated `depends_on`. | `docker-compose.yml` |
| **Agent metrics** | Prometheus counters and histograms per task via a `TaskTracker` context manager. | `online/agent_monitoring_dashboard.py` |
| **Central LLM gateway** | A LiteLLM proxy holds all provider keys, routes requests, enforces rate limits, and logs spend. | `online/litellm_proxy_server.py` |
| **Serverless deploy** | Build → push to Artifact Registry → Cloud Run with higher memory and a long timeout. Scales to zero when idle. | `online/cloud_run_deploy.py` |

## Files

| File | What it shows |
|---|---|
| `api.py` | The chapter project: FastAPI service with sync, SSE, and Celery async endpoints. |
| `docker-compose.yml` | Full local stack (API, worker, Redis, Postgres, Prometheus). |
| `online/agent_monitoring_dashboard.py` | `instrument_app(app)` → `/metrics`, with a demo that simulates tasks. |
| `online/litellm_proxy_server.py` | Configure, start, and test a LiteLLM proxy. |
| `online/cloud_run_deploy.py` | Scripted Google Cloud Run deployment. |

## What needs to be done

- [ ] `pip install fastapi uvicorn anthropic celery redis` and set `ANTHROPIC_API_KEY`.
- [ ] Run the API locally and call each of the three endpoints (see below).
- [ ] Start Redis and a Celery worker, submit an async task, and poll its status.
- [ ] Add a `Dockerfile` and `prometheus.yml` (Compose references both), then `docker compose up`. Set `POSTGRES_PASSWORD` in `.env`.
- [ ] Instrument the app with `instrument_app(app)` and check `/metrics`.
- [ ] Decide on per-user rate limits and authentication before exposing the service.

## Run it

```bash
cd ch19_deployment
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
celery -A api.celery_app worker --loglevel=info      # separate terminal, Redis running

curl -X POST localhost:8000/agent/run    -H 'content-type: application/json' -d '{"message":"What is MCP?"}'
curl -N -X POST localhost:8000/agent/stream -H 'content-type: application/json' -d '{"message":"What is MCP?"}'
curl -X POST localhost:8000/agent/async  -H 'content-type: application/json' -d '{"message":"Long research task"}'
curl localhost:8000/agent/status/<task_id>
```

`AgentRequest` fields: `message` (required), `session_id` (default `"default"`), `webhook_url` (optional, for async completion callbacks).

## Run with Gemma 4 on Ollama

> **One-time setup:** follow *Run everything locally with Gemma 4 on Ollama* in the [root README](../README.md): Ollama running, `gemma4-longctx` created, `.env` set to Option B. Run every command below from the **repo root**.

**Status: ✅ Works.** The API calls Gemma through the Anthropic-compatible endpoint. The main local catch is **networking from Docker**: inside a container, `localhost` is the container itself, not your machine.

### Setup

`.env` keys: `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=gemma4-longctx`.

```bash
pip install fastapi uvicorn anthropic celery redis python-dotenv litellm[proxy] prometheus-client
```

### Commands: directly on your machine

```bash
cd ch19_deployment
uvicorn api:app --port 8000 --reload
curl -X POST localhost:8000/agent/run    -H 'content-type: application/json' -d '{"message":"What is MCP?"}'
curl -N -X POST localhost:8000/agent/stream -H 'content-type: application/json' -d '{"message":"What is MCP?"}'

# Async mode (needs Redis: docker run -p 6379:6379 redis:7-alpine)
celery -A api.celery_app worker --loglevel=info
curl -X POST localhost:8000/agent/async -H 'content-type: application/json' -d '{"message":"Long task"}'
```

### Commands: Docker Compose with Ollama on the host

The containers must reach Ollama at `host.docker.internal`. Create `ch19_deployment/docker-compose.ollama.yml`:

```yaml
services:
  agent-api:
    environment:
      - ANTHROPIC_BASE_URL=http://host.docker.internal:11434
    extra_hosts: ["host.docker.internal:host-gateway"]   # needed on Linux; harmless on Mac/Windows
  agent-worker:
    environment:
      - ANTHROPIC_BASE_URL=http://host.docker.internal:11434
    extra_hosts: ["host.docker.internal:host-gateway"]
```

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up --build
```

(Compose also expects a `Dockerfile` and `prometheus.yml`; see "What needs to be done" above.) On Linux, Ollama listens on 127.0.0.1 by default. Start it with `OLLAMA_HOST=0.0.0.0 ollama serve` so containers can connect.

**LiteLLM proxy:** the `local` route points at `ollama_chat/<OLLAMA_MODEL>`:

```bash
python ch19_deployment/online/litellm_proxy_server.py          # then:  --test
```

### What to expect on Gemma 4

- One Ollama server handles requests **one model-generation at a time** by default. With 4 Celery workers, requests queue inside Ollama. Raise `OLLAMA_NUM_PARALLEL` (memory permitting) or lower worker concurrency.
- SSE streaming works the same. Tokens arrive at your hardware's speed.

### Troubleshooting

- **`Connection refused` from inside a container**: you used `localhost`. Use `host.docker.internal`, plus `OLLAMA_HOST=0.0.0.0` on Linux.
- **Async tasks time out**: local generations are slower than cloud. Raise Celery and HTTP timeouts.

## Production notes

- Put authentication, per-tenant rate limits, and request size limits in front of the API. An open agent endpoint lets anyone spend your money.
- Keep provider keys in one place (the proxy or a secret manager), not in every service.
- Alert on cost per session and budget overruns as well as 5xx rates.

## Takeaways

1. Offer sync, streaming, and async modes. Long agent tasks belong in a queue.
2. Retries, health checks, and durable state make the deployment survivable.
3. Monitor agent behavior (tools, tokens, cost), not only HTTP status.

**Prev:** [Ch. 18](../ch18_evaluation/README.md) · **Next:** [Chapter 20 — Loop Engineering](../ch20_loop_engineering/README.md)
