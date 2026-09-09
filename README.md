# Git Score

Local demo: analyze a git repo into independent checks, browse the tree, and chat about the findings.

Product: [SPEC.md](SPEC.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md).

## Run

Git must be on `PATH`. Copy `.env.example` to `.env` and set an OpenAI-compatible key if you want chat.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r gitscore_back\requirements.txt
.\.venv\Scripts\python -m uvicorn gitscore_back.app:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd gitscore_front
npm install
npm run dev
```

Open http://127.0.0.1:5173 and paste a local clone path or a public git URL.
