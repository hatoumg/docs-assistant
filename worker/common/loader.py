"""A small helper for importing from files whose names start with a number, such as 1_chunk.py.

Python's normal 'from 1_chunk import x' is not allowed, because names cannot start with a digit.
This does the same thing with the name written as text:

    split_documents = load("1_indexing.3_chunk", "split_documents")
"""
from importlib import import_module


def load(module_name, *names):
    """Returns the named functions from the module. One name gives the function itself, several give a list."""
    module = import_module(module_name)
    found = [getattr(module, name) for name in names]
    return found[0] if len(found) == 1 else found
