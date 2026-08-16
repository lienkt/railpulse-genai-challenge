import json
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from database import (
    ensure_database,
    execute_select,
    get_schema_summary,
    get_latest_data_timestamp,
    get_db_mode,
)
from llm_client import generate_sql_from_prompt, generate_recommendation


HISTORY_PATH = Path(__file__).resolve().parent / ".chat_history.json"


# ---------------------------------------------------------
# Chat history
# ---------------------------------------------------------

def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []

    try:
        return json.loads(
            HISTORY_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return []


def save_history(messages: list) -> None:
    try:
        HISTORY_PATH.write_text(
            json.dumps(
                messages,
                default=str,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"Could not save chat history: {exc}")


# ---------------------------------------------------------
# Clean SQL returned by the LLM
# ---------------------------------------------------------

def clean_generated_sql(sql: str) -> str:
    if not sql:
        raise ValueError("The model returned an empty SQL response.")

    # Remove Markdown SQL fences
    sql = re.sub(
        r"```(?:sql)?",
        "",
        sql,
        flags=re.IGNORECASE,
    )
    sql = sql.replace("```", "").strip()

    # Find the first SELECT statement.
    # This protects against responses such as:
    # "Here is your SQL: SELECT ..."
    match = re.search(
        r"\bSELECT\b",
        sql,
        flags=re.IGNORECASE,
    )

    if not match:
        raise ValueError(
            "The model did not generate a SELECT query."
        )

    return sql[match.start():].strip()


# ---------------------------------------------------------
# Streamlit configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="RailPulse AI",
    page_icon="🚉",
    layout="wide",
)


# ---------------------------------------------------------
# Database connection
# ---------------------------------------------------------

@st.cache_resource
def get_connection():
    return ensure_database()


conn = get_connection()

try:
    data_anchor = get_latest_data_timestamp(conn)
except Exception as exc:
    print(f"Could not determine latest data timestamp: {exc}")
    data_anchor = None


try:
    db_mode = get_db_mode()
except Exception:
    db_mode = "sqlite"


# ---------------------------------------------------------
# Session state
# ---------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = load_history()


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------

st.title("🚉 RailPulse AI Operations Co-Pilot")

st.caption(
    "👋 Hi, I'm RailPulse — your rail operations co-pilot. "
    "Ask me anything about network performance and delays."
)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    st.header("RailPulse")

    # Database status
    st.markdown("##### 🗄️ Database")

    if db_mode == "azure_sql":
        st.success(
            "Azure SQL · liveboard schema",
            icon="✅",
        )
        st.caption(
            "Tables: stations, vehicles, liveboard_records"
        )

    else:
        st.warning(
            "Local SQLite fallback",
            icon="⚠️",
        )
        st.caption(
            "Running with local demo data."
        )

    # Latest data timestamp
    st.markdown("##### 📅 Latest data loaded")

    if data_anchor:
        st.info(str(data_anchor))

        st.caption(
            'Relative questions such as "today", "now", '
            'and "last 24 hours" are anchored to this timestamp.'
        )

    else:
        st.warning(
            "No data timestamp available",
            icon="⚠️",
        )

        st.caption(
            "Relative date questions may use the current time."
        )

    st.divider()

    # Suggested questions
    st.markdown("##### 💬 Try asking")

    st.markdown(
        """
- Which station had the worst average delay in the last 24 hours?
- Show the most delayed vehicles leaving today.
- Which platforms are causing the most disruption at Brussels-Central?
        """
    )

    st.divider()

    # LLM backend
    st.markdown("##### 🤖 Model backend")

    if os.getenv("GROQ_API_KEY"):
        model = os.getenv(
            "GROQ_MODEL",
            "Groq model",
        )

        st.success(
            "Groq API configured",
            icon="✅",
        )

        st.caption(f"Model: {model}")

    elif os.getenv("OLLAMA_URL"):
        st.info(
            "Ollama mode enabled",
            icon="🖥️",
        )

        st.caption(
            os.getenv(
                "OLLAMA_URL",
                "Local Ollama server",
            )
        )

    else:
        st.warning(
            "No model backend configured",
            icon="⚠️",
        )

        st.caption(
            "Start Ollama or add GROQ_API_KEY to .env"
        )

    st.divider()

    # Clear history
    if st.button(
        "🗑️ Clear conversation",
        use_container_width=True,
    ):
        st.session_state.messages = []
        save_history([])
        st.rerun()


# ---------------------------------------------------------
# Assistant response renderer
# ---------------------------------------------------------

def render_assistant_answer(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])

        st.info(
            "Try another railway operations question. "
            "If the problem continues, check the terminal logs."
        )

        return

    # Generated SQL
    with st.expander(
        "Generated SQL",
        expanded=False,
    ):
        st.code(
            msg.get("sql", ""),
            language="sql",
        )

    # Query result
    with st.expander(
        "Query result",
        expanded=False,
    ):
        rows = msg.get("rows", [])

        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                width="stretch",
            )

        else:
            st.info(
                "No results found for that query."
            )

    # Recommendation
    with st.expander(
        "Recommendation",
        expanded=True,
    ):
        st.write(
            msg.get(
                "recommendation",
                "No recommendation available.",
            )
        )


