"""Stand-ins for the AI services, so tests run with no network."""
import re
import zlib

import numpy as np

from common.usage import UsageMeter


class FakeEmbedder:
    """Hashes words into a fixed-size vector, so texts that share words end up close together."""

    DIM = 128

    def __init__(self, usage=None):
        self.usage = usage or UsageMeter()
        self.document_calls = 0

    @property
    def model_id(self):
        return f"fake|{self.DIM}"

    def _vector(self, text):
        v = np.zeros(self.DIM)
        for word in re.findall(r"[a-z0-9_]+", text.lower()):
            v[zlib.crc32(word.encode()) % self.DIM] += 1
        norm = np.linalg.norm(v)
        return (v / norm if norm else v).tolist()

    def embed_documents(self, texts):
        self.document_calls += 1
        self.usage.embed_calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        self.usage.embed_calls += 1
        return self._vector(text)


class ScriptedLLM:
    """Replies with a fixed string, or with whatever a function returns for the prompt."""

    def __init__(self, reply="NOT_FOUND", usage=None):
        self.reply = reply
        self.prompts = []
        self.usage = usage or UsageMeter()

    @property
    def model_id(self):
        return "scripted"

    def complete(self, prompt):
        self.prompts.append(prompt)
        self.usage.llm_calls += 1
        return self.reply(prompt) if callable(self.reply) else self.reply
