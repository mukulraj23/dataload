"""Offline tests: the model is replaced by a fake, so no API key is needed.
Run:  pip install pytest httpx  &&  python -m pytest -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


class FakeGemma:
    def __init__(self, key):
        self.key = key

    def plan(self, schema, q):
        if self.key != "good":
            raise ValueError("400 API key not valid. API_KEY_INVALID")
        if "AC" in q:
            return {"intent": "unsupported", "missing": "AC data"}
        return {"intent": "rank", "metric": "kwh", "agg": "sum", "group_by": "building", "order": "desc"}

    def table_from_image(self, b, m):
        return "date,floor,units\n01/10,Ground,412\n02/10,1st Floor,4??"


server.GemmaClient = FakeGemma
c = TestClient(server.app)


FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "campus_electricity_sample.csv")


def _sample():
    with open(FIX, "rb") as f:
        return c.post("/api/upload", files={"file": ("campus.csv", f.read(), "text/csv")}).json()


def test_sample_loads_with_health_report():
    d = _sample()
    assert d["n_rows"] == 53
    text = " ".join(h["en"] for h in d["health"])
    assert "Library" in text and "Canteen" in text


def test_missing_and_bad_key_are_reported():
    d = _sample()
    server.SERVER_KEY = ""
    assert c.post("/api/ask", json={"dataset_id": d["id"], "question": "top"}).json()["error"] == "API_KEY_MISSING"
    r = c.post("/api/ask", json={"dataset_id": d["id"], "question": "top"}, headers={"X-Api-Key": "bad"})
    assert r.status_code == 401 and r.json()["error"] == "API_KEY_INVALID"


def test_answer_is_code_verified():
    d = _sample()
    r = c.post("/api/ask", json={"dataset_id": d["id"], "question": "sabse zyada"}, headers={"X-Api-Key": "good"}).json()
    df = pd.read_csv(FIX)
    top = df.groupby("building")["kwh"].sum().idxmax()
    assert r["ok"] and top in r["en"] and r["chart"]["labels"][0] == top


def test_unsupported_question_is_honest():
    d = _sample()
    r = c.post("/api/ask", json={"dataset_id": d["id"], "question": "Har AC?"}, headers={"X-Api-Key": "good"}).json()
    assert r["ok"] is False


def test_photo_to_table_flow():
    r = c.post("/api/photo", files={"file": ("r.jpg", b"x", "image/jpeg")}, headers={"X-Api-Key": "good"}).json()
    assert r["table"]["columns"] == ["date", "floor", "units"]
    d = c.post("/api/table", json={"columns": r["table"]["columns"], "rows": r["table"]["rows"]}).json()
    assert d["n_rows"] == 2


def test_overview_and_safe_pandas():
    from core.executor import run
    from core.schema import build_schema, clean_frame
    df = clean_frame(pd.DataFrame({"sex": ["M", "F", "M", "F"], "age": [40, 50, 60, 70], "sick": [1, 0, 1, 1]}))
    s = build_schema(df)
    assert run({"intent": "overview"}, df, s).ok
    ok = run({"intent": "pandas", "code": "result = df.groupby('sex')['sick'].mean()", "label_en": "x"}, df, s)
    assert ok.ok and "M" in ok.en
    for bad in ("import os\nresult = 1", "result = df.__class__", "result = df.to_csv('x')", "result = open('x')"):
        assert run({"intent": "pandas", "code": bad}, df, s).ok is False


def test_every_demo_dataset_loads():
    demos = c.get("/api/demos").json()
    assert len(demos) == 7
    for d in demos:
        r = c.post(f"/api/demo/{d['id']}").json()
        assert r["n_rows"] > 50 and r["is_sample"] and len(r["suggestions"]) == 6


def test_xls_and_one_column_and_empty_files():
    import io
    buf = io.BytesIO()
    pd.DataFrame({"a": [1, 2]}).to_excel(buf, index=False)
    assert c.post("/api/upload", files={"file": ("x.xlsx", buf.getvalue(), "application/octet-stream")}).status_code == 200
    assert c.post("/api/upload", files={"file": ("x.csv", b"name\nA\nB\n", "text/csv")}).status_code == 200
    r = c.post("/api/upload", files={"file": ("x.csv", b"", "text/csv")})
    assert r.status_code == 400 and r.json()["error"] == "EMPTY_FILE"


def test_photo_table_with_bad_shape_is_fixed():
    r = c.post("/api/table", json={"columns": ["a", "a", ""], "rows": [["1", "2", "3", "4"], ["5"]]})
    assert r.status_code == 200
    assert [x["name"] for x in r.json()["columns"]][:2] != ["a", "a"]


def test_dataset_survives_restart():
    d = _sample()
    server.DATASETS.clear()
    assert c.get(f"/api/dataset/{d['id']}").status_code == 200


def test_rate_limit_only_with_server_key():
    d = _sample()
    server.SERVER_KEY, server.RATE_LIMIT = "good", 2
    server._HITS.clear()
    codes = [c.post("/api/ask", json={"dataset_id": d["id"], "question": f"q{i}"}).status_code for i in range(3)]
    assert codes == [200, 200, 429]
    assert c.post("/api/ask", json={"dataset_id": d["id"], "question": "q9"}, headers={"X-Api-Key": "good"}).status_code == 200
    server.SERVER_KEY, server.RATE_LIMIT = "", 20


def test_decimal_comma_and_trimmed_text():
    from core.schema import clean_frame
    df = clean_frame(pd.DataFrame({"m": ["23,06", "0", "-4,93"], "amt": ["1,200", "3,450", "12,000"], "name": [" Focus", "India ", "x"]}))
    assert df["m"].tolist() == [23.06, 0.0, -4.93]
    assert df["amt"].tolist() == [1200, 3450, 12000]
    assert df["name"].tolist() == ["Focus", "India", "x"]
