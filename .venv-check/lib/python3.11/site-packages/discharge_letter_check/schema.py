"""Load the JSON schema for extracted discharge instructions that ships inside the package."""

import json
from importlib import resources


SCHEMA_FILENAME = "discharge-extraction.schema.json"


def schema_text() -> str:
    """The bundled schema as the JSON text that was packaged."""

    return (
        resources.files("discharge_letter_check")
        .joinpath("schemas", SCHEMA_FILENAME)
        .read_text(encoding="utf-8")
    )


def load_schema() -> dict:
    """The bundled schema as a new dict, so a caller may change its copy."""

    return json.loads(schema_text())
