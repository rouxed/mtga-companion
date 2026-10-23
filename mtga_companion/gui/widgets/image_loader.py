"""Descarga de imágenes de cartas usando QNetworkAccessManager (nativo de Qt).

No hay hilos secundarios creando objetos Qt, evitando SIGABRT/SIGSEGV.
Todas las descargas son asíncronas dentro del mismo hilo de la aplicación.

El loader mantiene:
  * una caché en memoria (QPixmap),
  * una caché en disco (un archivo por URL),
  * una cola con un máximo de descargas concurrentes.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from mtga_companion.config import CARD_IMAGES_DIR

logger = logging.getLogger(__name__)

IMAGE_CACHE_DIR = CARD_IMAGES_DIR
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

MAX_CONCURRENT_DOWNLOADS = 6

_HEADERS = {"User-Agent": "mtga-companion/1.0 (personal use)"}


class ImageLoader(QObject):
    """Descarga imágenes de forma asíncrona usando QNetworkAccessManager.

    Todo corre en el hilo de la GUI (no hay hilos secundarios), así que no
    hay riesgo de crear objetos Qt en hilos incorrectos.
    """

    image_ready = pyqtSignal(str, object)  # url, QPixmap | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._manager.finished.connect(self._on_reply_finished)

        self._memory_cache: dict[str, QPixmap | None] = {}
        self._pending: dict[str, list] = {}  # url -> lista de callbacks
        self._active: set[str] = set()       # URLs con petición en curso
        self._queue: list[str] = []          # URLs esperando turno
        self._lock = threading.Lock()

    def _cache_path(self, url: str) -> Path:
        # MD5 se usa solo como nombre de archivo de caché (no es seguridad).
        # Se mantiene para reutilizar las imágenes ya descargadas.
        return IMAGE_CACHE_DIR / (hashlib.md5(url.encode("utf-8")).hexdigest() + ".jpg")

    def load(self, url: str | None, callback) -> QPixmap | None:
        """Devuelve QPixmap si está disponible, None si hay que descargar.

        ``callback(pixmap)`` se invoca en el hilo de la GUI.
        """
        if not url:
            callback(None)
            return None

        # Si es una ruta local de archivo, cargar directamente.
        if os.path.isfile(url):
            pixmap = QPixmap(url)
            if not pixmap.isNull():
                with self._lock:
                    self._memory_cache[url] = pixmap
                callback(pixmap)
                return pixmap
            callback(None)
            return None

        # Memoria.
        with self._lock:
            if url in self._memory_cache:
                pix = self._memory_cache[url]
                if pix is not None:
                    callback(pix)
                    return pix

        # Disco (caché descargado).
        path = self._cache_path(url)
        if path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                with self._lock:
                    self._memory_cache[url] = pixmap
                callback(pixmap)
                return pixmap

        # Encolar: si ya hay una petición activa o en cola, solo agregamos
        # el callback. Si es nueva, se arranca (o se encola) una descarga.
        with self._lock:
            if url in self._pending:
                self._pending[url].append(callback)
                return None

            self._pending[url] = [callback]
            self._queue.append(url)

        self._pump()
        return None

    def _pump(self) -> None:
        """Inicia descargas nuevas mientras no se supere el máximo concurrente."""
        while True:
            with self._lock:
                if len(self._active) >= MAX_CONCURRENT_DOWNLOADS or not self._queue:
                    return
                url = self._queue.pop(0)
                # Si se limpió la cola mientras tanto, ignorar.
                if url not in self._pending:
                    continue
                self._active.add(url)

            request = QNetworkRequest(QUrl(url))
            user_agent = _HEADERS["User-Agent"]
            request.setHeader(
                QNetworkRequest.KnownHeaders.UserAgentHeader, user_agent
            )
            request.setAttribute(
                QNetworkRequest.Attribute.RedirectPolicyAttribute,
                QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
            )
            self._manager.get(request)

    def _on_reply_finished(self, reply: QNetworkReply) -> None:
        url = reply.request().url().toString()
        pixmap: QPixmap | None = None

        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(bytes(data))
            if pixmap.isNull():
                pixmap = None
            else:
                path = self._cache_path(url)
                try:
                    # Escritura atómica para no dejar archivos a medias si la
                    # app se cierra durante la descarga.
                    tmp_path = path.with_suffix(path.suffix + ".tmp")
                    tmp_path.write_bytes(bytes(data))
                    os.replace(tmp_path, path)
                except OSError:
                    logger.warning("No se pudo guardar la imagen en caché: %s", path)
        else:
            logger.debug("Error descargando imagen %s: %s", url, reply.errorString())

        reply.deleteLater()
        self._deliver(url, pixmap)

    def _deliver(self, url: str, pixmap: QPixmap | None) -> None:
        """Entrega el resultado a todos los callbacks pendientes de esa URL."""
        with self._lock:
            self._active.discard(url)
            self._memory_cache[url] = pixmap
            callbacks = self._pending.pop(url, [])

        for callback in callbacks:
            try:
                callback(pixmap)
            except Exception:
                logger.exception("Error en callback de imagen para %s", url)

        self._pump()

    def clear_pending(self) -> None:
        """Descartar callbacks pendientes (usar al cambiar de mazo).

        Las peticiones ya iniciadas se dejan terminar; simplemente se
        descartan sus callbacks para no actualizar widgets que ya no existen.
        """
        with self._lock:
            for url in list(self._pending):
                if url in self._active:
                    self._pending[url] = []
                else:
                    self._pending.pop(url, None)
            self._queue.clear()


# Instancia global del loader
_global_loader: ImageLoader | None = None
_global_loader_lock = threading.Lock()


def get_global_loader() -> ImageLoader:
    global _global_loader
    with _global_loader_lock:
        if _global_loader is None:
            _global_loader = ImageLoader()
        return _global_loader


def clear_all_pending() -> None:
    """Descartar todas las descargas pendientes (usar al cambiar de mazo)."""
    loader = get_global_loader()
    loader.clear_pending()
