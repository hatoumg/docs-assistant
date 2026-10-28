"""Keep calls under a provider's tokens-per-minute limit by waiting when needed."""
import time



class TokenWindow:
    """Remembers what was sent in the last 60 seconds and waits until a new request fits."""

    def __init__(self, tokens_per_minute: int, clock=time.monotonic, sleep=time.sleep):
        self._limit = tokens_per_minute
        self._clock = clock
        self._sleep = sleep
        self._recent = []  # (time of call, estimated tokens)

    @property
    def limit(self) -> int:
        return self._limit

    def wait_for(self, tokens: int) -> None:
        """Block until `tokens` fits under the limit, then record them as used."""
        announced = False
        while True:
            now = self._clock()
            self._recent = [(t, n) for t, n in self._recent if now - t < 60]
            used = sum(n for _, n in self._recent)
            if not self._recent or used + tokens <= self._limit:
                break
            wait = self._recent[0][0] + 60 - now + 0.5
            if not announced:
                print(f"  pacing: waiting about {wait:.0f}s to stay under the {self._limit} tokens/minute limit")
                announced = True
            self._sleep(max(wait, 0.5))
        self._recent.append((self._clock(), tokens))


class ThrottledLLM:
    def __init__(self, inner, tokens_per_minute: int, reserve_output: int = 1500, chars_per_token: float = 3.0, clock=time.monotonic, sleep=time.sleep):
        self._inner = inner
        self._window = TokenWindow(tokens_per_minute, clock, sleep)
        self._reserve = reserve_output  # room for the model's reply (reasoning models use a lot)
        self._chars_per_token = chars_per_token  # a cautious estimate, so we never undercount

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def complete(self, prompt: str) -> str:
        self._window.wait_for(int(len(prompt) / self._chars_per_token) + self._reserve)
        return self._inner.complete(prompt)
