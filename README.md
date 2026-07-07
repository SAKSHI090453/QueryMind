# 🧠 QueryMind — Ask Your Data in Plain English

An **agentic AI-powered SQL assistant** built with Streamlit. Upload any Excel or CSV file and ask questions in plain English — the agent generates SQL, runs it, validates the result, and auto-fixes errors without any manual intervention.

---

## ✨ Features

### 🤖 Agentic Capabilities
| Feature | Description |
|---|---|
| **SQL Auto-Fix** | If a query fails, the agent sends the error back to the LLM and retries up to 2 times automatically |
| **Chain-of-Thought** | Toggle step-by-step reasoning to see how the LLM thinks before writing SQL |
| **Multi-step Planning** | Detects complex questions and breaks them into sequential SQL queries |
| **Result Validation** | Flags suspicious/empty results and offers a retry button |
| **Composite Ranking** | Automatically uses CTE + averaged ranks when asked to rank by multiple metrics |
| **Gemini Retry** | Retries Gemini API calls with exponential backoff on 503/500 errors |

### 📊 Data Support
- Upload **multiple Excel (.xlsx, .xls) and CSV** files simultaneously
- Each sheet in an Excel file becomes a separate queryable table
- Cross-file **JOINs** supported — query across all uploaded files at once

### 💾 Persistence
- **Query history** saved to `query_history.json` (survives page refresh)
- **Saved queries** bookmarked with custom names, accessible from the sidebar
- **Export results** as CSV, Excel, or JSON

### 🎨 UI
- Fresh sky-blue + coral color palette
- Hero banner, metric cards, status badges
- Debug toggle to inspect raw LLM responses

---

## 🚀 Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/SAKSHI090453/QueryMind.git
cd QueryMind
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

> **Dell / corporate network?** Add trusted hosts:
> ```bash
> pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
> ```

### 3. Configure secrets
Create `.streamlit/secrets.toml` (never commit this file):
```toml
gemini_api_key = "your-gemini-api-key-here"

# Optional — HuggingFace
# hf_token = 
# hf_model = 

# Optional — Ollama (local)
# ollama_url = 
# ollama_model = 

# Optional — LLM provider default
# llm_provider = "Gemini (free API)"
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

### 4. Run the app
```bash
python -m streamlit run app.py
```

---

## 🧭 How to Use

1. **Upload** one or more Excel/CSV files in the sidebar
2. **Type** your question in plain English
3. Click **▶ Run Query**
4. View the **logic**, **SQL**, and **results**
5. **Download** results as CSV, Excel, or JSON
6. **Save** frequent queries by name for one-click reuse

### Example questions
```
Which product has the highest trend score?
Rank each product by combining trend score and revenue — top 10
Show products where revenue is greater than 50000 then find average trend score
```

---

## 🗂️ Project Structure

```
SQL Agent/
├── app.py                  # Main Streamlit application
├── test_app.py             # Unit tests (37 tests)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── .gitignore
└── .streamlit/
    ├── secrets.toml        # API keys (gitignored — never commit)
    └── config.toml         # Theme settings (gitignored)
```

---

## 🧪 Running Tests

```bash
python -m pytest test_app.py -v
```

All 37 tests cover: `dtype_to_sql`, `build_schema_from_df`, `build_prompt`, `parse_llm_response`, `run_query_excel`, multi-step detection.

---

## ☁️ Deploy to Streamlit Cloud

1. Push your code to GitHub (secrets and JSON files are gitignored)
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repository and `app.py` as the main file
4. Under **Advanced settings → Secrets**, paste your `secrets.toml` contents
5. Click **Deploy**

> **Note:** `query_history.json` and `saved_queries.json` reset on redeploy (ephemeral filesystem). For persistent storage on cloud, connect an external DB like Supabase.

---

## 🤖 Supported LLM Providers

| Provider | Setup |
|---|---|
| **Gemini (free API)** | Get key at aistudio.google.com — 15 req/min free tier |
| **HuggingFace (free API)** | Get token at huggingface.co — free inference API |
| **Ollama (local)** | Run `ollama serve` locally — fully offline, no API key needed |

---

## 🛠️ Tech Stack

- **[Streamlit](https://streamlit.io)** — UI framework
- **[Google Gemini](https://aistudio.google.com)** — Default LLM
- **[Pandas](https://pandas.pydata.org)** — Data processing
- **[SQLite](https://sqlite.org)** — In-memory query engine for Excel/CSV
- **[openpyxl](https://openpyxl.readthedocs.io)** — Excel read/write

---

## 📄 License

MIT License — free to use, modify, and distribute.
