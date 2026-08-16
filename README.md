# 🚉 RailPulse AI

**RailPulse AI** is a Generative AI railway operations co-pilot that allows station managers and operational teams to query transit data using natural language.

Instead of writing SQL manually, a user can ask:

> **"Which station had the worst average delay in the last 24 hours?"**

RailPulse converts the question into a safe SQL `SELECT` query, validates and executes it against the railway database, and uses an open-source LLM to turn the result into a short operational recommendation.

---

## 🎯 Project Goal

RailPulse AI was developed as a GenAI extension to an existing railway data pipeline.

The objective is to demonstrate how open-source Generative AI can safely interact with operational transit data while keeping the database protected from destructive or unauthorized queries.

The application demonstrates:

- Natural Language → SQL generation
- Open-source LLM integration
- Azure SQL connectivity
- SQL safety guardrails
- Context-aware operational recommendations
- Human-readable delay metrics
- Interactive Streamlit chat
- Local fallback support for development and demos

---

## ✨ Features

### 💬 Conversational Railway Analytics

Users interact with RailPulse through a Streamlit chat interface using:

- `st.chat_input`
- `st.chat_message`

Example questions:

- Which station had the worst average delay in the last 24 hours?
- Show the most delayed vehicles leaving today.
- Which platforms are causing the most disruption at Brussels-Central?

Each response contains three expandable sections:

1. **SQL query**
2. **Query result**
3. **Recommendation**

---

### 🤖 Open-Source LLM Integration

RailPulse supports two LLM backends:

**Groq**

Uses Groq-hosted open-source/open-weight models through the Groq API.

**Ollama**

Allows models to run locally without requiring a paid third-party inference API.

The application automatically detects the configured backend using environment variables.

---

### 🧠 Text-to-SQL

The LLM receives:

- The user's natural-language question
- The actual database schema
- SQL generation rules
- The latest available dataset timestamp

It then generates a SQL query appropriate for the configured database.

For example:

```text
User:
Which station had the highest average delay in the last 24 hours?
```

The model may generate:

```sql
SELECT TOP 1
    s.station_name,
    AVG(CAST(l.delay_seconds AS FLOAT)) / 60.0 AS avg_delay_minutes
FROM dbo.liveboard_records AS l
JOIN dbo.stations AS s
    ON s.station_id = l.station_id
WHERE l.scheduled_departure >= DATEADD(hour, -24, GETDATE())
GROUP BY s.station_name
ORDER BY AVG(CAST(l.delay_seconds AS FLOAT)) DESC;
```

The generated SQL is **never trusted directly**. It must pass the application safety layer before execution.

---

## ⏱️ Data-Aware Time Handling

The railway pipeline may contain historical or backfilled data rather than records from the actual current date.

For this reason, questions containing expressions such as:

```text
today
now
last 24 hours
this morning
```

are anchored to the **latest `scheduled_departure` timestamp available in the database**.

For example, if the newest railway record is:

```text
2026-07-20 23:58
```

then:

```text
"today"
```

means July 20 in the dataset rather than the computer's current date.

This prevents valid historical datasets from incorrectly returning zero rows.

The current data anchor is displayed in the Streamlit sidebar.

---

## 📊 Delay Metric Conversion

Raw railway delay values are stored in **seconds**.

RailPulse converts them into minutes before presenting operational insights.

Example:

```text
420 seconds → 7 minutes
```

SQL queries can perform this conversion using:

```sql
delay_seconds / 60.0
```

This keeps the final response understandable for non-technical stakeholders.

---

## 🛡️ SQL Safety and Guardrails

### The LLM Never Executes SQL Directly

The most important security rule in RailPulse is:

> **The LLM generates SQL text, but only the application is allowed to execute validated SQL.**

The execution flow is:

```text
User question
      │
      ▼
Open-source LLM
      │
      ▼
Generated SQL
      │
      ▼
Python Safety Guardrails
      │
      ▼
Approved SELECT query
      │
      ▼
Azure SQL / SQLite
```

---

### Defense in Depth

RailPulse applies multiple security layers.

#### Layer 1 — Prompt Restrictions

The LLM is instructed to generate read-only queries.

#### Layer 2 — SQL Validation

The Python backend blocks destructive operations such as:

```text
DELETE
DROP
UPDATE
INSERT
ALTER
EXEC
```

Only safe `SELECT` queries are accepted.

#### Layer 3 — Table Whitelist

Queries are restricted to approved railway tables.

The primary Azure schema uses:

```text
dbo.stations
dbo.vehicles
dbo.liveboard_records
```

Queries attempting to access unauthorized tables are rejected.

#### Layer 4 — Read-Only Database Access

For production usage, the Azure SQL account used by RailPulse should have read-only permissions.

This provides a final database-level security boundary even if an application guardrail fails.

---

## 🏗️ Architecture

```text
┌─────────────────────────┐
│      Streamlit UI       │
│    Natural Language     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Groq / Ollama LLM    │
│       Text → SQL        │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      SQL Guardrails     │
│                         │
│  • SELECT only          │
│  • Keyword blocking     │
│  • Table whitelist      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Azure SQL / SQLite      │
│ Railway Operational DB  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Query Result Data    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    RailPulse LLM        │
│ Result → Recommendation │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Operational Recommendation │
└─────────────────────────┘
```

