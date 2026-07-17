"""
prose_verifier.py — The marketing /goal verifier from §21.4 as plain Python.

Proof that "creative" work can have a machine-checkable termination
condition. Every metric in the chapter's marketing /goal is implemented
below, and none of them needs a model:

  - Flesch-Kincaid grade      → a formula
  - "I/we"-to-"you" ratio     → arithmetic
  - Passive voice             → regex
  - Banned buzzwords          → a blocklist
  - Platform character limits → len()

Wire this as the verifier in a Chapter 20 loop and the agent grades its own
homework and regenerates before you ever see the draft.

Usage:
    python prose_verifier.py copy.txt --platform linkedin
    echo "Our seamless platform..." | python prose_verifier.py - --platform google

Requires: nothing beyond the standard library.
"""

import argparse
import re
import sys

MAX_GRADE = 8.0          # Flesch-Kincaid reading grade ceiling
MAX_SELF_RATIO = 0.3     # ("I" + "we") / "you" must stay below this
BUZZWORDS = {"synergy", "seamless", "paradigm", "leverage", "disrupt",
             "best-in-class", "cutting-edge", "revolutionize"}
PLATFORM_LIMITS = {"linkedin": 3000, "google": 90, "twitter": 280, "none": 10**9}

PASSIVE_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being)\s+(\w+ed|"
    r"given|taken|made|done|seen|known|shown|built|sent|held|kept)\b",
    re.IGNORECASE,
)


def count_syllables(word: str) -> int:
    word = word.lower().strip(".,;:!?\"'()")
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and n > 1 and not word.endswith(("le", "ee")):
        n -= 1
    return max(n, 1)


def flesch_kincaid_grade(text: str) -> float:
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z'\-]+", text)
    if not sentences or not words:
        return 0.0
    syllables = sum(count_syllables(w) for w in words)
    return (0.39 * len(words) / len(sentences)
            + 11.8 * syllables / len(words) - 15.59)


def self_to_you_ratio(text: str) -> float:
    words = [w.lower() for w in re.findall(r"[A-Za-z']+", text)]
    self_refs = sum(w in ("i", "we", "our", "us", "my") for w in words)
    you_refs = sum(w in ("you", "your", "yours") for w in words)
    return self_refs / you_refs if you_refs else float(self_refs)


def verify(text: str, platform: str = "none") -> tuple[bool, list[str]]:
    """The termination condition: (passed, list of concrete failures)."""
    failures = []

    grade = flesch_kincaid_grade(text)
    if grade >= MAX_GRADE:
        failures.append(f"reading grade {grade:.1f} (must be < {MAX_GRADE})")

    ratio = self_to_you_ratio(text)
    if ratio >= MAX_SELF_RATIO:
        failures.append(f'"I/we"-to-"you" ratio {ratio:.2f} (must be < {MAX_SELF_RATIO})')

    passives = PASSIVE_RE.findall(text)
    if passives:
        failures.append(f"passive voice x{len(passives)} (must be zero): "
                        f"{', '.join(passives[:3])}")

    found = sorted({b for b in BUZZWORDS if b in text.lower()})
    if found:
        failures.append(f"banned buzzwords: {', '.join(found)}")

    limit = PLATFORM_LIMITS[platform]
    if len(text) > limit:
        failures.append(f"{len(text)} chars exceeds {platform} limit of {limit}")

    return not failures, failures


def main():
    parser = argparse.ArgumentParser(description="Machine-check marketing copy")
    parser.add_argument("file", help="Copy file, or '-' for stdin")
    parser.add_argument("--platform", choices=PLATFORM_LIMITS, default="none")
    args = parser.parse_args()

    text = sys.stdin.read() if args.file == "-" else open(args.file).read()
    passed, failures = verify(text, args.platform)

    if passed:
        print("✅ PASS — every metric a shell script can check, checked.")
        sys.exit(0)
    print("❌ FAIL — scrap the draft and regenerate:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)


if __name__ == "__main__":
    main()
