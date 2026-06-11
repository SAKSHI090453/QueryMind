import streamlit as st
import psycopg2
import pandas as pd
import requests
import re
import sqlite3
import time
from datetime import datetime

st.set_page_config(
    page_title="SQL Agent (PostgreSQL / Greenplum)",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .logic-box {
        background-color: #f0f7ff;
        border-left: 4px solid #2196F3;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
        font-size: 0.95rem;
    }
    .section-label {
        font-weight: 600;
        font-size: 0.85rem;
        color: #555;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.3rem;
    }
    .mode-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────────────
if "conn" not in st.session_state:
    st.session_state.conn = None
if "schema_text" not in st.session_state:
    st.session_state.schema_text = ""
if "history" not in st.session_state:
    st.session_state.history = []
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
    return f"Table: {table_name}\nColumns: {cols}"


def build_prompt(schema: str, question: str, data_source: str = "postgres") -> str:
    if data_source == "excel":
        db_note = (
            "SQLite (in-memory). "
            "Do NOT use information_schema, pg_catalog, or PRAGMA — they are unavailable. "
            "The full schema is already provided below; use only the table and column names listed there. "
            "IMPORTANT: For ALL string/text comparisons use LOWER() on both sides, e.g. LOWER(column) = LOWER('value'), to ensure case-insensitive matching."
        )
    else:
        db_note = "PostgreSQL-compatible SQL syntax."
    return f"""You are a SQL assistant. The database uses {db_note}

STRICT RULES:
- Only generate SELECT queries.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE.
- If asked to modify data, set SQL to: N/A
- Column names with spaces must be wrapped in double quotes.
- Respond EXACTLY in the format below — no markdown, no extra text.

LOGIC: <one or two sentences explaining the approach>
SQL: <the SELECT query, no trailing semicolon>

DATABASE SCHEMA:
{schema}

User Question: {question}"""


def call_ollama(prompt: str, model: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/api/generate"
    response = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=180
    )
    response.raise_for_status()
    return response.json()["response"]


def call_gemini(prompt: str, model: str, api_key: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "X-goog-api-key": api_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 512, "temperature": 0.1}
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code == 429:
        raise RuntimeError("⏳ Gemini rate limit hit (free tier: 15 req/min). Wait a few seconds and click Run again.")
    if response.status_code in (400, 403, 404):
        raise RuntimeError(f"Gemini error: {response.json().get('error', {}).get('message', response.text)}")
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_huggingface(prompt: str, model: str, token: str) -> str:
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 512,
            "return_full_text": False,
            "temperature": 0.1
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
    logic_match = re.search(r"LOGIC:\s*(.+?)(?=\nSQL:|\Z)", text, re.DOTALL | re.IGNORECASE)
    sql_match = re.search(r"SQL:\s*(SELECT[\s\S]+?)(?:\s*$)", text, re.IGNORECASE)
    logic = logic_match.group(1).strip() if logic_match else ""
    sql = sql_match.group(1).strip().rstrip(";") if sql_match else ""
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
        index=0
    )

    st.divider()

    # ── Greenplum mode ──
    if mode == "🗄️ PostgreSQL / Greenplum":
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

        if st.button("Connect & Load Schema", type="primary", use_container_width=True):
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
                                lines.append(f"Table: {qname}\nColumns: {cols}")
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
        st.subheader("📁 Upload Your File")
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["xlsx", "xls", "csv"],
            help="Supports Excel (.xlsx, .xls) and CSV files"
        )

        if uploaded_file is not None:
            try:
                file_name = uploaded_file.name

                if file_name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                    table_name = re.sub(r"[^a-zA-Z0-9_]", "_", file_name.replace(".csv", "")).lower()
                    sheets = {table_name: df}
                else:
                    xls = pd.ExcelFile(uploaded_file)
                    sheets = {}
                    for sname in xls.sheet_names:
                        tname = re.sub(r"[^a-zA-Z0-9_]", "_", sname).lower()
                        sheets[tname] = pd.read_excel(uploaded_file, sheet_name=sname)
                    table_name = list(sheets.keys())[0]
                    df = sheets[table_name]

                st.session_state.excel_sheets = sheets
                st.session_state.excel_df = df
                st.session_state.excel_table_name = table_name
                st.session_state.schema_text = "\n\n".join(
                    build_schema_from_df(sdf, sname) for sname, sdf in sheets.items()
                )
                st.session_state.data_source = "excel"
                st.session_state.conn = None

                total_rows = sum(len(s) for s in sheets.values())
                st.success(f"✅ Loaded {len(sheets)} sheet(s) — {total_rows:,} total rows")

                with st.expander("📐 View Schema (all sheets)"):
                    st.text(st.session_state.schema_text)

                for sname, sdf in sheets.items():
                    with st.expander(f"👁️ Preview: {sname} (first 5 rows)"):
                        st.dataframe(sdf.head(), use_container_width=True)

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

