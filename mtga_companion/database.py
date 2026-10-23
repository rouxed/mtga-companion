"""Capa de persistencia SQLite: partidas, mazos y cartas."""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any

from .config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2


def _utc_now_naive() -> datetime:
    """Hora actual en UTC sin tzinfo (formato histórico de la tabla matches)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _to_utc_naive(value: datetime) -> datetime:
    """Normaliza un datetime a UTC sin tzinfo.

    La base guarda timestamps ISO en UTC sin sufijo; si no tiene tzinfo se
    asume que ya está en UTC.
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_timestamp(value: datetime | str | None) -> datetime:
    """Convierte el timestamp de una partida a UTC sin tzinfo.

    Acepta datetime, ISO 8601 o ``None``. Si el valor no se puede interpretar
    se usa la hora actual, que es lo que hacía la versión anterior.
    """
    if value is None or value == "":
        return _utc_now_naive()
    if isinstance(value, datetime):
        return _to_utc_naive(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _utc_now_naive()
        return _to_utc_naive(parsed)
    return _utc_now_naive()


def format_local_timestamp(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Formatea un timestamp UTC guardado en la base en hora local.

    Las partidas nuevas usan la hora real del log (UTC). La base histórica
    guarda ISO sin tzinfo, así que se interpreta como UTC.
    """
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:16].replace("T", " ")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime(fmt)


def local_midnight_utc_naive(
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> datetime:
    """Devuelve la medianoche local de hoy, expresada en UTC sin tzinfo.

    Se usa para que "Hoy" signifique el día calendario del usuario y no las
    últimas 24 horas. Si no se pasa ``tz``, se usa la zona horaria del sistema.
    """
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    local_tz = tz or datetime.now().astimezone().tzinfo or timezone.utc
    local_now = now_utc.astimezone(local_tz)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path), timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_db(db_path: Path = DB_PATH) -> None:
    """Crea o migra la base de datos al esquema actual.

    La versión se guarda en ``PRAGMA user_version``. Las bases antiguas
    (versión 0) se migran en sitio sin perder partidas ni mazos.
    """
    con = get_connection(db_path)
    try:
        previous_version = int(con.execute("PRAGMA user_version").fetchone()[0])
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT,
                timestamp TEXT NOT NULL,
                deck_name TEXT,
                deck_cards TEXT,        -- JSON: lista de {"cardId": int, "quantity": int}
                result TEXT,            -- 'win' | 'loss' | 'unknown'
                opponent TEXT,
                format TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                format TEXT,
                card_ids TEXT,          -- JSON: {"cardId_str": qty}
                first_seen TEXT,
                last_seen TEXT,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                unknown INTEGER DEFAULT 0
            )
            """
        )

        # Migración 0 -> 2: agregar match_id a bases antiguas.
        columns = {
            row["name"] for row in con.execute("PRAGMA table_info(matches)").fetchall()
        }
        if "match_id" not in columns:
            try:
                con.execute("ALTER TABLE matches ADD COLUMN match_id TEXT")
                logger.info("Migración SQLite: agregada columna matches.match_id")
            except sqlite3.OperationalError as exc:
                # Otra instancia pudo migrar entre la lectura y el ALTER.
                if "duplicate column name" not in str(exc).lower():
                    raise

        try:
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_matches_match_id "
                "ON matches(match_id) WHERE match_id IS NOT NULL"
            )
        except sqlite3.IntegrityError:
            # No debería ocurrir en bases normales; se conserva un índice no
            # único para no impedir el arranque si hubiera datos corruptos.
            logger.warning("No se pudo crear el índice único de match_id")
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_matches_match_id "
                "ON matches(match_id)"
            )

        con.execute("CREATE INDEX IF NOT EXISTS idx_matches_timestamp ON matches(timestamp)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_matches_deck ON matches(deck_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_matches_result ON matches(result)")
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        con.commit()

        if previous_version < SCHEMA_VERSION:
            logger.info(
                "Base de datos migrada de la versión %s a %s",
                previous_version,
                SCHEMA_VERSION,
            )
    finally:
        con.close()


def match_exists(match_id: str | None, db_path: Path = DB_PATH) -> bool:
    """Indica si una partida con ese ``matchId`` ya está guardada."""
    if not match_id:
        return False
    con = get_connection(db_path)
    try:
        row = con.execute(
            "SELECT 1 FROM matches WHERE match_id = ? LIMIT 1", (match_id,)
        ).fetchone()
        return row is not None
    finally:
        con.close()


