import requests
from langchain.tools import tool


def _login():
    pass


@tool
def get_invoces() -> list[str]:
    """
    return a list of invoces
    """
    _login()
    invoces = []

    return invoces


@tool
def get_invoces(id: str) -> str:
    """
    return the invoces with the given id
    """
    _login()
    invoce = ""

    return invoce
