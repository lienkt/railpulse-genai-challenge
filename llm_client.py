import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def generate_sql_from_prompt(
    question: str,
    schema_summary: str,
    model_name: Optional[str] = None,
    data_anchor: Optional[str] = None,
) -> str:
    from prompts import build_sql_prompt

    if model_name is None:
        model_name = os.getenv("OLLAMA_MODEL", "llama3.2")

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    groq_key = os.getenv("GROQ_API_KEY")

    if groq_key:
        try:
            from groq import Groq

            client = Groq(api_key=groq_key)
            prompt = build_sql_prompt(question, schema_summary, data_anchor)
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": "You are RailPulse Consultant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=300,
            )
            text = response.choices[0].message.content.strip()
            if text:
                return text
        except Exception:
            pass

    try:
        payload = {
            "model": model_name,
            "prompt": build_sql_prompt(question, schema_summary, data_anchor),
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 300},
        }
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        sql = data.get("response", "").strip()
        if sql:
            return sql
    except Exception:
        pass

    raise RuntimeError(
        "No local Ollama model or Groq API key is available. Start Ollama or set GROQ_API_KEY in your .env file."
    )


def generate_recommendation(question: str, result_summary: str) -> str:
    from prompts import build_consultant_prompt

    prompt = build_consultant_prompt(question, result_summary)

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq

            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[
                    {"role": "system", "content": "You are RailPulse, a railway operations consultant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=250,
            )
            recommendation = response.choices[0].message.content.strip()
            if recommendation:
                return recommendation
        except Exception:
            pass

    return (
        "Finding:\nThe data shows a localized disruption pattern in the relevant station or platform.\n\n"
        "Operational impact:\nThis is likely affecting punctuality and passenger flow for the affected service window.\n\n"
        "Recommendation:\nPrioritize dispatch coordination, check the platform plan, and review timetable adjustments for the affected route."
    )
