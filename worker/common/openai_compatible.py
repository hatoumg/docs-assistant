"""One adapter for every service that speaks the OpenAI "chat completions" format.

Groq, OpenRouter and Mistral all accept the same request, so a provider is just three facts:
a web address, a key and a model name. Uses only the standard library, so nothing extra to install.
"""
import json
import re
import urllib.error
import urllib.request

from common.retry import call_with_retries


class LLMRequestError(RuntimeError):
    """The provider answered with an error. status is the HTTP code, or None for network trouble."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def is_transient(error) -> bool:
    """Worth retrying: network trouble, rate limits (429) and server-side errors (5xx)."""
    if not isinstance(error, LLMRequestError):
        return True
    return error.status is None or error.status == 429 or error.status >= 500


def suggested_wait(error):
    """Read "Please try again in 1m2.5s" (or 850ms, or 7.2s) out of a rate-limit message. None if absent."""
    match = re.search(r"try again in\s+(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)(ms|s))?", str(error))
    if not match or not (match.group(1) or match.group(2)):
        return None
    seconds = int(match.group(1) or 0) * 60
    if match.group(2):
        value = float(match.group(2))
        seconds += value / 1000 if match.group(3) == "ms" else value
    return min(seconds + 1.0, 90.0)


def _http_post(url, headers, payload, timeout):
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:300]
        raise LLMRequestError(f"HTTP {error.code}: {body}", error.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LLMRequestError(f"network problem: {error}") from None


class OpenAICompatibleLLM:
    def __init__(self, provider, base_url, api_key, model, retries=5, post=_http_post, sleep=None, timeout=60):
        self._provider = provider
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._retries = retries
        self._post = post
        self._sleep = sleep
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return f"{self._provider}:{self._model}"

    def complete(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "docs-assistant/1.0",  # some providers block the default Python agent
        }
        payload = {"model": self._model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}

        def call():
            data = self._post(self._url, headers, payload, self._timeout)
            try:
                return data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                raise LLMRequestError(f"unexpected reply from {self._provider}: {str(data)[:200]}") from None

        extra = {"sleep": self._sleep} if self._sleep else {}
        return call_with_retries(call, tries=self._retries, retryable=is_transient, wait_hint=suggested_wait, **extra)
