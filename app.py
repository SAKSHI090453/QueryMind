import streamlit as st
import psycopg2
import pandas as pd
import requests
import re
import sqlite3
import time
import json
import io
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="QueryMind — Ask Your Data in Plain English",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Persistence paths ─────────────────────────────────────────────────────────
_BASE = Path(__file__).parent
HISTORY_FILE = _BASE / "query_history.json"
SAVED_FILE   = _BASE / "saved_queries.json"

def _load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def _save_json(path: Path, data):
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

st.markdown("""
<style>
    /* ── Global ── */
    @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Fredoka:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Nunito', sans-serif; background: #f0f9ff; }

    /* ── Hero banner ── */
    .hero-banner {
        background: linear-gradient(135deg, #bae6fd 0%, #e0f2fe 100%);
        color: #0c4a6e;
        padding: 1.8rem 2rem 1.4rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        box-shadow: 0 6px 28px rgba(14,165,233,0.25);
    }
    .hero-banner h1 { margin: 0; font-size: 2.5rem; font-weight: 700; letter-spacing: -0.5px; font-family: 'Fredoka', sans-serif; }
    .hero-banner p  { margin: 0.3rem 0 0; font-size: 0.95rem; opacity: 0.9; }

    /* ── Metric cards ── */
    .metric-row { display: flex; gap: 14px; margin-bottom: 1.2rem; flex-wrap: wrap; }
    .metric-card {
        flex: 1; min-width: 130px;
        background: white;
        border: 1.5px solid #bae6fd;
        border-radius: 14px;
        padding: 0.9rem 1.1rem;
        text-align: center;
        box-shadow: 0 2px 10px rgba(14,165,233,0.1);
    }
    .metric-card .val { font-size: 1.7rem; font-weight: 800; color: #0284c7; line-height: 1.2; }
    .metric-card .lbl { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 3px; font-weight: 600; }

    /* ── Status badges ── */
    .badge {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 5px 14px; border-radius: 20px;
        font-size: 0.8rem; font-weight: 700;
    }
    .badge-green  { background: #e0f2fe; color: #075985; border: 1.5px solid #7dd3fc; }
    .badge-blue   { background: #ede9fe; color: #5b21b6; border: 1.5px solid #c4b5fd; }
    .badge-teal   { background: #ccfbf1; color: #134e4a; border: 1.5px solid #5eead4; }
    .badge-orange { background: #fff7ed; color: #c2410c; border: 1.5px solid #fdba74; }

    /* ── Logic box ── */
    .logic-box {
        background: linear-gradient(135deg, #e0f2fe, #fff7ed);
        border-left: 4px solid #0ea5e9;
        padding: 0.9rem 1.2rem;
        border-radius: 0 12px 12px 0;
        margin-bottom: 0.5rem;
        font-size: 0.95rem;
        line-height: 1.65;
        color: #0c1a3a;
    }

    /* ── Section labels ── */
    .section-label {
        font-weight: 800;
        font-size: 0.76rem;
        color: #0284c7;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.25rem;
    }

    /* ── Result table ── */
    .stDataFrame { border-radius: 12px; overflow: hidden; border: 1px solid #bae6fd; }

    /* ── Step badge ── */
    .step-badge {
        display: inline-block;
        background: linear-gradient(90deg, #0ea5e9, #f97316);
        color: white;
        padding: 3px 13px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-bottom: 5px;
    }

    /* ── Agentic info box ── */
    .agent-box {
        background: linear-gradient(135deg, #fff7ed, #e0f2fe);
        border-left: 4px solid #f97316;
        padding: 0.75rem 1rem;
        border-radius: 0 12px 12px 0;
        font-size: 0.88rem;
        color: #7c2d12;
        margin: 0.5rem 0;
        font-weight: 600;
    }

    /* ── Saved query pill ── */
    .saved-pill {
        background: #e0f2fe;
        border: 1px solid #7dd3fc;
        border-radius: 8px;
        padding: 0.45rem 0.75rem;
        font-size: 0.83rem;
        color: #075985;
        margin-bottom: 4px;
        cursor: pointer;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] > div { background: #f0f9ff; }
    section[data-testid="stSidebar"] * { color: #0c1a3a !important; }
    section[data-testid="stSidebar"] .stRadio label { font-size: 0.9rem; color: #0c1a3a !important; }
    section[data-testid="stSidebar"] .stTextInput input,
    section[data-testid="stSidebar"] .stNumberInput input { background: #ffffff; color: #0c1a3a !important; border: 1.5px solid #7dd3fc; border-radius: 8px; }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span { color: #0c1a3a !important; }
    section[data-testid="stSidebar"] .stSuccess p { color: #065f46 !important; }
    section[data-testid="stSidebar"] .stError p  { color: #7f1d1d !important; }
    section[data-testid="stSidebar"] .stCaption  { color: #64748b !important; }

    /* ── File uploader ── */
    [data-testid="stFileUploader"] > label { color: #0c1a3a !important; font-weight: 700; }
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"],
    [data-testid="stFileUploadDropzone"] {
        background: #e0f2fe !important;
        border: 2px dashed #0284c7 !important;
        border-radius: 10px !important;
    }
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] *,
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] p,
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] span,
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] small,
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] div,
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] button { color: #0c1a3a !important; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────────────
if "conn" not in st.session_state:
    st.session_state.conn = None
if "schema_text" not in st.session_state:
    st.session_state.schema_text = ""
if "history" not in st.session_state:
    st.session_state.history = _load_json(HISTORY_FILE, [])
if "saved_queries" not in st.session_state:
    st.session_state.saved_queries = _load_json(SAVED_FILE, [])
if "prefill_question" not in st.session_state:
    st.session_state.prefill_question = ""
if "excel_df" not in st.session_state:
    st.session_state.excel_df = None
if "excel_table_name" not in st.session_state:
    st.session_state.excel_table_name = "data"
if "excel_sheets" not in st.session_state:
    st.session_state.excel_sheets = {}
if "db_schema_df" not in st.session_state:
    st.session_state.db_schema_df = None
if "selected_tables" not in st.session_state:
    st.session_state.selected_tables = []
if "data_source" not in st.session_state:
    st.session_state.data_source = None
if "error_log" not in st.session_state:
    st.session_state.error_log = []

# ─── Helpers ──────────────────────────────────────────────────────────────────

def dtype_to_sql(dtype) -> str:
    dtype_str = str(dtype)
    if "int" in dtype_str:
        return "INTEGER"
    if "float" in dtype_str:
        return "REAL"
    if "datetime" in dtype_str:
        return "TIMESTAMP"
    if "bool" in dtype_str:
        return "BOOLEAN"
    return "TEXT"


def build_schema_from_df(df: pd.DataFrame, table_name: str) -> str:
    cols = ", ".join(f"{col} ({dtype_to_sql(dtype)})" for col, dtype in zip(df.columns, df.dtypes))
    
    # Add sample data hints (first 2 rows, limited to 50 chars per value)
    sample_hints = []
    for _, row in df.head(2).iterrows():
        sample_values = []
        for col in df.columns:
            val = row[col]
            if pd.isna(val):
                sample_values.append("NULL")
            elif isinstance(val, (int, float)):
                sample_values.append(str(val)[:20])
            else:
                sample_values.append(str(val)[:50])
        sample_hints.append(f"Sample: {', '.join(sample_values)}")
    
    sample_section = "\n".join(sample_hints) if sample_hints else ""
    schema = f"Table: {table_name}\nColumns: {cols}\n{sample_section}"
    
    # Truncate if too long (keep under 2000 chars per table)
    if len(schema) > 2000:
        schema = schema[:2000] + "\n... (truncated)"
    
    return schema


def build_prompt(schema: str, question: str, data_source: str = "postgres", error_context: str = "", verbose_reasoning: bool = False) -> str:
    if data_source == "excel":
        db_note = (
            "SQLite (in-memory). "
            "Do NOT use information_schema, pg_catalog, or PRAGMA — they are unavailable. "
            "The full schema is already provided below; use only the table and column names listed there. "
            "IMPORTANT: For ALL string/text comparisons use LOWER() on both sides, e.g. LOWER(column) = LOWER('value'), to ensure case-insensitive matching."
        )
    else:
        db_note = "PostgreSQL-compatible SQL syntax."
    
    if verbose_reasoning:
        reasoning_instruction = """STEP-BY-STEP REASONING:
Before generating SQL, think through the problem step-by-step:
1. Understand what the user is asking for
2. Identify which tables contain the relevant data
3. Identify which columns to select and any conditions needed
4. Plan any joins or aggregations required
5. Then write the SQL query

Show this reasoning in the LOGIC section. Ensure the logic accurately reflects the SQL query you generate."""
    else:
        reasoning_instruction = ""
    
    return f"""You are an expert SQL assistant. Convert natural language questions to SQL queries.

DATABASE TYPE: {db_note}

CORE PRINCIPLES:
1. Use the SIMPLEST possible SQL that answers the question
2. Prefer basic SELECT, WHERE, JOIN, GROUP BY over complex CTEs
3. Only use window functions (RANK, OVER) when explicitly asked for ranking
4. Column names with spaces MUST be wrapped in double quotes
5. Only generate SELECT queries - never INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE

SIMPLE QUERY EXAMPLES:
Q: "Show all customers"
SQL: SELECT * FROM customers

Q: "Get orders where amount > 1000"
SQL: SELECT * FROM orders WHERE amount > 1000

Q: "Count total revenue by category"
SQL: SELECT category, SUM(revenue) as total FROM sales GROUP BY category

Q: "Join customers with their orders"
SQL: SELECT c.name, o.order_id FROM customers c JOIN orders o ON c.id = o.customer_id

RANKING (only when asked):
Q: "Rank products by revenue"
SQL: SELECT name, revenue, RANK() OVER (ORDER BY revenue DESC) AS rank FROM products

Q: "Top 5 by revenue"
SQL: SELECT name, revenue FROM products ORDER BY revenue DESC LIMIT 5

Q: "Rank by score AND revenue together (multi-metric)"
SQL: WITH r AS (SELECT name, score, revenue, RANK() OVER (ORDER BY score DESC) AS score_rank, RANK() OVER (ORDER BY revenue DESC) AS rev_rank FROM products), combined AS (SELECT *, (score_rank + rev_rank) / 2.0 AS combined_rank FROM r ORDER BY combined_rank) SELECT name, score, revenue, score_rank, rev_rank, RANK() OVER (ORDER BY combined_rank ASC) AS rank FROM combined LIMIT 5

{reasoning_instruction}

OUTPUT FORMAT:
LOGIC: <clear explanation of what the query does>
SQL: <the SELECT query, no trailing semicolon>

DATABASE SCHEMA:
{schema}

USER QUESTION: {question}

{error_context}"""


def call_ollama(prompt: str, model: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/api/generate"
    response = requests.post(
        url,
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2048
            }
        },
        timeout=180
    )
    response.raise_for_status()
    return response.json()["response"]


def call_gemini(prompt: str, model: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 4096,
            "temperature": 0.0,
            "topP": 0.8,
            "topK": 40
        }
    }
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 429:
            raise RuntimeError("⏳ Gemini rate limit hit (free tier: 15 req/min). Wait a few seconds and click Run again.")
        if response.status_code in (400, 403, 404):
            raise RuntimeError(f"Gemini error: {response.json().get('error', {}).get('message', response.text)}")
        if response.status_code in (500, 503):
            if attempt < max_attempts:
                time.sleep(3 ** attempt)
                continue
            raise RuntimeError(f"⚠️ Gemini service unavailable after {max_attempts} retries. Google's API is temporarily down — try again in a moment.")
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_huggingface(prompt: str, model: str, token: str) -> str:
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 1024,
            "return_full_text": False,
            "temperature": 0.1,
            "top_p": 0.9
        }
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code == 503:
        raise RuntimeError("Model is loading on HuggingFace servers — wait ~20s and try again.")
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list) and data:
        return data[0].get("generated_text", "")
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"HuggingFace error: {data['error']}")
    return str(data)


def parse_llm_response(text: str):
    # Strip markdown code fences (```sql ... ``` or ``` ... ```)
    clean = re.sub(r"```(?:sql)?", "", text, flags=re.IGNORECASE)
    clean = clean.replace("```", "")

    # Extract LOGIC section
    logic_match = re.search(r"LOGIC:\s*(.+?)(?=SQL:|\Z)", clean, re.DOTALL | re.IGNORECASE)
    logic = logic_match.group(1).strip() if logic_match else ""

    # Extract SQL: grab everything after the SQL: label, then find first SELECT or WITH
    sql = ""
    sql_label = re.search(r"SQL:\s*([\s\S]*)", clean, re.IGNORECASE)
    if sql_label:
        after_label = sql_label.group(1).strip()
        sql_start = re.search(r"\b(SELECT|WITH)\b", after_label, re.IGNORECASE)
        if sql_start:
            sql = after_label[sql_start.start():].strip().rstrip(";")

    # Fallback 1: scan the whole response for any SELECT/WITH if SQL: label was absent
    if not sql:
        sql_start = re.search(r"\b(SELECT|WITH)\b[\s\S]+", clean, re.IGNORECASE)
        sql = sql_start.group(0).strip().rstrip(";") if sql_start else ""

    # Fallback 2: if SQL has multiple statements, take only the first one
    if sql:
        # Split on semicolon and take first statement
        statements = [s.strip() for s in sql.split(";") if s.strip()]
        if statements:
            sql = statements[0]

    # Validation: ensure SQL starts with SELECT or WITH
    if sql and not re.match(r"^\s*(SELECT|WITH)", sql, re.IGNORECASE):
        sql = ""

    return logic, sql


def run_query_greenplum(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, conn)


def run_query_excel(sheets: dict, sql: str) -> pd.DataFrame:
    mem_conn = sqlite3.connect(":memory:")
    for tname, df in sheets.items():
        df.to_sql(tname, mem_conn, if_exists="replace", index=False)
    result = pd.read_sql(sql, mem_conn)
    mem_conn.close()
    return result

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("� Data Source")
    mode = st.radio(
        "Choose your data source",
        ["🗄️ PostgreSQL / Greenplum", "📊 Excel / CSV File"],
        index=1
    )

    st.divider()

    # ── Greenplum mode ──
    if mode == "🗄️ PostgreSQL / Greenplum":
        st.info("🚧 **PostgreSQL / Greenplum support is coming soon!**\n\nWe're actively working on this feature. For now, please use **Excel / CSV File** to get started.", icon="🔧")
        st.stop()
        st.subheader("🔌 Connection Settings")
        _s = st.secrets
        db_host = st.text_input("Host", value=_s.get("db_host", "localhost"))
        db_port = st.number_input("Port", value=int(_s.get("db_port", 5432)), step=1)
        db_name = st.text_input("Database Name", value=_s.get("db_name", ""))
        db_user = st.text_input("Username", value=_s.get("db_user", ""))
        db_pass = st.text_input("Password", value=_s.get("db_password", ""), type="password")
        db_schema = st.text_input(
            "DB Schema(s)",
            value=_s.get("db_schema", "public"),
            help="Comma-separated for multiple schemas, e.g. public, sales, crm"
        )

        if st.button("Connect & Load Schema", type="primary", width='stretch'):
            try:
                with st.spinner("Connecting..."):
                    conn = psycopg2.connect(
                        host=db_host, port=int(db_port),
                        dbname=db_name, user=db_user, password=db_pass,
                        connect_timeout=10
                    )
                    st.session_state.conn = conn
                    st.session_state.excel_df = None
                    st.session_state.data_source = "postgres"

                    schema_list = [s.strip() for s in db_schema.split(",") if s.strip()]
                    schema_df = pd.read_sql(
                        """
                        SELECT table_schema, table_name, column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = ANY(%s)
                        ORDER BY table_schema, table_name, ordinal_position
                        """,
                        conn, params=(schema_list,)
                    )

                    if schema_df.empty:
                        st.warning(f"No tables found in schema(s): {db_schema}")
                        st.session_state.schema_text = f"(No tables found in schema(s): {db_schema})"
                        st.session_state.db_schema_df = None
                        st.session_state.selected_tables = []
                    else:
                        schema_df["qualified_name"] = schema_df["table_schema"] + "." + schema_df["table_name"]
                        st.session_state.db_schema_df = schema_df
                        all_tables = sorted(schema_df["qualified_name"].unique().tolist())
                        st.session_state.selected_tables = all_tables

                        def _build_pg_schema(df, tables):
                            lines = []
                            for qname in tables:
                                grp = df[df["qualified_name"] == qname]
                                cols = ", ".join(
                                    f"{r['column_name']} ({r['data_type']})"
                                    for _, r in grp.iterrows()
                                )
                                schema = f"Table: {qname}\nColumns: {cols}"
                                # Truncate if too long
                                if len(schema) > 2000:
                                    schema = schema[:2000] + "\n... (truncated)"
                                lines.append(schema)
                            return "\n\n".join(lines)

                        st.session_state.schema_text = _build_pg_schema(schema_df, all_tables)

                st.success(f"✅ Connected — {len(st.session_state.selected_tables)} table(s) across {len(schema_list)} schema(s) found!")
            except Exception as e:
                st.error(f"Connection failed: {e}")

        if st.session_state.data_source == "postgres" and st.session_state.conn:
            st.markdown("**Status:** 🟢 Connected")

            if st.session_state.db_schema_df is not None:
                all_tables = sorted(st.session_state.db_schema_df["qualified_name"].unique().tolist())
                chosen = st.multiselect(
                    "📋 Tables to include in prompt",
                    options=all_tables,
                    default=st.session_state.selected_tables,
                    help="Shown as schema.table — select only tables relevant to your question."
                )
                if chosen != st.session_state.selected_tables:
                    st.session_state.selected_tables = chosen
                    st.session_state.schema_text = _build_pg_schema(st.session_state.db_schema_df, chosen)

            with st.expander("📐 View Active Schema"):
                st.text(st.session_state.schema_text)

    # ── Excel / CSV mode ──
    else:
        st.markdown("""
<div style="background:#e0f2fe; border-radius:12px; padding:1rem 1.1rem; border:1px solid #7dd3fc; margin-bottom:0.8rem;">
  <div style="font-size:1rem; font-weight:700; color:#0c1a3a; margin-bottom:0.3rem;">� Upload Your Data File</div>
  <div style="font-size:0.85rem; color:#0c1a3a; line-height:1.5;">
    Supports <strong>Excel (.xlsx, .xls)</strong> and <strong>CSV</strong> files.<br>
    Multi-sheet Excel files are fully supported — each sheet becomes a queryable table.
  </div>
</div>
""", unsafe_allow_html=True)
        with st.container(border=True):
            uploaded_files = st.file_uploader(
                "Choose files",
                type=["xlsx", "xls", "csv"],
                accept_multiple_files=True,
                label_visibility="collapsed"
            )

        if uploaded_files:
            try:
                all_sheets = {}
                for uploaded_file in uploaded_files:
                    file_name = uploaded_file.name
                    file_base = re.sub(r"[^a-zA-Z0-9_]", "_", file_name.rsplit(".", 1)[0]).lower()

                    if file_name.endswith(".csv"):
                        df = pd.read_csv(uploaded_file)
                        tname = file_base
                        # avoid name collisions across files
                        if tname in all_sheets:
                            tname = f"{tname}_2"
                        all_sheets[tname] = df
                    else:
                        xls = pd.ExcelFile(uploaded_file)
                        for sname in xls.sheet_names:
                            tname = re.sub(r"[^a-zA-Z0-9_]", "_", sname).lower()
                            if tname in all_sheets:
                                tname = f"{file_base}_{tname}"
                            all_sheets[tname] = pd.read_excel(uploaded_file, sheet_name=sname)

                first_table = list(all_sheets.keys())[0]
                st.session_state.excel_sheets = all_sheets
                st.session_state.excel_df = all_sheets[first_table]
                st.session_state.excel_table_name = first_table
                st.session_state.schema_text = "\n\n".join(
                    build_schema_from_df(sdf, sname) for sname, sdf in all_sheets.items()
                )
                st.session_state.data_source = "excel"
                st.session_state.conn = None

                total_rows = sum(len(s) for s in all_sheets.values())
                st.success(f"✅ Loaded **{len(uploaded_files)} file(s)** → **{len(all_sheets)} table(s)** — {total_rows:,} total rows")

                with st.expander("📐 View Schema (all tables)"):
                    st.text(st.session_state.schema_text)

                for sname, sdf in all_sheets.items():
                    with st.expander(f"👁️ Preview: {sname} (first 5 rows)"):
                        st.dataframe(sdf.head(), width='stretch')

            except Exception as e:
                st.error(f"Failed to read file: {e}")

    st.divider()
    st.subheader("🤖 LLM Settings")
    _providers = ["Gemini (free API)", "HuggingFace (free API)", "Ollama (local)"]
    _saved_provider = st.secrets.get("llm_provider", "Gemini (free API)")
    _provider_idx = _providers.index(_saved_provider) if _saved_provider in _providers else 0
    llm_provider = st.radio("LLM Provider", _providers, index=_provider_idx)

    if llm_provider == "Gemini (free API)":
        _raw = st.secrets.get("gemini_api_key", "")
        gemini_key = None if (not _raw or _raw == "PASTE_YOUR_GEMINI_KEY_HERE") else _raw
        llm_model = st.secrets.get("gemini_model", "gemini-2.5-flash")
        st.caption(f"Model: `{llm_model}`")
        if gemini_key:
            st.success("🔑 Gemini key loaded from config")
        else:
            st.error("❌ Gemini key missing — add to `.streamlit/secrets.toml`")
        hf_token = None
        ollama_url = None
    elif llm_provider == "HuggingFace (free API)":
        _raw = st.secrets.get("hf_token", "")
        gemini_key = None
        hf_token = None if not _raw else _raw
        llm_model = st.secrets.get("hf_model", "mistralai/Mistral-7B-Instruct-v0.3")
        st.caption(f"Model: `{llm_model}`")
        if hf_token:
            st.success("🔑 HuggingFace token loaded from config")
        else:
            st.error("❌ HF token missing — add `hf_token` to `.streamlit/secrets.toml`")
        ollama_url = None
    else:
        gemini_key = None
        hf_token = None
        ollama_url = st.secrets.get("ollama_url", "http://localhost:11434")
        llm_model = st.secrets.get("ollama_model", "llama3")
        st.caption(f"URL: `{ollama_url}` | Model: `{llm_model}`")

    verbose_reasoning = st.checkbox("Enable verbose reasoning (step-by-step thinking)", value=False, help="Show detailed LLM reasoning before SQL generation")
    debug_raw = st.checkbox("🔬 Show raw LLM response (debug)", value=False, help="Display the exact text returned by the LLM")

    # ── Saved Queries panel ──
    st.markdown("---")
    st.markdown("### ⭐ Saved Queries")
    if st.session_state.saved_queries:
        for idx, sq in enumerate(st.session_state.saved_queries):
            col_sq, col_del = st.columns([5, 1])
            with col_sq:
                if st.button(f"▶ {sq['name']}", key=f"sq_use_{idx}", width='stretch', help=sq["question"]):
                    st.session_state.prefill_question = sq["question"]
                    st.rerun()
            with col_del:
                if st.button("✕", key=f"sq_del_{idx}", help="Remove"):
                    st.session_state.saved_queries.pop(idx)
                    _save_json(SAVED_FILE, st.session_state.saved_queries)
                    st.rerun()
    else:
        st.caption("No saved queries yet. Run a query and click ⭐ Save.")

# ─── Main UI ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <h1>QueryMind</h1>
    <p>Ask questions in plain English &mdash; instantly converted to SQL and executed on your data.</p>
</div>
""", unsafe_allow_html=True)

