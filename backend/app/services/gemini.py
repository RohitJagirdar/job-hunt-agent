import json
import logging

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)

_ATTEMPTS = 2


class GeminiNotConfiguredError(RuntimeError):
    pass


def generate_json(prompt: str) -> dict:
    """Ask Gemini for a JSON object; retries once on transient failures."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiNotConfiguredError("Set GEMINI_API_KEY in backend/.env to enable Gemini.")

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(settings.llm_timeout_seconds * 1000)),
    )
    last_error: Exception | None = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            if not response.text:
                raise ValueError("Gemini returned an empty response.")
            parsed = json.loads(response.text)
            if not isinstance(parsed, dict):
                raise ValueError("Gemini returned JSON in an unexpected format.")
            return parsed
        except Exception as error:
            last_error = error
            logger.warning("Gemini attempt %d/%d failed: %s", attempt, _ATTEMPTS, error)
    assert last_error is not None
    raise last_error
