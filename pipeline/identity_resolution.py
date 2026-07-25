"""Reviewed person aliases and safe identity resolution for suspect mentions.

The source name printed in each CIABOC PDF remains in ``suspects.name``.
``suspects.person_id`` links that source mention to a canonical person.

Only punctuation, whitespace, and letter-case variants are grouped
automatically. Abbreviations and spelling variants must be listed in
VERIFIED_IDENTITIES so similarly named people are not merged accidentally.
"""

import os
import sqlite3
import sys
import unicodedata
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "ciaboc.db")


VERIFIED_IDENTITIES = (
    {
        "canonical_name": "Keheliya B.D. Rambukwella",
        "aliases": (
            "K.B.D. Rambukwella",
            "Keheliya B.D. Rambukwella",
            "Keheliya B.D. Rambukawella",
            "Keheliya Bandara Dissanayake Rambukwella",
        ),
        "source_note": (
            "Reviewed identity: CIABOC lists K.B.D. Rambukwella as an MP; "
            "Sri Lanka Parliament records Keheliya Bandara Dissanayake "
            "Rambukwella."
        ),
    },
)


IDENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person_aliases (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id        INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    alias             TEXT NOT NULL,
    normalized_alias  TEXT NOT NULL UNIQUE,
    match_method      TEXT NOT NULL,
    confidence        REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reviewed          INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1)),
    source_note       TEXT
);

CREATE INDEX IF NOT EXISTS idx_person_aliases_person
    ON person_aliases(person_id);
CREATE INDEX IF NOT EXISTS idx_person_aliases_alias
    ON person_aliases(alias);
