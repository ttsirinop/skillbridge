"""Parses and validates an employee-profile CSV before anything touches the database.

Expected columns: full_name, email, department, skills, summary
- skills are separated by semicolons, for example "Python; FastAPI; PostgreSQL"
- department and summary may be blank

Bad rows are reported with their line number instead of failing the whole file, so one typo
doesn't block 999 good rows.
"""

import csv
import io

from pydantic import ValidationError

from app.schemas import ImportRowError, ProfileCreate

REQUIRED_COLUMNS = ("full_name", "email", "skills")
OPTIONAL_COLUMNS = ("department", "summary")
MAX_ROWS = 1000
MAX_BYTES = 1_000_000


class CsvFormatError(ValueError):
    """The file as a whole is unusable (wrong encoding, missing columns, too many rows)."""


def parse_profiles_csv(content: bytes) -> tuple[list[ProfileCreate], list[ImportRowError]]:
    if len(content) > MAX_BYTES:
        raise CsvFormatError(f"File is larger than {MAX_BYTES // 1000} KB.")
    try:
        text = content.decode("utf-8-sig")  # tolerate the BOM Excel adds
    except UnicodeDecodeError as exc:
        raise CsvFormatError("File must be UTF-8 encoded CSV.") from exc

    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise CsvFormatError(f"Missing required column(s): {', '.join(missing)}.")
    reader.fieldnames = headers

    valid: list[ProfileCreate] = []
    errors: list[ImportRowError] = []
    seen_emails: set[str] = set()

    for index, raw in enumerate(reader):
        line = index + 2  # line 1 is the header
        if index >= MAX_ROWS:
            raise CsvFormatError(f"File has more than {MAX_ROWS} rows.")
        if raw is None or not any((v or "").strip() for k, v in raw.items() if k is not None):
            continue  # skip blank lines

        record = {
            "full_name": (raw.get("full_name") or "").strip(),
            "email": (raw.get("email") or "").strip(),
            "department": (raw.get("department") or "").strip() or None,
            "skills": [s for s in (raw.get("skills") or "").split(";")],
            "summary": (raw.get("summary") or "").strip(),
        }
        try:
            profile = ProfileCreate(**record)
        except ValidationError as exc:
            for err in exc.errors():
                field = str(err["loc"][0]) if err["loc"] else None
                errors.append(ImportRowError(row=line, field=field, message=err["msg"]))
            continue

        if profile.email in seen_emails:
            errors.append(ImportRowError(row=line, field="email", message="Duplicate email in this file."))
            continue
        seen_emails.add(profile.email)
        valid.append(profile)

    return valid, errors
