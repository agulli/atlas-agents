"""
Escalation Chains (Online Extra)
==================================
Monitors an agent's execution trajectory and auto-escalates
to a human queue when the agent hits repeated tool failures.

Usage:
    python escalation_chains.py
"""

from dataclasses import dataclass


@dataclass
class TrajectoryStep:
    """A single step in an agent's execution trajectory."""
    tool_name: str
    input: str
    output: str
    success: bool


def escalation_handler(trajectory: list[TrajectoryStep], threshold: int = 3) -> dict:
    """
    Monitors an agent's execution trajectory. If the agent fails
    to get useful output after `threshold` consecutive tool calls,
    auto-escalates to human queue.
    """
    consecutive_failures = 0
    for step in trajectory:
        if not step.success or "Error" in step.output:
            consecutive_failures += 1
        else:
            consecutive_failures = 0  # Reset on success

        if consecutive_failures >= threshold:
            return {
                "status": "escalated",
                "reason": f"Agent hit {threshold} consecutive tool failures.",
                "failed_tools": [s.tool_name for s in trajectory if not s.success],
                "handoff_to": "human_queue",
            }

    return {"status": "continue", "steps_completed": len(trajectory)}


# ── Demo ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate an agent that keeps failing
    trajectory = [
        TrajectoryStep("search_web", "LangGraph docs", "Results found", True),
        TrajectoryStep("read_url", "https://example.com", "Error: 404 Not Found", False),
        TrajectoryStep("read_url", "https://example.com/v2", "Error: Timeout", False),
        TrajectoryStep("read_url", "https://example.com/v3", "Error: Connection refused", False),
    ]

    result = escalation_handler(trajectory)
    print(f"Status: {result['status']}")
    if result["status"] == "escalated":
        print(f"Reason: {result['reason']}")
        print(f"Failed tools: {result['failed_tools']}")
    else:
        print(f"Steps completed: {result['steps_completed']}")