# ---------------------------------------------------------
# Chat history display
# ---------------------------------------------------------

chat_box = st.container(
    height="stretch",
    border=False,
)


for message in st.session_state.messages:
    with chat_box.chat_message(
        message["role"]
    ):
        if message["role"] == "user":
            st.write(
                message.get(
                    "content",
                    "",
                )
            )

        else:
            render_assistant_answer(message)


# ---------------------------------------------------------
# Chat input
# ---------------------------------------------------------

question = st.chat_input(
    "Ask about network performance, e.g. "
    "'Which station had the highest average delay "
    "in the last 24 hours?'"
)


# ---------------------------------------------------------
# Process user question
# ---------------------------------------------------------

if question:

    # Save and display user message
    user_message = {
        "role": "user",
        "content": question,
    }

    st.session_state.messages.append(
        user_message
    )

    save_history(
        st.session_state.messages
    )

    with chat_box.chat_message("user"):
        st.write(question)

    # Generate assistant response
    with chat_box.chat_message("assistant"):

        with st.spinner(
            "Generating SQL and running the analysis..."
        ):

            try:
                # 1. Get real database schema
                schema = get_schema_summary(conn)

                # 2. Ask LLM to generate SQL
                generated_sql = generate_sql_from_prompt(
                    question,
                    schema,
                    data_anchor=data_anchor,
                )

                # 3. Clean LLM output
                sql = clean_generated_sql(
                    generated_sql
                )

                # Debug log
                print(
                    "\n--- RailPulse Generated SQL ---"
                )
                print(sql)
                print("-------------------------------\n")

                # 4. Validate and execute SQL
                # execute_select() performs:
                # - SELECT-only validation
                # - forbidden keyword blocking
                # - table whitelist validation
                # - Azure / SQLite normalization
                # - data-anchor replacement
                rows = execute_select(
                    conn,
                    sql,
                    data_anchor=data_anchor,
                )

                # 5. Convert result into text for LLM
                df = pd.DataFrame(rows)

                if not df.empty:
                    summary = df.to_string(
                        index=False
                    )
                else:
                    summary = "No data returned"

                # 6. Generate operational recommendation
                recommendation = generate_recommendation(
                    question,
                    summary,
                )

                # 7. Build assistant message
                answer = {
                    "role": "assistant",
                    "sql": sql,
                    "rows": rows,
                    "recommendation": recommendation,
                }

            except Exception as exc:

                # Keep technical details in terminal,
                # not in the stakeholder-facing UI.
                print(
                    f"RailPulse error: {exc}"
                )

                answer = {
                    "role": "assistant",
                    "error": (
                        "The request could not be processed. "
                        "Please try a different railway "
                        "operations question."
                    ),
                }

        # Display response
        render_assistant_answer(answer)

        # Save response to history
        st.session_state.messages.append(
            answer
        )

        save_history(
            st.session_state.messages
        )