# ─── Main UI ──────────────────────────────────────────────────────────────────
st.title("🗄️ SQL Agent")
st.caption("Ask questions in plain English — works with PostgreSQL, Greenplum, or Excel/CSV.")

# Active source badge
if st.session_state.data_source == "postgres":
    st.info("🟢 **Mode: PostgreSQL / Greenplum** — queries run on live DB")
elif st.session_state.data_source == "excel":
    st.info(f"📊 **Mode: Excel / CSV** — table name: `{st.session_state.excel_table_name}`")
else:
    st.warning("⚠️ No data source connected. Choose one in the sidebar.")

st.markdown("---")

question = st.text_area(
    "Your Question",
    placeholder=(
        "e.g.  How many unique accounts do I have in EMEA?\n"
        "       How many unique accounts have a domain name?\n"
        "       How many unique accounts have a local name?"
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

        # Step 1 – Generate SQL via LLM
        provider_label = llm_provider.split("(")[0].strip()
        with st.spinner(f"Generating SQL with {provider_label} ({llm_model})..."):
            try:
                prompt = build_prompt(st.session_state.schema_text, question, st.session_state.data_source)
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
        if not sql or sql.upper() == "N/A":
            st.info("No valid SELECT query was generated. " + (logic or ""))
        else:
            st.code(sql, language="sql")

            # ── 3. Output ──
            st.markdown('<p class="section-label">📊 Output</p>', unsafe_allow_html=True)
            source_label = "PostgreSQL / Greenplum" if st.session_state.data_source == "postgres" else "Excel/CSV (in-memory SQLite)"
            with st.spinner(f"Running query on {source_label}..."):
                try:
                    if st.session_state.data_source == "postgres":
                        result_df = run_query_greenplum(st.session_state.conn, sql)
                    else:
                        result_df = run_query_excel(
                            st.session_state.excel_sheets,
                            sql
                        )

                    st.dataframe(result_df, use_container_width=True)
                    st.caption(f"✅ {len(result_df)} row(s) returned")

                    csv_bytes = result_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv_bytes,
                        file_name=f"query_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )

                    st.session_state.history.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "question": question,
                        "logic": logic,
                        "sql": sql,
                        "rows": len(result_df),
                        "source": st.session_state.data_source

                    })

                except Exception as e:
                    st.error(f"Query execution error: {e}")
                    st.info("The generated SQL may reference columns that don't exist. Try rephrasing your question.")

# ─── Query History ────────────────────────────────────────────────────────────
if st.session_state.history:
    st.markdown("---")
    st.subheader("📜 Query History")
    for item in reversed(st.session_state.history[-15:]):
        source_icon = "🗄️" if item.get("source") == "postgres" else "📊"
        with st.expander(f"{source_icon} [{item['time']}]  {item['question'][:85]}"):
            st.markdown(f"**Logic:** {item['logic']}")
            st.code(item["sql"], language="sql")
            st.caption(f"{item['rows']} row(s) returned")
