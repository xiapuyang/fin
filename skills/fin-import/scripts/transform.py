"""Map arbitrary row dicts to canonical schema via template aliases.

Gaps (unmapped column, missing required, ambiguous date) are returned in the
result for the caller to ask the user about — we never silently guess.

CLI usage (matches SKILL.md contract):
    python transform.py --type <domain> --rows <path|json> \\
        [--default-account NAME] [--snapshot-id N]
    --rows accepts either a file path or an inline JSON list.
    Output is JSON {"rows": [...], "gaps": [...]} to stdout.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@dataclass
class Gap:
    kind: str  # 'missing_required' | 'unmapped_column' | 'ambiguous_date' | 'bad_type'
    field: str | None = None
    row_index: int | None = None
    message: str = ""


@dataclass
class TransformResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)


def _invert(
    aliases: dict[str, list[str]],
    properties: dict[str, Any] | None = None,
    extra_fields: list[str] | None = None,
) -> dict[str, str]:
    """Build a lowercase alias -> canonical lookup.

    Schema property names are auto-registered as identity aliases so a CSV
    column literally named like a canonical field (e.g. `currency`) maps even
    when the template's `aliases` dict omits an entry for it. Without this,
    such columns are silently dropped and the schema default takes over —
    a data-corruption hazard (e.g. HKD overwritten by USD default).

    `extra_fields` enables pass-through of non-schema columns the skill needs
    for resolution steps (e.g. balance items carry `account` / `sub_account`
    names before the skill swaps them for `account_id` / `sub_account_id`).
    """
    out: dict[str, str] = {}
    if properties:
        for canonical in properties:
            out[canonical.lower()] = canonical
    if extra_fields:
        for canonical in extra_fields:
            out[canonical.lower()] = canonical
    for canonical, syns in aliases.items():
        out[canonical.lower()] = canonical
        for s in syns:
            out[s.lower()] = canonical
    return out


def _coerce(value: Any, schema_type: str) -> Any:
    """Coerce a raw cell value to the schema's declared type."""
    if value is None or value == "":
        return None
    if schema_type == "number":
        return float(str(value).replace(",", ""))
    if schema_type == "integer":
        return int(float(str(value).replace(",", "")))
    if schema_type == "boolean":
        return str(value).lower() in ("true", "1", "yes", "y")
    return value


def _ambiguous_date(value: str) -> bool:
    """Return True if both first two date parts are 1-12 and differ."""
    if not isinstance(value, str):
        return False
    parts = [p for p in value.replace("-", "/").split("/") if p]
    if len(parts) != 3:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 1 <= a <= 12 and 1 <= b <= 12 and a != b


def transform(
    rows: list[dict[str, Any]],
    template: dict,
    default_account: str | None = None,
    snapshot_id: int | None = None,
) -> TransformResult:
    """Map raw rows to canonical schema; collect gaps for caller to resolve."""
    aliases = template.get("aliases", {})
    schema = template["schema"]
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    extra_fields = template.get("extra_fields", []) or []
    alias_map = _invert(aliases, properties, extra_fields)

    result = TransformResult()

    for idx, raw in enumerate(rows):
        canonical: dict[str, Any] = {}
        for k, v in raw.items():
            mapped = alias_map.get(k.lower()) if k else None
            if not mapped:
                result.gaps.append(
                    Gap(
                        kind="unmapped_column",
                        field=k,
                        row_index=idx,
                        message=f"row {idx}: column {k!r} has no alias mapping",
                    )
                )
                continue
            prop = properties.get(mapped, {})
            schema_type = prop.get("type", "string")
            try:
                canonical[mapped] = _coerce(v, schema_type)
            except (ValueError, TypeError):
                result.gaps.append(
                    Gap(
                        kind="bad_type",
                        field=mapped,
                        row_index=idx,
                        message=(
                            f"row {idx}: {mapped}={v!r} not coercible to {schema_type}"
                        ),
                    )
                )
                continue
            if "date" in mapped.lower() and _ambiguous_date(v):
                result.gaps.append(
                    Gap(
                        kind="ambiguous_date",
                        field=mapped,
                        row_index=idx,
                        message=f"row {idx}: date {v!r} ambiguous (DD/MM vs MM/DD)",
                    )
                )

        if default_account and "account" not in canonical and "account" in properties:
            canonical["account"] = default_account
        if (
            snapshot_id
            and "snapshot_id" not in canonical
            and "snapshot_id" in properties
        ):
            canonical["snapshot_id"] = snapshot_id

        for req in required:
            if req not in canonical or canonical[req] is None:
                result.gaps.append(
                    Gap(
                        kind="missing_required",
                        field=req,
                        row_index=idx,
                        message=f"row {idx}: missing required field {req!r}",
                    )
                )

        result.rows.append(canonical)
    return result


def _load_rows(arg: str) -> list[dict]:
    """Accept either an inline JSON list or a file path."""
    stripped = arg.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(arg)
    return json.loads(Path(arg).read_text())


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--type",
        required=True,
        help="domain name (alerts, transactions, holdings, income, ledger, balance, watchlist)",
    )
    p.add_argument("--rows", required=True, help="path to JSON list or inline JSON")
    p.add_argument("--default-account", default=None)
    p.add_argument("--snapshot-id", type=int, default=None)
    args = p.parse_args()

    template_path = TEMPLATES_DIR / f"{args.type}.json"
    if not template_path.exists():
        print(
            f"error: no template for type {args.type!r} at {template_path}",
            file=sys.stderr,
        )
        return 2
    template = json.loads(template_path.read_text())
    rows = _load_rows(args.rows)
    result = transform(
        rows=rows,
        template=template,
        default_account=args.default_account,
        snapshot_id=args.snapshot_id,
    )
    out = {
        "rows": result.rows,
        "gaps": [
            {
                "kind": g.kind,
                "field": g.field,
                "row_index": g.row_index,
                "message": g.message,
            }
            for g in result.gaps
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