The database remains the source of truth. The LLM interprets database results rather than inventing operational statistics.

---

## 🗄️ Database Modes

RailPulse supports two database modes.

### Azure SQL

If the following environment variable exists:

```env
SQL_CONNECTION_STRING=...
```

RailPulse connects to Azure SQL.

The Azure database uses three approved operational tables:

```text
dbo.stations
├── station_id
├── station_name
├── standard_name
├── longitude
├── latitude
└── link

dbo.vehicles
├── id
├── short_name
├── vehicle_type
├── vehicle_class_code
├── vehicle_number
└── link

dbo.liveboard_records
├── record_id
├── station_id
├── vehicle_id
├── destination
├── scheduled_departure
├── delay_seconds
├── platform
└── canceled
```

The important joins used by Text-to-SQL are:

```text
liveboard_records.station_id → stations.station_id
liveboard_records.vehicle_id → vehicles.id
```

The schema summary is supplied to the LLM so it can generate queries using the real table and column names instead of inventing database fields.

### SQLite Fallback

If Azure SQL is not configured, RailPulse uses a local SQLite database:

```text
railpulse.db
```

On first use, the application initializes the local database with the same three logical tables and adds a small demo dataset if the `stations` table is empty. It does **not** recreate the database on every application run.

This makes it possible to develop and demonstrate the application without requiring a live Azure connection.

If `SQL_CONNECTION_STRING` is configured but Azure cannot be reached, SQLite fallback is allowed by default. Set the following environment variable to disable that behavior:

```env
ALLOW_SQLITE_FALLBACK=false
```

---

## 📁 Project Structure

```text
railpulse-genai-challenge/
│
├── app.py
├── database.py
├── llm_client.py
├── prompts.py
├── guardrails.py
├── report.py
├── requirements.txt
├── .env.example
├── challenge.md
└── README.md
```

### Main Files

| File               | Purpose                                                     |
| ------------------ | ----------------------------------------------------------- |
| `app.py`           | Streamlit chat UI, sidebar status and conversation history  |
| `database.py`      | Database connections, query execution and data-anchor logic |
| `llm_client.py`    | Groq and Ollama LLM integration                             |
| `prompts.py`       | Text-to-SQL and recommendation prompt engineering           |
| `guardrails.py`    | SQL security rules and table whitelist                      |
| `report.py`        | Reporting utilities                                         |
| `requirements.txt` | Python dependencies                                         |
| `.env.example`     | Environment configuration template                          |
| `challenge.md`     | Original challenge requirements                             |

---

## 💾 Conversation Persistence

Chat history is stored locally in:

```text
.chat_history.json
```

This means the conversation survives:

- Streamlit reruns
- Browser refreshes
- Cache changes

The sidebar contains a:

```text
🗑️ Clear conversation
```

button that intentionally deletes the stored conversation.

---

# 🚀 Running the Project

## 1. Clone or Open the Repository

```bash
git clone <repository-url>
cd railpulse-genai-challenge
```

If the repository is already downloaded:

```bash
cd /path/to/railpulse-genai-challenge
```

---

## 2. Create a Virtual Environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

---

## 3. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Main dependencies include:

- `streamlit`
- `python-dotenv`
- `pandas`
- `numpy`
- `requests`
- `pyodbc`
- `groq`

---

# ⚙️ Environment Configuration

Copy the environment template:

### macOS / Linux

```bash
cp .env.example .env
```

### Windows

```powershell
Copy-Item .env.example .env
```

Then configure the required variables.

---

## Option A — Groq

Add your Groq API key:

```env
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

Do **not** commit your real API key to GitHub.

---

## Option B — Ollama

Install Ollama and download a compatible model.

For example:

```bash
ollama pull llama3.2
ollama run llama3.2
```

Then configure the Ollama endpoint if required:

```env
OLLAMA_URL=http://localhost:11434
```

This allows RailPulse to run its LLM locally.

---

## Option C — Azure SQL

Configure:

```env
SQL_CONNECTION_STRING='Driver={ODBC Driver 18 for SQL Server};Server=tcp:<server-name>.database.windows.net,1433;Database=<database-name>;Uid=<user>;Pwd=<password>;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
```

Azure SQL requires:

- `pyodbc`
- Microsoft ODBC Driver 18 for SQL Server
- Valid Azure SQL credentials
- Azure firewall access for your IP address

---

## Option D — Local Demo

If Azure SQL is not configured, the application uses its SQLite fallback.

The local database is initialized automatically when needed and seeded with a small demo dataset only when it is empty.

This is useful for:

- Local development
- Testing
- Demonstrations
- Working without an Azure connection

---

# ▶️ Run RailPulse

Start the Streamlit application:

```bash
streamlit run app.py
```

Streamlit will normally make the application available at:

```text
http://localhost:8501
```

---

## 💬 Try It

Example questions:

```text
Which station had the highest average delay in the last 24 hours?
```

```text
Show the most delayed vehicles leaving today.
```

```text
Which platforms are causing the most disruption at Brussels-Central?
```

RailPulse will:

```text
Question
   ↓
