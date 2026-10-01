"""
Atlas v0.12 — Data Analyst Agent (E2B Sandbox)
================================================
Chapter 12 Project: Natural language data analysis with sandboxed code execution.

Usage:
    python data_analyst.py "Analyze sales.csv and show monthly trends"

Requires: pip install e2b-code-interpreter anthropic
"""

import sys
from pathlib import Path

import anthropic


sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


client = anthropic.Anthropic()


# ── Code Agent Prompt ────────────────────────────────────────────────

CODE_AGENT_PROMPT = """You are Atlas, a data analyst agent.

You analyze data by writing and executing Python code.
You have access to pandas, matplotlib, seaborn, and numpy.

RULES:
1. Always start by loading and inspecting the data (head, describe, dtypes).
2. Write clean, well-commented code.
3. Save all charts to /tmp/ as PNG files.
4. Print clear summaries of your findings.
5. If code fails, analyze the error and fix it.
6. Maximum 5 code iterations.

When you write code, wrap it in a Python code block:
```python
# your code here
```
"""


# ── Code Extraction ──────────────────────────────────────────────────

def extract_code_block(text: str) -> str | None:
    """Extract Python code from a markdown code block."""
    import re
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else None


# ── Sandbox Agent Loop ───────────────────────────────────────────────

def run_data_analyst(task: str, data_path: str | None = None, max_iterations: int = 5):
    """Run the data analyst agent with (optionally) E2B sandbox."""
    # Try E2B, fall back to local subprocess
    use_e2b = False
    sandbox = None
    try:
        from e2b_code_interpreter import Sandbox
        sandbox = Sandbox()
        use_e2b = True
        print("🔒 Using E2B sandbox for code execution")

        # Upload data file if provided
        if data_path and Path(data_path).exists():
            with open(data_path, "rb") as f:
                sandbox.files.write(f"/tmp/{Path(data_path).name}", f.read())
            print(f"📁 Uploaded {data_path} to sandbox")
    except ImportError:
        print("⚠️ E2B not installed, using local subprocess (less safe)")
    except Exception as e:
        print(f"⚠️ E2B unavailable ({e}), using local subprocess")

    # The prompt tells the model the data lives in /tmp/, so mirror that locally too
    if not use_e2b and data_path and Path(data_path).exists():
        import shutil
        shutil.copy(data_path, f"/tmp/{Path(data_path).name}")

    messages = [
        {"role": "user", "content": task},
    ]

    if data_path:
        messages[-1]["content"] += f"\n\nData file is at: /tmp/{Path(data_path).name}"

    for iteration in range(max_iterations):
        print(f"\n── Iteration {iteration + 1} ──")

        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            system=CODE_AGENT_PROMPT,
            messages=messages,
            max_tokens=2048,
        )

        content = response.content[0].text
        messages.append({"role": "assistant", "content": content})
        code = extract_code_block(content)

        if not code:
            print("✅ Agent finished (no more code to execute)")
            return {"answer": content, "iterations": iteration + 1}

        print(f"💻 Executing code ({len(code)} chars)...")

        # Execute
        if use_e2b and sandbox:
            result = sandbox.run_code(code)
            output = result.text or ""
            error = str(result.error) if result.error else ""
        else:
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                f.flush()
                try:
                    proc = subprocess.run(
                        ["python", f.name], capture_output=True, text=True, timeout=30
                    )
                    output = proc.stdout
                    error = proc.stderr
                except subprocess.TimeoutExpired:
                    output = ""
                    error = "Timeout: code took more than 30 seconds."

        if error and not output:
            print(f"❌ Error:\n{error[:200]}")
            messages.append({
                "role": "user",
                "content": f"The code produced an error:\n```\n{error}\n```\nPlease fix it."
            })
        else:
            preview = output[:300] + "..." if len(output) > 300 else output
            print(f"📊 Output:\n{preview}")
            messages.append({
                "role": "user",
                "content": f"Code executed successfully. Output:\n```\n{output}\n```\nIf analysis is complete, summarize findings. If more analysis needed, continue."
            })

    if sandbox:
        sandbox.kill()

    return {"answer": "Max iterations reached.", "iterations": max_iterations}


# ── Sample Data Generator ────────────────────────────────────────────

def create_sample_csv():
    """Create a sample CSV for demonstration."""
    csv_path = Path(__file__).parent / "sample_sales.csv"
    if not csv_path.exists():
        import random
        random.seed(42)
        lines = ["date,product,units,revenue"]
        products = ["Widget A", "Widget B", "Widget C"]
        for month in range(1, 13):
            for product in products:
                units = random.randint(50, 500)
                price = {"Widget A": 29.99, "Widget B": 49.99, "Widget C": 99.99}[product]
                revenue = round(units * price, 2)
                lines.append(f"2025-{month:02d}-15,{product},{units},{revenue}")
        csv_path.write_text("\n".join(lines))
        print(f"📝 Created sample data: {csv_path}")
    return str(csv_path)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("📊 Atlas v0.12 — Data Analyst Agent\n")

    if len(sys.argv) >= 2:
        task = " ".join(sys.argv[1:])
    else:
        task = "Load the sales data, show summary stats, and create a chart of monthly revenue by product."

    csv_path = create_sample_csv()

    result = run_data_analyst(task, data_path=csv_path)
    print(f"\n{'='*60}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Iterations used: {result['iterations']}")
    print(f"\n{result['answer']}")
