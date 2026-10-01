"""
Atlas v0.13 — Multimodal Document Analyst
==========================================
Chapter 13 Project: Analyze images and PDFs, answer questions.

Routes each input to the right model:
  - Images  → Claude (vision API)
  - PDFs    → Gemini 2.5 Flash (native PDF understanding)
  - Text    → Claude

Usage:
    python multimodal_agent.py image screenshot.png "What errors do you see?"
    python multimodal_agent.py pdf   report.pdf    "Summarize the key findings"
    python multimodal_agent.py text  notes.txt     "What are the action items?"

Requires: pip install anthropic google-genai
"""

import base64
import subprocess
import sys
from pathlib import Path

import anthropic


sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


client = anthropic.Anthropic()


# ── Image Analysis (Claude vision) ──────────────────────────────────────

def analyze_image(image_path: str, question: str) -> str:
    """Send an image to Claude for visual analysis."""
    path = Path(image_path)
    if not path.exists():
        return f"Error: file not found — {image_path}"

    with open(path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    mime = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": mime, "data": image_data},
                },
                {"type": "text", "text": question},
            ]
        }],
        max_tokens=1024,
    )
    return response.content[0].text


# ── PDF Analysis (Gemini — native PDF support) ──────────────────────────

def analyze_pdf_gemini(pdf_path: str, question: str) -> str:
    """
    Use Gemini for native PDF understanding.

    Gemini can read PDFs directly — no preprocessing, no text extraction.
    This preserves tables, charts, and document structure that pdftotext
    would destroy.
    """
    from google import genai
    from google.genai import types

    gclient = genai.Client()

    with open(pdf_path, "rb") as f:
        uploaded = gclient.files.upload(
            file=f,
            config={"display_name": Path(pdf_path).name},
        )

    response = gclient.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(parts=[
                types.Part.from_uri(file_uri=uploaded.uri, mime_type="application/pdf"),
                types.Part.from_text(question),
            ])
        ],
    )
    return response.text


def analyze_pdf_fallback(pdf_path: str, question: str) -> str:
    """
    Fallback when Gemini is unavailable: extract text with pdftotext,
    then answer with Claude.
    """
    result = subprocess.run(
        ["pdftotext", pdf_path, "-"],
        capture_output=True, text=True, timeout=30,
    )
    text = result.stdout[:8000] if result.returncode == 0 else "(text extraction failed)"

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        system="Answer the question based solely on the document text provided.",
        messages=[{
            "role": "user",
            "content": f"Document:\n{text}\n\nQuestion: {question}",
        }],
        max_tokens=1024,
    )
    return response.content[0].text


# ── Router ───────────────────────────────────────────────────────────────

def route_and_analyze(input_type: str, file_path: str, question: str) -> str:
    """Route to the appropriate analysis pipeline based on input type."""
    if input_type == "image":
        print(f"🖼️  Routing to: Claude vision")
        return analyze_image(file_path, question)

    elif input_type == "pdf":
        print(f"📄 Routing to: Gemini PDF (fallback: Claude text)")
        try:
            return analyze_pdf_gemini(file_path, question)
        except Exception as e:
            print(f"   Gemini unavailable ({e}), using text fallback")
            return analyze_pdf_fallback(file_path, question)

    else:
        print(f"📝 Routing to: Claude text")
        text = Path(file_path).read_text() if Path(file_path).exists() else file_path
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            messages=[{"role": "user", "content": f"{question}\n\n{text}"}],
            max_tokens=1024,
        )
        return response.content[0].text


# ── Main ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python multimodal_agent.py <type> <file> <question>")
        print("  type: image | pdf | text")
        print()
        print("Examples:")
        print('  python multimodal_agent.py image screenshot.png "What errors do you see?"')
        print('  python multimodal_agent.py pdf   report.pdf    "Summarize key findings"')
        sys.exit(1)

    input_type = sys.argv[1]
    file_path  = sys.argv[2]
    question   = " ".join(sys.argv[3:])

    print(f"🔮 Atlas v0.13 — Multimodal Agent")
    print(f"   File: {file_path}  |  Type: {input_type}")
    print(f"   Question: {question}\n")

    answer = route_and_analyze(input_type, file_path, question)
    print(f"\n🤖 Atlas:\n{answer}")
