"""Step 2: send the prompt to the answering model and get its reply."""
from common.models import ask_llm


def generate_answer(prompt):
    """Returns the model's reply as text."""
    print("Asking the model...")
    return ask_llm(prompt).strip()
