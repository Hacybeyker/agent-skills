#!/usr/bin/env python3
"""Genera el reporte HTML de hb-implement a partir de git y de un meta.json.

El código (antes, después y diff) sale de git: el agente solo escribe el meta.json
con el contexto que git no sabe (título, tipo, por qué de cada archivo, resultado del DoD).

Un meta por tarea (reports/<fecha>-<slug>.meta.json): así un bloque no pisa el de otro.
Los archivos masivos o generados (goldens, fixtures) se explican en grupo, por carpeta o patrón,
con "groups"; un archivo con su propia entrada en "files" se muestra aparte.

Uso:
  python3 -I report.py --meta reports/<fecha>-<slug>.meta.json [--base HEAD] [--out reports] [--repo .]
"""
import argparse
import base64
import datetime
import difflib
import fnmatch
import html
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "report-template.html"
TYPES = {
    "feature": ("badge-feature", "✨ Feature"),
    "bugfix": ("badge-bugfix", "🐛 Bug Fix"),
    "enhancement": ("badge-enhancement", "⚡ Enhancement"),
    "refactor": ("badge-refactor", "♻️ Refactor"),
}
PILLS = {
    "pass": ("pill-pass", "✅ PASS"),
    "fail": ("pill-fail", "❌ FAIL"),
    "skipped": ("pill-skipped", "⏭️ SKIPPED"),
}
MAX_LINES = 2000
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
e = html.escape


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def decode(data):
    if data is None:
        return None
    if b"\0" in data[:8000]:
        return False  # binario
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return False


def changed_files(repo, base, out_dir):
    files = []
    for line in git(repo, "diff", "--name-status", "-M", base).decode().splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R":
            files.append({"status": "M", "path": parts[2], "old": parts[1]})
        elif status in "AMD":
            files.append({"status": status, "path": parts[1], "old": parts[1]})
    for path in git(repo, "ls-files", "--others", "--exclude-standard").decode().splitlines():
        files.append({"status": "A", "path": path, "old": None})
    out_rel = out_dir.resolve()
    return [f for f in files if out_rel not in (repo / f["path"]).resolve().parents]


def read_before(repo, base, path):
    if path is None:
        return None
    try:
        return git(repo, "show", f"{base}:{path}")
    except RuntimeError:
        return None


def read_after(repo, path):
    p = repo / path
    return p.read_bytes() if p.is_file() else None


def code_block(text, dim=False):
    if text is False:
        return '<div class="empty-state">Archivo binario: no se muestra el contenido.</div>'
    lines = text.splitlines()
    cut = len(lines) > MAX_LINES
    body = "\n".join(f'<span class="line-num">{i}</span>{e(l)}' for i, l in enumerate(lines[:MAX_LINES], 1))
    if cut:
        body += f'\n<span class="line-num">…</span>(recortado: {len(lines) - MAX_LINES} líneas más)'
    style = ' style="opacity:.6"' if dim else ""
    return f'<pre class="code-block"{style}>{body}</pre>'


def diff_block(before, after):
    if before is False or after is False:
        return '<div class="empty-state">Archivo binario: no se muestra el diff.</div>'
    rows, new_no = [], 0
    for line in list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=3))[2:]:
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_no = int(m.group(1)) - 1 if m else new_no
            rows.append(("hunk", "···", line))
        elif line.startswith("+"):
            new_no += 1
            rows.append(("add", "+", line))
        elif line.startswith("-"):
            rows.append(("del", "−", line))
        else:
            new_no += 1
            rows.append(("", str(new_no), line))
    if not rows:
        return '<div class="empty-state">Sin cambios de contenido (solo renombre o permisos).</div>'
    html_rows = "".join(
        f'<div class="diff-line {cls}"><div class="gutter">{g}</div><div class="content">{e(c)}</div></div>'
        for cls, g, c in rows
    )
    return f'<div class="diff-block">{html_rows}</div>'


def summary(items):
    cells = "".join(
        f'<div class="change-summary-item change-summary-{kind}"><div class="change-summary-label">{label}</div>{e(text)}</div>'
        for kind, label, text in items if text
    )
    return f'<div class="change-summary">{cells}</div>' if cells else ""


