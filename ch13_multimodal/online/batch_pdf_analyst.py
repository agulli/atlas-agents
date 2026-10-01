"""
batch_pdf_analyst.py — Analyze visually complex PDFs page by page with Claude.

pdftotext and PyMuPDF are great for text-heavy PDFs. They fail badly on PDFs
that ARE the visual content: scanned reports, slide decks exported as PDF,
financial statements with merged cells, charts embedded in tables.

For those, convert each page to an image and send it to Claude's vision API.
The model sees the page exactly as a human would — layout, fonts, charts,
and all — and can answer questions that pure text extraction would miss.

This script processes up to MAX_PAGES pages from a PDF, sends each to Claude,
and returns a per-page analysis plus a final synthesis.

Usage:
    python batch_pdf_analyst.py report.pdf "What are the key financial trends?"
    python batch_pdf_analyst.py slides.pdf "Summarize each slide in one sentence"

Requires:
    pip install anthropic pdf2image
    # Also needs poppler installed:
    # macOS:  brew install poppler
    # Linux:  apt-get install poppler-utils
"""

import base64
import sys
import tempfile
from pathlib import Path

import anthropic
from pdf2image import convert_from_path


sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.config import ANTHROPIC_MODEL  # also loads .env


client = anthropic.Anthropic()

MAX_PAGES = 5        # Cap to control cost; raise for longer documents
IMAGE_DPI  = 150     # 150 dpi is sharp enough for text; higher costs more tokens


def pdf_page_to_base64(image) -> str:
    """Convert a PIL image (one PDF page) to a base64 PNG string."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        image.save(tmp.name, "PNG")
        with open(tmp.name, "rb") as f:
            return base64.b64encode(f.read()).decode()


def analyze_page(page_image, page_num: int, question: str) -> str:
    """Send one PDF page (as an image) to Claude and return the analysis."""
    image_b64 = pdf_page_to_base64(page_image)

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": f"This is page {page_num} of a PDF document.\n\n{question}",
                },
            ]
        }],
        max_tokens=512,
    )
    return response.content[0].text


def synthesize(per_page: list[dict], question: str) -> str:
    """Ask Claude to synthesize the per-page analyses into a final answer."""
    combined = "\n\n".join(
        f"=== Page {r['page']} ===\n{r['analysis']}" for r in per_page
    )
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        system="You are synthesizing per-page analyses of a PDF into a single answer.",
        messages=[{
            "role": "user",
            "content": (
                f"Original question: {question}\n\n"
                f"Per-page analyses:\n{combined}\n\n"
                f"Provide a concise, unified answer to the original question."
            ),
        }],
        max_tokens=1024,
    )
    return response.content[0].text


def analyze_pdf(pdf_path: str, question: str) -> dict:
    """
    Convert each page of a PDF to an image and analyze with Claude.
    Returns per-page results and a synthesized final answer.
    """
    print(f"Converting {pdf_path} to images (up to {MAX_PAGES} pages)...")
    pages = convert_from_path(pdf_path, dpi=IMAGE_DPI, last_page=MAX_PAGES)
    print(f"Processing {len(pages)} page(s)...\n")

    per_page_results = []
    for i, page_image in enumerate(pages, start=1):
        print(f"  Page {i}/{len(pages)}...", end=" ", flush=True)
        analysis = analyze_page(page_image, i, question)
        per_page_results.append({"page": i, "analysis": analysis})
        print("done")

    print("\nSynthesizing final answer...")
    final = synthesize(per_page_results, question)

    return {"pages": per_page_results, "answer": final}


def main():
    if len(sys.argv) < 3:
        print("Usage: python batch_pdf_analyst.py <pdf_path> <question>")
        print()
        print("Examples:")
        print('  python batch_pdf_analyst.py report.pdf "What are the key trends?"')
        print('  python batch_pdf_analyst.py slides.pdf "Summarize each slide"')
        sys.exit(1)

    pdf_path = sys.argv[1]
    question = " ".join(sys.argv[2:])

    if not Path(pdf_path).exists():
        print(f"Error: {pdf_path} not found.")
        sys.exit(1)

    result = analyze_pdf(pdf_path, question)

    print("\n" + "=" * 60)
    print("PER-PAGE ANALYSIS")
    print("=" * 60)
    for r in result["pages"]:
        print(f"\n--- Page {r['page']} ---")
        print(r["analysis"])

    print("\n" + "=" * 60)
    print("FINAL ANSWER")
    print("=" * 60)
    print(result["answer"])


if __name__ == "__main__":
    main()