Generate SQL
   ↓
Validate SQL
   ↓
Execute SELECT
   ↓
Display results
   ↓
Generate operational recommendation
```

The generated SQL and raw query results remain visible in expandable sections so that users can inspect how the answer was produced.

---

# 🖥️ Sidebar

The sidebar provides information about the current application state.

### Database

Shows whether RailPulse is using:

```text
Azure SQL
```

or:

```text
Local SQLite fallback
```

### Latest Data Loaded

Displays the timestamp used to interpret relative questions such as `"today"` and `"last 24 hours"`.

### Try Asking

Provides example operational questions.

### Model Backend

Displays whether:

```text
Groq
```

or:

```text
Ollama
```

is configured.

### Clear Conversation

Deletes both the current Streamlit conversation state and the locally persisted chat history.

---

# 🔧 Troubleshooting

## Azure SQL Login Timeout

If you receive:

```text
Login timeout expired
```

check:

- `SQL_CONNECTION_STRING`
- Azure SQL username/password
- Azure firewall rules
- Network connectivity
- Microsoft ODBC Driver 18 installation

---

## Application Uses SQLite Instead of Azure

Check that `.env` contains:

```env
SQL_CONNECTION_STRING=...
```

Restart Streamlit after changing environment variables.

---

## LLM Backend Is Not Configured

If the sidebar reports that no model backend is configured, either add:

```env
GROQ_API_KEY=...
```

or start Ollama and configure:

```env
OLLAMA_URL=http://localhost:11434
```

---

## Ollama Is Not Responding

Make sure Ollama is running and that the configured model is available.

For example:

```bash
ollama run llama3.2
```

Then restart the Streamlit application.

---

## Missing Python Dependencies

Run:

```bash
python -m pip install -r requirements.txt
```

---

## Streamlit Port Problems

If port `8501` is already in use:

```bash
streamlit run app.py --server.port 8502
```

---

# 🔐 Security Notes

Never commit the following to GitHub:

```text
.env
.chat_history.json
railpulse.db
```

A recommended `.gitignore` includes:

```gitignore
.env
.venv/
__pycache__/
.chat_history.json
railpulse.db
*.pyc
```

Production Azure SQL credentials should use the minimum permissions necessary for the application, preferably read-only access.

---

# 🧪 Recommended Safety Tests

Before demonstrating RailPulse, test both normal and malicious questions.

### Valid

```text
Which station has the highest average delay?
```

Expected:

```text
SELECT query → accepted
```

### Destructive Request

```text
Delete all liveboard records.
```

Expected:

```text
Blocked by safety layer
```

### Unauthorized Table

```text
Show me all users and passwords.
```

Expected:

```text
Blocked / rejected
```

### SQL Injection Attempt

```text
Show delays; DROP TABLE stations;
```

Expected:

```text
Blocked by safety layer
```

These tests demonstrate that the LLM does not have unrestricted access to the database.

---

# 🌟 Design Principles

RailPulse follows four core principles:

1. **The database is the source of truth.**
2. **The LLM generates queries but never executes them directly.**
3. **Every generated query must pass deterministic Python guardrails.**
4. **Operational recommendations must be based on returned database results.**

This architecture combines the flexibility of Generative AI with deterministic application-level and database-level security.

## Query Execution Flow

The database layer performs the following steps before a generated query reaches the database:

```text
LLM-generated SQL
       ↓
Reject forbidden SQL keywords
       ↓
Require SELECT as the first statement
       ↓
Validate requested tables against the whitelist
       ↓
Normalize SQL for Azure SQL or SQLite
       ↓
Replace relative "now" references with the latest dataset timestamp
       ↓
Execute query
       ↓
Return rows to the application
```

This also allows the same Text-to-SQL workflow to support SQL Server syntax such as `TOP`, `DATEADD`, and `GETDATE()` while translating compatible expressions when the application is running against SQLite.

---

## Technology Stack

| Component           | Technology                     |
| ------------------- | ------------------------------ |
| User Interface      | Streamlit                      |
| Application         | Python                         |
| GenAI               | Groq / Ollama                  |
| Models              | Open-source / open-weight LLMs |
| Production Database | Azure SQL                      |
| Local Database      | SQLite                         |
| SQL Connector       | pyodbc / sqlite3               |
| Data Display        | Pandas                         |

---

## Challenge Requirements Covered

- ✅ Open-source/open-weight LLM integration
- ✅ Natural-language Text-to-SQL
- ✅ Azure SQL integration
- ✅ Local development fallback
- ✅ SQL safety guardrails
- ✅ Table whitelist
- ✅ Delay conversion from seconds to minutes
- ✅ Context-aware RailPulse consultant recommendations
- ✅ Interactive Streamlit chat interface
- ✅ Data-aware relative date handling
- ✅ Persistent conversation history
- ✅ Transparent SQL and query-result display
- ✅ Defense-in-depth database security

---

## Repository

```text
railpulse-genai-challenge
```

Built as the **RailPulse AI: Intelligent Transit Insights** GenAI challenge.