STATUS = {"A": ("status-new", "New"), "M": ("status-modified", "Modified"), "D": ("status-deleted", "Deleted")}


def status_summary(status, info):
    if status == "A":
        return summary([("after", "✅ Por qué se crea", info.get("why"))])
    if status == "D":
        return summary([("before", "🗑️ Por qué se elimina", info.get("why"))])
    return summary([("before", "⚠️ Antes", info.get("before")), ("after", "✅ Después", info.get("after") or info.get("why"))])


def file_entry(index, f, info):
    status = STATUS[f["status"]]
    path = f["path"] if f["status"] != "M" or f["old"] in (None, f["path"]) else f'{f["old"]} → {f["path"]}'
    head = (f'<div class="file-header" onclick="toggleFile(this)"><span class="file-status {status[0]}">{status[1]}</span>'
            f'<span class="file-path">{e(path)}</span><span class="file-toggle">▼</span></div>')
    if f["status"] == "A":
        body = status_summary("A", info) + code_block(f["after"])
    elif f["status"] == "D":
        body = status_summary("D", info) + code_block(f["before"], dim=True)
    else:
        fid = f"f{index}"
        tabs = "".join(
            f'<div class="panel-tab{" active" if t == "diff" else ""}" onclick="switchTab(\'{fid}\',\'{t}\')">{label}</div>'
            for t, label in (("before", "Antes"), ("after", "Después"), ("diff", "Diff"))
        )
        panels = (f'<div class="panel-content" id="{fid}-before">{code_block(f["before"])}</div>'
                  f'<div class="panel-content" id="{fid}-after">{code_block(f["after"])}</div>'
                  f'<div class="panel-content active" id="{fid}-diff">{diff_block(f["before"], f["after"])}</div>')
        body = status_summary("M", info) + f'<div class="panel-tabs" id="tabs-{fid}">{tabs}</div>{panels}'
    return f'<div class="file-entry open">{head}<div class="file-body">{body}</div></div>'


def group_for(path, groups):
    """El primer grupo cuyo "match" cubre la ruta: una carpeta (termina en /) o un patrón fnmatch."""
    for group in groups:
        pattern = group.get("match") or ""
        if pattern.endswith("/") and path.startswith(pattern):
            return group
        if pattern and not pattern.endswith("/") and fnmatch.fnmatchcase(path, pattern):
            return group
    return None


def group_entry(group, status, paths):
    label = STATUS[status]
    total = f"{len(paths)} archivo" + ("" if len(paths) == 1 else "s")
    head = (f'<div class="file-header" onclick="toggleFile(this)"><span class="file-status {label[0]}">{label[1]}</span>'
            f'<span class="file-path">{e(group["match"])} · {total}</span><span class="file-toggle">▼</span></div>')
    listing = '<pre class="code-block">' + e("\n".join(paths)) + "</pre>"
    return f'<div class="file-entry open">{head}<div class="file-body">{status_summary(status, group)}{listing}</div></div>'


def section(icon, title, entries, empty, count=None):
    content = "".join(entries) or f'<div class="empty-state">{empty}</div>'
    count = len(entries) if count is None else count
    return (f'<div class="section"><div class="section-header"><span class="section-icon">{icon}</span>'
            f'<span class="section-title">{title}</span><span class="section-count">{count}</span></div>{content}</div>')


def dod_section(steps):
    if not steps:
        return ""
    rows = ['<div class="dod-row dod-header"><div></div><div>Tarea</div><div>Comando</div><div>Resultado</div></div>']
    outputs = []
    for s in steps:
        cls, label = PILLS.get(s.get("status", "skipped"), PILLS["skipped"])
        note = f' · {e(s["note"])}' if s.get("note") else ""
        rows.append(f'<div class="dod-row"><div>{e(s.get("icon", "•"))}</div><div>{e(s.get("name", ""))}</div>'
                    f'<div>{e(s.get("command", ""))}</div><div><span class="pill {cls}">{label}</span>{note}</div></div>')
        if s.get("output"):
            outputs.append(f'<p style="margin:20px 0 8px"><strong>{e(s.get("name", ""))}</strong></p>{code_block(s["output"])}')
    return (f'<div class="section"><div class="section-header"><span class="section-icon">✅</span>'
            f'<span class="section-title">Definition of Done</span></div><div class="dod-grid">{"".join(rows)}</div>'
            f'{"".join(outputs)}</div>')


