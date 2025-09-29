# src/validators.py
import re

def normalize_email(email: str) -> str:
    if not email or not isinstance(email, str):
        return ""
    email = email.strip().lower()
    if re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return email
    return ""

def is_valid_email(email: str) -> bool:
    return bool(normalize_email(email))

def normalize_phone(phone: str) -> str:
    if not phone or not isinstance(phone, str):
        return ""
    # Keep only digits and leading '+'
    phone = re.sub(r"[^\d+]", "", phone)
    return phone

def normalize_skills(skills) -> str:
    if not skills:
        return ""
    if isinstance(skills, str):
        skill_list = [s.strip().lower() for s in re.split(r",|;|\n", skills) if s.strip()]
        return ", ".join(skill_list)
    if isinstance(skills, (list, tuple)):
        skill_list = [str(s).strip().lower() for s in skills if s]
        return ", ".join(skill_list)
    return str(skills).strip().lower()

def to_int(value, default=0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        # extract digits
        import re
        m = re.search(r"\d+", str(value))
        if m:
            return int(m.group())
    return default
