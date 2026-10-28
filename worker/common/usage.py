"""Counts real calls to paid or rate-limited APIs, so experiments can report their cost."""
from dataclasses import dataclass


@dataclass
class UsageMeter:
    llm_calls: int = 0
    embed_calls: int = 0

    def snapshot(self):
        return (self.llm_calls, self.embed_calls)

    def since(self, snapshot):
        return (self.llm_calls - snapshot[0], self.embed_calls - snapshot[1])
