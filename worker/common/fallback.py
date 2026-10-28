"""FallbackLLM: try the first model, and if it fails, the next one."""


class FallbackLLM:
    def __init__(self, models: list):
        if not models:
            raise ValueError("FallbackLLM needs at least one model")
        self._models = models

    @property
    def model_id(self) -> str:
        return self._models[0].model_id

    def complete(self, prompt: str) -> str:
        last_error = None
        for index, model in enumerate(self._models):
            try:
                return model.complete(prompt)
            except Exception as error:  # includes daily-budget errors, so a used-up provider hands over
                last_error = error
                if index + 1 < len(self._models):
                    print(f"  {model.model_id} failed ({str(error)[:120]}); trying {self._models[index + 1].model_id}")
        raise last_error
