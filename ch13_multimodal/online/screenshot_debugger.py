"""
screenshot_debugger.py — Visual QA: compare a design spec against a rendered screenshot.

The workflow: a designer exports a Figma frame as PNG. A developer ships the
component. You want to know if they match — not approximately, but exactly.
Font sizes, padding values, hex colors, alignment offsets.

This script sends both images to Claude with a structured prompt asking for
specific, actionable CSS differences. The output is a list of concrete fixes,
not a vague "these look different."

Usage:
    # Compare two images from the command line
    python screenshot_debugger.py expected.png actual.png

    # Or use the Python API
    from screenshot_debugger import compare_designs
    fixes = compare_designs("figma_export.png", "playwright_screenshot.png")

Requires:
    pip install anthropic playwright
    playwright install chromium  # only needed for the live capture example
"""

import base64
import sys
from pathlib import Path

import anthropic

client = anthropic.Anthropic()

COMPARISON_PROMPT = """You are an expert front-end QA engineer doing a pixel-level design review.

Image 1 is the EXPECTED design (Figma export or design spec).
Image 2 is the ACTUAL rendered page (browser screenshot).

Your job: find CSS regressions. Look at:
- Spacing and padding (margin, padding, gap values)
- Typography (font size, weight, line-height, letter-spacing)
- Colors (background, text, border — include hex values where you can read them)
- Alignment (flexbox/grid issues, off-center elements)
- Border radius, shadows, and other decorative properties

Return ONLY a numbered list of actionable CSS fixes in this format:

1. [ELEMENT] [PROPERTY]: expected `VALUE`, got `VALUE`
   Fix: `selector { property: value; }`

If the designs match, return: "No regressions found."

Do not describe what the designs look like. Only list differences that need fixing."""


def load_image_b64(path: str) -> tuple[str, str]:
    """Load an image file and return (base64_data, mime_type)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(p.suffix.lower(), "image/png")

    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime


def compare_designs(expected_path: str, actual_path: str) -> str:
    """
    Compare two images and return actionable CSS fixes.

    expected_path: the reference design (Figma export, mockup, etc.)
    actual_path:   the rendered screenshot to check against it
    """
    expected_b64, expected_mime = load_image_b64(expected_path)
    actual_b64,   actual_mime   = load_image_b64(actual_path)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        messages=[{
            "role": "user",
            "content": [
                # Image 1: expected
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": expected_mime,
                        "data": expected_b64,
                    },
                },
                # Image 2: actual
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": actual_mime,
                        "data": actual_b64,
                    },
                },
                {"type": "text", "text": COMPARISON_PROMPT},
            ]
        }],
        max_tokens=1024,
    )
    return response.content[0].text


def capture_screenshot(url: str, output_path: str = "actual.png"):
    """
    Capture a live browser screenshot with Playwright.
    Use this to grab the 'actual' image from a running dev server.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.screenshot(path=output_path, full_page=False)
        browser.close()

    print(f"Screenshot saved to {output_path}")
    return output_path


def main():
    if len(sys.argv) == 3:
        if sys.argv[1].startswith("http"):
            # Capture + compare: URL + expected image
            url           = sys.argv[1]
            expected_path = sys.argv[2]
            actual_path   = capture_screenshot(url)
        else:
            # Direct comparison: two existing image files
            expected_path = sys.argv[1]
            actual_path   = sys.argv[2]

    else:
        print("Usage:")
        print("  python screenshot_debugger.py expected.png actual.png")
        print("  python screenshot_debugger.py http://localhost:3000 expected.png")
        print()
        print("Example:")
        print("  python screenshot_debugger.py figma_export.png browser_render.png")
        sys.exit(1)

    print(f"Comparing:")
    print(f"  Expected: {expected_path}")
    print(f"  Actual:   {actual_path}\n")

    fixes = compare_designs(expected_path, actual_path)

    print("CSS Regression Report")
    print("=" * 50)
    print(fixes)


if __name__ == "__main__":
    main()