# ── Status + Metric cards ──
_hist = st.session_state.history
_tables = len(st.session_state.selected_tables) if st.session_state.data_source == "postgres" else len(st.session_state.excel_sheets)
_queries = len(_hist)
_last_rows = _hist[-1]["rows"] if _hist else "—"

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card"><div class="val">{_queries}</div><div class="lbl">Queries Run</div></div>
    <div class="metric-card"><div class="val">{_tables}</div><div class="lbl">Tables Loaded</div></div>
    <div class="metric-card"><div class="val">{_last_rows}</div><div class="lbl">Last Result Rows</div></div>
</div>
""", unsafe_allow_html=True)

# ── Connection badge ──
if st.session_state.data_source == "postgres":
    st.markdown('<span class="badge badge-green">🟢 PostgreSQL / Greenplum &nbsp;|&nbsp; Live DB</span>', unsafe_allow_html=True)
elif st.session_state.data_source == "excel":
    tname = st.session_state.excel_table_name
    st.markdown(f'<span class="badge badge-blue">📊 Excel / CSV &nbsp;|&nbsp; {tname}</span>', unsafe_allow_html=True)
else:
    st.markdown('<span class="badge badge-orange">⚠️ No data source connected — choose one in the sidebar</span>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

_prefill = st.session_state.prefill_question
st.session_state.prefill_question = ""   # clear after use
question = st.text_area(
    "Your Question",
    value=_prefill,
    placeholder=(
        "write your question here..."
    ),
    height=90
)

run_btn = st.button("▶ Run Query", type="primary")

data_ready = st.session_state.data_source in ("postgres", "excel") and st.session_state.schema_text

if run_btn:
    if not question.strip():
        st.error("Please enter a question.")
    elif not data_ready:
        st.error("No data source loaded. Connect to Greenplum or upload a file in the sidebar.")
    else:
        # ─ Handle structural meta-questions for Excel directly from DataFrame ─
        if st.session_state.data_source == "excel" and st.session_state.excel_df is not None:
            q_low = question.lower()
            df_meta = st.session_state.excel_df
            tname = st.session_state.excel_table_name
            if any(kw in q_low for kw in ["how many column", "number of column", "count column", "list column", "what are the column", "which column"]):
                cols = df_meta.columns.tolist()
                st.markdown("---")
                st.subheader("Results")
                st.markdown(f"**Table `{tname}` has {len(cols)} columns:**")
                st.write(", ".join(cols))
                st.stop()
            if any(kw in q_low for kw in ["how many row", "number of row", "count row", "total row", "how many record"]):
                st.markdown("---")
                st.subheader("Results")
                st.markdown(f"**Table `{tname}` has {len(df_meta):,} rows.**")
                st.stop()

        # Step 1 – Detect multi-step questions (require strong sequential signals)
        q_low = question.lower()
        strong_multi_step = ["then get", "then find", "then show", "after that", "and then", "followed by", "next get", "next find"]
        is_multi_step = any(kw in q_low for kw in strong_multi_step)
        
        # Step 2 – Generate SQL via LLM
        provider_label = llm_provider.split("(")[0].strip()
        with st.spinner(f"Generating SQL with {provider_label} ({llm_model})..."):
            try:
                if is_multi_step:
                    # Multi-step: ask LLM to break down into sequential queries
                    planning_prompt = f"""You are a query planner. Break this complex question into at most 3 sequential SQL queries.

