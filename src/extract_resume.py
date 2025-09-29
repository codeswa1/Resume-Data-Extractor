import os, sys, pathlib
from docx import Document
from pypdf import PdfReader
from .llm_client import call_llm_resume_json
from .airtable_client import upsert_record, record_exists
from .validators import is_valid_email, normalize_email, normalize_phone, normalize_skills, to_int

def read_text(path: str) -> str:
    p = path.lower()
    if p.endswith(".pdf"):
        try:
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except: return ""
    if p.endswith(".docx"):
        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def extract_one(file_path: str) -> dict:
    txt = read_text(file_path)
    if not txt.strip():
        txt = f"File: {pathlib.Path(file_path).name}\n\n[No text extracted]"

    # Use existing internal extractor (returns normalized dict)
    parsed = call_llm_resume_json(txt)
    name = (parsed.get("name") or "").strip()
    email = normalize_email(parsed.get("email"))
    phone = normalize_phone(parsed.get("phone"))
    skills = normalize_skills(parsed.get("skills"))
    exp_years = to_int(parsed.get("exp_years"), 0)
    current_location = (parsed.get("current_location") or "").strip()
    salary = (parsed.get("salary") or "").strip()
    notice_period = (parsed.get("notice_period") or "").strip()
    job_role = (parsed.get("job_role") or "").strip()

    normalized = {
        "name": name,
        "email": email,
        "phone": phone,
        "skills": skills,
        "exp_years": exp_years,
        "current_location": current_location,
        "salary": salary,
        "notice_period": notice_period,
        "job_role": job_role,
    }
    return {"file": file_path, "parsed": normalized}


def process_path(path: str) -> list:
    p = pathlib.Path(path)
    results = []
    if p.is_dir():
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in (".pdf",".docx",".txt"):
                try:
                    results.append(extract_one(str(f)))
                except Exception as e:
                    results.append({"file": str(f), "error": str(e)})
    else:
        results.append(extract_one(str(p)))
    return results

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.extract_resume <file_or_folder>")
        sys.exit(1)
    out = process_path(sys.argv[1])
    inserted = sum(1 for r in out if "id" in r and "error" not in r and not str(r["id"]).startswith("exists-"))
    skipped = sum(1 for r in out if str(r.get("id","")).startswith("exists-"))
    errors = [r for r in out if "error" in r]

    print(f"Inserted: {inserted}, Skipped (already exists): {skipped}, Errors: {len(errors)}")
    if errors:
        for e in errors:
            print("Error:", e["file"], "->", e.get("error",""))
