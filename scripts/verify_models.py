"""Verify configured Gemini model IDs exist by making a test call, or list available models on error."""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.config import get_api_key, get_fallback_model, get_model


def verify_models(api_key: str | None = None) -> int:
    """Test primary and fallback models with a lightweight call or list available models."""
    key = api_key or get_api_key()
    if not key:
        print("Error: No Gemini API key provided or found.")
        print("Please provide via GEMINI_API_KEY environment variable or --key argument.")
        return 1

    try:
        from google import genai
    except ImportError:
        print("Error: 'google-genai' SDK is not installed in the active Python environment.")
        print("Install dependencies with: pip install -r requirements.txt")
        return 1

    client = genai.Client(api_key=key)

    primary_model = get_model()
    fallback_model = get_fallback_model()

    models_to_test = [
        ("Primary Model", primary_model),
        ("Fallback Model", fallback_model),
    ]

    all_ok = True

    print("============================================================")
    print("Testing Configured Gemini Model IDs")
    print(f"Primary:  {primary_model}")
    print(f"Fallback: {fallback_model}")
    print("============================================================\n")

    for label, model_id in models_to_test:
        print(f"--> Testing {label}: '{model_id}'...")
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents="Ping. Reply with one word: PONG",
            )
            reply = resp.text.strip() if (resp and resp.text) else "(no text returned)"
            print(f"    [OK] {label} '{model_id}' responded: {reply}\n")
        except Exception as exc:
            all_ok = False
            print(f"    [FAILED] {label} '{model_id}' error: {exc}\n")

    if not all_ok:
        print("============================================================")
        print("Retrieving Available Model IDs from Gemini API...")
        print("============================================================")
        try:
            available_models = []
            for m in client.models.list():
                m_name = getattr(m, "name", None) or getattr(m, "display_name", None) or str(m)
                clean_name = m_name.replace("models/", "")
                available_models.append(clean_name)

            print(f"Found {len(available_models)} available models:")
            gemini_models = [name for name in sorted(available_models) if "gemini" in name.lower()]
            for name in (gemini_models or sorted(available_models)):
                print(f"  - {name}")

            print("\nRecommended update:")
            print("Set GEMINI_MODEL and GEMINI_FALLBACK_MODEL to active model IDs from the list above.")
            print("Example:")
            print("  export GEMINI_MODEL=gemini-2.5-flash")
            print("  export GEMINI_FALLBACK_MODEL=gemini-2.0-flash")
        except Exception as list_exc:
            print(f"Failed to list models from API: {list_exc}")
        return 1

    print("============================================================")
    print("All configured models verified successfully!")
    print("============================================================")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify configured Gemini model IDs")
    parser.add_argument("--key", help="Gemini API Key (optional, defaults to config resolution)")
    args = parser.parse_args()
    sys.exit(verify_models(args.key))


if __name__ == "__main__":
    main()
