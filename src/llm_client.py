from dotenv import load_dotenv
load_dotenv()

import os
import json
import re
import logging
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from openai import OpenAI
except Exception as e:
    raise RuntimeError("OpenAI SDK import failed. Ensure 'openai' package (v1+) is installed.") from e

from .validators import normalize_email, normalize_phone, normalize_skills, to_int

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("src.llm_client")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not found in environment (.env)")

client = OpenAI(api_key=OPENAI_API_KEY)

JSON_PROMPT_TMPL = """You are a strict resume parser. Respond with JSON ONLY (no prose).
Return a single JSON object with keys exactly:
Candidate Name, Email, Phone, Skills, Exp Years, Source, ResumeURL, Salary, Notice Period, Current Location, Status, Job Role

Rules:
- If a value is missing, return empty string "" (or 0 for Exp Years)
- Candidate Name: full name
- Email: extract email
- Phone: digits + + only
- Skills: comma-separated lowercase string
- Exp Years: integer number
- Source: set to "CV Upload" by default
- ResumeURL: string (empty if unknown)
- Status: "New" by default
- Job Role: extract if mentioned
- Do not return extra keys

Resume text:
{resume}
"""

def _clean_model_output(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s, flags=re.IGNORECASE)
    return s.strip()

def _extract_json(text: str) -> Dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response")
    sub = text[start:]
    depth = 0
    for i, ch in enumerate(sub):
        if ch == "{": depth += 1
        elif ch == "}": depth -= 1
        if depth == 0:
            candidate = sub[:i+1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    return json.loads(text)

def _ensure_keys(parsed: Dict[str, Any]) -> Dict[str, Any]:
    keys = ["Candidate Name", "Email", "Phone", "Skills", "Exp Years", "Source", "ResumeURL",
            "Salary", "Notice Period", "Current Location", "Status", "Job Role"]
    for k in keys:
        if k not in parsed:
            parsed[k] = "" if k != "Exp Years" else 0
    return parsed

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8),
       retry=retry_if_exception_type(Exception))
def _call_openai_chat(prompt: str, model: str = "gpt-4o-mini") -> str:
    logger.info("Calling OpenAI model %s (prompt len=%d)", model, len(prompt))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts structured JSON from resumes."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1000,
        temperature=0.0,
    )
    try:
        choice = response.choices[0]
        content = getattr(choice.message, "content", "") if hasattr(choice, "message") else getattr(choice, "text", "")
        return str(content).strip()
    except Exception:
        raise ValueError(f"Failed to extract assistant content; raw response: {str(response)[:1000]}")

def call_llm_resume_json(resume_text: str) -> Dict[str, Any]:
    if not isinstance(resume_text, str):
        raise ValueError("resume_text must be a string")
    prompt = JSON_PROMPT_TMPL.format(resume=resume_text[:16000])
    raw = _call_openai_chat(prompt, model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    cleaned = _clean_model_output(raw)
    parsed = _extract_json(cleaned)
    parsed = _ensure_keys(parsed)

    normalized = {
        "Candidate Name": (parsed.get("Candidate Name") or "").strip(),
        "Email": normalize_email(parsed.get("Email")),
        "Phone": normalize_phone(parsed.get("Phone")),
        "Skills": normalize_skills(parsed.get("Skills")),
        "Exp Years": to_int(parsed.get("Exp Years"), 0),
        "Source": (parsed.get("Source") or "CV Upload").strip(),
        "ResumeURL": (parsed.get("ResumeURL") or "").strip(),
        "Salary": (parsed.get("Salary") or "").strip(),
        "Notice Period": (parsed.get("Notice Period") or "").strip(),
        "Current Location": (parsed.get("Current Location") or "").strip(),
        "Status": (parsed.get("Status") or "New").strip(),
        "Job Role": (parsed.get("Job Role") or "").strip(),
    }
    return normalized
