"""Phase 0 sanity check: confirm GOOGLE_API_KEY works against the real Gemini API.

Run: python hello_gemini.py
"""

from pathlib import Path

from dotenv import load_dotenv
from google import genai

# .env lives at the repo root (one level up from browser_automation/), not in here.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    client = genai.Client()  # reads GOOGLE_API_KEY from the environment
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say hello in exactly five words.",
    )
    print(response.text)


if __name__ == "__main__":
    main()
