"""Tests for the JSON Schema template exporter."""

from scripts.export_schemas import DOMAINS, build_template, export_all


def test_build_template_returns_schema_aliases_examples():
    t = build_template("alerts")
    assert "schema" in t and "aliases" in t and "examples" in t
    assert t["schema"]["type"] == "object"
    assert "symbol" in t["schema"]["required"]
    assert "symbol" in t["aliases"]
    assert len(t["examples"]) >= 1


def test_export_all_writes_seven_files(tmp_path):
    export_all(tmp_path)
    files = sorted(p.name for p in tmp_path.glob("*.json"))
    assert files == sorted(f"{d}.json" for d in DOMAINS)


def test_every_required_field_has_aliases():
    for domain in DOMAINS:
        t = build_template(domain)
        for f in t["schema"]["required"]:
            assert f in t["aliases"], f"{domain}: required field {f!r} has no aliases"


def test_examples_are_valid_against_schema():
    from jsonschema import validate

    for domain in DOMAINS:
        t = build_template(domain)
        for ex in t["examples"]:
            validate(ex, t["schema"])
