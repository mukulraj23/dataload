"""DataLoad web server (FastAPI). Serves the UI and a small JSON API.

Run locally:   uvicorn server:app --reload      then open http://localhost:8000
API key: put GEMINI_API_KEY in a .env file / environment, or paste it once in the app
(stored in your browser, sent with each request).
"""
from __future__ import annotations

import io
import math
import re
import os
import time
import pickle
import tempfile
import uuid
from collections import OrderedDict, deque

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.executor import run
from core.health import health_report
from core.llm import MODEL, GemmaClient
from core.schema import build_schema, clean_frame
from core.suggest import suggestions

BASE = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    path = os.path.join(BASE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
SERVER_KEY = os.getenv("GEMINI_API_KEY", "").strip()

app = FastAPI(title="DataLoad")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

DATASETS: "OrderedDict[str, dict]" = OrderedDict()   # id -> {df, schema, name, is_sample}
PLAN_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
CLIENTS: dict[str, GemmaClient] = {}

GENERAL_Q = re.compile(r"(about|summary|summar|overview|describe|explain|batao|bata|kya hai|samjhao|data|file)", re.I)

# Demo datasets: public files supplied by the team, kept in data/demo/. Questions are hand-picked per file.
DEMOS = [
    {"id": "insurance", "file": "insurance.csv", "title": "Medical insurance charges",
     "about": "Age, BMI, smoker and region vs yearly charges",
     "questions": ["Tell me about this data", "Average charges for smokers vs non-smokers",
                   "Which region has the highest average charges?", "How many people are in each region?",
                   "Average charges by number of children", "What does the bmi distribution look like?"]},
    {"id": "heart", "file": "heart.csv", "title": "Heart disease patients",
     "about": "Clinical readings for 918 patients",
     "questions": ["Tell me about this data", "What % have heartdisease, by sex?",
                   "Average cholesterol by chestpaintype", "How many patients in each chestpaintype?",
                   "Average maxhr by heartdisease", "What does the age distribution look like?"]},
    {"id": "laptop_price", "file": "laptop_price.csv", "title": "Laptop prices",
     "about": "1,303 laptops with specs and price in euros",
     "questions": ["Tell me about this data", "Which company has the highest average price_euros?",
                   "How many laptops does each company have?", "Average price_euros by typename",
                   "Top 5 most expensive laptops", "Average price_euros by opsys"]},
    {"id": "ford", "file": "ford.csv", "title": "Used Ford cars",
     "about": "17,966 listings with year, mileage and price",
     "questions": ["Tell me about this data", "Which model has the highest average price?",
                   "What is the trend of average price by year?", "Compare Manual vs Automatic average price",
                   "How many cars for each fueltype?", "Which model has the highest average mpg?"]},
    {"id": "countries", "file": "countries_of_the_world.csv", "title": "Countries of the world",
     "about": "Population, GDP, literacy and more for 227 countries",
     "questions": ["Tell me about this data", "Top 10 countries by population",
                   "Which region has the highest average gdp per capita?", "Average literacy by region",
                   "How many countries are in each region?", "Which countries have the highest infant mortality?"]},
    {"id": "netflix", "file": "netflix.csv", "title": "Netflix titles",
     "about": "7,787 movies and TV shows",
     "questions": ["Tell me about this data", "How many Movies vs TV Shows?",
                   "How many titles were added each year?", "Which rating has the most titles?",
                   "Top 10 countries by number of titles", "What is the trend of titles by release_year?"]},
    {"id": "zoo", "file": "zoo.csv", "title": "Zoo animals",
     "about": "101 animals and their traits",
     "questions": ["Tell me about this data", "How many animals have feathers?",
                   "Average legs for animals with and without hair", "Which animals are venomous?",
                   "How many animals are aquatic?", "What does the legs distribution look like?"]},
]
DEMO_BY_ID = {d["id"]: d for d in DEMOS}

# In-memory store, mirrored to disk so a server restart doesn't lose uploaded data.
STORE_DIR = os.path.join(tempfile.gettempdir(), "dataload_store")
os.makedirs(STORE_DIR, exist_ok=True)

# Simple per-IP limit, only when the server's own key is paying for the calls.
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
_HITS: dict[str, deque] = {}


def rate_check(request: Request, own_key: str | None):
    if not SERVER_KEY or (own_key or "").strip():
        return
    ip = request.client.host if request.client else "?"
    now = time.time()
    q = _HITS.setdefault(ip, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "RATE_LIMIT")
    q.append(now)


# helpers
def client_for(key_header: str | None) -> GemmaClient:
    key = SERVER_KEY or (key_header or "").strip()
    if not key:
        raise HTTPException(401, "API_KEY_MISSING")
    if key not in CLIENTS:
        CLIENTS[key] = GemmaClient(key)
    return CLIENTS[key]


def jsonable(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(v, (pd.Timestamp,)):
        return str(v.date())
    return v if isinstance(v, (int, str, bool)) else str(v)


def model_error(e: Exception) -> HTTPException:
    """Map a model/API failure to a clear error code for the UI."""
    msg = str(e)
    low = msg.lower()
    if "api key" in low or "api_key_invalid" in low or "permission_denied" in low or " 401" in low or " 403" in low:
        return HTTPException(401, "API_KEY_INVALID")
    if "429" in msg or "resource_exhausted" in low or "quota" in low:
        return HTTPException(429, "RATE_LIMIT")
    if "timed out" in low or "timeout" in low or "deadline" in low:
        return HTTPException(504, "MODEL_TIMEOUT")
    return HTTPException(502, "MODEL_FAILED: " + msg[:200])


def frame_rows(df: pd.DataFrame | None, limit: int = 60) -> dict | None:
    if df is None:
        return None
    df = df.head(limit)
    return {"columns": [str(c) for c in df.columns],
            "rows": [[jsonable(v) for v in row] for row in df.itertuples(index=False)],
            "total": None}


def chart_spec(fig) -> dict | None:
    if fig is None:
        return None
    datasets, labels = [], None
    kind = "bar"
    for tr in fig.data:
        x = [jsonable(v) for v in (tr.x if tr.x is not None else [])]
        y = [jsonable(v) for v in (tr.y if tr.y is not None else [])]
        labels = labels or x
        if tr.type == "scatter":
            kind = "line"
        datasets.append({"label": tr.name or "", "data": y, "x": x})
    # align grouped bars on a shared label list
    if len(datasets) > 1:
        all_labels = []
        for d in datasets:
            for v in d["x"]:
                if v not in all_labels:
                    all_labels.append(v)
        for d in datasets:
            m = dict(zip(d["x"], d["data"]))
            d["data"] = [m.get(l) for l in all_labels]
        labels = all_labels
    for d in datasets:
        d.pop("x", None)
    ytitle = fig.layout.yaxis.title.text if fig.layout.yaxis and fig.layout.yaxis.title else ""
    return {"kind": kind, "labels": labels or [], "datasets": datasets, "y_title": ytitle or ""}


def get_ds(did: str) -> dict | None:
    if did in DATASETS:
        return DATASETS[did]
    if not re.fullmatch(r"[0-9a-f]{12}", did or ""):
        return None
    path = os.path.join(STORE_DIR, did + ".pkl")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            d = pickle.load(f)
    except Exception:
        return None
    d["schema"] = build_schema(d["df"])
    DATASETS[did] = d
    return d


def register(df_raw: pd.DataFrame, name: str, is_sample: bool, lang: str = "en", demo: str | None = None) -> dict:
    df = clean_frame(df_raw)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty or len(df.columns) == 0:
        raise HTTPException(400, "EMPTY_DATA")
    schema = build_schema(df)
    did = uuid.uuid4().hex[:12]
    DATASETS[did] = {"df": df, "schema": schema, "name": name, "is_sample": is_sample, "demo": demo}
    try:
        with open(os.path.join(STORE_DIR, did + ".pkl"), "wb") as f:
            pickle.dump({"df": df, "name": name, "is_sample": is_sample, "demo": demo}, f)
    except Exception:
        pass
    while len(DATASETS) > 50:
        DATASETS.popitem(last=False)
    return describe(did, lang)


def describe(did: str, lang: str = "en") -> dict:
    d = get_ds(did)
    df, schema = d["df"], d["schema"]
    return {
        "id": did, "name": d["name"], "is_sample": d["is_sample"],
        "n_rows": len(df), "n_cols": len(df.columns),
        "columns": [{"name": c.name, "kind": c.kind} for c in schema.columns],
        "preview": frame_rows(df, 100),
        "health": health_report(df, schema),
        "suggestions": DEMO_BY_ID[d["demo"]]["questions"] if d.get("demo") in DEMO_BY_ID else suggestions(schema, "en"),
    }


def read_table(raw: bytes, filename: str) -> pd.DataFrame:
    fn = filename.lower()
    if not raw or not raw.strip():
        raise HTTPException(400, "EMPTY_FILE")
    try:
        if fn.endswith(".xlsx"):
            return pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        if fn.endswith(".xls"):
            return pd.read_excel(io.BytesIO(raw), engine="xlrd")
        for enc in ("utf-8-sig", "latin-1"):
            try:
                try:
                    return pd.read_csv(io.BytesIO(raw), encoding=enc, sep=None, engine="python")
                except pd.errors.ParserError:
                    raise
                except Exception:
                    # the delimiter sniffer fails on one-column files
                    return pd.read_csv(io.BytesIO(raw), encoding=enc)
            except UnicodeDecodeError:
                continue
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"READ_FAILED: {e}")
    raise HTTPException(400, "READ_FAILED")


# API
@app.get("/")
def welcome():
    return FileResponse(os.path.join(BASE, "static", "welcome.html"))


@app.get("/app")
def index():
    return FileResponse(os.path.join(BASE, "static", "index.html"))


@app.get("/api/config")
def config():
    return {"server_key": bool(SERVER_KEY), "model": MODEL}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), lang: str = "en"):
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "FILE_TOO_BIG")
    return register(read_table(raw, file.filename or "data.csv"), file.filename or "data", False, lang)


