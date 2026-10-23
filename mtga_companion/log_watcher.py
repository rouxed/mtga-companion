"""Watcher del Player.log: sigue el archivo en tiempo real y emite eventos.

Incluye auto-detección de ruta, reintento automático si el archivo no existe,
detección de rotación/truncado, backfill del mazo en curso y deduplicación de
partidas mediante el ``matchId`` de Arena.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .config import (
    DECK_SUBMIT_MARKER,
    MATCH_COMPLETE_MARKER,
    MATCH_COMPLETE_STATE,
    detect_log_path,
)
from .database import (
    DB_PATH,
    init_db,
    match_exists,
    save_match,
    similar_legacy_match_exists,
)
from .game_state import GameStateTracker
from .i18n import tr
from .models import DetectedDeck, MatchResult
from .parser import (
    _extract_json_blob,
    _find_course_dicts,
    _pick_active_course,
    normalize_deck_cards,
    parse_match_result,
)
from .thread_registry import register_thread, unregister_thread

logger = logging.getLogger(__name__)

# Al iniciar se leen los últimos 5 MB para recuperar el mazo de una partida en
# curso y, si corresponde, una partida recién terminada.
BACKFILL_BYTES = 5 * 1024 * 1024
BACKFILL_MAX_AGE = timedelta(minutes=15)


class LogWatcherSignals(QObject):
    deck_detected = pyqtSignal(object)       # DetectedDeck
    match_detected = pyqtSignal(object)      # MatchResult
    game_state_changed = pyqtSignal(object)  # GameSnapshot
    status_changed = pyqtSignal(str)         # mensaje de estado
    error_occurred = pyqtSignal(str)         # mensaje de error


class LogWatcherThread(QThread):
    """Hilo que hace tail -f del Player.log y emite señales con lo que encuentra.

    Características:
    * Reintenta abrir el archivo si no existe todavía (juego no iniciado).
    * Detecta si el archivo fue reemplazado (inodo cambió) o truncado.
    * Re-detecta automáticamente la ruta si la configurada deja de ser válida.
    * Al arrancar recupera el mazo actual desde el final del log.
    * Deduplica partidas con ``matchId`` (seguro ante reintentos/backfill).
    """

    def __init__(
        self,
        log_path: str | Path | None = None,
        player_name: str | None = None,
        db_path: Path = DB_PATH,
    ):
        super().__init__()
        self.signals = LogWatcherSignals()
        self.log_path = Path(log_path).expanduser() if log_path else None
        self.player_name = player_name
        self.db_path = db_path
        self._stop_event = threading.Event()
        self._current_deck: DetectedDeck | None = None
        self._game_state = GameStateTracker()
        self._last_inode: int | None = None
        self._last_size: int = 0
        register_thread(self)

    def _resolve_path(self) -> Path | None:
        """Devuelve la ruta válida del Player.log, probando la configurada y
        luego la detección automática."""
        if self.log_path and self.log_path.is_file():
            return self.log_path
        detected = detect_log_path()
        if detected:
            if self.log_path != detected:
                logger.info("Player.log detectado en %s", detected)
            self.log_path = detected
            return detected
        return None

    def run(self) -> None:
        try:
            init_db(self.db_path)
            logger.info(
                "Watcher iniciado (db=%s, jugador=%s)",
                self.db_path,
                self.player_name or "sin configurar",
            )
            while not self._stop_event.is_set():
                path = self._resolve_path()
                if path is None:
                    self.signals.status_changed.emit(
                        "Esperando a que exista el Player.log..."
                    )
                    self._stop_event.wait(2.0)
                    continue

                self.signals.status_changed.emit(f"Observando: {path}")
                logger.info("Observando %s", path)
                try:
                    self._tail_file(path)
                except OSError as exc:
                    logger.warning("Error leyendo %s: %s", path, exc)
                    self.signals.status_changed.emit(
                        "No se pudo leer el Player.log; reintentando..."
                    )
                    self._stop_event.wait(1.0)
        except Exception as exc:  # noqa: BLE001
            logger.exception("El watcher terminó por un error inesperado")
            self.signals.error_occurred.emit(str(exc))
        finally:
            unregister_thread(self)
            logger.info("Watcher detenido")

    def _tail_file(self, path: Path) -> None:
        """Lee el log en modo tail hasta que se detenga o el archivo cambie."""
        # Guardar el tamaño antes del backfill: si el juego escribe mientras
        # se procesa el final del log, esas líneas no se deben perder.
        start_position = self._file_size(path) or 0
        self._backfill(path)

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            self._last_inode = self._get_inode(path)
            f.seek(start_position)
            self._last_size = start_position

            while not self._stop_event.is_set():
                new_inode = self._get_inode(path)
                if (
                    new_inode is not None
                    and self._last_inode is not None
                    and new_inode != self._last_inode
                ):
                    logger.info("Player.log reemplazado; reabriendo %s", path)
                    self.signals.status_changed.emit(
                        f"Archivo reemplazado, releyendo: {path}"
                    )
                    return

                size = self._file_size(path)
                if size is not None and size < self._last_size:
                    logger.info("Player.log truncado; releyendo desde el inicio")
                    f.seek(0)
                    self._last_size = 0

                line = f.readline()
                if not line:
                    self._stop_event.wait(0.4)
                    continue

                self._process_line(line)
                self._last_size = self._file_size(path) or self._last_size

    def _backfill(self, path: Path) -> None:
        """Procesa el final del log al abrirlo.

        Sirve para recuperar el mazo de una partida que ya empezó y para no
        perder una partida que terminó justo antes de abrir la aplicación.
        Solo se aceptan partidas recientes y con ``matchId``.
        """
        try:
            size = path.stat().st_size
        except OSError:
            return

        start = max(0, size - BACKFILL_BYTES)
        lines = 0
        try:
            with open(path, "rb") as f:
                f.seek(start)
                if start > 0:
                    f.readline()  # descartar la primera línea parcial
                for raw_line in f:
                    self._process_line(
                        raw_line.decode("utf-8", errors="ignore"),
                        backfill=True,
                    )
                    lines += 1
        except OSError as exc:
            logger.warning("No se pudo hacer backfill de %s: %s", path, exc)
            return

        logger.info(
            "Backfill de %s: %s líneas (desde byte %s)", path, lines, start
        )

    def _process_line(self, line: str, backfill: bool = False) -> None:
        try:
            self._process_line_inner(line, backfill)
        except Exception:  # noqa: BLE001
            logger.exception("Error procesando una línea del Player.log")

    def _process_line_inner(self, line: str, backfill: bool) -> None:
        # ---- estado de la partida en curso (overlay) ----
        snapshot = self._game_state.process_line(line)
        if snapshot is not None:
            self.signals.game_state_changed.emit(snapshot)

        # ---- mazo activo ----
        if DECK_SUBMIT_MARKER in line:
            idx = line.find("{")
            data = _extract_json_blob(line, idx) if idx != -1 else None
            if data:
                courses = _find_course_dicts(data)
                course = _pick_active_course(courses)
                if course:
                    summary = course.get("CourseDeckSummary", {}) or {}
                    course_deck = course.get("CourseDeck", {}) or {}
                    self._current_deck = DetectedDeck(
                        name=summary.get("Name") or tr("Mazo sin nombre"),
                        fmt=summary.get("Format") or None,
                        cards=normalize_deck_cards(course_deck.get("MainDeck", [])),
                        source_module=course.get("CurrentModule"),
                    )
                    self._game_state.set_deck(self._current_deck)
                    self.signals.deck_detected.emit(self._current_deck)
                    # El mazo recién se conoce al final del mensaje: emitimos
                    # un snapshot nuevo para que el overlay no se quede con la
                    # versión anterior sin deck.
                    self.signals.game_state_changed.emit(
                        self._game_state.snapshot()
                    )

        # ---- fin de partida ----
        if MATCH_COMPLETE_MARKER not in line or MATCH_COMPLETE_STATE not in line:
            return

        idx = line.find("{")
        data = _extract_json_blob(line, idx) if idx != -1 else None
        if not data:
            return

        match = parse_match_result(data, self.player_name)

        # En el backfill solo se aceptan partidas recientes y con matchId,
        # para no duplicar el historial antiguo del log.
        if backfill:
            if not match.match_id or not self._is_recent(match.timestamp):
                return

        if match.match_id and match_exists(match.match_id, self.db_path):
            logger.debug("Partida %s ya estaba guardada", match.match_id)
            return

        deck_to_save = self._current_deck
        if backfill and similar_legacy_match_exists(
            opponent=match.opponent,
            result=match.result,
            deck_name=deck_to_save.name if deck_to_save else None,
            timestamp=match.timestamp or None,
            db_path=self.db_path,
        ):
            logger.debug(
                "Partida reciente ya guardada por una versión anterior; se omite"
            )
            return
        try:
            save_match(
                deck_name=deck_to_save.name if deck_to_save else None,
                deck_cards=(
                    [
                        {"cardId": card.card_id, "quantity": card.quantity}
                        for card in deck_to_save.cards
                    ]
                    if deck_to_save
                    else []
                ),
                result=match.result,
                opponent=match.opponent,
                fmt=deck_to_save.fmt if deck_to_save else None,
                db_path=self.db_path,
                timestamp=match.timestamp or None,
                match_id=match.match_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("No se pudo guardar la partida")
            self.signals.error_occurred.emit(f"No se pudo guardar la partida: {exc}")
            return

        logger.info(
            "Partida guardada: %s vs %s (%s, match_id=%s, timestamp=%s)",
            deck_to_save.name if deck_to_save else "mazo desconocido",
            match.opponent,
            match.result,
            match.match_id or "sin id",
            match.timestamp or "sin timestamp",
        )
        self.signals.match_detected.emit(
            MatchResult(
                deck=deck_to_save,
                result=match.result,
                opponent=match.opponent,
                timestamp=match.timestamp,
                match_id=match.match_id,
            )
        )

        # La partida terminó: el overlay vuelve a estado de espera. Se conserva
        # el mazo para mostrarlo si el jugador encadena otra partida.
        self._game_state.reset()
        self.signals.game_state_changed.emit(self._game_state.snapshot())

    @staticmethod
    def _is_recent(timestamp: str, max_age: timedelta = BACKFILL_MAX_AGE) -> bool:
        if not timestamp:
            return False
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            return False
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return parsed >= now - max_age

    @staticmethod
    def _get_inode(path: Path) -> int | None:
        try:
            return os.stat(path).st_ino
        except OSError:
            return None

    @staticmethod
    def _file_size(path: Path) -> int | None:
        try:
            return os.stat(path).st_size
        except OSError:
            return None

    def stop(self) -> None:
        """Solicita al hilo que termine de forma cooperativa."""
        self._stop_event.set()
