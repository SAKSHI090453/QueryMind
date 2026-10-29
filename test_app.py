"""
Unit tests for SQL Agent (app.py) core functions.
Run with:  python -m pytest test_app.py -v
"""

import pytest
import pandas as pd
import sqlite3
import re
from unittest.mock import patch, MagicMock

# ── Import helpers from app (non-Streamlit functions only) ────────────────────
import importlib, types, sys

# Stub out streamlit so we can import app.py without a running server
st_stub = types.ModuleType("streamlit")
for attr in [
    "set_page_config", "markdown", "title", "caption", "info", "warning",
    "error", "success", "stop", "spinner", "button", "text_input",
    "number_input", "text_area", "radio", "multiselect", "expander",
    "sidebar", "header", "subheader", "divider", "file_uploader",
    "dataframe", "code", "write", "columns", "rerun", "checkbox",
    "download_button", "secrets",
]:
    setattr(st_stub, attr, MagicMock())

st_stub.secrets = {}
st_stub.session_state = MagicMock()
sys.modules["streamlit"] = st_stub

# Now we can safely import the pure functions
from app import (
    dtype_to_sql,
    build_schema_from_df,
    build_prompt,
    parse_llm_response,
    run_query_excel,
)


# ─── dtype_to_sql ─────────────────────────────────────────────────────────────

class TestDtypeToSql:
    def test_int(self):
        assert dtype_to_sql("int64") == "INTEGER"

    def test_float(self):
        assert dtype_to_sql("float64") == "REAL"

    def test_datetime(self):
        assert dtype_to_sql("datetime64[ns]") == "TIMESTAMP"

    def test_bool(self):
        assert dtype_to_sql("bool") == "BOOLEAN"

    def test_object_text(self):
        assert dtype_to_sql("object") == "TEXT"

    def test_unknown_defaults_to_text(self):
        assert dtype_to_sql("category") == "TEXT"


# ─── build_schema_from_df ─────────────────────────────────────────────────────

class TestBuildSchemaFromDf:
    def test_basic_schema(self):
        df = pd.DataFrame({"name": ["Alice"], "age": [30], "salary": [50000.0]})
        result = build_schema_from_df(df, "employees")
        assert "Table: employees" in result
        assert "name (TEXT)" in result
        assert "age (INTEGER)" in result
        assert "salary (REAL)" in result

    def test_empty_df_schema(self):
        df = pd.DataFrame(columns=["id", "value"])
        result = build_schema_from_df(df, "empty_table")
        assert "Table: empty_table" in result
        assert "id" in result


# ─── build_prompt ─────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_postgres_prompt_contains_rules(self):
        prompt = build_prompt("Table: accounts\nColumns: id (INTEGER)", "How many accounts?", "postgres")
        assert "SELECT" in prompt
        assert "STRICT RULES" in prompt
        assert "PostgreSQL" in prompt

    def test_excel_prompt_contains_sqlite_note(self):
        prompt = build_prompt("Table: sheet1\nColumns: name (TEXT)", "List names", "excel")
        assert "SQLite" in prompt
        assert "LOWER()" in prompt

    def test_verbose_reasoning_included(self):
        prompt = build_prompt("Table: t\nColumns: id (INTEGER)", "Count rows", "postgres", verbose_reasoning=True)
        assert "STEP-BY-STEP REASONING" in prompt

    def test_no_verbose_reasoning_by_default(self):
        prompt = build_prompt("Table: t\nColumns: id (INTEGER)", "Count rows", "postgres")
        assert "STEP-BY-STEP REASONING" not in prompt

    def test_error_context_included(self):
        ctx = "PREVIOUS ATTEMPT FAILED.\nError: no such table: xyz"
        prompt = build_prompt("Table: t\nColumns: id (INTEGER)", "Count rows", "postgres", error_context=ctx)
        assert "PREVIOUS ATTEMPT FAILED" in prompt

    def test_question_in_prompt(self):
        q = "How many unique countries exist?"
        prompt = build_prompt("Table: geo\nColumns: country (TEXT)", q, "postgres")
        assert q in prompt


# ─── parse_llm_response ───────────────────────────────────────────────────────

