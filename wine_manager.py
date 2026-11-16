#!/usr/bin/env python3
"""Import and progressively clean a personal wine database.

The program deliberately uses only Python's standard library so it is easy to
run on a new computer: ``python3 wine_manager.py import``.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
from collections import Counter
from pathlib import Path


INPUT = Path("input_file.csv")
DATABASE = Path("wine_database.csv")
RULES = Path("cleaning_rules.csv")
SOURCE_COLUMNS = [
    "Name", "Winery/Estate", "Colour", "Year", "Owner", "Denomination",
    "Grape/Vine", "Country", "Region", "ABV", "Acquisition Date", "Store",
    "Drinking Date", "Bar/Restaurant/Place", "Price", "Retail Price",
    "Description", "Review", "ID",
]
FIELDS = {
    "grape": ("Grape/Vine", "grapes_clean", "grapes_status"),
    "producer": ("Winery/Estate", "producer_clean", "producer_status"),
    "appellation": ("Denomination", "appellation_clean", "appellation_status"),
}
EXTRA_COLUMNS = ["_record_key"] + [item for triple in FIELDS.values() for item in triple[1:]]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def record_key(row: dict[str, str]) -> str:
    return f"id:{row['ID'].strip()}"


def normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def initial_grapes(value: str) -> str:
    """Create a predictable grape list, without guessing spelling corrections."""
    value = normalise_space(value)
    if not value:
        return ""
    # Percentages describe proportions, not grape names.
    value = re.sub(r"\s*\([^)]*\)", "", value)
    # Numbers describe proportions or other metadata, never a grape name.
    # Removing them before splitting also handles forms such as
    # "100% Montepulciano" and "1/2 Terret, 1/2 Riesling".
    value = re.sub(r"\d+(?:[.,]\d+)?\s*%?", " ", value)
    value = re.sub(r"\s*(?:,|;|/|\band\b|\be\b|\bet\b|\+| - )\s*", "|", value, flags=re.I)
    grapes = [normalise_space(part) for part in value.split("|") if normalise_space(part)]
    return " | ".join(sorted(dict.fromkeys(grapes), key=str.casefold))


def rules() -> dict[tuple[str, str], str]:
    return {(row["field"], row["raw_value"]): row["clean_value"] for row in read_csv(RULES)}


def apply_rules(row: dict[str, str], known_rules: dict[tuple[str, str], str], fields=None) -> None:
    """Refresh clean values for new records or changed controlled fields."""
    for field in fields or FIELDS:
        raw_column, clean_column, status_column = FIELDS[field]
        raw = normalise_space(row.get(raw_column, ""))
        if not raw:
            row[clean_column], row[status_column] = "", "empty"
            continue
        if (field, raw) in known_rules:
            clean = known_rules[field, raw]
            row[clean_column], row[status_column] = (initial_grapes(clean) if field == "grape" else clean), "reviewed"
        elif field == "grape":
            row[clean_column], row[status_column] = initial_grapes(raw), "pending"
        else:
            row[clean_column], row[status_column] = raw, "pending"


def import_rows() -> None:
    source = read_csv(INPUT)
    if not source:
        raise SystemExit(f"Cannot find source file: {INPUT}")
    missing = [column for column in SOURCE_COLUMNS if column not in source[0]]
    if missing:
        raise SystemExit("Source is missing columns: " + ", ".join(missing))
    source = [row for row in source if any(value.strip() for value in row.values())]
    ids = [row["ID"].strip() for row in source]
    if not all(ids):
        raise SystemExit("Every non-empty source row needs an ID before importing.")
    if len(ids) != len(set(ids)):
        raise SystemExit("IDs must be unique in the source file before importing.")
    database = read_csv(DATABASE)
    # Repair a record created by an older version before its ID was filled in.
    # It is safe to discard only when the same source record now exists with an ID.
    source_without_id = {
        tuple(row.get(column, "") for column in SOURCE_COLUMNS if column != "ID")
        for row in source
    }
    original_count = len(database)
    database = [
        row for row in database
        if row.get("ID", "").strip()
        or tuple(row.get(column, "") for column in SOURCE_COLUMNS if column != "ID")
        not in source_without_id
    ]
    repaired = original_count - len(database)
    existing = {row.get("_record_key"): row for row in database}
    known_rules = rules()
    new_rows = []
    updated = 0
    for row in source:
        key = record_key(row)
        current = existing.get(key)
        # One-time migration for a record imported before its missing ID was fixed.
        if current is None:
            current = next((old for old in database if not old.get("ID", "").strip()
                            and all(old.get(column, "") == row.get(column, "")
                                    for column in SOURCE_COLUMNS if column != "ID")), None)
        if current is None:
            new = {column: row.get(column, "") for column in SOURCE_COLUMNS}
            new["_record_key"] = key
            apply_rules(new, known_rules)
            new_rows.append(new)
            existing[key] = new
            continue
        changed = {column for column in SOURCE_COLUMNS if current.get(column, "") != row.get(column, "")}
        if changed:
            current.update({column: row.get(column, "") for column in SOURCE_COLUMNS})
            changed_fields = [field for field, (raw, _, _) in FIELDS.items() if raw in changed]
            if changed_fields:
                apply_rules(current, known_rules, changed_fields)
            updated += 1
        current["_record_key"] = key
        existing[key] = current
    # Keep the analysis list canonical even for rows created by an older version.
    for row in database + new_rows:
        if row.get("grapes_clean"):
            row["grapes_clean"] = initial_grapes(row["grapes_clean"])
    write_csv(DATABASE, SOURCE_COLUMNS + EXTRA_COLUMNS, database + new_rows)
    print(f"Imported {len(new_rows)} new row(s); synchronized {updated} existing row(s).")
    if repaired:
        print(f"Removed {repaired} obsolete blank-ID row(s) created before the ID was corrected.")


def save_rule(field: str, raw: str, clean: str) -> None:
    if field == "grape":
        clean = initial_grapes(clean)
    rows = read_csv(RULES)
    rows = [row for row in rows if not (row["field"] == field and row["raw_value"] == raw)]
    rows.append({"field": field, "raw_value": raw, "clean_value": clean})
    write_csv(RULES, ["field", "raw_value", "clean_value"], rows)


def candidate_values(rows: list[dict[str, str]], field: str) -> Counter:
    raw_column = FIELDS[field][0]
    return Counter(normalise_space(row.get(raw_column, "")) for row in rows if normalise_space(row.get(raw_column, "")))


def grape_counts(rows: list[dict[str, str]], replacement_raw: str, replacement_clean: str) -> Counter:
    """Count individual grapes after applying the pending replacement."""
    counts = Counter()
    for row in rows:
        raw = normalise_space(row.get(FIELDS["grape"][0], ""))
        clean = replacement_clean if raw == replacement_raw else row.get("grapes_clean", "")
        counts.update(grape for grape in clean.split(" | ") if grape)
    return counts


def print_grapes(grapes: str) -> None:
    items = grapes.split(" | ") if grapes else []
    print("\n  GRAPES TO SAVE\n  " + "─" * 56)
    for number, grape in enumerate(items, start=1):
        print(f"    {number:>2}.  {grape}")


def review_header(field: str, total: int, full_audit: bool) -> None:
    """Print a calm, readable introduction to an interactive review."""
    print("\n" + "═" * 64)
    title = "FULL AUDIT" if full_audit else "RARE-VALUE REVIEW"
    print(f"  WINE DATABASE  /  {title}")
    print("═" * 64)
    print(f"  Field: {field.title()}     Items to review: {total}")
    print("\n  Keep a value, choose a suggestion when one is shown, or type")
    print("  a replacement. Each saved decision is remembered for next time.")


def review_prompt(has_suggestions: bool) -> str:
    """Return instructions which never imply numbered choices where none exist."""
    if has_suggestions:
        return (
            "  Action  [Enter] keep  ·  [number] use suggestion  ·  "
            "[text] replace\n"
            "          [s] skip for later  ·  [q] stop review\n  › "
        )
    return (
        "  No numbered suggestions are available for this value.\n"
        "  Action  [Enter] keep  ·  [text] replace  ·  "
        "[s] skip for later  ·  [q] stop review\n  › "
    )


def trusted_values(rows: list[dict[str, str]], field: str,
                   known_rules: dict[tuple[str, str], str]) -> list[str]:
    """Return values a user has previously approved for use as suggestions."""
    _, clean_column, status_column = FIELDS[field]
    values = {
        normalise_space(clean)
        for (rule_field, _), clean in known_rules.items()
        if rule_field == field and normalise_space(clean)
    }
    values.update(
        normalise_space(row.get(clean_column, ""))
        for row in rows
        if row.get(status_column) == "reviewed" and normalise_space(row.get(clean_column, ""))
    )
    return sorted(values, key=str.casefold)


def saved_suggestions(rows: list[dict[str, str]], field: str,
                      known_rules: dict[tuple[str, str], str],
                      review_value: str) -> list[tuple[str, list[str]]]:
    """Return prior replacements with the source value that established them.

    A cleaned grape list can be identical to the value currently on screen.
    Keeping the original source alongside it makes clear that it is a saved
    correction (for example a percentage-formatted blend), not a duplicate
    database value being suggested as its own replacement.
    """
    raw_column, clean_column, status_column = FIELDS[field]
    prior: dict[str, list[str]] = {}
    for (rule_field, source), clean in known_rules.items():
        if rule_field == field and normalise_space(clean):
            clean = initial_grapes(clean) if field == "grape" else normalise_space(clean)
            prior.setdefault(clean, []).append(source)
    for row in rows:
        if row.get(status_column) != "reviewed":
            continue
        source = normalise_space(row.get(raw_column, ""))
        clean = normalise_space(row.get(clean_column, ""))
        if source and clean:
            prior.setdefault(clean, []).append(source)

    # A source spelling or a prior cleaned value can establish a useful match.
    # Score the strongest of the two so percentage/punctuation variants still
    # find their prior correction through their normalised cleaned value.
    scored = []
    for clean, sources in prior.items():
        source_score = max(
            (difflib.SequenceMatcher(None, review_value.casefold(), source.casefold()).ratio()
             for source in sources),
            default=0,
        )
        clean_score = difflib.SequenceMatcher(
            None, review_value.casefold(), clean.casefold()
        ).ratio()
        score = max(source_score, clean_score)
        if score >= 0.72:
            scored.append((score, clean, sorted(set(sources), key=str.casefold)))
    scored.sort(key=lambda item: (-item[0], item[1].casefold()))
    return [(clean, sources) for _, clean, sources in scored[:3]]


def print_review_summary(field: str, saved: int, kept: int, suggestions: int,
                         replacements: int, skipped: int) -> None:
    """Make the outcome of a review session clear before returning to the shell."""
    print("\n" + "═" * 64)
    print("  REVIEW SUMMARY")
    print("═" * 64)
    print(f"  Field: {field.title()}")
    print(f"  Saved decisions: {saved}")
    print(f"    Kept as shown: {kept}")
    print(f"    Used suggestion: {suggestions}")
    print(f"    Typed replacement: {replacements}")
    print(f"  Skipped for later: {skipped}")


def ask(prompt: str) -> str | None:
    """Return None for Ctrl-D, allowing a review to end without an error."""
    try:
        return input(prompt).strip()
    except EOFError:
        print("\n\nReview stopped. Decisions already made have been saved.")
        return None


def review(field: str, full_audit: bool = False) -> None:
    rows = read_csv(DATABASE)
    if not rows:
        raise SystemExit("No working database yet. Run: python3 wine_manager.py import")
    raw_column, clean_column, status_column = FIELDS[field]
    counts = candidate_values(rows, field)
    known = rules()
    unresolved = [
        value for value, count in counts.items()
        if (field, value) not in known and (full_audit or count <= 2)
    ]
    if not unresolved:
        scope = "unreviewed" if full_audit else "rare unreviewed"
        print(f"No {scope} {field} values.")
        return
    ordering = (lambda value: (-counts[value], value.casefold())) if full_audit else str.casefold
    saved = kept = suggestions = replacements = skipped = 0
    review_header(field, len(unresolved), full_audit)
    for position, raw in enumerate(sorted(unresolved, key=ordering), start=1):
        # Grapes are reviewed as their analysis value, rather than the source
        # notation for their proportions (for example, "100% Pecorino").
        # Keep ``raw`` for looking up and saving the source-specific rule.
        review_value = initial_grapes(raw) if field == "grape" else raw
        # Keep exact matches too.  They commonly arise when two source
        # spellings normalise to the same grape list (for example, accents or
        # proportion notation).  In that case the previously approved list is
        # still useful confirmation rather than a reason to review it blind.
        matches = saved_suggestions(rows, field, known, review_value)
        print(f"\n{'─' * 64}")
        print(f"  {position:>2} of {len(unresolved):<2}   {field.title().upper()}   ·   found in {counts[raw]} row(s)")
        print("\n  VALUE TO REVIEW")
        print(f"\n    {review_value}")
        if matches:
            print("\n  PREVIOUSLY SAVED CORRECTIONS")
            for number, (match, sources) in enumerate(matches, start=1):
                print(f"   {number:>2}   {match}")
                if sources:
                    print(f"        saved for: {sources[0]}")
        else:
            print("\n  SIMILAR VALUES\n  No close existing values found.")
        print()
        answer = ask(review_prompt(bool(matches)))
        if answer is None or answer.lower() == "q":
            break
        if answer.lower() == "s":
            skipped += 1
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(matches):
            clean = matches[int(answer) - 1][0]
            decision = "suggestion"
        else:
            clean = answer or (initial_grapes(raw) if field == "grape" else raw)
            decision = "replacement" if answer else "kept"
        if field == "grape":
            clean = initial_grapes(clean)
            print_grapes(clean)
            confirmation = ask("  Save this grape list? [Y/n] ")
            if confirmation is None or confirmation.lower() in {"n", "no"}:
                if confirmation is None:
                    break
                print("  Not saved; this value remains for a later review.")
                skipped += 1
                continue
            components = grape_counts(rows, raw, clean)
            flagged = [grape for grape in clean.split(" | ") if components[grape] <= 2]
            approved = True
            for grape in flagged:
                print("\n  ANOMALY CHECK")
                print("  " + "─" * 56)
                print("  Uncommon grape:\n")
                print(f"    {grape}")
                confirmation = ask(
                    f"\n  Appears in only {components[grape]} row(s).\n"
                    "  Save it anyway? [y/N] "
                )
                if confirmation is None or confirmation.lower() not in {"y", "yes"}:
                    print("  Not saved; this value remains for a later review.")
                    approved = False
                    break
            if not approved:
                if confirmation is None:
                    break
                skipped += 1
                continue
        save_rule(field, raw, clean)
        # The queue was assembled before this interactive session started.
        # Make each decision available immediately, so a later spelling with
        # the same normalised value receives it as a suggestion.
        saved += 1
        if decision == "suggestion":
            suggestions += 1
        elif decision == "replacement":
            replacements += 1
        else:
            kept += 1
        for row in rows:
            if normalise_space(row.get(raw_column, "")) == raw:
                row[clean_column], row[status_column] = clean, "reviewed"
        # Persist each decision, so Ctrl-D or an interruption never loses it.
        write_csv(DATABASE, SOURCE_COLUMNS + EXTRA_COLUMNS, rows)
    # Also canonicalise historic grape clean values whenever the grape review runs.
    if field == "grape":
        for row in rows:
            if row.get(clean_column):
                row[clean_column] = initial_grapes(row[clean_column])
    write_csv(DATABASE, SOURCE_COLUMNS + EXTRA_COLUMNS, rows)
    print_review_summary(field, saved, kept, suggestions, replacements, skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import and clean the wine database.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("import", help="Copy only unseen source rows into the working database")
    review_parser = subcommands.add_parser("review", help="Interactively review rare values")
    review_parser.add_argument("field", choices=FIELDS, help="Field to review")
    review_parser.add_argument(
        "--all", action="store_true", dest="full_audit",
        help="Review every unreviewed value, including values that occur often",
    )
    args = parser.parse_args()
    if args.command == "import":
        import_rows()
    else:
        review(args.field, args.full_audit)


if __name__ == "__main__":
    main()