"""


def normalize_alias(name: str) -> str:
    """Return a lookup key insensitive to case, punctuation, and whitespace."""
    normalized = unicodedata.normalize("NFKC", name).casefold()
    return "".join(char for char in normalized if char.isalnum())


def clean_source_name(name: str) -> str:
    """Trim source names without expanding initials or correcting spelling."""
    return " ".join(name.split())


def _merge_people(conn: sqlite3.Connection, source_id: int, target_id: int) -> None:
    if source_id == target_id:
        return
    conn.execute(
        "UPDATE suspects SET person_id = ? WHERE person_id = ?",
        (target_id, source_id),
    )
    conn.execute(
        "UPDATE person_aliases SET person_id = ? WHERE person_id = ?",
        (target_id, source_id),
    )
    conn.execute("DELETE FROM people WHERE id = ?", (source_id,))


def _seed_verified_identity(
    conn: sqlite3.Connection,
    canonical_name: str,
    aliases: tuple[str, ...],
    source_note: str,
) -> int:
    all_aliases = tuple(dict.fromkeys((canonical_name, *aliases)))
    alias_keys = [normalize_alias(alias) for alias in all_aliases]

    row = conn.execute(
        "SELECT id FROM people WHERE canonical_name = ?",
        (canonical_name,),
    ).fetchone()
    if row:
        person_id = row[0]
    else:
        placeholders = ",".join("?" for _ in alias_keys)
        row = conn.execute(
            f"""SELECT person_id FROM person_aliases
                WHERE normalized_alias IN ({placeholders})
                LIMIT 1""",
            alias_keys,
        ).fetchone()
        if row:
            person_id = row[0]
            conn.execute(
                "UPDATE people SET canonical_name = ? WHERE id = ?",
                (canonical_name, person_id),
            )
        else:
            person_id = conn.execute(
                "INSERT INTO people (canonical_name, created_at) VALUES (?, ?)",
                (canonical_name, datetime.now().isoformat(timespec="seconds")),
            ).lastrowid

    for alias in all_aliases:
        normalized_alias = normalize_alias(alias)
        existing = conn.execute(
            "SELECT person_id FROM person_aliases WHERE normalized_alias = ?",
            (normalized_alias,),
        ).fetchone()
        if existing and existing[0] != person_id:
            _merge_people(conn, existing[0], person_id)

        conn.execute(
            """INSERT INTO person_aliases
                   (person_id, alias, normalized_alias, match_method,
                    confidence, reviewed, source_note)
               VALUES (?, ?, ?, 'verified_alias', 1.0, 1, ?)
               ON CONFLICT(normalized_alias) DO UPDATE SET
                   person_id = excluded.person_id,
                   alias = excluded.alias,
                   match_method = excluded.match_method,
                   confidence = excluded.confidence,
                   reviewed = excluded.reviewed,
                   source_note = excluded.source_note""",
            (person_id, alias, normalized_alias, source_note),
        )

    return person_id


def seed_verified_identities(conn: sqlite3.Connection) -> None:
    for identity in VERIFIED_IDENTITIES:
        _seed_verified_identity(conn, **identity)


def resolve_person_id(conn: sqlite3.Connection, source_name: str) -> int:
    """Resolve one source mention, creating an unreviewed exact-name identity."""
    source_name = clean_source_name(source_name)
    normalized_alias = normalize_alias(source_name)
    if not normalized_alias:
        raise ValueError("suspect name has no letters or numbers")

    row = conn.execute(
        "SELECT person_id FROM person_aliases WHERE normalized_alias = ?",
        (normalized_alias,),
    ).fetchone()
    if row:
        return row[0]

    row = conn.execute(
        "SELECT id FROM people WHERE canonical_name = ?",
        (source_name,),
    ).fetchone()
    if row:
        person_id = row[0]
    else:
        person_id = conn.execute(
            "INSERT INTO people (canonical_name, created_at) VALUES (?, ?)",
            (source_name, datetime.now().isoformat(timespec="seconds")),
        ).lastrowid

    conn.execute(
        """INSERT INTO person_aliases
               (person_id, alias, normalized_alias, match_method,
                confidence, reviewed, source_note)
           VALUES (?, ?, ?, 'exact_normalized', 1.0, 0, ?)""",
        (
            person_id,
            source_name,
            normalized_alias,
            "Automatically grouped by punctuation, whitespace, and case only.",
        ),
    )
    return person_id


def backfill_person_ids(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT id, name FROM suspects WHERE person_id IS NULL ORDER BY id"
    ).fetchall()
    for suspect_id, source_name in rows:
        person_id = resolve_person_id(conn, source_name)
        conn.execute(
            "UPDATE suspects SET person_id = ? WHERE id = ?",
            (person_id, suspect_id),
        )
    return len(rows)


def initialize_identity_schema(conn: sqlite3.Connection) -> int:
    """Create/migrate identity tables, seed reviewed aliases, and backfill."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(IDENTITY_SCHEMA)

    suspect_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(suspects)").fetchall()
    }
    if "person_id" not in suspect_columns:
        conn.execute(
            """ALTER TABLE suspects
               ADD COLUMN person_id INTEGER REFERENCES people(id) ON DELETE SET NULL"""
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_suspects_person ON suspects(person_id)"
    )

    seed_verified_identities(conn)
    resolved = backfill_person_ids(conn)
    conn.commit()
    return resolved


def migrate_database(db_path: str = DB_PATH) -> dict[str, int]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'suspects'"
        ).fetchone():
            raise RuntimeError("suspects table not found; run the PDF pipeline first")
        resolved = initialize_identity_schema(conn)
        return {
            "resolved_mentions": resolved,
            "people": conn.execute("SELECT COUNT(*) FROM people").fetchone()[0],
            "aliases": conn.execute(
                "SELECT COUNT(*) FROM person_aliases"
            ).fetchone()[0],
        }
    finally:
        conn.close()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    try:
        stats = migrate_database(target)
    except (FileNotFoundError, RuntimeError) as exc:
        sys.exit(f"ERROR: {exc}")
    print(
        "Identity migration complete: "
        f"{stats['resolved_mentions']} mentions resolved, "
        f"{stats['people']} people, {stats['aliases']} aliases"
    )
