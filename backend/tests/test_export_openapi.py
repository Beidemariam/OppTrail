import json

import pytest

from app.export_openapi import main


def test_main_prints_the_openapi_schema_as_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main()

    schema = json.loads(capsys.readouterr().out)

    assert schema["info"]["title"] == "OppTrail API"
    assert "/api/opportunities" in schema["paths"]
