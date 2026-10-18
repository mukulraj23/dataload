"""All Gemma 4 calls live here.

Speed rules (target: answer in under 4-5 seconds):
1. The model sees only the schema, never the full dataset.
2. The model returns a tiny JSON "query plan" (~40-80 tokens), not code or prose.
3. Thinking is set to minimal, temperature 0, output capped.
4. Same question on same dataset is served from cache.
pandas does all the maths; the explanation is built from templates, so no
second model call is needed for a normal answer.
"""
from __future__ import annotations

import json
import os
import re

MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")

PLAN_PROMPT = """You turn a question about a table into a JSON query plan. Reply with JSON only, no prose.

TABLE SCHEMA (variable name: df)
{schema}

PLAN FORMAT (omit keys you don't need)
{{"intent": "overview|rank|aggregate|trend|compare|ratio|count|distribution|pandas|unsupported",
 "metric": "<number column>",
 "agg": "sum|mean|max|min|median|count",
 "group_by": "<column>",
 "filters": [{{"col": "<column>", "op": "==|!=|>|<|>=|<=|in|contains", "value": <value or list>}}],
 "compare": {{"col": "<column>", "a": <value>, "b": <value>}},
 "denominator": "<number column, only for ratio e.g. per student>",
 "order": "desc|asc", "top_n": <int>,
 "code": "<only for intent pandas>", "label_en": "<only for pandas: 3-8 word English label of the result>",
 "label_hi": "<only for pandas: same label in simple Hinglish>",
 "missing": "<only for unsupported: what data is missing>"}}

WHICH INTENT
- overview: general/vague questions about the data itself ("tell me about this data", "data ke baare mein batao",
  "summary", "kya hai isme").
- rank: highest/lowest/top N of a metric per group. Use agg "mean" for per-person/per-row values (age, marks,
  cholesterol, price) and "sum" for amounts that add up (sales, units, bill).
- trend: change over time (uses the time column). compare: A vs B. ratio: metric per denominator.
- aggregate: one total/average/max. count: how many rows (with filters). distribution: how values of ONE column
  are spread ("kitne log kis type mein", "age distribution") -> put that column in group_by.
- pandas: anything else the columns CAN answer (percentages, conditions on several columns, cross-tabs,
  correlations, "how many X have Y", "% of patients with heart disease by sex"). Write short pandas code that
  uses only `df`, `pd`, `np` and assigns the final answer to `result` (a number, a Series, or a small DataFrame).
  No imports, no files, no printing, no loops. Max 4 lines. Example:
  "result = (df.groupby('sex')['heartdisease'].mean() * 100).round(1).sort_values(ascending=False)"
- unsupported: ONLY when the needed information is truly not in any column. Never invent columns.

RULES
- Use exact column names and exact category values from the schema.
- "last month"/"pichle mahine" = the latest value of the time column.
- The question may be in Hindi, Hinglish or English, and may have typos.

QUESTION: {question}
JSON:"""

IMAGE_PROMPT = """This image is a photo of a table or register (possibly handwritten, Hindi or English).
Transcribe it as CSV. First line = column headers in short English snake_case.
Write numbers without commas or units. If a cell is unreadable write ?? .
Reply with CSV only."""

INSIGHT_PROMPT = """You are a helpful data assistant for non-technical people in India.
Below is a question, and a result that was ALREADY CALCULATED by code. Do not change any number.
Write {lang} in 2 short sentences: what it means, and one practical action. Simple words.

QUESTION: {question}
RESULT:
{result}
"""


class GemmaClient:
    def __init__(self, api_key: str):
        from google import genai
        from google.genai import types

        self._types = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15000))

    def _config(self, max_tokens: int, timeout_ms: int | None = None):
        t = self._types
        return t.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_tokens,
            thinking_config=t.ThinkingConfig(thinking_level="minimal"),
            http_options=t.HttpOptions(timeout=timeout_ms) if timeout_ms else None,
        )

    def plan(self, schema_text: str, question: str) -> dict:
        prompt = PLAN_PROMPT.format(schema=schema_text, question=question)
        resp = self.client.models.generate_content(model=MODEL, contents=prompt, config=self._config(400))
        return parse_json(resp.text or "")

    def table_from_image(self, image_bytes: bytes, mime: str) -> str:
        part = self._types.Part.from_bytes(data=image_bytes, mime_type=mime)
        resp = self.client.models.generate_content(model=MODEL, contents=[part, IMAGE_PROMPT],
                                                   config=self._config(4096, timeout_ms=60000))
        text = (resp.text or "").strip()
        return re.sub(r"^```(csv)?|```$", "", text, flags=re.M).strip()

    def insight(self, question: str, result_text: str, lang: str) -> str:
        prompt = INSIGHT_PROMPT.format(question=question, result=result_text,
                                       lang="in simple Hindi (Devanagari)" if lang == "hi" else "in simple English")
        resp = self.client.models.generate_content(model=MODEL, contents=prompt, config=self._config(200))
        return (resp.text or "").strip()


def parse_json(text: str) -> dict:
    text = re.sub(r"```(json)?", "", text)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return {"intent": "unsupported", "missing": "Model ka jawab samajh nahi aaya / could not read model output"}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"intent": "unsupported", "missing": "Model ka jawab samajh nahi aaya / could not read model output"}