def preview_figure(repo, preview, missing):
    path = pathlib.Path(preview.get("image", ""))
    path = path if path.is_absolute() else repo / path
    name, note = e(preview.get("name", path.stem)), e(preview.get("note", ""))
    caption = f'<figcaption style="margin-top:8px;color:var(--text-secondary)"><strong>{name}</strong>{" · " + note if note else ""}</figcaption>'
    mime = IMAGE_TYPES.get(path.suffix.lower())
    if mime and path.is_file():
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        body = (f'<img src="data:{mime};base64,{data}" alt="{name}" '
                f'style="width:100%;max-width:360px;border:1px solid var(--border);border-radius:var(--radius-md)">')
    else:
        missing.append(str(path))
        body = f'<div class="empty-state">No se encontró la imagen: {e(str(path))}</div>'
    return f'<figure style="margin:0">{body}{caption}</figure>'


def previews_section(repo, previews, missing):
    """Imágenes incrustadas en base64: el reporte sigue siendo un solo archivo que se puede compartir."""
    if not previews:
        return ""
    figures = "".join(preview_figure(repo, p, missing) for p in previews)
    return (f'<div class="section"><div class="section-header"><span class="section-icon">🖼️</span>'
            f'<span class="section-title">Previews de UI</span><span class="section-count">{len(previews)}</span></div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:20px">{figures}</div></div>')


def dod_stat(steps):
    statuses = {s.get("status") for s in steps}
    if not steps:
        return "—", ""
    if "fail" in statuses:
        return "FAIL", "red"
    if statuses == {"pass"}:
        return "PASS", "green"
    return "PARTIAL", "orange"


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "reporte"


