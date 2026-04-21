"""
Atlas v0.4 — Customer Support Triage System (Agents SDK)
=========================================================
Chapter 4 Project: Three specialist agents + triage router.

Usage:
    python triage.py "My API key stopped working after the update"

Requires: pip install openai-agents
"""

import asyncio
import sys
from pathlib import Path

# Note: This requires the openai-agents package
# pip install openai-agents
from agents import Agent, Runner, InputGuardrail, GuardrailFunctionOutput, InputGuardrailTripwireTriggered

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import require_key

require_key("openai")


# ── Tool Stubs (replace with real implementations) ──────────────────

def get_invoice(customer_id: str) -> str:
    """Look up a customer's invoice."""
    return f"Invoice for {customer_id}: $99.00/month, last payment 2025-03-01, status: active."

def process_refund(customer_id: str, amount: float, reason: str) -> str:
    """Process a refund for a customer."""
    return f"Refund of ${amount:.2f} initiated for {customer_id}. Reason: {reason}. ETA: 3-5 business days."

def update_payment(customer_id: str, method: str) -> str:
    """Update payment method."""
    return f"Payment method updated to {method} for {customer_id}."

def search_docs(query: str) -> str:
    """Search technical documentation."""
    return f"Documentation results for '{query}': Found 3 articles. Top result: 'API Authentication Guide v2.3 — Breaking Changes'."

def create_ticket(title: str, description: str, priority: str = "medium") -> str:
    """Create a support ticket."""
    return f"Ticket created: #{1234} — '{title}' (Priority: {priority})"

def check_status(ticket_id: str) -> str:
    """Check ticket status."""
    return f"Ticket #{ticket_id}: Status = In Progress, Assigned to: Engineering Team."


# ── Specialist Agents ────────────────────────────────────────────────

billing_agent = Agent(
    name="Billing Specialist",
    instructions="""You are a billing specialist at Atlas Corp. You help customers with:
    - Invoice questions and payment history
    - Payment method updates
    - Refund requests
    - Subscription changes

    Be empathetic, precise, and always reference specific account details.
    If the question is not about billing, say so and the system will route appropriately.""",
    tools=[get_invoice, process_refund, update_payment],
)

technical_agent = Agent(
    name="Technical Support",
    instructions="""You are a technical support engineer at Atlas Corp. You help with:
    - Bug reports and error troubleshooting
    - API integration issues
    - Feature questions and how-to guides
    - System status inquiries

    Always ask for error messages and steps to reproduce.
    If the issue is about billing, say so and the system will route appropriately.""",
    tools=[search_docs, create_ticket, check_status],
)

general_agent = Agent(
    name="General Support",
    instructions="""You are a general support agent at Atlas Corp. You handle:
    - General product inquiries
    - Account information
    - Business hours and company policies
    - Feature requests

    Be friendly and helpful. If the question clearly belongs to billing or
    technical support, say so and the system will route appropriately.""",
    handoffs=[billing_agent, technical_agent],
)


# ── Input Guardrail ─────────────────────────────────────────────────

async def profanity_check(ctx, agent, input_text):
    """Block messages containing profanity."""
    blocked_patterns = ["damn", "hell", "stupid"]  # Simplified for demo
    input_lower = input_text.lower()
    for word in blocked_patterns:
        if word in input_lower:
            return GuardrailFunctionOutput(
                output_info={"blocked": True, "reason": "profanity"},
                tripwire_triggered=True,
            )
    return GuardrailFunctionOutput(
        output_info={"blocked": False},
        tripwire_triggered=False,
    )


# ── Triage Router ───────────────────────────────────────────────────

triage_agent = Agent(
    name="Triage Router",
    instructions="""You are the first point of contact for Atlas Corp support.
    Your ONLY job is to route the customer to the right specialist:

    - Questions about invoices, payments, refunds, subscriptions → Billing Specialist
    - Questions about bugs, errors, API issues, technical problems → Technical Support
    - Everything else (general inquiries, policies) → General Support

    Do NOT try to answer questions yourself. Greet the customer briefly,
    then hand off to the appropriate specialist immediately.""",
    handoffs=[billing_agent, technical_agent, general_agent],
    input_guardrails=[InputGuardrail(guardrail_function=profanity_check)],
)


# ── Main ─────────────────────────────────────────────────────────────

async def handle_customer(message: str):
    """Process a customer message through the triage system."""
    print(f"📧 Customer: {message}\n")

    try:
        result = await Runner.run(triage_agent, message)
        print(f"🤖 Agent ({result.last_agent.name}):")
        print(f"   {result.final_output}")
    except InputGuardrailTripwireTriggered:
        print("🚫 Message blocked by guardrail.")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python triage.py \"Your support question\"")
        print("Examples:")
        print('  python triage.py "I was charged twice for my subscription"')
        print('  python triage.py "My API key stopped working"')
        print('  python triage.py "What are your business hours?"')
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    asyncio.run(handle_customer(message))