def similar_legacy_match_exists(
    opponent: str,
    result: str,
    deck_name: str | None,
    timestamp: datetime | str | None,
    db_path: Path = DB_PATH,
    window_seconds: int = 600,
) -> bool:
    """Busca una partida antigua equivalente sin ``match_id``.

    Las bases anteriores a la versión 1 no guardaban ``matchId``. Al hacer el
    backfill de una partida recién terminada podría insertarse una copia de
    una partida que la versión anterior ya había guardado. Esta comprobación
    solo se usa en el backfill y compara oponente, resultado, mazo y una
    ventana temporal alrededor de la hora del log.
    """
    if not timestamp:
        return False
    match_time = _normalize_timestamp(timestamp)
    start = (match_time - timedelta(seconds=window_seconds)).isoformat()
    end = (match_time + timedelta(seconds=window_seconds)).isoformat()
    con = get_connection(db_path)
    try:
        row = con.execute(
            """
            SELECT 1 FROM matches
            WHERE match_id IS NULL
              AND opponent = ?
              AND result = ?
              AND COALESCE(deck_name, '') = COALESCE(?, '')
              AND timestamp BETWEEN ? AND ?
            LIMIT 1
            """,
            (opponent, result, deck_name, start, end),
        ).fetchone()
        return row is not None
    finally:
        con.close()


