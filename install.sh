#!/bin/sh
# Depoloma installer for Ubuntu / Linux and macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh
#   (no curl?  wget -qO- https://raw.githubusercontent.com/musakartalengin/depoloma/main/install.sh | sh)
#
# Puts Depoloma in ~/.local/share/depoloma, a `depoloma` command in ~/.local/bin and,
# on Linux, an entry in the applications menu. Needs no root and no extra packages:
# Python 3.8+ is all it uses (Ubuntu ships it).
#
# To remove it again:  sh ~/.local/share/depoloma/install.sh --uninstall
set -e
REPO="${DEPOLOMA_REPO:-musakartalengin/depoloma}"
BRANCH="${DEPOLOMA_BRANCH:-main}"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/depoloma"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="$APPS/depoloma.desktop"

if [ "$1" = "--uninstall" ]; then
    rm -f "$BIN/depoloma" "$DESKTOP"
    rm -rf "$DEST"
    echo "Depoloma kaldirildi (removed)."
    exit 0
fi

PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
        PY="$(command -v "$cand")"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "Depoloma icin Python 3.8+ gerekiyor (needs Python 3.8+):  sudo apt install python3" >&2
    exit 1
fi

URL="https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
echo "Depoloma indiriliyor (downloading)..."
if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" | tar -xz -C "$TMP"
elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$URL" | tar -xz -C "$TMP"
else
    "$PY" - "$URL" "$TMP" <<'EOF'
import io, sys, tarfile, urllib.request
with urllib.request.urlopen(sys.argv[1]) as r:
    tarfile.open(fileobj=io.BytesIO(r.read()), mode="r:gz").extractall(sys.argv[2])
EOF
fi
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
[ -n "$SRC" ] && [ -d "$SRC/depoloma" ] || { echo "Indirme basarisiz (download failed)." >&2; exit 1; }
mkdir -p "$(dirname "$DEST")" "$BIN"
rm -rf "$DEST"                                   # replaces a previous Depoloma install only
mv "$SRC" "$DEST"

cat > "$BIN/depoloma" <<EOF
#!/bin/sh
cd "$DEST" && exec "$PY" -m depoloma "\$@"
EOF
chmod +x "$BIN/depoloma"

if [ "$(uname -s)" = "Linux" ]; then
    mkdir -p "$APPS"
    cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Depoloma
GenericName=Disk Usage Analyzer
GenericName[tr]=Disk Kullanım Çözümleyici
Comment=See where your disk space went
Comment[tr]=Disk alanın nereye gitti?
Exec=$BIN/depoloma
Icon=$DEST/depoloma/web/icon.png
Terminal=false
Categories=System;Utility;Filesystem;
Keywords=disk;storage;space;cleanup;depolama;temizlik;
StartupNotify=true
EOF
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi

echo ""
echo "Depoloma kuruldu (installed): $DEST"
if [ "$(uname -s)" = "Linux" ]; then
    echo "Uygulamalar menusunde 'Depoloma' diye arayin, ya da terminalde:  depoloma"
    echo "Find 'Depoloma' in the applications menu, or run:  depoloma"
else
    echo "Run:  depoloma"
fi
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) echo "Not: '$BIN' PATH icinde degil; yeni bir terminal acin ya da su satiri ~/.profile dosyasina ekleyin:"
       echo "      export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac
