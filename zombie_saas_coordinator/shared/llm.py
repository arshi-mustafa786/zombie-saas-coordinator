"""Shared Gemini helpers for tools that send untrusted data to the LLM.

Every caller wraps external data (IdP names, Trello rule text, ...) in a
tagged block and passes each value through ``prompt_safe`` first, so data
cannot close the block or inject new lines of instructions.
"""

import os
import re

from zombie_saas_coordinator.shared.constants import MAX_PROMPT_FIELD_LENGTH


def prompt_safe(value: object, max_length: int = MAX_PROMPT_FIELD_LENGTH) -> str:
    """Flatten untrusted text into one bounded line before it reaches the LLM."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value))
    # Angle brackets are swapped so data cannot close a <..._data> block.
    text = text.replace("<", "(").replace(">", ")")
    return text.strip()[:max_length]


def gemini_generate(prompt: str, *, json_output: bool = False) -> str | None:
    """Run one Gemini Pro call; None when not configured or on any failure.

    Callers must treat the result as untrusted and validate it.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model = os.getenv("GEMINI_PRO_MODEL")
    if not api_key or not model:
        return None

    try:
        from google import genai

        # Keep the client referenced: a temporary Client is garbage-collected and
        # closes its HTTP session before generate_content finishes.
        client = genai.Client(api_key=api_key)
        if json_output:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
        else:
            response = client.models.generate_content(model=model, contents=prompt)
    except Exception:
        return None

    text = (getattr(response, "text", None) or "").strip()
    return text or None
