#!/usr/bin/env python3
import argparse, pathlib, logging, os, sys, json
from dotenv import load_dotenv
load_dotenv()
from src.llm_client import call_llm_resume_json
from src.validators import normalize_email, normalize_phone, normalize_skills, to_int, is_valid_email
from src.airtable_client import upsert_record, record_exists

# date parsing
try:
    from dateutil.parser import parse as dateparse
except Exception:
    dateparse = None
    from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_resumes")

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt"}

# Fixed fields we will send to Airtable (no linked-record fields or lookups from Jobs)
FIXED_FIELDS = [
    "Candidate Name", "Email", "Phone", "Skills", "Exp Years",
    "Source", "ResumeURL", "Salary", "Notice Period",
    "Current Location", "Status", "Candidate Status", "Job Role",
]

def iter_resume_files(path: str):
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if p.is_dir():
        return sorted([f for f in p.iterdir() if f.suffix.lower() in SUPPORTED_SUFFIXES])
    if p.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {p.suffix}")
    return [p]

def read_text(path: str) -> str:
    try:
        p = str(path).lower()
        if p.endswith(".pdf"):
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        if p.endswith(".docx"):
            from docx import Document
            doc = Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
    except Exception as e:
        logger.warning("Failed specialized extraction for %s: %s", path, e)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()

def _parse_date_to_iso(val):
    """Return ISO date string 'YYYY-MM-DD' or empty string if invalid/missing."""
    if not val:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    # try dateutil if available
    try:
        if dateparse:
            dt = dateparse(s, fuzzy=True)
            return dt.date().isoformat()
        else:
            # simple fallback attempts
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    dt = datetime.strptime(s, fmt)
                    return dt.date().isoformat()
                except Exception:
                    continue
    except Exception:
        return ""
    return ""

def coerce_fields(parsed: dict):
    """Normalize and coerce values for Airtable insertion."""
    payload = {}

    # Allowed options for single-select fields in Airtable (must match Airtable exactly)
    ALLOWED_SOURCES = ["Referral", "Website", "LinkedIn", "Event", "Other"]
    ALLOWED_STATUS = ["New", "Screened", "Shortlisted", "Rejected", "Contacted", "Interview", "Hired"]
    ALLOWED_CANDIDATE_STATUS = ["CV Sent", "Interview Scheduled", "Feedback Received", "Offer Sent", "Offer Accepted", "Candidate Joined"]

    for field in FIXED_FIELDS:
        value = parsed.get(field)

        # Numeric fields -> int or None (Airtable numeric must not be empty string)
        if field in ("Exp Years", "Salary"):
            try:
                value = to_int(value)
                if value == 0:
                    raw = parsed.get(field)
                    if raw is None or str(raw).strip() == "" or not any(ch.isdigit() for ch in str(raw)):
                        value = None
            except Exception:
                value = None

        # Email
        elif field == "Email":
            value = normalize_email(value) if value else ""

        # Phone
        elif field == "Phone":
            value = normalize_phone(value) if value else ""

        # Skills
        elif field == "Skills":
            value = normalize_skills(value) if value else ""

        # Resume URL -> empty string if None (Airtable URL accepts "" or valid URL)
        elif field == "ResumeURL":
            if value and str(value).strip():
                value = str(value).strip()
            else:
                value = ""

        # Single-select fields -> only allowed options
        elif field == "Source":
            val = (value or "").strip()
            value = val if val in ALLOWED_SOURCES else None

        elif field == "Status":
            val = (value or "").strip()
            value = val if val in ALLOWED_STATUS else None

        elif field == "Candidate Status":
            val = (value or "").strip()
            value = val if val in ALLOWED_CANDIDATE_STATUS else None

        # Date fields -> ISO date OR None (do NOT send empty string)
        #elif field in ("CV Sent Date", "Offer Date", "Joining Date"):
            #iso = _parse_date_to_iso(value)
            #value = iso if iso else None
        # Default: empty string if None (safe for text fields)
        else:
            value = value or ""

        payload[field] = value

    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import resumes into Airtable (fixed schema).")
    ap.add_argument("path", help="File or directory containing resumes")
    ap.add_argument("--table", default=os.getenv("AIRTABLE_TABLE_NAME", "Candidates"),
                    help="Airtable table name")
    ap.add_argument("--dry-run", action="store_true", help="Don't upsert; just print payloads")
    args = ap.parse_args(argv)

    try:
        files = iter_resume_files(args.path)
    except Exception as e:
        logger.error("Error enumerating files: %s", e)
        sys.exit(1)

    inserted = skipped_exists = skipped_invalid = errors = 0
    details = []

    for f in files:
        fpath = str(f)
        logger.info("Processing: %s", fpath)
        try:
            txt = read_text(fpath)
            if not txt.strip():
                txt = f"File: {f.name}\n[No text extracted]"

            parsed = call_llm_resume_json(txt)
            payload = coerce_fields(parsed)

            # dedupe key: email if valid, else candidate name
            email = payload.get("Email")
            name = payload.get("Candidate Name") or f.name
            dedupe_key = email if is_valid_email(email) else name

            try:
                exists = record_exists(args.table, "Email", dedupe_key)
            except Exception as e:
                logger.warning("Existence check failed for %s: %s — proceeding", dedupe_key, e)
                exists = False

            if exists:
                logger.info("Record already exists, skipping: %s", dedupe_key)
                skipped_exists += 1
                details.append({"file": fpath, "status": "skipped_exists", "key": dedupe_key})
                continue

            if args.dry_run:
                logger.info("[DRY RUN] Would upsert: key=%s payload=%s", dedupe_key, json.dumps(payload, indent=2))
                details.append({"file": fpath, "status": "dry_run", "key": dedupe_key, "payload": payload})
                continue

            rec = upsert_record(args.table, "Email", dedupe_key, payload)
            rec_id = rec.get("id")
            logger.info("Upserted %s -> id=%s", dedupe_key, rec_id)
            inserted += 1
            details.append({"file": fpath, "status": "inserted", "key": dedupe_key, "id": rec_id})

        except Exception as e:
            logger.exception("Error processing %s: %s", fpath, e)
            errors += 1
            details.append({"file": fpath, "status": "error", "error": str(e)})

    # Summary
    print("\n===== Import Summary =====")
    print(f"Total files processed : {len(files)}")
    print(f"Inserted             : {inserted}")
    print(f"Skipped (exists)     : {skipped_exists}")
    print(f"Skipped (invalid)    : {skipped_invalid}")
    print(f"Errors               : {errors}")
    print("==========================\n")

    for d in details:
        s = d.get("status")
        fp = d.get("file")
        if s == "inserted":
            print(f"[INSERTED] {fp} -> {d.get('key')} (id={d.get('id')})")
        elif s == "skipped_exists":
            print(f"[SKIP:EXISTS] {fp} -> {d.get('key')}")
        elif s == "dry_run":
            print(f"[DRY RUN] {fp} -> {d.get('key')}")
            print(json.dumps(d.get("payload", {}), indent=2))
        else:
            print(f"[ERROR] {fp} -> {d.get('error')}")

    sys.exit(0 if errors == 0 else 2)

if __name__ == "__main__":
    main()
