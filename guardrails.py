"""RailPulse guardrails.

Critical rule:
    LLMs do not execute SQL directly. They only generate SQL text.
    The backend validates, normalizes, and executes the query in a controlled path.
"""

from __future__ import annotations

import re

ALLOWED_TABLES = {
    "stations",
    "vehicles",
    "liveboard_records",
}

VALIDATION_RULES = {
    "do_not_execute_sql_directly": True,
    "only_select_allowed": True,
    "deny_destructive_keywords": [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "ALTER",
        "ATTACH",
        "DETACH",
        "CREATE",
        "TRUNCATE",
        "EXEC",
        "PRAGMA",
        "GRANT",
        "REVOKE",
    ],
    "allowed_tables": sorted(ALLOWED_TABLES),
}


def explain_guardrail() -> str:
    return (
        "The LLM never has direct permission to execute SQL. "
        "It only generates SQL text, while the backend validates and executes it safely."
    )


def validate_tables(query: str):
    query_upper = query.upper()
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([A-Z0-9_.\[\]]+)", query_upper)

    for table in matches:
        normalized = (
            table.replace("[", "")
            .replace("]", "")
            .split(".")[-1]
            .lower()
        )

        if normalized not in ALLOWED_TABLES:
            return False, f"Unauthorized table: {normalized}"

    return True, None
