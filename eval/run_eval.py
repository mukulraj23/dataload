"""Accuracy + speed test for DataLoad .

    GEMINI_API_KEY=xxx python eval/run_eval.py

For each test question: ask Gemma 4 for a plan, run it, and compare the answer
with the answer from a hand-written correct ("gold") plan. Also records latency.
"""
import csv
import json
import os
import statistics
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.executor import run  # noqa: E402
from core.llm import GemmaClient  # noqa: E402
from core.schema import build_schema, clean_frame  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
df = clean_frame(pd.read_csv(os.path.join(BASE, "tests/fixtures/campus_electricity_sample.csv")))
schema = build_schema(df)
client = GemmaClient(os.environ["GEMINI_API_KEY"])

results = []
with open(os.path.join(BASE, "eval/test_questions.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        gold = run(json.loads(row["gold_plan"]), df, schema)
        t0 = time.perf_counter()
        try:
            plan = client.plan(schema.to_prompt(), row["question"])
        except Exception as e:  # network / quota
            plan = {"intent": "unsupported", "missing": str(e)}
        got = run(plan, df, schema)
        secs = time.perf_counter() - t0
        correct = (got.ok == gold.ok) and (not gold.ok or got.en == gold.en)
        results.append({"question": row["question"], "correct": correct, "seconds": round(secs, 2),
                        "answer": got.en, "expected": gold.en})
        print(f"{'PASS' if correct else 'FAIL'}  {secs:4.1f}s  {row['question']}")

out = pd.DataFrame(results)
out.to_csv(os.path.join(BASE, "eval/results.csv"), index=False)
acc = out.correct.mean() * 100
print(f"\nAccuracy: {acc:.0f}%  |  median {statistics.median(out.seconds):.1f}s  |  max {out.seconds.max():.1f}s")
print("Saved eval/results.csv")
