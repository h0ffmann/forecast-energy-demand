"""
translate_latex.py — PT-BR → EN-US LaTeX translation
Uses GitHub Models API (free, no extra secrets needed).
Only re-translates files whose content hash changed since the last run.

Usage:
    python scripts/translate_latex.py              # translates all changed files
    python scripts/translate_latex.py --force      # re-translates everything
    python scripts/translate_latex.py --dry-run    # shows what would be translated
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
PT_DIR    = REPO_ROOT / "docs" / "project" / "pt"
EN_DIR    = REPO_ROOT / "docs" / "project" / "en"
SHARED_DIR= REPO_ROOT / "docs" / "project" / "shared"
CACHE_FILE= REPO_ROOT / "docs" / "project" / ".translation-cache.json"

# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

# GitHub Models endpoint — uses the GITHUB_TOKEN that's already in Actions.
# No extra secrets needed. Rate limits: 15 req/min, 16k tokens/min, 170k/day.
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"

# Best free model available on GitHub Models for academic translation.
# Alternatives: "mistral-large-2407", "gpt-4o-mini" (also available on free tier)
MODEL = "meta-llama-3.1-70b-instruct"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an academic LaTeX translator specialising in engineering and computer science.
Your task is to translate a LaTeX source file from Brazilian Portuguese to American English.

STRICT RULES — follow every one of them:
1. Translate ONLY natural-language text: prose, section titles, captions, footnotes, abstracts.
2. NEVER modify LaTeX commands, environments, labels, refs, citations, or math.
   Examples of things you must NOT change:
     \\chapter{...} → translate the text inside the braces, not the command itself
     \\label{cap1} \\ref{cap1} \\cite{costa2024} → leave completely unchanged
     \\begin{equation} ... \\end{equation} → leave completely unchanged
     \\includegraphics[...]{fig/foo} → leave completely unchanged
3. Preserve blank lines, indentation, and comment lines (starting with %).
4. Use formal academic register (IEEE / ACM style).
5. Return ONLY the translated LaTeX source. No explanations, no markdown fences."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def file_hash(path: Path) -> str:
    """SHA-256 (first 20 chars) of file content — used as change detector."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:20]


def load_cache() -> dict[str, str]:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def translate(client: OpenAI, content: str) -> str:
    """Send content to GitHub Models and return translated LaTeX."""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        temperature=0.2,        # low temperature for consistent/accurate translation
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": content},
        ],
    )
    return response.choices[0].message.content


def setup_shared_symlinks() -> None:
    """
    Create symlinks in en/ pointing to shared/ for style files, bib, and figs.
    This way both pt/ and en/ compile against the same shared assets.
    """
    EN_DIR.mkdir(parents=True, exist_ok=True)
    for item in SHARED_DIR.iterdir():
        link = EN_DIR / item.name
        if not link.exists():
            link.symlink_to(item.resolve())
            print(f"  symlink: en/{item.name} → shared/{item.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Translate LaTeX PT-BR → EN-US")
    p.add_argument("--force",   action="store_true", help="Re-translate all files")
    p.add_argument("--dry-run", action="store_true", help="Show what would be translated")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Validate environment
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("ERROR: GITHUB_TOKEN environment variable not set.", file=sys.stderr)
        print("Locally, set it to a GitHub PAT with 'models:read' scope.", file=sys.stderr)
        sys.exit(1)

    if not PT_DIR.exists():
        print(f"ERROR: PT source directory not found: {PT_DIR}", file=sys.stderr)
        sys.exit(1)

    # Setup
    client = OpenAI(base_url=GITHUB_MODELS_BASE_URL, api_key=github_token)
    cache  = load_cache()

    EN_DIR.mkdir(parents=True, exist_ok=True)

    if SHARED_DIR.exists():
        setup_shared_symlinks()
    else:
        print(f"  WARNING: shared/ dir not found at {SHARED_DIR} — skipping symlinks")

    # Collect .tex files to translate
    tex_files = sorted(PT_DIR.glob("*.tex"))
    if not tex_files:
        print(f"No .tex files found in {PT_DIR}")
        return

    to_translate = []
    for pt_file in tex_files:
        h        = file_hash(pt_file)
        en_file  = EN_DIR / pt_file.name
        cached_h = cache.get(pt_file.name)

        if not args.force and cached_h == h and en_file.exists():
            print(f"  ✓ unchanged : {pt_file.name}")
        else:
            reason = "forced" if args.force else ("new" if not en_file.exists() else "modified")
            to_translate.append((pt_file, en_file, h, reason))

    if not to_translate:
        print("\nAll files up-to-date. Nothing to translate.")
        return

    print(f"\n{len(to_translate)} file(s) to translate:")
    for pt_file, _, _, reason in to_translate:
        print(f"  → {pt_file.name}  ({reason})")

    if args.dry_run:
        print("\n[dry-run] Stopping before actual API calls.")
        return

    # Translate
    print()
    translated = 0
    for pt_file, en_file, h, reason in to_translate:
        print(f"  translating: {pt_file.name} ...", end=" ", flush=True)
        try:
            content    = pt_file.read_text(encoding="utf-8")
            translated_text = translate(client, content)
            en_file.write_text(translated_text, encoding="utf-8")
            cache[pt_file.name] = h
            translated += 1
            print("done")
        except Exception as exc:
            print(f"FAILED — {exc}", file=sys.stderr)
            # Don't update cache for failed files — they'll be retried next run

        # Respect GitHub Models rate limit: 15 requests/minute
        if translated < len(to_translate):
            time.sleep(4)  # ~15 req/min ceiling

    save_cache(cache)
    print(f"\nDone. {translated}/{len(to_translate)} file(s) translated.")
    print(f"Cache saved to {CACHE_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()