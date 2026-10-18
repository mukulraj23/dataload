# DataLoad

Ask questions about a CSV, an Excel sheet or a photo of a register, in plain words.
Gemma 4 works out what you are asking, pandas does the maths, and every answer shows the code that produced it.

Built for Hacktoberfest HackDay 2026 (E-Cell IIMTU), Track 1, PS 03: Community and Environmental Data Intelligence.

## Why

A lot of useful local data (hostel electricity, water, canteen sales, attendance) sits in spreadsheets and paper registers.
The people who keep it usually can't write formulas, and a general chatbot can give a wrong number with no way to check it.

## What it does

- Upload a CSV / Excel file, or a photo of a register. Photos are turned into a table you can edit before using it.
- A data health check runs as soon as a file loads (missing months, empty cells, duplicates, zeros that look like missing values). No model call.
- Ask in English or Hindi, e.g. "Which hostel used the most electricity last month?"
- You get the answer, a chart, caveats, and a Proof tab with the plan, the pandas code and the rows used.
- If the data can't answer the question, it says so instead of guessing.
- Download the answer as a text report or share it on WhatsApp.

Question types: overview of the data, distributions, ranking, trend over time, comparison, totals and averages, ratios, counts.
Anything else goes to a short pandas snippet written by Gemma, which is checked (no imports, no file access) before it runs.

## How it works

1. The browser sends the question to `server.py`.
2. Gemma 4 gets the question and the column names (not the rows) and replies with a small JSON plan.
3. The plan is checked against the real columns. Unknown column? The app says the data doesn't have it.
4. pandas runs the plan. The answer sentence is built from templates, so there's no second model call.
5. The same question on the same file is served from a cache.

Answers usually come back in a few seconds; the app shows the model time and the calculation time for each one.

| File | Purpose |
|---|---|
| `server.py` | FastAPI app: upload, demo datasets, photo to table, ask, explain |
| `core/schema.py` | Column types, number cleanup, day-first dates (06/10 = 6 Oct) |
| `core/health.py` | Data health check |
| `core/llm.py` | All Gemma 4 calls |
| `core/executor.py` | Turns the plan into pandas code, runs it, writes the answer |
| `core/extra.py` | Overview, distributions and the checked pandas snippet |
| `core/suggest.py` | Suggested questions for any file |
| `static/` | UI in plain HTML/CSS/JS. Chart.js and fonts are bundled in `static/vendor/` |

## Model

Gemma 4 `gemma-4-26b-a4b-it` through the Gemini API (free tier).
Set `GEMMA_MODEL` to use another Gemma 4 model, e.g. `gemma-4-31b-it`.

## Running locally

Get a free key at https://aistudio.google.com/apikey, then copy `.env.example` to `.env` and paste it in.
You can also enter the key in the app; it's stored in your browser.

```bash
cd dataload
uv run --no-project --with-requirements requirements.txt python -m uvicorn server:app --port 8000
```

Then open http://localhost:8000 (the app itself is at `/app`). On Windows you can also run `run.bat`.

## Deploying

The `Dockerfile` works on Hugging Face Spaces (Docker SDK) and Render. Add `GEMINI_API_KEY` as a secret.
Don't commit `.env`; it's in `.gitignore`.

## Tests

```bash
pip install pytest httpx
python -m pytest -q
```

The tests use a fake model, so they run without a key.

`eval/run_eval.py` checks real model plans against hand-written ones for the questions in `eval/test_questions.csv`
(ranking, trend, comparison, ratio, count, and two the data can't answer) and prints accuracy and latency.

## Demo datasets

`data/demo/` has 7 public CSV files: insurance, heart disease, laptop prices, used Ford cars, countries of the world,
Netflix titles and zoo animals. Open them from "Demo datasets" in the app. They are demo data, not official records.

## Limitations

- Needs the Gemini API, so it doesn't work offline. The free tier has rate limits.
- One table at a time, no joins.
- Photo reading can get messy handwriting wrong, so check the table before asking questions.