@app.get("/api/demos")
def demos():
    out = []
    for d in DEMOS:
        path = os.path.join(BASE, "data", "demo", d["file"])
        if os.path.exists(path):
            out.append({"id": d["id"], "title": d["title"], "about": d["about"], "file": d["file"]})
    return out


@app.post("/api/demo/{demo_id}")
def demo(demo_id: str):
    d = DEMO_BY_ID.get(demo_id)
    path = os.path.join(BASE, "data", "demo", d["file"]) if d else ""
    if not d or not os.path.exists(path):
        raise HTTPException(404, "DEMO_NOT_FOUND")
    with open(path, "rb") as f:
        df = read_table(f.read(), d["file"])
    return register(df, d["file"], True, demo=demo_id)


@app.post("/api/photo")
async def photo(request: Request, file: UploadFile = File(...), x_api_key: str | None = Header(default=None)):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "EMPTY_FILE")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "FILE_TOO_BIG")
    cl = client_for(x_api_key)
    rate_check(request, x_api_key)
    t0 = time.perf_counter()
    try:
        csv_text = cl.table_from_image(raw, file.content_type or "image/jpeg")
    except Exception as e:
        raise model_error(e)
    try:
        df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    except Exception:
        raise HTTPException(422, "PHOTO_NOT_TABLE")
    return {"table": frame_rows(df, 500), "seconds": round(time.perf_counter() - t0, 2)}


