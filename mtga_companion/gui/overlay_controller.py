"""Control de ciclo de vida del proceso de overlay y envío de snapshots."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from mtga_companion.draw_odds import DrawOddsEngine
from mtga_companion.game_state import GameSnapshot
from mtga_companion.i18n import LANGUAGE_ENV_VAR, get_language, tr
from mtga_companion.overlay_positions import (
    DEFAULT_POSITION,
    POSITION_KEYS,
    normalize_position,
)
from .widgets.deck_loader import DeckLoaderThread

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]


class OverlayController(QObject):
    """Lanza el proceso XCB y le manda el estado ya calculado.

    El proceso de overlay no conoce Arena ni el Player.log: recibe únicamente
    un JSON compacto. Así la app principal puede seguir corriendo en Wayland.
    """

    status_changed = pyqtSignal(str)
    position_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._position = DEFAULT_POSITION
        self._click_through = True
        self._opacity = 0.94
        self._process: QProcess | None = None
        self._last_snapshot = GameSnapshot()
        self._last_payload: dict | None = None
        self._engine = DrawOddsEngine()
        self._start_failed = False
        self._deck = None
        self._deck_signature: tuple | None = None
        self._resolved_signature: tuple | None = None
        self._loader: DeckLoaderThread | None = None
        self._loader_generation = 0
        self._opponent_loader: DeckLoaderThread | None = None
        self._opponent_loader_generation = 0
        self._opponent_failed: set[str] = set()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def configure(
        self,
        *,
        enabled: bool,
        position: str = DEFAULT_POSITION,
        click_through: bool = True,
        opacity: float = 0.94,
    ) -> None:
        self._position = normalize_position(position)
        self._click_through = bool(click_through)
        try:
            self._opacity = max(0.45, min(1.0, float(opacity)))
        except (TypeError, ValueError):
            self._opacity = 0.94
        self._enabled = bool(enabled)
        self._start_failed = False

        if not self._enabled:
            self._stop_opponent_loader()
            self._stop_process()
            self.status_changed.emit(tr("Overlay desactivado"))
            return

        if self._deck is not None:
            self._resolve_deck_metadata(self._deck)
        self._resolve_opponent_metadata(self._last_snapshot)
        if self._ensure_process():
            self.status_changed.emit(tr("Overlay activo"))
            self._send_current()

    # ------------------------------------------------------------------
    # Eventos de la app
    # ------------------------------------------------------------------
    def on_game_state(self, snapshot) -> None:
        self._last_snapshot = snapshot if isinstance(snapshot, GameSnapshot) else GameSnapshot()
        if self._enabled:
            self._resolve_opponent_metadata(self._last_snapshot)
            self._send_current()

    def clear(self) -> None:
        """Oculta el overlay cuando se detiene el seguimiento en vivo."""
        self._last_snapshot = GameSnapshot()
        if self._enabled:
            self._send_current()

    def on_deck_detected(self, deck) -> None:
        # El mazo ya fue aplicado al GameStateTracker por el watcher. Acá
        # resolvemos nombres/tipos de cartas en segundo plano para que el
        # overlay pueda agrupar tierras, criaturas y hechizos.
        if deck is None:
            return
        signature = (
            str(getattr(deck, "name", "") or ""),
            tuple(sorted(
                (str(card.card_id), int(card.quantity))
                for card in getattr(deck, "cards", [])
            )),
        )
        if signature == self._deck_signature:
            if self._enabled:
                self._send_current()
            return
        self._deck = deck
        self._deck_signature = signature
        if self._enabled:
            self._resolve_deck_metadata(deck)
            self._send_current()

    def _resolve_deck_metadata(self, deck) -> None:
        if self._deck_signature is None:
            return
        self._opponent_failed.clear()
        if self._resolved_signature == self._deck_signature:
            return
        if self._loader is not None:
            self._stop_loader()
        # Evitamos dos clientes de Scryfall escribiendo la caché a la vez.
        self._stop_opponent_loader()

        entries = [
            {"cardId": str(card.card_id), "quantity": int(card.quantity)}
            for card in getattr(deck, "cards", [])
        ]
        if not entries:
            return
        self._loader_generation += 1
        generation = self._loader_generation
        signature = self._deck_signature
        loader = DeckLoaderThread(entries)
        loader.signals.finished.connect(
            lambda cards, gen=generation, sig=signature: self._on_cards_resolved(
                cards, gen, sig
            )
        )
        loader.signals.error.connect(
            lambda msg, gen=generation: self._on_cards_error(msg, gen)
        )
        self._loader = loader
        loader.start()

    def _on_cards_resolved(self, cards: list[dict], generation: int, signature) -> None:
        if generation != self._loader_generation:
            return
        self._resolved_signature = signature
        self._loader = None
        self._engine.update_card_meta(cards)
        if self._enabled:
            self._resolve_opponent_metadata(self._last_snapshot)
            self._send_current()

    def _on_cards_error(self, message: str, generation: int) -> None:
        if generation != self._loader_generation:
            return
        self._loader = None
        logger.warning("No se pudieron resolver cartas del overlay: %s", message)
        if self._enabled:
            self._resolve_opponent_metadata(self._last_snapshot)

    def _resolve_opponent_metadata(self, snapshot: GameSnapshot) -> None:
        """Resuelve nombres de cartas reveladas que no estén en la caché."""
        if not self._enabled or not snapshot.opponent_revealed:
            return
        if self._loader is not None or self._opponent_loader is not None:
            return
        entries = [
            {"cardId": str(card_id), "quantity": 1}
            for card_id in snapshot.opponent_revealed
            if not self._engine.has_card_meta(card_id)
            and str(card_id) not in self._opponent_failed
        ][:24]
        if not entries:
            return
        card_ids = [str(entry["cardId"]) for entry in entries]
        self._opponent_loader_generation += 1
        generation = self._opponent_loader_generation
        loader = DeckLoaderThread(entries)
        loader.signals.finished.connect(
            lambda cards, gen=generation: self._on_opponent_cards_resolved(
                cards, gen
            )
        )
        loader.signals.error.connect(
            lambda msg, gen=generation, ids=card_ids: self._on_opponent_cards_error(
                msg, gen, ids
            )
        )
        self._opponent_loader = loader
        loader.start()

    def _on_opponent_cards_resolved(
        self, cards: list[dict], generation: int
    ) -> None:
        if generation != self._opponent_loader_generation:
            return
        self._opponent_loader = None
        self._engine.update_card_meta(cards)
        if self._enabled:
            self._resolve_opponent_metadata(self._last_snapshot)
            self._send_current()

    def _on_opponent_cards_error(
        self, message: str, generation: int, card_ids: list[str]
    ) -> None:
        if generation != self._opponent_loader_generation:
            return
        self._opponent_loader = None
        self._opponent_failed.update(card_ids)
        logger.warning(
            "No se pudieron resolver cartas reveladas del oponente: %s", message
        )

    def _stop_opponent_loader(self) -> None:
        loader = self._opponent_loader
        self._opponent_loader = None
        self._opponent_loader_generation += 1
        if loader is None:
            return
        self._disconnect_loader(loader)
        loader.stop()
        loader.join(timeout=0.5)

    @staticmethod
    def _disconnect_loader(loader: DeckLoaderThread) -> None:
        try:
            loader.signals.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            loader.signals.error.disconnect()
        except (TypeError, RuntimeError):
            pass

    def _stop_loader(self) -> None:
        loader = self._loader
        self._loader = None
        self._loader_generation += 1
        if loader is None:
            return
        self._disconnect_loader(loader)
        loader.stop()
        loader.join(timeout=0.5)

    # ------------------------------------------------------------------
    # Proceso
    # ------------------------------------------------------------------
    @staticmethod
    def _overlay_command() -> tuple[str, list[str]]:
        """Comando para el proceso XCB, válido en fuente y empaquetado.

        En un AppImage/PyInstaller ``sys.executable`` es el binario de la app,
        no un intérprete de Python, así que ``-m`` no existe. El binario se
        relanza a sí mismo con ``--overlay-process``.
        """
        if getattr(sys, "frozen", False):
            return sys.executable, ["--overlay-process"]
        return sys.executable, ["-m", "mtga_companion.overlay_process"]

    def _ensure_process(self) -> bool:
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            return True
        if self._start_failed:
            return False
        if not os.environ.get("DISPLAY"):
            self._start_failed = True
            self.status_changed.emit(
                tr("Overlay no disponible: no se detectó X11/XWayland (DISPLAY)")
            )
            return False

        process = QProcess(self)
        program, arguments = self._overlay_command()
        process.setProgram(program)
        process.setArguments(arguments)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "xcb")
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert(LANGUAGE_ENV_VAR, get_language())
        if not getattr(sys, "frozen", False):
            # En fuente el proceso auxiliar necesita encontrar el paquete.
            # Empaquetado, PyInstaller ya incluye los módulos en el binario.
            process.setWorkingDirectory(str(_ROOT))
            current_path = env.value("PYTHONPATH", "")
            env.insert(
                "PYTHONPATH",
                str(_ROOT) + (os.pathsep + current_path if current_path else ""),
            )
        process.setProcessEnvironment(env)

        process.started.connect(self._on_process_started)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_process_finished)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)

        self._process = process
        logger.info("Iniciando proceso de overlay XCB")
        process.start()
        return True

    def _send_current(self) -> None:
        snapshot = self._last_snapshot
        odds = self._engine.compute(snapshot).to_dict()
        payload = {
            "visible": bool(snapshot.in_game),
            "position": self._position,
            "click_through": self._click_through,
            "opacity": self._opacity,
            "odds": odds,
        }
        self._last_payload = payload
        self._send(payload)

    def _send(self, payload: dict) -> None:
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        process.write(data)

    def _on_process_started(self) -> None:
        logger.info("Proceso de overlay iniciado")
        if self._last_payload is not None:
            self._send(self._last_payload)

    def _on_process_error(self, error) -> None:
        logger.warning("Error del proceso de overlay: %s", error)
        self.status_changed.emit(
            tr("No se pudo iniciar el overlay ({error})", error=error)
        )

    def _on_process_finished(self, code, status) -> None:
        logger.info("Proceso de overlay terminado (%s, %s)", code, status)
        if self._process is not None:
            self._process.deleteLater()
            self._process = None

    def _read_stdout(self) -> None:
        process = self._process
        if process is None:
            return
        raw = bytes(process.readAllStandardOutput()).decode("utf-8", errors="ignore")
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Overlay stdout: %s", line)
                continue
            if isinstance(data, dict) and data.get("type") == "position":
                position = str(data.get("position") or "")
                if position in POSITION_KEYS:
                    self.position_changed.emit(position)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None:
            return
        raw = bytes(process.readAllStandardError()).decode("utf-8", errors="ignore")
        for line in raw.splitlines():
            if line.strip():
                logger.debug("Overlay: %s", line)

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        process.closeWriteChannel()
        if process.state() != QProcess.ProcessState.NotRunning:
            # El proceso auxiliar termina solo al recibir EOF por stdin.
            # Le damos un instante antes de forzar la salida.
            if not process.waitForFinished(400):
                process.terminate()
                if not process.waitForFinished(1200):
                    process.kill()
                    process.waitForFinished(800)
        process.deleteLater()
        logger.info("Proceso de overlay detenido")

    def cleanup(self) -> None:
        self._enabled = False
        self._stop_loader()
        self._stop_opponent_loader()
        self._stop_process()
