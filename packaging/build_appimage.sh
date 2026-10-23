#!/usr/bin/env bash
# Construye un AppImage autocontenido de MTGA Companion.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -d "$ROOT/.venv" ]; then
    # shellcheck disable=SC1091
    source "$ROOT/.venv/bin/activate"
fi

if ! python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "Falta PyInstaller. Instalá las dependencias de desarrollo:"
    echo "  python -m pip install -r requirements-dev.txt"
    exit 1
fi

VERSION="$(python -c 'from mtga_companion import __version__; print(__version__)')"
BUILD_DIR="$ROOT/build/appimage"
APPDIR="$BUILD_DIR/AppDir"
DIST_DIR="$ROOT/dist"
OUTPUT="$DIST_DIR/MTGA-Companion-${VERSION}-x86_64.AppImage"
TOOL="$ROOT/build/tools/appimagetool-x86_64.AppImage"

rm -rf "$APPDIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR" "$ROOT/build/tools"

echo "Construyendo ejecutable con PyInstaller..."
python -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath "$DIST_DIR" \
    --workpath "$ROOT/build/pyinstaller" \
    "$ROOT/packaging/mtga-companion.spec"

echo "Armando AppDir..."
mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp -a "$DIST_DIR/mtga-companion/." "$APPDIR/usr/bin/"
cp "$ROOT/packaging/mtga-companion.desktop" "$APPDIR/mtga-companion.desktop"
cp "$ROOT/packaging/mtga-companion.desktop" \
    "$APPDIR/usr/share/applications/mtga-companion.desktop"

if [ ! -f "$ROOT/packaging/mtga-companion.png" ]; then
    echo "Generando icono..."
    rsvg-convert \
        -w 256 -h 256 \
        "$ROOT/mtga_companion/gui/assets/icons/logo.svg" \
        -o "$ROOT/packaging/mtga-companion.png"
fi
cp "$ROOT/packaging/mtga-companion.png" "$APPDIR/mtga-companion.png"
cp "$ROOT/packaging/mtga-companion.png" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps/mtga-companion.png"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/mtga-companion" "$@"
EOF
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
    echo "Descargando appimagetool..."
    curl -L --fail --retry 3 \
        -o "$TOOL" \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi

echo "Empaquetando AppImage..."
rm -f "$OUTPUT"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" "$APPDIR" "$OUTPUT"
chmod +x "$OUTPUT"
(
    cd "$DIST_DIR"
    sha256sum "$(basename "$OUTPUT")" > "$(basename "$OUTPUT").sha256"
)

echo
echo "AppImage listo: $OUTPUT"
echo "Checksum: $OUTPUT.sha256"
echo "Ejecutalo con: $OUTPUT"
