# MTGA Companion para Linux

Clon del Companion de [Untapped.gg](https://untapped.gg) para **Magic: The Gathering Arena**, nativo para Linux (CachyOS / cualquier distro).

Lee el `Player.log` de MTG Arena (Steam/Proton, Lutris, Heroic/Epic, Bottles, Wine manual o una partición Windows) en tiempo real y te muestra:

- **Dashboard**: winrate global (todo el historial), winrate diario (hoy, últimos 7 días, últimos 30 días) y partidas recientes.
- **Historial**: listado completo de partidas con mazo, resultado, oponente y fecha.
- **Mazos**: tus mazos con las cartas agrupadas por tipo (Criaturas, Tierras, Instantáneos, etc.) e imágenes reales de Scryfall, al estilo Untapped.gg.
- **Meta**: mazos meta de internet (MTGGoldfish) para Standard, Historic, Explorer y Alchemy. Muestra el meta share y los precios de Tabletop/MTGO, y al seleccionar un mazo carga su decklist de muestra (main deck + banquillo) con imágenes reales de **Scryfall**. La lista se puede copiar en formato de importación de MTG Arena. El listado se cachea por formato durante 6 horas; si falla internet se usa la caché existente o mazos de respaldo locales.
- **Overlay opcional**: deck tracker flotante sobre MTG Arena con las cartas que te quedan, probabilidades hipergeométricas de robo, contador de tierras y cartas vistas del oponente. Se calcula solo con tu mazo, tu mano y las zonas públicas o reveladas del log.
- **Configuración**: selector de rutas detectadas, ruta manual de respaldo, nombre de jugador, arranque/parada del seguimiento en vivo, controles del overlay y selector de idioma (español/inglés).

## Requisitos

- Python 3.10+
- PyQt6, requests
- MTG Arena instalado con Wine/Proton (Steam, Lutris, Heroic/Epic, Bottles o Wine manual) y haber jugado al menos una partida
- En MTG Arena: **Configuración > Cuenta > "Detailed Logs (Plugin Support)" activado**

## Instalación

```bash
# Clonar / entrar al proyecto
cd mtga-companion

# Crear entorno virtual e instalar dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -r mtga_companion/requirements.txt
```

## Ejecución

```bash
source .venv/bin/activate
python -m mtga_companion
```

La aplicación es una ventana de escritorio (PyQt6), no un servidor web.

## Distribución (AppImage)

El formato principal de distribución es un **AppImage**. No requiere Python instalado ni permisos de root, y mantiene acceso directo al `Player.log` y a los prefijos de Proton (un sandbox como Flatpak complicaría esas rutas).

### Construir

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
./packaging/build_appimage.sh
```

El script usa PyInstaller en modo `onedir`, arma el `AppDir` y lo empaqueta con `appimagetool` (si no está, lo descarga a `build/tools/`). El resultado es:

```text
dist/MTGA-Companion-0.1.0-x86_64.AppImage
dist/MTGA-Companion-0.1.0-x86_64.AppImage.sha256
```

La versión sale de `mtga_companion/__init__.py`; cambiala ahí para generar una release nueva. El icono ya está incluido en `packaging/`; solo hace falta `rsvg-convert` si querés regenerarlo. El `.sha256` se genera junto al AppImage para verificar la descarga:

```bash
cd dist
sha256sum -c MTGA-Companion-0.1.0-x86_64.AppImage.sha256
cd ..
```

### Ejecutar

```bash
chmod +x dist/MTGA-Companion-0.1.0-x86_64.AppImage
./dist/MTGA-Companion-0.1.0-x86_64.AppImage
./dist/MTGA-Companion-0.1.0-x86_64.AppImage --version
```

Como el AppImage incluye Python, PyQt6 y Qt, no necesita el entorno virtual. Si el sistema no tiene FUSE disponible, se puede extraer y ejecutar igual:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./dist/MTGA-Companion-0.1.0-x86_64.AppImage
```

El AppImage no guarda datos dentro de sí mismo: sigue usando las rutas XDG de la tabla de abajo. La app principal corre en Wayland y el overlay se relanza desde el mismo ejecutable con `--overlay-process` en un proceso XCB/XWayland.

## Interfaz

La interfaz usa un tema oscuro con navegación lateral, superficies en capas y acentos dorados. El **Dashboard** muestra el winrate global en un anillo y las partidas recientes en una tabla compacta. Las pestañas **Mazos** y **Meta** presentan las cartas en una grilla de imágenes adaptable al ancho de la ventana, con la cantidad sobre cada carta. El detalle de un mazo meta incluye metadatos, banquillo y un panel para copiar la lista en formato MTG Arena.

### Idioma

La aplicación está disponible en **español** e **inglés**. El idioma inicial es español; se cambia en **Configuración > Idioma** y se guarda en `settings.json` con la clave `language`. El cambio se aplica inmediatamente reconstruyendo la ventana y reiniciando el overlay con el idioma elegido. No se detecta automáticamente desde el locale del sistema.

Las cadenas fuente siguen en español y se traducen en tiempo de ejecución desde `mtga_companion/i18n.py`; el proceso auxiliar del overlay recibe el idioma mediante `MTGA_COMPANION_LANG`.

## Overlay de partida

El overlay se activa con el botón **Overlay** de la cabecera o desde **Configuración > Overlay de partida**. Es opcional y arranca desactivado.

- **Mazo restante**: lista las cartas que todavía tenés en la biblioteca, agrupadas por tipo y con la probabilidad de robar cada una en el próximo robo.
- **Probabilidades**: muestra la chance del **próximo robo** y de robar al menos una carta de tierras, criaturas, hechizos y otras en los **próximos 3 robos**.
- **Tierras**: cuenta las tierras en el campo de batalla, cuántas están sin girar, las que tenés en mano y las que quedan en la biblioteca. Las tierras giradas/desgiradas se actualizan con las anotaciones del log.
- **Cartas vistas del oponente**: acumula las cartas del oponente que aparecen en zonas públicas o reveladas (pila, cementerio, exilio, comando y `ZoneType_Revealed`). **No lee la mano ni la biblioteca del oponente, ni la carta de arriba de tu biblioteca.** La lista se reinicia al empezar una partida nueva.
- Las probabilidades son hipergeométricas y usan el mazo actual, las cartas en la biblioteca y las cartas propias conocidas en mano, campo, cementerio, exilio, pila y comando. No se lee memoria del juego.
- No modela scry, surveil, tutores, milagros ni cartas que cambian el orden de la biblioteca; por eso las probabilidades son de robos naturales y pueden diferir de las de otros trackers.
- Por defecto es click-through (los clics pasan al juego), aparece **centrado a la izquierda** de la pantalla y usa opacidad 94%. Podés elegir las cuatro esquinas o los laterales centrados (centro izquierda / centro derecha). Si desactivás click-through, podés moverlo con el mouse. La posición, opacidad y click-through se guardan en la configuración.
- En KDE Wayland la ventana principal sigue usando Wayland y el overlay se ejecuta en un proceso aparte con XCB/XWayland. Necesita un servidor X11 o XWayland (`DISPLAY`); si no existe, la app lo informa en Configuración y el resto sigue funcionando.
- La ventana se oculta al terminar la partida y vuelve a aparecer en la siguiente. Los nombres y tipos de cartas se resuelven con Scryfall en segundo plano; mientras tanto el panel muestra **Resolviendo cartas**.

## Pruebas

```bash
# Dependencias de desarrollo (incluye las de ejecución)
pip install -r requirements-dev.txt

# Toda la suite
python -m pytest

# Un archivo en particular
python -m pytest tests/test_parser.py -v
```

Las pruebas no necesitan un servidor gráfico: usan el plugin `offscreen` de Qt.

## Primera vez

1. Abrí la aplicación con `./run.sh`.
2. El `Player.log` se detecta automáticamente buscando el patrón interno de cualquier prefijo Wine/Proton (`drive_c/users/*/AppData/LocalLow/Wizards Of The Coast/MTGA/Player.log`) en instalaciones de Steam (nativo y Flatpak), Lutris, Heroic/Epic, Bottles, Wine manual y particiones Windows montadas. El seguimiento se inicia solo, incluso si MTG Arena todavía no está abierto: el watcher espera a que aparezca el archivo y lo vuelve a detectar cuando el juego lo crea.
   - Si hay varias instalaciones, en **Configuración** podés elegir la ruta en el selector **Detectadas**; se usa por defecto la más reciente. La ruta manual sigue teniendo prioridad.
   - Si no se detecta, usá **Examinar…** o pegá una ruta que todavía no exista; el watcher la esperará.
3. Ingresá tu nombre de jugador de Arena (formato `Nombre#12345`) en Configuración para que el companion sepa cuándo ganaste o perdiste.
4. Jugá partidas en MTG Arena; se irán registrando solas en el Dashboard y el Historial.

## Dónde se guardan los datos

La aplicación usa las rutas estándar XDG, no escribe datos dentro del paquete:

| Dato | Ruta |
| --- | --- |
| Base de datos SQLite | `~/.local/share/mtga-companion/mtga_companion.db` |
| Caché de cartas / meta | `~/.local/share/mtga-companion/card_cache.json`, `meta_cache.json` |
| Imágenes de cartas | `~/.local/share/mtga-companion/card_images/` |
| Configuración | `~/.config/mtga-companion/settings.json` |
| Logs rotativos | `~/.local/share/mtga-companion/logs/mtga-companion.log` |

En la primera ejecución se **copian** automáticamente los datos de la versión anterior que estaban en `mtga_companion/data/` y `mtga_companion/settings.json`. Los archivos originales no se borran, así que quedan como copia de seguridad. Si `XDG_DATA_HOME` o `XDG_CONFIG_HOME` están definidos, se respetan.

> **Importante:** En MTG Arena, activá **Configuración > Cuenta > "Detailed Logs (Plugin Support)"**, si no el juego no escribe suficiente detalle en el log y el companion no podrá trackear tus partidas.

## Cómo funciona

- Un hilo de fondo hace `tail -f` del `Player.log` de MTG Arena, con detección de rotación/truncado y re-escaneo automático de prefijos Wine/Proton si el archivo todavía no existe.
- Detecta mazos al inicio de cada partida (`CourseDeckSummary`) y el resultado al terminar (`matchGameRoomStateChangedEvent` + `MatchCompleted`).
- Al arrancar hace un backfill de los últimos 5 MB del log: recupera el mazo de una partida en curso y una partida que haya terminado hace pocos minutos, sin duplicar el historial.
- Cada partida se guarda con la hora real del log y el `matchId` de Arena. El `matchId` tiene un índice único, así que reinicios, relecturas y backfills no duplican partidas.
- La base SQLite se migra automáticamente con `PRAGMA user_version` (esquema actual: 2, con `match_id`).
- Los IDs internos de cartas de Arena se resuelven a nombres e imágenes mediante la API pública de **Scryfall** (sin API key), con caché local en disco.
- Para el overlay, el watcher reconstruye las zonas GRE de la partida en curso, las tierras y las cartas públicas del oponente. El motor calcula las probabilidades con la lista del mazo activo y el proceso XCB recibe solo un JSON compacto; nunca recibe la identidad de la carta superior de la biblioteca ni la mano oculta del oponente.
- La pestaña Meta usa un listado por formato (Standard, Historic, Explorer, Alchemy) con TTL de 6 horas. Las shares (`11.5%`) y los precios (`$241` Tabletop, `42 tix` MTGO) se normalizan antes de mostrarse. La caché antigua de un solo formato se migra automáticamente al leerla.
- El decklist de un arquetipo se obtiene del main deck + sideboard de muestra de MTGGoldfish y se exporta con encabezados `Deck`/`Sideboard`, el formato que acepta MTG Arena.
- Al cerrar se detienen el watcher, los temporizadores y los hilos de descarga de forma cooperativa. El proceso del overlay se cierra por EOF; solo si no responde se fuerza su terminación.

## Estructura del proyecto

```
mtga_companion/
  main.py           # Punto de entrada: logging, migración, QApplication
  __main__.py       # Permite `python -m mtga_companion`
  config.py         # Rutas XDG, migración y escáner universal de prefijos Wine/Proton
  i18n.py           # Traducciones español/inglés y cambio de idioma en tiempo de ejecución
  database.py       # SQLite: esquema/migraciones, partidas, mazos, estadísticas
  logging_config.py # Log rotativo + excepthook + mensajes de Qt
  models.py         # Modelos de datos
  parser.py         # Parser del Player.log (mazos + resultados + matchId)
  log_watcher.py    # Tail -f, backfill, rotación/truncado y deduplicación
  game_state.py     # Reconstruye zonas, tierras y cartas públicas desde los mensajes GRE
  draw_odds.py      # Probabilidades, deck tracker y cartas vistas del oponente
  overlay_positions.py # Posiciones admitidas del overlay
  overlay_process.py # Proceso XCB que dibuja el overlay y recibe snapshots JSON
  overlay_window.py  # Panel transparente y click-through del overlay
  scryfall.py       # Cliente Scryfall (nombres + imágenes de cartas)
  meta_fetcher.py   # MTGGoldfish (listado + decklists), caché TTL y fallback
  thread_registry.py# Cierre cooperativo de hilos
  gui/              # Interfaz de escritorio PyQt6
    theme.py        # Paleta, QSS global e íconos
    main_window.py  # Ventana principal con sidebar y cabecera
    dashboard_widget.py
    history_widget.py
    decks_widget.py
    settings_widget.py
    meta_widget.py
    overlay_controller.py # Ciclo de vida del proceso de overlay y envío de estado
    assets/icons/   # Íconos SVG del tema
    widgets/        # CardTile, DeckGroup, ImageLoader, DeckLoader, UI
packaging/          # PyInstaller, .desktop, icono y build del AppImage
tests/              # Suite de regresión con pytest
```

## Limitaciones conocidas

- El nombre de algunos mazos predeterminados aparece como claves de localización (ej. `?=?Loc/Decks/Precon/...`) porque MTG Arena no escribe el nombre traducido en el log.
- El parser se basa en marcadores del `Player.log` que no son un estándar oficial; pueden cambiar con actualizaciones del juego.
- MTGGoldfish no siempre publica mazos para todos los formatos (Alchemy suele aparecer vacío); en ese caso la pestaña Meta lo indica y no inventa datos.
- No hay integración de colección: MTG Arena no expone tus cartas en un archivo local y no se lee la memoria del proceso.
- El overlay requiere X11/XWayland y un compositor que respete ventanas override-redirect; en Wayland puro sin XWayland no se muestra (la app principal sigue funcionando).
- Las probabilidades del overlay son solo para robos naturales: no contemplan scry, surveil, tutores, robos extra ni cartas que muevan o barajen la biblioteca.
- Las **cartas vistas del oponente** solo incluyen lo que Arena escribe como público o revelado. Si una carta nunca pasó por esas zonas, el overlay no puede mostrarla y no intenta adivinarla.
- El seguimiento en vivo depende de **Detailed Logs (Plugin Support)** activado en MTG Arena.
