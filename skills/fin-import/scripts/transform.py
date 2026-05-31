"""Map arbitrary row dicts to canonical schema via template aliases.

Gaps (unmapped column, missing required, ambiguous date) are returned in the
result for the caller to ask the user about — we never silently guess.
"""

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


def _invert(aliases: dict[str, list[str]]) -> dict[str, str]:
    """Build a lowercase alias -> canonical lookup."""
    out: dict[str, str] = {}
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
    alias_map = _invert(aliases)

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
