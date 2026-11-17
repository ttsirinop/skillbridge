from scripts.export_openapi import SPEC_PATH, render_spec


def test_committed_openapi_spec_matches_the_code():
    """Stops the Unit 3 problem: code and documented contract drifting apart.

    If this fails, run `python -m scripts.export_openapi` and commit docs/openapi.json.
    """
    assert SPEC_PATH.read_text(encoding="utf-8") == render_spec()