class TestParseLlmResponse:
    def test_standard_format(self):
        raw = "LOGIC: Count all rows in accounts.\nSQL: SELECT COUNT(*) FROM accounts"
        logic, sql = parse_llm_response(raw)
        assert logic == "Count all rows in accounts."
        assert sql == "SELECT COUNT(*) FROM accounts"

    def test_strips_trailing_semicolon(self):
        raw = "LOGIC: Select all.\nSQL: SELECT * FROM t;"
        _, sql = parse_llm_response(raw)
        assert not sql.endswith(";")

    def test_missing_logic(self):
        raw = "SQL: SELECT * FROM t"
        logic, sql = parse_llm_response(raw)
        assert logic == ""
        assert "SELECT" in sql

    def test_missing_sql(self):
        raw = "LOGIC: Nothing to query."
        logic, sql = parse_llm_response(raw)
        assert "Nothing to query" in logic
        assert sql == ""

    def test_case_insensitive_parsing(self):
        raw = "logic: Count rows.\nsql: SELECT COUNT(*) FROM orders"
        logic, sql = parse_llm_response(raw)
        assert "Count rows" in logic
        assert "SELECT" in sql

    def test_multiline_logic(self):
        raw = "LOGIC: Step 1: find table.\nStep 2: count.\nSQL: SELECT COUNT(*) FROM t"
        logic, sql = parse_llm_response(raw)
        assert "Step 1" in logic
        assert "SELECT COUNT" in sql

    def test_cte_with_clause(self):
        raw = "LOGIC: Use a CTE.\nSQL: WITH top AS (SELECT * FROM t) SELECT * FROM top"
        logic, sql = parse_llm_response(raw)
        assert "WITH top" in sql
        assert "SELECT" in sql

    def test_fallback_extracts_select(self):
        raw = "Here is the query:\nSELECT name FROM products ORDER BY profit DESC LIMIT 1"
        _, sql = parse_llm_response(raw)
        assert "SELECT name" in sql

    def test_strips_markdown_code_fences(self):
        raw = "LOGIC: Rank products.\nSQL:\n```sql\nSELECT name, RANK() OVER (ORDER BY trend_score DESC) AS rank FROM products\n```"
        logic, sql = parse_llm_response(raw)
        assert "RANK()" in sql
        assert "```" not in sql

    def test_sql_on_next_line_after_label(self):
        raw = "LOGIC: Simple query.\nSQL:\nSELECT * FROM accounts"
        _, sql = parse_llm_response(raw)
        assert "SELECT * FROM accounts" in sql


# ─── run_query_excel ──────────────────────────────────────────────────────────

class TestRunQueryExcel:
    def setup_method(self):
        self.sheets = {
            "employees": pd.DataFrame({
                "name": ["Alice", "Bob", "Charlie"],
                "dept": ["HR", "IT", "IT"],
                "salary": [50000, 70000, 65000]
            }),
            "departments": pd.DataFrame({
                "dept": ["HR", "IT"],
                "budget": [100000, 200000]
            })
        }

    def test_simple_select(self):
        df = run_query_excel(self.sheets, "SELECT * FROM employees")
        assert len(df) == 3
        assert "name" in df.columns

    def test_count_query(self):
        df = run_query_excel(self.sheets, "SELECT COUNT(*) as cnt FROM employees")
        assert df["cnt"].iloc[0] == 3

    def test_filter_query(self):
        df = run_query_excel(self.sheets, "SELECT name FROM employees WHERE dept = 'IT'")
        assert len(df) == 2

    def test_case_insensitive_lower(self):
        df = run_query_excel(self.sheets, "SELECT name FROM employees WHERE LOWER(dept) = LOWER('it')")
        assert len(df) == 2

    def test_cross_sheet_join(self):
        df = run_query_excel(
            self.sheets,
            "SELECT e.name, d.budget FROM employees e JOIN departments d ON e.dept = d.dept"
        )
        assert len(df) == 3
        assert "budget" in df.columns

    def test_aggregation(self):
        df = run_query_excel(self.sheets, "SELECT dept, SUM(salary) as total FROM employees GROUP BY dept")
        assert len(df) == 2

    def test_invalid_sql_raises(self):
        with pytest.raises(Exception):
            run_query_excel(self.sheets, "SELECT * FROM nonexistent_table")


# ─── Multi-step detection ─────────────────────────────────────────────────────

class TestMultiStepDetection:
    """Test the strong multi-step keyword detection logic (inline, not a function)."""

    def _is_multi_step(self, question: str) -> bool:
        strong_multi_step = ["then get", "then find", "then show", "after that", "and then", "followed by", "next get", "next find"]
        return any(kw in question.lower() for kw in strong_multi_step)

    def test_detects_and_then(self):
        assert self._is_multi_step("List accounts and then find contacts") is True

    def test_detects_after_that(self):
        assert self._is_multi_step("Get top 10 customers, after that show their orders") is True

    def test_detects_then_find(self):
        assert self._is_multi_step("Get accounts with revenue > 1M then find their managers") is True

    def test_no_false_positive_first(self):
        assert self._is_multi_step("Show me the first 10 rows") is False

    def test_no_false_positive_next(self):
        assert self._is_multi_step("What is the next available date?") is False

    def test_no_false_positive_plain_sentence(self):
        assert self._is_multi_step("Show all accounts where revenue is greater than 100") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
