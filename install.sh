#!/usr/bin/env bash
# Instala las skills de este repo como enlaces simbólicos en los directorios globales de los agentes:
#   ~/.claude/skills  → Claude Code (respeta CLAUDE_CONFIG_DIR)
#   ~/.agents/skills  → Android Studio (Gemini), Junie, Codex y otros agentes compatibles con Agent Skills
#
# Uso:
#   ./install.sh               instala o actualiza los enlaces
#   ./install.sh --uninstall   quita los enlaces que apuntan a este repo
#
# Como son enlaces, un `git pull` actualiza las skills sin reinstalar.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd -P)"
SKILLS="$REPO/skills"
TARGETS=("${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" "$HOME/.agents/skills")

points_to_repo() { case "$(readlink "$1")" in "$SKILLS"/*) return 0 ;; *) return 1 ;; esac; }

uninstall() {
  for target in "${TARGETS[@]}"; do
    [ -d "$target" ] || continue
    for link in "$target"/*; do
      if [ -L "$link" ] && points_to_repo "$link"; then
        rm "$link" && echo "✖ $link"
      fi
    done
  done
}

install() {
  for target in "${TARGETS[@]}"; do
    mkdir -p "$target"
    for link in "$target"/*; do
      if [ -L "$link" ] && points_to_repo "$link" && [ ! -e "$link" ]; then
        rm "$link" && echo "🧹 $link (ya no existe en el repo)"
      fi
    done
    for skill in "$SKILLS"/*/; do
      skill="${skill%/}"
      [ -f "$skill/SKILL.md" ] || continue
      link="$target/$(basename "$skill")"
      if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "⚠️  $link existe y no es un enlace: no lo toco"
        continue
      fi
      ln -sfn "$skill" "$link" && echo "✔ $link"
    done
  done
}

case "${1:-}" in
  --uninstall) uninstall ;;
  "") install ;;
  *) echo "Uso: $0 [--uninstall]" >&2; exit 1 ;;
esac
