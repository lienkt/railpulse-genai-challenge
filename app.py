import json
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from database import ensure_database, execute_select, get_schema_summary, get_latest_data_timestamp
from llm_client import generate_sql_from_prompt, generate_recommendation

HISTORY_PATH = Path(__file__).resolve().parent / ".chat_history.json"


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except Exception:
        return []


def save_history(messages: list) -> None:
    try:
        HISTORY_PATH.write_text(json.dumps(messages, default=str))
    except Exception:
        pass


st.set_page_config(page_title="RailPulse AI", page_icon="🚉", layout="wide")


@st.cache_resource
def get_connection():
    return ensure_database()


conn = get_connection()
try:
    data_anchor = get_latest_data_timestamp(conn)
except Exception:
    data_anchor = None


st.title("RailPulse AI Operations Co-Pilot")
st.caption("👋 Hi, I'm RailPulse — your rail operations co-pilot. Ask me anything about network performance and delays.")

with st.sidebar:
    st.header("Rail Pulse")

    st.markdown("##### 🗄️ Database")
    if os.getenv("SQL_CONNECTION_STRING"):
        st.success("Azure SQL · liveboard schema", icon="✅")
        st.caption("Tables: stations, vehicles, liveboard_records")
    else:
        st.warning("Local SQLite fallback", icon="⚠️")
        st.caption("No Azure SQL connection string configured.")

    st.markdown("##### 📅 Latest data loaded")
    if data_anchor:
        st.info(data_anchor)
        st.caption("Data backfills one day at a time — \"today\"/\"now\" always means this date.")
    else:
        st.warning("No data yet", icon="⚠️")
        st.caption("Relative date questions will use the real current time.")

    st.divider()
    st.markdown("##### 💬 Try asking")
    st.markdown(
        """
        - Which station had the worst average delay in the last 24 hours?
        - Show the most delayed vehicles leaving today.
        - Which platforms are causing the most disruption at Brussels-Central?
        """
    )

    st.divider()
    st.markdown("##### 🤖 Model backend")
    if os.getenv("GROQ_API_KEY"):
        st.success("Groq API configured", icon="✅")
    elif os.getenv("OLLAMA_URL"):
        st.info("Ollama mode enabled", icon="🖥️")
    else:
        st.warning("No model backend configured. Start Ollama or add GROQ_API_KEY in .env", icon="⚠️")

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        save_history([])
        st.rerun()


if "messages" not in st.session_state:
    st.session_state.messages = load_history()


def render_assistant_answer(msg: dict) -> None:
    if msg.get("error"):
        st.error(msg["error"])
        st.info("Try starting Ollama with: `ollama run llama3.2` or add a valid GROQ API key.")
        return

    with st.expander("SQL query", expanded=False):
        st.code(msg["sql"], language="sql")

    with st.expander("Query result", expanded=False):
        if msg["rows"]:
            st.dataframe(pd.DataFrame(msg["rows"]), width="stretch")
        else:
            st.info("No results found for that query.")

    with st.expander("Recommendation", expanded=True):
        st.write(msg["recommendation"])


chat_box = st.container(height="stretch", border=False)

for message in st.session_state.messages:
    with chat_box.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["content"])
        else:
            render_assistant_answer(message)

question = st.chat_input("Ask about network performance, e.g. 'Which station had the highest average delay in the last 24 hours?'")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    save_history(st.session_state.messages)
    with chat_box.chat_message("user"):
        st.write(question)

    with chat_box.chat_message("assistant"):
        with st.spinner("Generating SQL and running the analysis..."):
            try:
                schema = get_schema_summary(conn)
                sql = generate_sql_from_prompt(question, schema, data_anchor=data_anchor)
                sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()

                rows = execute_select(conn, sql, data_anchor=data_anchor)
                df = pd.DataFrame(rows)

                summary = df.to_string(index=False) if not df.empty else "No data returned"
                recommendation = generate_recommendation(question, summary)

                answer = {"role": "assistant", "sql": sql, "rows": rows, "recommendation": recommendation}
            except Exception as exc:
                answer = {"role": "assistant", "error": f"The request could not be processed: {exc}"}

            render_assistant_answer(answer)
            st.session_state.messages.append(answer)
            save_history(st.session_state.messages)
