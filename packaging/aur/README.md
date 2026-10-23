# AUR — `mtga-companion-bin`

Paquete binario para Arch Linux basado en el AppImage publicado en GitHub Releases.

## Probar localmente

```bash
cd packaging/aur/mtga-companion-bin
makepkg --verifysource
makepkg -si
```

El `PKGBUILD` descarga el AppImage del release `v0.1.0`, verifica su SHA-256 e instala:

- `/usr/bin/mtga-companion`
- `/usr/share/applications/mtga-companion.desktop`
- `/usr/share/icons/hicolor/256x256/apps/mtga-companion.png`

## Publicar en AUR

Se necesita una cuenta de AUR con una clave SSH registrada.

```bash
git clone ssh://aur@aur.archlinux.org/mtga-companion-bin.git
cd mtga-companion-bin
cp /ruta/al/repo/packaging/aur/mtga-companion-bin/{PKGBUILD,.SRCINFO,mtga-companion.desktop,mtga-companion.png} .
git add PKGBUILD .SRCINFO mtga-companion.desktop mtga-companion.png
git commit -m "Initial upload: mtga-companion-bin 0.1.0"
git push
```

Antes de publicar una versión nueva, actualizar `pkgver`, el SHA-256 del AppImage en `sha256sums` y regenerar `.SRCINFO`:

```bash
makepkg --printsrcinfo > .SRCINFO
```