def ensure_ignored(repo, out_dir, report):
    """Si git no ignora el reporte, deja su carpeta en .git/info/exclude: local, el repo y su .gitignore no cambian.
    Devuelve un aviso para stderr, o None."""
    if subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", str(report)]).returncode == 0:
        return None
    try:
        relative = out_dir.resolve().relative_to(repo.resolve()).as_posix()
        found = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
                               capture_output=True, text=True)
        if found.returncode != 0 or relative in ("", "."):
            raise OSError("sin ruta de exclude")
        exclude = repo / found.stdout.strip()
        exclude.parent.mkdir(parents=True, exist_ok=True)
        current = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(("" if not current or current.endswith("\n") else "\n") + f"/{relative}/\n")
        print(f"✔ git ignora {relative} (en .git/info/exclude, local: el repo no cambia)")
    except (OSError, ValueError):
        return f"⚠️  {out_dir.name}/ no está ignorada por git y no pude agregarla a .git/info/exclude: que no entre a un commit"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--meta", required=True, help="JSON con título, tipo, explicaciones por archivo y DoD")
    ap.add_argument("--base", default="HEAD", help="ref contra la que se compara (por defecto HEAD)")
    ap.add_argument("--out", default="reports", help="carpeta de salida (relativa al repo)")
    ap.add_argument("--repo", default=".", help="raíz del repositorio")
    args = ap.parse_args()

    repo = pathlib.Path(git(args.repo, "rev-parse", "--show-toplevel").decode().strip())
    meta = json.loads(pathlib.Path(args.meta).read_text(encoding="utf-8"))
    out_dir = repo / args.out
    template = TEMPLATE.read_text(encoding="utf-8")
    style = re.search(r"<style>.*?</style>", template, re.S).group(0)
    script = re.search(r"<script>.*?</script>", template, re.S).group(0)

    infos = meta.get("files", {})
    group_defs = meta.get("groups", [])
    files = []
    for f in changed_files(repo, args.base, out_dir):
        f["before"] = decode(read_before(repo, args.base, f["old"])) if f["status"] != "A" else None
        f["after"] = decode(read_after(repo, f["path"])) if f["status"] != "D" else None
        # Un archivo con su propia entrada en "files" se muestra aparte, aunque un grupo lo cubra.
        f["group"] = None if f["path"] in infos else group_for(f["path"], group_defs)
        files.append(f)

    groups = {k: [] for k in "AMD"}
    counts = {k: sum(1 for f in files if f["status"] == k) for k in "AMD"}
    for k in "AMD":
        grouped = {}
        for i, f in enumerate(files):
            if f["status"] != k:
                continue
            if f["group"] is None:
                groups[k].append(file_entry(i, f, infos.get(f["path"], {})))
            else:
                grouped.setdefault(id(f["group"]), (f["group"], []))[1].append(f["path"])
        groups[k].extend(group_entry(group, k, paths) for group, paths in grouped.values())
    project = meta.get("project") or repo.name
    date = meta.get("date") or datetime.date.today().isoformat()
    badge_cls, badge_label = TYPES.get(meta.get("type", "feature"), TYPES["feature"])
    dod = meta.get("dod", [])
    dod_value, dod_color = dod_stat(dod)
    scope = f'<span class="tag">{e(meta["scope"])}</span>' if meta.get("scope") else ""
    missing_previews = []
    previews = previews_section(repo, meta.get("previews", []), missing_previews)

    page = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(project)} · {e(meta.get("title", "Reporte"))}</title>
{style}
</head><body>
<div class="topbar"><span class="topbar-logo">{e(project)}</span><span class="topbar-sep">/</span>
<span class="topbar-title">Implementation Report</span><div class="topbar-spacer"></div><span class="topbar-date">{date}</span></div>
<div class="container">
<div class="hero"><div class="hero-eyebrow"><span class="badge {badge_cls}">{badge_label}</span>{scope}</div>
<h1 class="hero-title">{e(meta.get("title", ""))}</h1><p class="hero-desc">{e(meta.get("description", ""))}</p>
<div class="stats-row">
<div class="stat-card"><div class="stat-label">Archivos Nuevos</div><div class="stat-value green">{counts["A"]}</div></div>
<div class="stat-card"><div class="stat-label">Archivos Modificados</div><div class="stat-value" style="color:var(--accent-blue)">{counts["M"]}</div></div>
<div class="stat-card"><div class="stat-label">Archivos Eliminados</div><div class="stat-value red">{counts["D"]}</div></div>
<div class="stat-card"><div class="stat-label">DoD</div><div class="stat-value {dod_color}">{dod_value}</div></div>
</div></div>
{previews}
{section("🆕", "Archivos Nuevos", groups["A"], "No hay archivos nuevos.", counts["A"])}
{section("✏️", "Archivos Modificados", groups["M"], "No hay archivos modificados.", counts["M"])}
{section("🗑️", "Archivos Eliminados", groups["D"], "Ningún archivo fue eliminado.", counts["D"])}
{dod_section(dod)}
<div class="footer"><div><span class="footer-brand">{e(project)}</span> &nbsp;·&nbsp; Generado el {date}</div>
<div>Generado con <strong>hb-implement</strong> · No hacer commit sin revisión manual</div></div>
</div>
{script}
</body></html>
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{date}-{slug(meta.get('title', 'reporte'))}.html"
    out.write_text(page, encoding="utf-8")
    print(f"📄 Reporte generado: {out.relative_to(repo)}")
    warning = ensure_ignored(repo, out_dir, out)
    if warning:
        print(warning, file=sys.stderr)
    for path in missing_previews:
        print(f"⚠️  Preview sin imagen: {path}", file=sys.stderr)
    missing = [f["path"] for f in files if f["path"] not in infos and f["group"] is None]
    if missing:
        print("ℹ️  Archivos sin explicación en meta.json: " + ", ".join(missing), file=sys.stderr)
        if len(missing) > 5:
            print('ℹ️  Si son archivos generados o masivos (goldens, fixtures), explícalos en grupo con "groups".',
                  file=sys.stderr)
    for group in group_defs:
        if not any(f["group"] is group for f in files):
            print(f'ℹ️  El grupo "{group.get("match", "")}" no cubre ningún archivo cambiado.', file=sys.stderr)
    meta_path = pathlib.Path(args.meta).resolve()
    if meta_path.name == "meta.json" and meta_path.parent == out_dir.resolve():
        print("ℹ️  reports/meta.json lo pisa la siguiente tarea: usa un meta por tarea, "
              "reports/<fecha>-<slug>.meta.json.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError) as err:
        print(f"✖ {err}", file=sys.stderr)
        sys.exit(1)
