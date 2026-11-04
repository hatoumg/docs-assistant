"""Gemini as an answering model. The only place that imports google-genai."""
import re

from common.retry import call_with_retries

def is_transient(error) -> bool:
    """Worth retrying: rate limits, server-side errors, or no HTTP code at all (network trouble).

    A 400, 401, 403 or 404 means the request itself is wrong (bad key, unknown model), so waiting cannot fix it.
    A 429 that says the DAILY limit is used up will not clear for hours, so it is not retried either.
    """
    if "perday" in str(error).lower().replace(" ", "").replace("_", ""):
        return False
    code = getattr(error, "code", None)
    return not isinstance(code, int) or code == 429 or code >= 500


def suggested_wait(error):
    """Read "Please retry in 58.5s" (or retryDelay '58s') out of a Google rate-limit error. None if absent."""
    match = re.search(r"retry in\s+([\d.]+)s|retryDelay['\"]?:\s*['\"]([\d.]+)s", str(error))
    if not match:
        return None
    return min(float(match.group(1) or match.group(2)) + 1.0, 90.0)


def _client(api_key: str):
    from google import genai

    return genai.Client(api_key=api_key)


class GeminiLLM:
    def __init__(self, api_key, model, retries=5):
        self._api_key = api_key
        self._model = model
        self._retries = retries
        self._client_instance = None

    @property
    def model_id(self) -> str:
        return self._model

    def complete(self, prompt: str) -> str:
        from google.genai import types

        if self._client_instance is None:
            self._client_instance = _client(self._api_key)

        def call():
            response = self._client_instance.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            return response.text or ""

        text = call_with_retries(call, tries=self._retries, retryable=is_transient, wait_hint=suggested_wait)
        return text
