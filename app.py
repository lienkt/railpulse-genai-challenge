import os
import re

import pandas as pd
import streamlit as st

from database import ensure_database, execute_select, get_schema_summary, get_latest_data_timestamp
from llm_client import generate_sql_from_prompt, generate_recommendation


st.set_page_config(page_title="RailPulse AI", page_icon="🚉", layout="wide")


@st.cache_resource
def get_connection():
    return ensure_database()


conn = get_connection()
data_anchor = get_latest_data_timestamp(conn)


st.title("🚉 RailPulse AI Operations Co-Pilot")
st.caption("Conversational rail analytics with SQL safety guardrails and local open-source AI.")

if data_anchor:
    st.info(
        f"📅 Data is loaded up to **{data_anchor}**. Since the dataset backfills one day at a time, "
        "\"today\"/\"now\" in every question refers to this latest available day, not the real current date."
    )
else:
    st.warning("No data has been loaded yet, so relative date questions will use the real current time.")

with st.sidebar:
    st.header("Rail Pulse")
    st.markdown(
        """
        Ask questions like:
        - Which station had the worst average delay in the last 24 hours?
        - Show the most delayed vehicles leaving today.
        - Which platforms are causing the most disruption at Brussels-Central?
        """
    )

    if os.getenv("GROQ_API_KEY"):
        st.success("Groq API configured")
    elif os.getenv("OLLAMA_URL"):
        st.info("Ollama mode enabled")
    else:
        st.warning("No model backend configured. Start Ollama or add GROQ_API_KEY in .env")


question = st.text_input("Ask about network performance:", value="Which station had the highest average delay in the last 24 hours?")

if st.button("Analyze"):
    with st.spinner("Generating SQL and running the analysis..."):
        try:
            schema = get_schema_summary(conn)
            sql = generate_sql_from_prompt(question, schema, data_anchor=data_anchor)
            sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
            st.code(sql, language="sql")

            rows = execute_select(conn, sql, data_anchor=data_anchor)
            df = pd.DataFrame(rows)

            if df.empty:
                st.info("No results found for that query.")
            else:
                st.dataframe(df, use_container_width=True)

            summary = df.to_string(index=False) if not df.empty else "No data returned"
            recommendation = generate_recommendation(question, summary)
            st.markdown("### Recommendation")
            st.write(recommendation)

        except Exception as exc:
            st.error(f"The request could not be processed: {exc}")
            st.info("Try starting Ollama with: `ollama run llama3.2` or add a valid GROQ API key.")


st.markdown("---")
st.subheader("Database snapshot")
if os.getenv("SQL_CONNECTION_STRING"):
    st.info("Connected to Azure SQL using the liveboard schema.")
    st.caption("Using live tables: stations, vehicles, and liveboard_records.")
else:
    st.warning("No Azure SQL connection string is configured. The app is in local SQLite fallback mode only.")
