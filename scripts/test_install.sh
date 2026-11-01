#!/usr/bin/env bash
# Test de contrato de install.sh: es la interfaz pública que usan los instaladores externos.
#   - Sin argumentos instala un enlace por skill en ~/.claude/skills y ~/.agents/skills.
#   - Se puede correr varias veces sin romper nada.
#   - --uninstall quita solo los enlaces que apuntan a este repo.
#   - Nunca toca carpetas reales ni enlaces ajenos.
#   - Respeta CLAUDE_CONFIG_DIR: Claude Code permite mover su carpeta de configuración.
# Corre en un HOME temporal: no toca tu máquina.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd -P)"
HOME="$(mktemp -d)"
export HOME
unset CLAUDE_CONFIG_DIR
trap 'rm -rf "$HOME"' EXIT

fail() { echo "✖ $1" >&2; exit 1; }
count_links() { find "$1" -maxdepth 1 -type l 2>/dev/null | wc -l | tr -d ' '; }

expected="$(find "$REPO/skills" -mindepth 2 -maxdepth 2 -name SKILL.md | wc -l | tr -d ' ')"
mkdir -p "$HOME/.claude/skills/ajena-real" "$HOME/.agents/skills"
ln -s /tmp "$HOME/.agents/skills/ajena-enlace"

"$REPO/install.sh" > /dev/null
"$REPO/install.sh" > /dev/null

[ "$(count_links "$HOME/.claude/skills")" -eq "$expected" ] || fail "no hay $expected enlaces en .claude/skills"
[ "$(count_links "$HOME/.agents/skills")" -eq "$((expected + 1))" ] || fail "no hay $expected enlaces, más el ajeno, en .agents/skills"
for link in "$HOME"/.claude/skills/* "$HOME"/.agents/skills/hb-*; do
  [ -L "$link" ] && { [ -e "$link" ] || fail "enlace roto: $link"; }
done

"$REPO/install.sh" --uninstall > /dev/null

[ "$(count_links "$HOME/.claude/skills")" -eq 0 ] || fail "--uninstall dejó enlaces en ~/.claude/skills"
[ -L "$HOME/.agents/skills/ajena-enlace" ] || fail "--uninstall borró un enlace ajeno"
[ -d "$HOME/.claude/skills/ajena-real" ] || fail "install.sh tocó una carpeta real"

# Con CLAUDE_CONFIG_DIR, los enlaces de Claude Code van a esa carpeta y no a ~/.claude
export CLAUDE_CONFIG_DIR="$HOME/otra-config"
"$REPO/install.sh" > /dev/null

[ "$(count_links "$CLAUDE_CONFIG_DIR/skills")" -eq "$expected" ] || fail "no respeta CLAUDE_CONFIG_DIR al instalar"
[ "$(count_links "$HOME/.claude/skills")" -eq 0 ] || fail "con CLAUDE_CONFIG_DIR, igual escribió en .claude/skills"
[ "$(count_links "$HOME/.agents/skills")" -eq "$((expected + 1))" ] || fail "con CLAUDE_CONFIG_DIR, no instaló en .agents/skills"

"$REPO/install.sh" --uninstall > /dev/null

[ "$(count_links "$CLAUDE_CONFIG_DIR/skills")" -eq 0 ] || fail "--uninstall no respeta CLAUDE_CONFIG_DIR"
[ -L "$HOME/.agents/skills/ajena-enlace" ] || fail "--uninstall borró un enlace ajeno"
unset CLAUDE_CONFIG_DIR

echo "✔ install.sh cumple su contrato ($expected skills, también con CLAUDE_CONFIG_DIR)"
