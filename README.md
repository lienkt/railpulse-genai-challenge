# RailPulse AI

RailPulse AI is a rail operations co-pilot that turns natural-language questions into safe SQL queries and returns operational recommendations.

This project is designed to work in two modes:

- Azure SQL first: if `SQL_CONNECTION_STRING` is configured, the app uses Azure SQL directly.
- SQLite fallback: if Azure is not available or not configured, the app recreates a local `railpulse.db` file and runs in local demo mode.

This keeps the app usable in development, testing, and local demos while still supporting your real Azure database environment.

## What this app does

- Accepts user questions in plain English
- Converts them into safe SQL `SELECT` statements
- Runs the query against Azure SQL or SQLite
- Returns a concise operational recommendation
- Blocks destructive SQL commands such as `DELETE`, `DROP`, `UPDATE`, `INSERT`, and `ALTER`

## Project structure

- [app.py](app.py) — Streamlit UI
- [database.py](database.py) — database connection logic and SQL safety guards
- [llm_client.py](llm_client.py) — Groq / Ollama model integration
- [prompts.py](prompts.py) — SQL prompt templates and schema examples
- [requirements.txt](requirements.txt) — Python dependencies
- [.env.example](.env.example) — environment template
- [challenge.md](challenge.md) — original challenge brief

railpulse-genai-challenge/
│
├── app.py
├── database.py
├── llm.py
├── prompts.py
├── guardrails.py
├── report.py
├── config.py
│
├── requirements.txt
├── .env.example
├── README.md
│
└── tests/
└── test_guardrails.py

## Step-by-step run guide

### 1) Open the project folder

```bash
cd /path/to/railpulse-genai-challenge
```

### 2) Create and activate a virtual environment

On macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt --index-url https://pypi.org/simple
```

If you are in a restricted environment, use the same command exactly as above. The project dependencies include:

- streamlit
- python-dotenv
- pandas
- numpy
- requests
- pyodbc
- groq

### 4) Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Then edit `.env` and set the values you need.

#### Option A: Use Groq API

```env
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

#### Option B: Use Azure SQL directly

```env
SQL_CONNECTION_STRING='Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server-name>.database.windows.net,1433;Database=<database-name>;Uid=<user>;Pwd=<password>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
```

For Azure SQL, make sure the machine has the ODBC driver installed, especially:

- `ODBC Driver 18 for SQL Server`
- `pyodbc` installed in the virtual environment

#### Option C: Local fallback mode

Leave Azure and Groq empty if you only want to test locally. The app will automatically create a local SQLite fallback file named `railpulse.db`.

### 5) Validate the app environment

Run this check to confirm the app chooses the correct DB mode:

```bash
python - <<'PY'
from database import get_db_mode, is_azure_sql_enabled
print('db_mode:', get_db_mode())
print('azure_sql_enabled:', is_azure_sql_enabled())
PY
```

Expected behavior:

- With Azure connection configured: `db_mode: azure_sql`
- Without Azure config: `db_mode: sqlite`

### 6) Run the app

Start Streamlit:

```bash
streamlit run app.py --server.headless true --server.port 8501
```

Then open the browser at:

```text
http://localhost:8501
```

### 7) Use the app

Try questions like:

- Which station had the highest average delay in the last 24 hours?
- Show the most delayed vehicles leaving today.
- Which platform at Brussels-Central had the worst average delay?

## Azure-first behavior

The app prioritizes Azure SQL if `SQL_CONNECTION_STRING` is present.

If Azure is not reachable, the app falls back to a local SQLite database and recreates `railpulse.db` automatically so it does not crash during local testing.

## Troubleshooting

### Streamlit fails to bind to a port

This usually happens in a sandboxed or restricted environment:

```bash
PermissionError: [Errno 1] Operation not permitted
```

This is a runtime environment restriction, not a SQL logic error. Run Streamlit from a normal local terminal outside the sandbox if needed.

### Azure SQL login times out

If you see:

```text
Login timeout expired
```

check the following:

- SQL connection string is correct
- firewall rules allow your IP
- SQL login credentials are valid
- `ODBC Driver 18 for SQL Server` is installed

### App still tries to use local DB

Check your `.env`:

```bash
cat .env
```

Make sure `SQL_CONNECTION_STRING` is filled in if you want Azure mode.

### Missing dependencies

If Python reports a missing package:

```bash
python -m pip install -r requirements.txt --index-url https://pypi.org/simple
```

## Safety notes

- Only `SELECT` queries are allowed.
- Destructive commands are blocked.
- The app is built for operational analysis, not arbitrary database modification.

### 6. Guardrail: do not trust LLM-generated SQL

> The LLM should never have direct permission to execute SQL.

This is the most important rule in the project:

- The model may generate SQL text.
- The backend must validate the SQL first.
- The backend must reject destructive or unsafe statements.
- Only the application layer runs the final validated query.

In other words, the LLM is a SQL generator, not a database executor.

This rule is enforced in [database.py](database.py) through SQL validation and in [guardrails.py](guardrails.py) as the project-level policy.

## Defense in depth

RailPulse applies multiple layers of protection so that even if one layer fails, the database remains read-only.

Layer 1: Prompt restrictions

- The model is instructed to generate only `SELECT` statements.

Layer 2: Python regex and SQL validation

- The backend rejects forbidden SQL keywords like `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `EXEC`.

Layer 3: Table whitelist

- Only approved tables are allowed.
- The app blocks any query touching unauthorized tables.

Layer 4: Read-only Azure SQL credentials

- The Azure SQL account used by the app should have only read permissions.
- Even if a guardrail is bypassed, the database still refuses destructive actions.

```text
┌───────────────────────┐
│      Streamlit UI     │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Ollama / Llama 3.1 8B │
│      Text → SQL       │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    SQL Guardrails     │
│ SELECT-only           │
│ Keyword blacklist     │
│ Table whitelist       │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Azure SQL Database  │
│   Read-only account   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Llama 3.1 Consultant  │
│ Results → Insight     │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│ Operational Advice    │
└───────────────────────┘
```

This is the safest pattern for a GenAI-to-SQL product: the LLM can help generate queries, but the database itself remains the final enforcement point.

## Example env file

```env
# Use either Groq or Azure SQL
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile

SQL_CONNECTION_STRING=
```

This project is ready to run in either local demo mode or Azure-connected production mode.
