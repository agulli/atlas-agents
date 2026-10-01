"""
litellm_proxy_server.py — Centralized LiteLLM proxy for multi-provider routing.

The problem with giving every service its own API keys:
  - Keys scattered across environment variables on 12 services
  - No central visibility into what's spending what
  - Swapping providers means touching every service

The fix: a single LiteLLM proxy that holds all the keys. Your services
call one endpoint with one API key (yours). The proxy routes to the right
provider, enforces rate limits, and logs everything.

This file configures and starts the proxy. Run it with:
    python litellm_proxy_server.py                     # Start the proxy
    python litellm_proxy_server.py --test             # Run routing tests

Or use the Docker image in docker-compose.yml:
    docker compose up litellm-proxy

Requires: pip install litellm[proxy]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import (  # also loads .env
    ANTHROPIC_MODEL, ANTHROPIC_FAST_MODEL, ANTHROPIC_STRONG_MODEL, GEMINI_MODEL, OLLAMA_MODEL,
)

# ── Proxy configuration ───────────────────────────────────────────────

LITELLM_CONFIG = {
    "model_list": [
        # Primary: Claude Sonnet — default for all agent calls
        {
            "model_name":     "claude-sonnet",
            "litellm_params": {
                "model":   f"anthropic/{ANTHROPIC_MODEL}",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
        # Fallback: Claude Haiku — automatic fallback on Sonnet rate limit
        {
            "model_name":     "claude-sonnet",
            "litellm_params": {
                "model":   f"anthropic/{ANTHROPIC_FAST_MODEL}",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
        # Gemini Flash — cheap high-volume route (guardrails, classification)
        {
            "model_name":     "gemini-flash",
            "litellm_params": {
                "model":   f"gemini/{GEMINI_MODEL}",
                "api_key": "os.environ/GOOGLE_API_KEY",
            },
        },
        # Local Ollama — development and privacy-sensitive workloads
        {
            "model_name":     "local",
            "litellm_params": {
                "model":   f"ollama_chat/{OLLAMA_MODEL}",
                "api_base": "http://localhost:11434",
            },
        },
        # Opus 4.8 — complex reasoning, security reviews
        {
            "model_name":     "claude-opus",
            "litellm_params": {
                "model":   f"anthropic/{ANTHROPIC_STRONG_MODEL}",
                "api_key": "os.environ/ANTHROPIC_API_KEY",
            },
        },
    ],

    "router_settings": {
        "routing_strategy": "least-busy",
        "num_retries":       3,
        "fallbacks": [
            # If claude-sonnet hits rate limits, try gemini-flash
            {"claude-sonnet": ["gemini-flash"]},
        ],
        "context_window_fallbacks": [
            # If context exceeds Sonnet's window, route to Opus (1M context)
            {"claude-sonnet": ["claude-opus"]},
        ],
    },

    "litellm_settings": {
        "success_callback": ["prometheus"],
        "failure_callback": ["prometheus"],
        "request_timeout":  60,
        "drop_params":      True,   # Silently drop unsupported params per provider
    },

    "general_settings": {
        "master_key":        "os.environ/LITELLM_MASTER_KEY",
        "database_url":      "os.environ/DATABASE_URL",
        "store_model_in_db": True,
    },
}

# Per-team virtual keys with spend limits (set these in the LiteLLM UI or API)
VIRTUAL_KEYS_CONFIG = [
    {
        "team_id":    "atlas-research",
        "max_budget": 50.0,        # $50/month
        "models":     ["claude-sonnet", "gemini-flash"],
        "tpm_limit":  100_000,     # 100k tokens/min
    },
    {
        "team_id":    "atlas-guardrails",
        "max_budget": 10.0,        # $10/month (guardrails use cheap models)
        "models":     ["gemini-flash"],
        "tpm_limit":  500_000,
    },
]


def write_config(config: dict) -> str:
    """Write config to a temp YAML file and return the path."""
    import yaml
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        return f.name


def start_proxy(port: int = 4000, config_path: str | None = None):
    """Start the LiteLLM proxy server."""
    if config_path is None:
        config_path = write_config(LITELLM_CONFIG)

    print(f"Starting LiteLLM proxy on port {port}...")
    print(f"Config: {config_path}")
    print(f"\nRoutes available:")
    for model in LITELLM_CONFIG["model_list"]:
        name = model["model_name"]
        target = model["litellm_params"]["model"]
        print(f"  {name:20s} → {target}")
    print(f"\nProxy URL: http://localhost:{port}")
    print(f"Use any OpenAI-compatible client pointing to http://localhost:{port}/v1\n")

    subprocess.run([
        sys.executable, "-m", "litellm",
        "--config", config_path,
        "--port",   str(port),
        "--detailed_debug",
    ])


def test_proxy(port: int = 4000):
    """Test all model routes through the proxy."""
    import litellm

    litellm.api_base = f"http://localhost:{port}"
    litellm.api_key  = os.environ.get("LITELLM_MASTER_KEY", "test")

    test_routes = [
        ("claude-sonnet", "What is 2+2?"),
        ("gemini-flash",  "What is 3+3?"),
        ("local",         "What is 4+4?"),
    ]

    print(f"Testing LiteLLM proxy at http://localhost:{port}...")
    for model, prompt in test_routes:
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=50,
            )
            answer = response.choices[0].message.content
            cost   = litellm.completion_cost(response)
            print(f"  ✅ {model:20s} → {answer[:40]}  (${cost:.5f})")
        except Exception as e:
            print(f"  ❌ {model:20s} → ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="LiteLLM Proxy Server for Atlas")
    parser.add_argument("--port",   type=int, default=4000)
    parser.add_argument("--test",   action="store_true", help="Test routing only")
    parser.add_argument("--config", default=None, help="Path to custom config YAML")
    args = parser.parse_args()

    if args.test:
        test_proxy(args.port)
    else:
        start_proxy(args.port, args.config)


if __name__ == "__main__":
    main()
