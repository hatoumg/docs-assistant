"""Stand-ins for the AI services, so tests run with no network."""


class ScriptedLLM:
    """Replies with a fixed string, or with whatever a function returns for the prompt."""

    def __init__(self, reply="NOT_FOUND"):
        self.reply = reply
        self.prompts = []

    @property
    def model_id(self):
        return "scripted"

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.reply(prompt) if callable(self.reply) else self.reply
