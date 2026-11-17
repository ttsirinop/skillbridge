import pytest

from app.api.csv_import import MAX_ROWS, CsvFormatError, parse_profiles_csv

HEADER = "full_name,email,department,skills,summary\n"


def test_parse_valid_rows_and_report_bad_ones():
    content = (
        HEADER
        + "Avery Brooks,avery@example.com,Engineering,Python; FastAPI,Backend dev\n"
        + "No Email,,Engineering,Python,\n"
        + "Jordan Kim,jordan@example.com,,,\n"
        + "Avery Again,AVERY@example.com,Engineering,SQL,\n"
        + "\n"
        + "Riley Novak,riley@example.com,Data Science,SQL; pandas,\n"
    ).encode()
    valid, errors = parse_profiles_csv(content)

    assert [p.email for p in valid] == ["avery@example.com", "riley@example.com"]
    assert valid[0].skills == ["Python", "FastAPI"]
    assert {(e.row, e.field) for e in errors} == {(3, "email"), (4, "skills"), (5, "email")}


def test_excel_bom_and_header_case_are_tolerated():
    content = ("﻿Full_Name,EMAIL,Skills\nAvery Brooks,avery@example.com,Python\n").encode("utf-8")
    valid, errors = parse_profiles_csv(content)
    assert len(valid) == 1 and not errors


@pytest.mark.parametrize(
    "content, message",
    [
        (b"name,email\nA,a@example.com\n", "Missing required column"),
        ("full_name,email,skills\nÁ,a@example.com,x\n".encode("latin-1"), "UTF-8"),
        ((HEADER + "A,a{}@example.com,,x,\n" * (MAX_ROWS + 1)).encode(), "more than"),
    ],
    ids=["missing-columns", "not-utf8", "too-many-rows"],
)
def test_unusable_files_are_rejected(content, message):
    with pytest.raises(CsvFormatError, match=message):
        parse_profiles_csv(content)


@pytest.mark.db
def test_import_endpoint_creates_then_updates(clean_db, client):
    first = HEADER + "Avery Brooks,avery@example.com,Engineering,Python; FastAPI,\nBad Row,bad,,Python,\n"
    resp = client.post("/profiles/import", files={"file": ("people.csv", first, "text/csv")})
    assert resp.status_code == 200
    assert resp.json()["created"] == 1 and resp.json()["updated"] == 0
    assert resp.json()["errors"][0]["row"] == 3

    second = HEADER + "Avery Brooks,avery@example.com,Data Science,SQL,\n"
    resp = client.post("/profiles/import", files={"file": ("people.csv", second, "text/csv")})
    assert resp.json() == {"created": 0, "updated": 1, "errors": []}

    profile = client.get("/profiles/1").json()
    assert profile["department"] == "Data Science" and profile["skills"] == ["SQL"]


@pytest.mark.db
def test_import_endpoint_rejects_bad_files(clean_db, client):
    resp = client.post("/profiles/import", files={"file": ("x.csv", b"name\nA\n", "text/csv")})
    assert resp.status_code == 400
    big = b"a" * 1_000_001
    resp = client.post("/profiles/import", files={"file": ("x.csv", big, "text/csv")})
    assert resp.status_code == 413
