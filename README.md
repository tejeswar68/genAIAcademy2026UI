# CivicEYEAI — UI

Streamlit interface for uploading and geo-tagging drone snapshots for AI analysis.

## Project structure

```
ui/
├── streamlit_app.py          # Entrypoint: page config + screen routing
├── app/
│   ├── __init__.py
│   ├── config.py             # Env-driven settings (Settings dataclass)
│   ├── screens/
│   │   ├── __init__.py
│   │   └── upload_image.py   # Upload Image screen (render())
│   └── services/
│       ├── __init__.py
│       └── image_service.py  # Image decoding, isolated from the UI
├── requirements.txt
├── .env.example
└── .gitignore
```

The layout separates **screens** (declarative Streamlit UI) from **services**
(pure, testable logic) and **config** (environment-driven settings). Adding a
new screen = a new module in `app/screens/` exposing `render()`.

## Setup

```bash
cd ui
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run streamlit_app.py
```