Question: {question}

Database Schema:
{st.session_state.schema_text}

Respond with each query on a new line, numbered like:
1. SELECT ...
2. SELECT ...
3. SELECT ...

Each query should build on the previous if needed."""
                    
                    if llm_provider == "Gemini (free API)":
                        raw_plan = call_gemini(planning_prompt, llm_model, gemini_key)
                    elif llm_provider == "HuggingFace (free API)":
                        raw_plan = call_huggingface(planning_prompt, llm_model, hf_token)
                    else:
                        raw_plan = call_ollama(planning_prompt, llm_model, ollama_url)
                    
                    # Parse the plan into individual queries
                    queries = []
                    for line in raw_plan.split('\n'):
                        line = line.strip()
                        if line and (line[0].isdigit() or 'SELECT' in line.upper()):
                            # Remove numbering and clean
                            clean = re.sub(r'^\d+[\.\)]\s*', '', line)
                            if 'SELECT' in clean.upper():
                                queries.append(clean)
                    
                    if not queries:
                        # Fallback to single query generation
                        prompt = build_prompt(st.session_state.schema_text, question, st.session_state.data_source, verbose_reasoning=verbose_reasoning)
                        if llm_provider == "Gemini (free API)":
                            raw_response = call_gemini(prompt, llm_model, gemini_key)
                        elif llm_provider == "HuggingFace (free API)":
                            raw_response = call_huggingface(prompt, llm_model, hf_token)
                        else:
                            raw_response = call_ollama(prompt, llm_model, ollama_url)
                        logic, sql = parse_llm_response(raw_response)
                        queries = [sql]
                        st.info("🤖 Multi-step planning not available, using single query.")
                else:
                    # Single query generation
                    prompt = build_prompt(st.session_state.schema_text, question, st.session_state.data_source, verbose_reasoning=verbose_reasoning)
                    if llm_provider == "Gemini (free API)":
                        if not gemini_key:
                            st.error("Please enter your Gemini API key in the sidebar.")
                            st.stop()
                        raw_response = call_gemini(prompt, llm_model, gemini_key)
                    elif llm_provider == "HuggingFace (free API)":
                        if not hf_token:
                            st.error("Please enter your HuggingFace token in the sidebar.")
                            st.stop()
                        raw_response = call_huggingface(prompt, llm_model, hf_token)
                    else:
                        raw_response = call_ollama(prompt, llm_model, ollama_url)
                    logic, sql = parse_llm_response(raw_response)
                    queries = [sql]
                    if debug_raw:
                        with st.expander("🔬 Raw LLM Response"):
                            st.text(raw_response)
            except requests.exceptions.ConnectionError as e:
                if llm_provider == "Gemini (free API)":
                    st.error("Cannot reach Gemini API. Check your internet/proxy settings.")
                elif llm_provider == "HuggingFace (free API)":
                    st.error("Cannot reach HuggingFace API. Check your internet/proxy settings.")
                else:
                    st.error(
                        f"Cannot reach Ollama at `{ollama_url}`. "
                        "Make sure Ollama is running (`ollama serve`)."
                    )
                st.stop()
            except requests.exceptions.SSLError:
                st.error(
                    "SSL certificate error — likely a corporate proxy (Dell network). "
                    "This blocks outbound HTTPS. "
                    "Try switching to **Ollama (local)** which needs no internet."
                )
                st.stop()
            except RuntimeError as e:
                st.error(str(e))
                st.stop()
            except Exception as e:
                st.error(f"LLM error: {e}")
                st.stop()

        st.markdown("---")
        st.subheader("Results")

        # ── 1. Logic ──
        st.markdown('<p class="section-label">💡 Logic</p>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="logic-box">{logic or "No logic returned by the model."}</div>',
            unsafe_allow_html=True
        )

        # ── 2. SQL ──
        st.markdown('<p class="section-label">🔍 Generated SQL</p>', unsafe_allow_html=True)
        if not queries or not queries[0] or queries[0].upper() == "N/A":
            st.info("No valid SELECT query was generated. " + (logic or ""))
        else:
            if len(queries) > 1:
                st.markdown(f'<div class="agent-box">🤖 <strong>Multi-step execution</strong> — {len(queries)} sequential queries planned by agent</div>', unsafe_allow_html=True)
                for i, q in enumerate(queries, 1):
                    st.markdown(f'<span class="step-badge">Step {i}</span>', unsafe_allow_html=True)
                    st.code(q, language="sql")
            else:
                st.code(queries[0], language="sql")

            # ── 3. Output ──
            st.markdown('<p class="section-label">📊 Output</p>', unsafe_allow_html=True)
            source_label = "PostgreSQL / Greenplum" if st.session_state.data_source == "postgres" else "Excel/CSV (in-memory SQLite)"
            
            all_results = []
            for i, q in enumerate(queries, 1):
                with st.spinner(f"Running query {i}/{len(queries)} on {source_label}..."):
                    try:
                        if st.session_state.data_source == "postgres":
                            result_df = run_query_greenplum(st.session_state.conn, q)
                        else:
                            result_df = run_query_excel(st.session_state.excel_sheets, q)
                        all_results.append(result_df)
                        if len(queries) > 1:
                            st.markdown(f"**Step {i} Result:**")
                            st.dataframe(result_df, width='stretch')
                            st.caption(f"✅ {len(result_df)} row(s) returned")
                    except Exception as exec_err:
                        # Agentic: Auto-fix SQL errors
                        st.error(f"❌ Query {i} failed: {exec_err}")
                        st.markdown('<div class="agent-box">🔄 <strong>Agent activated</strong> — analyzing error and attempting automatic fix...</div>', unsafe_allow_html=True)
                        st.session_state.error_log.append({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "question": question,
                            "error": str(exec_err),
                            "sql": q
                        })
                        fixed_result = None
                        for attempt in range(1, 3):
                            with st.spinner(f"Retry {attempt}/2: Regenerating SQL..."):
                                try:
                                    error_context = f"PREVIOUS ATTEMPT FAILED.\nError: {exec_err}\nPrevious SQL:\n{q}\n\nFix it to resolve this error."
                                    fix_prompt = build_prompt(st.session_state.schema_text, question, st.session_state.data_source, error_context, verbose_reasoning)
                                    if llm_provider == "Gemini (free API)":
                                        raw_fix = call_gemini(fix_prompt, llm_model, gemini_key)
                                    elif llm_provider == "HuggingFace (free API)":
                                        raw_fix = call_huggingface(fix_prompt, llm_model, hf_token)
                                    else:
                                        raw_fix = call_ollama(fix_prompt, llm_model, ollama_url)
                                    _, fixed_sql = parse_llm_response(raw_fix)
                                    if st.session_state.data_source == "postgres":
                                        fixed_result = run_query_greenplum(st.session_state.conn, fixed_sql)
                                    else:
                                        fixed_result = run_query_excel(st.session_state.excel_sheets, fixed_sql)
                                    st.success(f"✅ Fixed on attempt {attempt}/2!")
                                    st.code(fixed_sql, language="sql")
                                    all_results.append(fixed_result)
                                    break
                                except Exception as retry_err:
                                    if attempt == 2:
                                        st.error(f"❌ Could not fix after 2 attempts: {retry_err}")
                                        st.info("Try rephrasing your question or selecting different tables.")
                        if fixed_result is None:
                            all_results.append(None)
            
            # Combine results for single-query display or show final result
            result_df = all_results[-1] if all_results[-1] is not None else all_results[0]
            if len(queries) == 1:
                st.dataframe(result_df, width='stretch')
                st.caption(f"✅ {len(result_df)} row(s) returned")
            
            # Agentic: Result validation
            validation_warnings = []
            q_low = question.lower()
            
            # Check for empty results when question implies data should exist
            if len(result_df) == 0:
                if any(kw in q_low for kw in ["show", "list", "get", "find", "display", "all", "every"]):
                    validation_warnings.append("⚠️ No results returned, but question suggests data should exist. Consider checking spelling or table selection.")
            
            # Check for suspicious patterns
            if len(result_df) > 0:
                # Check if all values are null in key columns
                non_id_cols = [c for c in result_df.columns if "id" not in c.lower()]
                if non_id_cols and result_df[non_id_cols].isnull().all().all():
                    validation_warnings.append("⚠️ All non-ID columns are null — possible join issue or missing data.")
            
            # Display warnings
            if validation_warnings:
                st.warning("\n".join(validation_warnings))
                if st.button("🔄 Retry with different approach", key=f"retry_{len(st.session_state.history)}"):
                    st.rerun()

            # ── Export row ──
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            exp_col1, exp_col2, exp_col3, exp_col4 = st.columns([2, 2, 2, 3])

            with exp_col1:
                st.download_button(
                    "⬇️ CSV",
                    data=result_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"result_{ts}.csv",
                    mime="text/csv",
                    width='stretch'
                )
            with exp_col2:
                _xls = io.BytesIO()
                result_df.to_excel(_xls, index=False, engine="openpyxl")
                st.download_button(
                    "⬇️ Excel",
                    data=_xls.getvalue(),
                    file_name=f"result_{ts}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width='stretch'
                )
            with exp_col3:
                st.download_button(
                    "⬇️ JSON",
                    data=result_df.to_json(orient="records", indent=2).encode("utf-8"),
                    file_name=f"result_{ts}.json",
                    mime="application/json",
                    width='stretch'
                )
            with exp_col4:
                save_name = st.text_input("Save as…", placeholder="e.g. Top 5 products by rank", key=f"save_name_{ts}", label_visibility="collapsed")
                if st.button("⭐ Save Query", key=f"save_btn_{ts}", width='stretch'):
                    if save_name.strip():
                        entry = {"name": save_name.strip(), "question": question, "sql": queries[0], "logic": logic}
                        st.session_state.saved_queries.append(entry)
                        _save_json(SAVED_FILE, st.session_state.saved_queries)
                        st.success(f"Saved as **{save_name}**!")
                    else:
                        st.warning("Enter a name before saving.")

            st.session_state.history.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "question": question,
                "logic": logic,
                "sql": queries[0],
                "rows": len(result_df),
                "source": st.session_state.data_source
            })
            _save_json(HISTORY_FILE, st.session_state.history[-200:])


# ─── Query History ────────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown("---")
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.subheader("📜 Query History")
    with col_h2:
        if st.button("🗑️ Clear History", width='stretch'):
            st.session_state.history = []
            st.session_state.error_log = []
            _save_json(HISTORY_FILE, [])
            st.rerun()
    for hidx, item in enumerate(reversed(st.session_state.history[-15:])):
        source_icon = "🗄️" if item.get("source") == "postgres" else "📊"
        auto_fixed = "auto-fixed" in item.get("logic", "").lower()
        fix_tag = " 🔧" if auto_fixed else ""
        with st.expander(f"{source_icon} [{item['time']}]  {item['question'][:80]}{fix_tag}"):
            st.markdown(f"**Logic:** {item['logic']}")
            st.code(item["sql"], language="sql")
            st.caption(f"✅ {item['rows']} row(s) returned &nbsp;|&nbsp; Source: {item.get('source','')}")
            if st.button("↩ Reuse this query", key=f"reuse_{hidx}"):
                st.session_state.prefill_question = item["question"]
                st.rerun()

# ─── Error Log ────────────────────────────────────────────────────────────────
if st.session_state.error_log:
    with st.expander(f"⚠️ Agent Error Log ({len(st.session_state.error_log)} event(s))"):
        for err in reversed(st.session_state.error_log[-10:]):
            st.markdown(f"**[{err['time']}]** `{err['question'][:60]}`")
            st.error(f"Error: {err['error']}")
            if err.get("sql"):
                st.code(err["sql"], language="sql")