def save_match(
    deck_name: str | None,
    deck_cards: list[dict],
    result: str,
    opponent: str,
    fmt: str | None = None,
    db_path: Path = DB_PATH,
    timestamp: datetime | str | None = None,
    match_id: str | None = None,
) -> int:
    """Guarda una partida y actualiza las estadísticas del mazo.

    ``match_id`` es el identificador único que escribe Arena; si ya existe, no
    se inserta de nuevo y se devuelve el id existente. ``timestamp`` permite
    usar la hora real del log en lugar de la hora de guardado.
    """
    match_id = (match_id or "").strip() or None
    match_time = _normalize_timestamp(timestamp)
    timestamp_iso = match_time.isoformat()

    con = get_connection(db_path)
    try:
        if match_id:
            existing = con.execute(
                "SELECT id FROM matches WHERE match_id = ?", (match_id,)
            ).fetchone()
            if existing is not None:
                logger.debug("Partida %s ya guardada; se omite", match_id)
                return int(existing["id"])

        try:
            with con:
                cur = con.execute(
                    """
                    INSERT INTO matches
                        (match_id, timestamp, deck_name, deck_cards, result, opponent, format)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        timestamp_iso,
                        deck_name,
                        json.dumps(deck_cards, ensure_ascii=False),
                        result,
                        opponent,
                        fmt,
                    ),
                )
                new_id = int(cur.lastrowid)
                _update_deck_stats(
                    deck_name,
                    deck_cards,
                    result,
                    fmt,
                    con,
                    seen_at=match_time,
                )
            return new_id
        except sqlite3.IntegrityError:
            if match_id:
                existing = con.execute(
                    "SELECT id FROM matches WHERE match_id = ?", (match_id,)
                ).fetchone()
                if existing is not None:
                    return int(existing["id"])
            logger.exception("No se pudo insertar la partida")
            raise
    finally:
        con.close()


def _update_deck_stats(
    deck_name: str | None,
    deck_cards: list[dict],
    result: str,
    fmt: str | None,
    con: sqlite3.Connection,
    seen_at: datetime,
) -> None:
    if not deck_name:
        return
    seen_iso = seen_at.isoformat()
    row = con.execute("SELECT * FROM decks WHERE name = ?", (deck_name,)).fetchone()
    card_ids = (
        json.dumps(
            {str(c.get("cardId")): c.get("quantity", 1) for c in deck_cards},
            ensure_ascii=False,
        )
        if deck_cards
        else None
    )
    if row is None:
        con.execute(
            """
            INSERT INTO decks (name, format, card_ids, first_seen, last_seen, wins, losses, unknown)
            VALUES (?, ?, ?, ?, ?, 0, 0, 0)
            """,
            (deck_name, fmt, card_ids or "{}", seen_iso, seen_iso),
        )
        row = con.execute("SELECT * FROM decks WHERE name = ?", (deck_name,)).fetchone()
    wins, losses, unknown = row["wins"], row["losses"], row["unknown"]
    if result == "win":
        wins += 1
    elif result == "loss":
        losses += 1
    else:
        unknown += 1

    first_seen = min(row["first_seen"] or seen_iso, seen_iso)
    last_seen = max(row["last_seen"] or seen_iso, seen_iso)
    con.execute(
        """
        UPDATE decks
        SET format = COALESCE(?, format),
            card_ids = COALESCE(?, card_ids),
            first_seen = ?,
            last_seen = ?,
            wins = ?, losses = ?, unknown = ?
        WHERE id = ?
        """,
        (
            fmt,
            card_ids,
            first_seen,
            last_seen,
            wins,
            losses,
            unknown,
            row["id"],
        ),
    )


def get_matches(db_path: Path = DB_PATH, limit: int | None = None) -> list[dict]:
    con = get_connection(db_path)
    try:
        query = "SELECT * FROM matches ORDER BY timestamp DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        rows = con.execute(query).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def compute_summary(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = get_connection(db_path)
    try:
        matches = [dict(r) for r in con.execute("SELECT * FROM matches").fetchall()]
    finally:
        con.close()

    total = len(matches)
    wins = sum(1 for m in matches if m["result"] == "win")
    losses = sum(1 for m in matches if m["result"] == "loss")
    unknown = sum(1 for m in matches if m["result"] == "unknown")
    overall_winrate = round(100 * wins / (wins + losses), 1) if (wins + losses) else None

    _RES_KEY = {"win": "wins", "loss": "losses", "unknown": "unknown"}
    by_deck: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "unknown": 0})
    by_format: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "unknown": 0})
    for m in matches:
        deck = m["deck_name"] or "Mazo sin nombre"
        fmt = m["format"] or "Desconocido"
        res = m["result"]
        key = _RES_KEY.get(res, "unknown")
        by_deck[deck][key] += 1
        by_format[fmt][key] += 1

    def build_list(source: dict[str, dict[str, int]]) -> list[dict]:
        out = []
        for name, r in source.items():
            t = r["wins"] + r["losses"]
            wr = round(100 * r["wins"] / t, 1) if t else None
            out.append({
                "name": name,
                "wins": r["wins"],
                "losses": r["losses"],
                "unknown": r["unknown"],
                "total": t,
                "winrate": wr,
            })
        out.sort(key=lambda x: (x["winrate"] or -1, x["total"]), reverse=True)
        return out

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "unknown": unknown,
        "overall_winrate": overall_winrate,
        "by_deck": build_list(by_deck),
        "by_format": build_list(by_format),
        "recent": matches[:20],
    }


def compute_summary_by_period(
    db_path: Path = DB_PATH,
    days: int | None = None,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Calcula un resumen de winrate filtrado por período.

    Args:
        days: Número de días hacia atrás desde ahora. Si es None y ``since``
              también es None, devuelve todas las partidas.
        since: Fecha/hora de corte exacta en UTC. Tiene prioridad sobre
               ``days``. Se usa para "hoy" (medianoche local).
    """
    if since is not None:
        cutoff: str | None = _to_utc_naive(since).isoformat()
    elif days is not None:
        cutoff = (_utc_now_naive() - timedelta(days=days)).isoformat()
    else:
        cutoff = None

    con = get_connection(db_path)
    try:
        if cutoff is not None:
            matches = [
                dict(r)
                for r in con.execute(
                    "SELECT * FROM matches WHERE timestamp >= ? ORDER BY timestamp DESC",
                    (cutoff,),
                ).fetchall()
            ]
        else:
            matches = [dict(r) for r in con.execute("SELECT * FROM matches").fetchall()]
    finally:
        con.close()

    total = len(matches)
    wins = sum(1 for m in matches if m["result"] == "win")
    losses = sum(1 for m in matches if m["result"] == "loss")
    unknown = sum(1 for m in matches if m["result"] == "unknown")
    winrate = round(100 * wins / (wins + losses), 1) if (wins + losses) else None

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "unknown": unknown,
        "winrate": winrate,
    }


def compute_daily_summary(
    db_path: Path = DB_PATH,
    now: datetime | None = None,
    tz: tzinfo | None = None,
) -> dict[str, Any]:
    """Devuelve resúmenes de hoy, últimos 7/30 días y todo el historial.

    "Hoy" es el día calendario local del usuario (desde la medianoche local),
    no una ventana móvil de 24 horas. ``now`` y ``tz`` existen para poder
    testear el cálculo de forma determinista.
    """
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    today_start = local_midnight_utc_naive(now_utc, tz)
    now_naive = _to_utc_naive(now_utc)

    today = compute_summary_by_period(db_path, since=today_start)
    last7 = compute_summary_by_period(db_path, since=now_naive - timedelta(days=7))
    last30 = compute_summary_by_period(db_path, since=now_naive - timedelta(days=30))
    all_time = compute_summary_by_period(db_path, days=None)

    return {
        "today": today,
        "last7": last7,
        "last30": last30,
        "all_time": all_time,
    }


def get_deck(db_name: str, db_path: Path = DB_PATH) -> dict | None:
    con = get_connection(db_path)
    try:
        row = con.execute("SELECT * FROM decks WHERE name = ?", (db_name,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()
