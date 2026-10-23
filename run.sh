#!/usr/bin/env bash
# Ejecutar MTGA Companion para Linux
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creando entorno virtual e instalando dependencias..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r mtga_companion/requirements.txt
fi

source .venv/bin/activate
exec python -m mtga_companion
