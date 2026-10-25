#!/bin/sh
# Installs an `anima` command in ~/.local/bin that works from any folder.
set -e
repo="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/anima" <<SH
#!/bin/sh
# Anima bot CLI, runnable from any folder. Project: $repo
exec uv run --project "$repo" anima "\$@"
SH
chmod +x "$HOME/.local/bin/anima"
echo "Installed $HOME/.local/bin/anima → $repo"