class TableIn(BaseModel):
    columns: list[str]
    rows: list[list]
    name: str = "Register photo"
    lang: str = "en"


@app.post("/api/table")
def table(body: TableIn):
    cols, seen = [], {}
    for i, c in enumerate(body.columns):
        c = str(c).strip() or f"col_{i + 1}"
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 1
        cols.append(c)
    n = len(cols)
    if not n:
        raise HTTPException(400, "EMPTY_DATA")
    rows = [(list(r) + [None] * n)[:n] for r in body.rows]
    df = pd.DataFrame(rows, columns=cols).replace({"??": None, "": None})
    return register(df, body.name, False, body.lang)


@app.get("/api/dataset/{did}")
def get_dataset(did: str, lang: str = "en"):
    if get_ds(did) is None:
        raise HTTPException(404, "DATASET_GONE")
    return describe(did, lang)


class AskIn(BaseModel):
    dataset_id: str
    question: str
    lang: str = "en"


@app.post("/api/ask")
def ask(request: Request, body: AskIn, x_api_key: str | None = Header(default=None)):
    d = get_ds(body.dataset_id)
    if d is None:
        raise HTTPException(404, "DATASET_GONE")
    q = body.question.strip()[:500]
    if not q:
        raise HTTPException(400, "EMPTY_QUESTION")
    cl = client_for(x_api_key)
    rate_check(request, x_api_key)
    schema_text = d["schema"].to_prompt()
    t0 = time.perf_counter()
    ck = (schema_text, q.lower())
    cached = ck in PLAN_CACHE
    if cached:
        plan = PLAN_CACHE[ck]
    else:
        try:
            plan = cl.plan(schema_text, q)
        except Exception as e:
            raise model_error(e)
        if plan.get("intent") == "unsupported" and GENERAL_Q.search(q) and len(q.split()) <= 8:
            plan = {"intent": "overview"}  # vague "tell me about the data" style question
        PLAN_CACHE[ck] = plan
        while len(PLAN_CACHE) > 1000:
            PLAN_CACHE.popitem(last=False)
    t_model = time.perf_counter() - t0
    ans = run(plan, d["df"], d["schema"])
    t_total = time.perf_counter() - t0
    return {
        "ok": ans.ok, "hi": ans.hi, "en": ans.en, "confidence": ans.confidence,
        "caveats": ans.caveats, "chart": chart_spec(ans.chart),
        "table": frame_rows(ans.table, 30),
        "rows_used": frame_rows(ans.rows_used, 50),
        "rows_used_count": int(len(ans.rows_used)) if ans.rows_used is not None else 0,
        "code": ans.code, "plan": plan,
        "timing": {"total": round(t_total, 2), "model": round(t_model, 2),
                   "calc": round(t_total - t_model, 3), "cached": cached},
    }


class ExplainIn(BaseModel):
    question: str
    result: str
    lang: str = "en"


@app.post("/api/explain")
def explain(request: Request, body: ExplainIn, x_api_key: str | None = Header(default=None)):
    cl = client_for(x_api_key)
    rate_check(request, x_api_key)
    t0 = time.perf_counter()
    try:
        text = cl.insight(body.question, body.result[:3000], body.lang)
    except Exception as e:
        raise model_error(e)
    return {"text": text, "seconds": round(time.perf_counter() - t0, 2)}


@app.exception_handler(HTTPException)
async def http_err(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
