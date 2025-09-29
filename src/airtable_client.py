# src/airtable_client.py
from dotenv import load_dotenv
load_dotenv()

import os
import requests
import urllib.parse
import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

API_BASE = "https://api.airtable.com/v0"
TOKEN = os.getenv("AIRTABLE_TOKEN")
BASE = os.getenv("AIRTABLE_BASE_ID")
HEADERS = {"Content-Type": "application/json"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

_AIRTABLE_CONFIGURED = bool(TOKEN and BASE)
if not _AIRTABLE_CONFIGURED:
    logger.warning("Airtable not configured (AIRTABLE_TOKEN/AIRTABLE_BASE_ID missing). Using mock mode.")


def _quote_table(table: str) -> str:
    return urllib.parse.quote(table, safe="")


def _cache_dir() -> Path:
    d = Path(".cache")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    p = _cache_dir() / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    p = _cache_dir() / f"{key}.json"
    p.write_text(json.dumps(value, indent=2), encoding="utf-8")


def get_table_fields(table: str, use_cache: bool = True, force_refresh: bool = False) -> List[str]:
    """
    Return a list of Airtable field names for `table`. Uses a lightweight GET (maxRecords=1).
    Caches result to .cache/airtable_fields_{base}_{table}.json
    """
    key = f"airtable_fields_{BASE}_{table}"
    if use_cache and not force_refresh:
        cached = _cache_get(key)
        if cached and isinstance(cached, dict) and "fields" in cached:
            return cached["fields"]

    if not _AIRTABLE_CONFIGURED:
        # nothing to query, return empty list
        logger.info("Airtable not configured; returning empty field list for %s", table)
        return []

    url = f"{API_BASE}/{BASE}/{_quote_table(table)}"
    try:
        r = requests.get(url, headers=HEADERS, params={"maxRecords": 1}, timeout=30)
    except requests.RequestException as ex:
        logger.exception("Network error calling Airtable to fetch fields: %s", ex)
        return []

    if r.status_code in (401, 403):
        logger.error("Airtable unauthorized when fetching fields (status=%s). Check AIRTABLE_TOKEN.", r.status_code)
        return []

    try:
        r.raise_for_status()
    except requests.HTTPError:
        logger.exception("Airtable returned error when fetching fields: %s", r.text[:1000])
        return []

    records = r.json().get("records", [])
    if not records:
        # no records yet; we cannot infer fields from a record, but try the keys of first record fallback
        logger.info("No records in table %s; returning empty fields list", table)
        _cache_set(key, {"fields": []})
        return []

    # get keys from the `fields` object of the first record
    first = records[0].get("fields", {})
    field_names = list(first.keys())
    _cache_set(key, {"fields": field_names})
    logger.info("Discovered %d fields for table %s (cached)", len(field_names), table)
    return field_names


def record_exists(table: str, key_field: str, key_value: str) -> bool:
    if not _AIRTABLE_CONFIGURED:
        return False
    safe_val = str(key_value).replace("'", "\\'")
    formula = f"{{{key_field}}}='{safe_val}'"
    url = f"{API_BASE}/{BASE}/{_quote_table(table)}"
    try:
        r = requests.get(url, headers=HEADERS, params={"filterByFormula": formula, "maxRecords": 1}, timeout=30)
    except requests.RequestException as ex:
        logger.exception("Network error calling Airtable record_exists: %s", ex)
        return False

    if r.status_code in (401, 403):
        logger.error("Airtable unauthorized for record_exists (status=%s). Check AIRTABLE_TOKEN permissions.", r.status_code)
        return False

    try:
        r.raise_for_status()
    except requests.HTTPError:
        logger.exception("Airtable record_exists HTTP error: %s", r.text[:500])
        return False

    records = r.json().get("records", [])
    return bool(records)

def find_record_by_name(table_name: str, name: str):
    """
    Find a record in Airtable by its Name field.
    Returns the record dict (with 'id') or None if not found.
    """
    from requests import get
    import os

    base_id = os.getenv("AIRTABLE_BASE_ID")
    api_key = os.getenv("AIRTABLE_API_KEY")
    url = f"https://api.airtable.com/v0/{base_id}/{table_name}?filterByFormula=NAME()='{name}'"

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = get(url, headers=headers)
    resp.raise_for_status()
    records = resp.json().get("records", [])
    return records[0] if records else None


def upsert_record(table: str, key_field: str, key_value: str, fields: dict) -> Dict[str, Any]:
    """
    Upsert record. If Airtable not configured -> return mock record.
    If unauthorized while trying to create/update -> return mock record.
    """
    if not _AIRTABLE_CONFIGURED:
        mock_id = f"mock-{str(key_value).replace(' ', '_')}"
        logger.info("Airtable not configured, returning mock record id=%s for table=%s", mock_id, table)
        return {"id": mock_id, "fields": fields}

    try:
        exists = record_exists(table, key_field, key_value)
    except Exception as ex:
        logger.warning("Error when checking for existing record: %s. Proceeding to create.", ex)
        exists = False

    if exists:
        mock_id = f"exists-{str(key_value).replace(' ', '_')}"
        logger.info("Record exists, skipping creation: %s=%s", key_field, key_value)
        return {"id": mock_id, "fields": fields}

    url = f"{API_BASE}/{BASE}/{_quote_table(table)}"
    payload = {"fields": fields}
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    except requests.RequestException as ex:
        logger.exception("Network error creating Airtable record: %s", ex)
        raise

    if r.status_code in (401, 403):
        logger.error("Airtable create unauthorized (status=%s). Returning mock record. Check AIRTABLE_TOKEN.", r.status_code)
        mock_id = f"mock-{str(key_value).replace(' ', '_')}"
        return {"id": mock_id, "fields": fields}

    if r.status_code == 422:
        # helpful debug details: include Airtable response and payload in logs
        logger.error("Airtable returned 422 Unprocessable Entity. Response: %s", r.text[:2000])
        logger.error("Payload that caused 422: %s", json.dumps(payload, indent=2))
        # re-raise to let caller decide how to handle (import_resumes will catch and log)
        r.raise_for_status()

    r.raise_for_status()
    return r.json()
