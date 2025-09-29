# src/__init__.py
"""
Package initializer for resume parsing project.
Allows imports like:
    from src import extract_one, call_llm_resume_json
"""

from .extract_resume import extract_one, process_path
from .llm_client import call_llm_resume_json
from .validators import (
    normalize_email,
    normalize_phone,
    normalize_skills,
    to_int,
    is_valid_email,
)

# Optional: Airtable upsert (mock-safe if not configured)
try:
    from .airtable_client import upsert_record, record_exists, find_record_by_name
except Exception:
    upsert_record = None
    record_exists = None
    find_record_by_name = None

__all__ = [
    "extract_one",
    "process_path",
    "call_llm_resume_json",
    "normalize_email",
    "normalize_phone",
    "normalize_skills",
    "to_int",
    "is_valid_email",
    "upsert_record",
    "record_exists",
]
