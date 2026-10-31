#!/usr/bin/env node
// coach.mjs — herramienta del Software Coach (Node 18+, sin dependencias).
//
// Port 1:1 de coach.py: mismos comandos, mismos archivos y misma salida.
// Gestiona el espacio de aprendizaje de un proyecto (por defecto ./aprendizaje):
// plan de estudio, notas de lecciones, glosario, dudas y el cuaderno HTML.
//
// Ejemplos:
//   node coach.mjs init hilt --tema "Hilt: inyección de dependencias en Android" --area android
//   node coach.mjs leccion hilt 1.1
//   node coach.mjs completar hilt 1.1
//   node coach.mjs estado
//   node coach.mjs build

import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const VERSION = "2.0.1";
const SKILL_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS = path.join(SKILL_DIR, "assets");
const TEMPLATES = path.join(ASSETS, "plantillas");
const VIEWER = path.join(ASSETS, "cuaderno.html");
const DATA_PLACEHOLDER = '"__COACH_DATA__"';
const BOOL_FLAGS = new Set(["json", "no-build", "convalidada", "force", "versionar", "gitignore", "help"]);
const NOTE_STATES = ["en-curso", "completada", "convalidada"];

const AYUDA = `Software Coach — herramienta del espacio de aprendizaje (v${VERSION})

Uso: coach <comando> [argumentos] [--root DIR]

Comandos:
  init <slug> --tema "Título" [--area A] [--nivel-objetivo N] [--versionar | --gitignore]
        Crea aprendizaje/<slug>/ con PLAN.md, GLOSARIO.md, DUDAS.md y lecciones/, más
        README.md y METODO.md en la raíz. Excluye aprendizaje/ de git con
        .git/info/exclude (salvo --versionar).
  leccion <slug> <id>          Crea (si falta) la nota de la lección y la marca como actual.
  completar <slug> <id> [--convalidada]
                               Marca la lección como hecha en PLAN.md y en su nota.
  reabrir <slug> <id>          Vuelve a dejar la lección pendiente y actual.
  estado [slug] [--json]       Progreso, huecos abiertos y sesión previa (detalle con un tema).
  build                        Regenera aprendizaje/cuaderno.html.
  check [slug]                 Valida formato, enlaces, anclas, diagramas y legibilidad.
  vendor [--force]             Descarga las librerías del cuaderno a aprendizaje/.vendor (modo offline).
  version                      Muestra la versión.

Opciones:
  --root DIR    Carpeta de aprendizaje (por defecto ./aprendizaje o $COACH_ROOT).
  --no-build    No regenerar el cuaderno después de un cambio.
`;

// ---------------------------------------------------------------------------- utilidades

class CoachError extends Error {}

function out(msg = "") {
  process.stdout.write(msg + "\n");
}

function readText(p) {
  let s = fs.readFileSync(p, "utf8");
  if (s.startsWith("\ufeff")) s = s.slice(1);
  return s.replace(/\r\n/g, "\n");
}

function writeText(p, s) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, s, "utf8");
}

function rel(p) {
  const r = path.relative(process.cwd(), path.resolve(p));
  return r === "" ? "." : r;
}

function isFile(p) {
  try { return fs.statSync(p).isFile(); } catch { return false; }
}

function isDir(p) {
  try { return fs.statSync(p).isDirectory(); } catch { return false; }
}

function now() {
  const sde = process.env.SOURCE_DATE_EPOCH;
  if (sde && /^[0-9]+$/.test(sde.trim())) return { date: new Date(Number(sde.trim()) * 1000), utc: true };
  return { date: new Date(), utc: false };
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function localParts() {
  const { date, utc } = now();
  const offMin = utc ? 0 : -date.getTimezoneOffset();
  const shifted = new Date(date.getTime() + offMin * 60000);
  return { iso: shifted.toISOString().slice(0, 19), offMin };
}

function today() {
  return localParts().iso.slice(0, 10);
}

function isoNow() {
  const { iso, offMin } = localParts();
  const sign = offMin >= 0 ? "+" : "-";
  const abs = Math.abs(offMin);
  return `${iso}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function slugify(s, limit = 48) {
  let r = s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  r = r.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (limit && r.length > limit) {
    let cut = r.slice(0, limit);
    if (r[limit] !== "-" && cut.includes("-")) cut = cut.slice(0, cut.lastIndexOf("-"));
    r = cut.replace(/-+$/, "");
  }
  return r;
}

function idKey(i) {
  return i.split(".").filter((x) => /^[0-9]+$/.test(x)).map((x) => parseInt(x, 10));
}

function cmpIds(a, b) {
  const x = idKey(a);
  const y = idKey(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
}

function fmtKb(n) {
  return `${Math.floor((n + 512) / 1024)} KB`;
}

function bar(done, total, width = 20) {
  const filled = total ? Math.floor((done * width) / total) : 0;
  return "[" + "\u25a0".repeat(filled) + "\u25a1".repeat(width - filled) + "]";
}

function stripLinks(s) {
  return s.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
}

function listDir(p) {
  return fs.readdirSync(p).sort();
}

// ---------------------------------------------------------------------------- frontmatter

const FM_KEY_RE = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/;

function splitFrontmatter(text) {
  const lines = text.split("\n");
  if (!lines.length || lines[0].trim() !== "---") return [null, text];
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---" || lines[i].trim() === "...") {
      return [lines.slice(1, i), lines.slice(i + 1).join("\n")];
    }
  }
  return [null, text];
}

function splitList(inner) {
  const items = [];
  let cur = "";
  let q = null;
  for (const ch of inner) {
    if (q) {
      if (ch === q) q = null;
      else cur += ch;
    } else if (ch === '"' || ch === "'") {
      q = ch;
    } else if (ch === ",") {
      items.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  items.push(cur.trim());
  return items.filter((x) => x !== "");
}

function parseValue(raw) {
  let v = raw.trim();
  if (v.slice(0, 1) === '"' || v.slice(0, 1) === "'") {
    const q = v[0];
    const end = v.lastIndexOf(q);
    if (end > 0) {
      let inner = v.slice(1, end);
      if (q === '"') inner = inner.split('\\"').join('"').split("\\\\").join("\\");
      return inner;
    }
  }
  v = v.replace(/\s+#.*$/, "");
  if (v.startsWith("[") && v.endsWith("]")) return splitList(v.slice(1, -1));
  return v;
}

function parseFrontmatter(text) {
  const [lines, body] = splitFrontmatter(text);
  if (lines === null) return [null, body];
  const fm = {};
  for (const line of lines) {
    const m = FM_KEY_RE.exec(line);
    if (m) fm[m[1]] = parseValue(m[2]);
  }
  return [fm, body];
}

function fmStr(fm, key) {
  const v = fm && Object.prototype.hasOwnProperty.call(fm, key) ? fm[key] : "";
  if (Array.isArray(v)) return v.join(", ");
  return String(v).trim();
}

const YAML_WORDS = new Set(["yes", "no", "on", "off", "true", "false", "null", "~"]);

function yamlQuote(value) {
  return '"' + String(value).split("\\").join("\\\\").split('"').join('\\"') + '"';
}

function fmtValue(value) {
  const s = String(value);
  if (
    s === "" ||
    /^[0-9.]+$/.test(s) ||
    /[:#\[\]{}",]|^\s|\s$/.test(s) ||
    /^[!&*|>'%@`?\-]/.test(s) ||
    YAML_WORDS.has(s.toLowerCase())
  ) {
    return yamlQuote(s);
  }
  return s;
}

function setFm(text, key, value) {
  const lines = text.split("\n");
  let end = null;
  if (lines.length && lines[0].trim() === "---") {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === "---" || lines[i].trim() === "...") { end = i; break; }
    }
  }
  const newLine = `${key}: ${fmtValue(value)}`;
  if (end === null) return "---\n" + newLine + "\n---\n" + text;
  for (let i = 1; i < end; i++) {
    const m = FM_KEY_RE.exec(lines[i]);
    if (m && m[1] === key) {
      lines[i] = newLine;
      return lines.join("\n");
    }
  }
  lines.splice(end, 0, newLine);
  return lines.join("\n");
}

// ---------------------------------------------------------------------------- plan

const LESSON_RE = /^\s*[-*+]\s+\[([ xX])\]\s+\*\*([0-9]+(?:\.[0-9]+)+)\.?\s+(.+?)\*\*(.*)$/;
const HEADING_RE = /^(#{1,6})\s+(.+?)\s*#*\s*$/;
const FENCE_RE = /^\s*(```|~~~)/;
const CONV_RE = /\(convalidada\)|\u23ed\ufe0f?/i;
const CONV_RE_G = /\(convalidada\)|\u23ed\ufe0f?/gi;
const MOD_ID_RE = /(?:m[oó]dulo|module|unidad|unit)\s+([0-9]+)/i;
const MOD_NUM_RE = /^([0-9]+)\s*[.):·\-—–]/;
const MOD_PREFIX_RE = /^(?:(?:m[oó]dulo|module|unidad|unit)\s+[0-9]+|[0-9]+)\s*[.):·\-—–]*\s*/i;
const LEVEL_TAIL_RE = /[\s·|\-—–]*(?:\u{1F7E2}|\u{1F7E1}|\u{1F7E0}|\u{1F534})?\s*(?:b[aá]sico|intermedio|avanzado|experto|basic|beginner|intermediate|advanced|expert)?\s*$/iu;
const LEVEL_EMOJI = [["basico", "\u{1F7E2}"], ["intermedio", "\u{1F7E1}"], ["avanzado", "\u{1F7E0}"], ["experto", "\u{1F534}"]];
const LEVEL_WORDS = [
  ["basico", /\bb[aá]sico\b|\bbasic\b|\bbeginner\b/i],
  ["intermedio", /\bintermedio\b|\bintermediate\b/i],
  ["avanzado", /\bavanzado\b|\badvanced\b/i],
  ["experto", /\bexperto\b|\bexpert\b/i],
];
const DESC_LEAD_RE = /^[\s—–\-:·|]+/;
const TITLE_LEAD_RE = /^[·:\-—–]\s*/;

function detectLevel(text) {
  for (const [key, emo] of LEVEL_EMOJI) if (text.includes(emo)) return key;
  for (const [key, rx] of LEVEL_WORDS) if (rx.test(text)) return key;
  return "";
}

function cleanModuleTitle(text) {
  let t = text.trim().replace(MOD_PREFIX_RE, "");
  t = t.replace(LEVEL_TAIL_RE, "").trim();
  return t || text.trim();
}

const HUECOS_RE = /huecos/i;
const BITACORA_RE = /bit[a\u00e1]cora/i;
const CLOSED_RE = /^(cerrad|resuelt)/i;

function headingTableTarget(text) {
  if (BITACORA_RE.test(text)) return "bitacora";
  if (HUECOS_RE.test(text)) return "huecos";
  return null;
}

function parsePlan(text) {
  const [fm] = parseFrontmatter(text);
  const lines = text.split("\n");
  let start = 0;
  if (lines.length && lines[0].trim() === "---") {
    for (let i = 1; i < lines.length; i++) {
      if (lines[i].trim() === "---" || lines[i].trim() === "...") { start = i + 1; break; }
    }
  }
  const modules = [];
  const lessons = [];
  const tables = { bitacora: [], huecos: [] };
  let heading = null;
  let headingUsed = false;
  let inFence = false;
  let tableTarget = null;
  for (let n = start; n < lines.length; n++) {
    const line = lines[n];
    if (FENCE_RE.test(line)) { inFence = !inFence; continue; }
    if (inFence) continue;
    const h = HEADING_RE.exec(line);
    if (h) {
      if (h[1].length >= 2) { heading = h[2]; headingUsed = false; }
      tableTarget = headingTableTarget(h[2]);
      continue;
    }
    if (tableTarget && line.trim().startsWith("|")) {
      const cells = line.trim().replace(/^\|+|\|+$/g, "").split("|").map((c) => c.trim());
      const nonEmpty = cells.filter((c) => c);
      if (nonEmpty.every((c) => /^:?-{2,}:?$/.test(c)) && cells.some((c) => c)) continue;
      tables[tableTarget].push(cells);
      continue;
    }
    const m = LESSON_RE.exec(line);
    if (!m) continue;
    if (!headingUsed) {
      const htext = heading !== null ? heading : "Plan";
      const mid = MOD_ID_RE.exec(htext);
      let moduleId;
      if (mid) moduleId = mid[1];
      else {
        const mn = MOD_NUM_RE.exec(htext.trim());
        moduleId = mn ? mn[1] : String(modules.length + 1);
      }
      modules.push({
        id: moduleId,
        titulo: cleanModuleTitle(htext),
        encabezado: htext,
        nivel: detectLevel(htext),
        lecciones: [],
      });
      headingUsed = true;
    }
    const rest = m[4];
    const conv = CONV_RE.test(rest);
    const desc = rest.replace(CONV_RE_G, "").replace(DESC_LEAD_RE, "").trim();
    const lesson = {
      id: m[2],
      titulo: m[3].trim().replace(TITLE_LEAD_RE, ""),
      descripcion: desc,
      hecha: m[1] === "x" || m[1] === "X",
      convalidada: conv,
      modulo: modules.length - 1,
      linea: n,
    };
    modules[modules.length - 1].lecciones.push(lesson.id);
    lessons.push(lesson);
  }
  return {
    fm,
    modulos: modules,
    lecciones: lessons,
    bitacora: tables.bitacora.length ? tables.bitacora.slice(1) : [],
    huecos: tables.huecos.length ? tables.huecos.slice(1) : [],
  };
}

function normState(s) {
  return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase().replace(/[\s_]+/g, "-");
}

// ---------------------------------------------------------------------------- espacio

function rootDir(opts) {
  return opts.root || process.env.COACH_ROOT || "aprendizaje";
}

const NOTE_ID_RE = /^([0-9]+(?:\.[0-9]+)+)(?=[-_ .])/;

function loadNotes(topicDir) {
  const notes = {};
  const d = path.join(topicDir, "lecciones");
  if (!isDir(d)) return notes;
  for (const name of listDir(d)) {
    const p = path.join(d, name);
    if (!isFile(p) || !name.endsWith(".md")) continue;
    const text = readText(p);
    const [fm] = parseFrontmatter(text);
    const m = NOTE_ID_RE.exec(name);
    const nid = m ? m[1] : fmStr(fm, "leccion");
    if (!nid) continue;
    if (!(nid in notes)) notes[nid] = { path: p, fm: fm || {}, text };
  }
  return notes;
}

function loadTopic(root, slug) {
  const tdir = path.join(root, slug);
  const planPath = path.join(tdir, "PLAN.md");
  if (!isFile(planPath)) {
    throw new CoachError(`No existe ${rel(planPath)}. Crea el tema con: coach init ${slug} --tema "..."`);
  }
  const text = readText(planPath);
  const plan = parsePlan(text);
  const notes = loadNotes(tdir);
  const fm = plan.fm || {};
  const actualId = fmStr(fm, "leccion_actual");
  for (const l of plan.lecciones) {
    const note = notes[l.id];
    const noteState = note ? normState(fmStr(note.fm, "estado")) : "";
    if (l.hecha) l.estado = l.convalidada ? "convalidada" : "completada";
    else if (l.id === actualId || noteState === "en-curso") l.estado = "en-curso";
    else l.estado = "pendiente";
    l.nota = note ? rel(note.path) : "";
  }
  return { slug, dir: tdir, planPath, text, plan, notes };
}

function listTopics(root) {
  if (!isDir(root)) return [];
  return listDir(root).filter((name) => {
    const p = path.join(root, name);
    return isDir(p) && !name.startsWith(".") && isFile(path.join(p, "PLAN.md"));
  });
}

function currentLesson(topic) {
  const fm = topic.plan.fm || {};
  const actualId = fmStr(fm, "leccion_actual");
  const lessons = topic.plan.lecciones;
  return (
    lessons.find((l) => !l.hecha && l.id === actualId) ||
    lessons.find((l) => l.estado === "en-curso") ||
    lessons.find((l) => !l.hecha) ||
    null
  );
}

function findLesson(topic, lid) {
  const l = topic.plan.lecciones.find((x) => x.id === lid);
  if (l) return l;
  throw new CoachError(
    `La lección ${lid} no existe en ${rel(topic.planPath)}. Añádela primero al plan con el formato ` +
      `\`- [ ] **${lid} Título** — descripción\`.`
  );
}

function moduleLabel(topic, lesson) {
  const mod = topic.plan.modulos[lesson.modulo];
  return `M${mod.id} · ${mod.titulo}`;
}

function openGaps(plan) {
  const gaps = [];
  for (const cells of plan.huecos || []) {
    if (!cells.some((c) => c)) continue;
    const name = cells.length ? cells[0] : "";
    if (!name || name.startsWith("[[")) continue;
    const estado = cells.length > 4 ? cells[4].trim() : "";
    if (CLOSED_RE.test(estado)) continue;
    gaps.push({
      hueco: name,
      detectado: cells.length > 1 ? cells[1] : "",
      intentos: cells.length > 2 ? cells[2] : "",
      proximo_repaso: cells.length > 3 ? cells[3] : "",
    });
  }
  return gaps;
}

function summarize(topic) {
  const plan = topic.plan;
  const fm = plan.fm || {};
  const lessons = plan.lecciones;
  const done = lessons.filter((l) => l.hecha).length;
  const total = lessons.length;
  const cur = currentLesson(topic);
  const upcoming = [];
  if (cur !== null) {
    const idx = lessons.indexOf(cur);
    for (const l of lessons.slice(idx + 1)) {
      if (!l.hecha) upcoming.push({ id: l.id, titulo: l.titulo });
      if (upcoming.length === 3) break;
    }
  }
  const mods = plan.modulos.map((mod, mi) => {
    const ls = lessons.filter((l) => l.modulo === mi);
    return {
      id: mod.id,
      titulo: mod.titulo,
      nivel: mod.nivel,
      hechas: ls.filter((l) => l.hecha).length,
      total: ls.length,
    };
  });
  return {
    slug: topic.slug,
    tema: fmStr(fm, "tema") || topic.slug,
    area: fmStr(fm, "area"),
    nivel_actual: fmStr(fm, "nivel_actual"),
    nivel_objetivo: fmStr(fm, "nivel_objetivo"),
    actualizado: fmStr(fm, "actualizado"),
    hechas: done,
    total,
    porcentaje: total ? Math.floor((done * 100) / total) : 0,
    actual: cur ? { id: cur.id, titulo: cur.titulo, estado: cur.estado } : null,
    proximas: upcoming,
    modulos: mods,
    lecciones: lessons.map((l) => ({
      id: l.id,
      titulo: l.titulo,
      estado: l.estado,
      modulo: plan.modulos[l.modulo].id,
      nota: l.nota,
    })),
    ultima_sesion: plan.bitacora.length ? plan.bitacora[plan.bitacora.length - 1] : null,
    huecos_abiertos: openGaps(plan),
    notas: Object.keys(topic.notes).length,
  };
}

function sortedSummaries(root, only = null) {
  const sums = listTopics(root)
    .filter((slug) => !only || slug === only)
    .map((slug) => summarize(loadTopic(root, slug)));
  sums.sort((a, b) => (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0));
  sums.sort((a, b) => (a.actualizado < b.actualizado ? 1 : a.actualizado > b.actualizado ? -1 : 0));
  return sums;
}

// ---------------------------------------------------------------------------- git

function git(args) {
  const r = spawnSync("git", args, { encoding: "utf8" });
  if (r.error) return null;
  if (r.status !== 0) return "";
  return (r.stdout || "").trim();
}

function gitPaths() {
  const top = git(["rev-parse", "--show-toplevel"]);
  if (top === null) {
    let d = path.resolve(process.cwd());
    for (;;) {
      if (isDir(path.join(d, ".git"))) return [d, path.join(d, ".git", "info", "exclude")];
      const parent = path.dirname(d);
      if (parent === d) break;
      d = parent;
    }
    return [null, null];
  }
  if (!top) return [null, null];
  const gp = git(["rev-parse", "--git-path", "info/exclude"]);
  if (!gp) return [null, null];
  const p = path.isAbsolute(gp) ? gp : path.join(process.cwd(), gp);
  return [top, p];
}

function realpath(p) {
  try { return fs.realpathSync(p); } catch { return path.resolve(p); }
}

function excludeFromGit(root, opts) {
  if (opts.versionar) {
    out(`\u2139 La carpeta ${rel(root)} se versionará con git (--versionar).`);
    return;
  }
  const [top, exclude] = gitPaths();
  if (top === null) {
    out(`\u2139 No es un repositorio git: no hace falta excluir ${rel(root)}.`);
    return;
  }
  const rp = path.relative(realpath(top), realpath(root));
  if (rp.startsWith("..") || path.isAbsolute(rp)) return;
  const entry = "/" + rp.split(path.sep).join("/").replace(/^\/+|\/+$/g, "") + "/";
  const target = opts.gitignore ? path.join(top, ".gitignore") : exclude;
  let existing = isFile(target) ? readText(target) : "";
  const variants = new Set([entry, entry.replace(/\/+$/, ""), entry.replace(/^\/+/, ""), entry.replace(/^\/+|\/+$/g, "")]);
  if (existing.split("\n").some((l) => variants.has(l.trim()))) {
    out(`\u{1F648} Git: '${entry}' ya estaba excluido en ${rel(target)}.`);
    return;
  }
  if (existing && !existing.endsWith("\n")) existing += "\n";
  existing += "# hb-coach: espacio de aprendizaje local\n" + entry + "\n";
  writeText(target, existing);
  if (opts.gitignore) out(`\u{1F648} Git: añadido '${entry}' a ${rel(target)}.`);
  else out(`\u{1F648} Git: añadido '${entry}' a ${rel(target)} (no se versiona y no modifica .gitignore).`);
}

// ---------------------------------------------------------------------------- plantillas

function renderTemplate(name, values) {
  const p = path.join(TEMPLATES, name);
  if (!isFile(p)) throw new CoachError(`Falta la plantilla ${p}`);
  let s = readText(p);
  for (const [k, v] of Object.entries(values)) s = s.split(`{{${k}}}`).join(v);
  return s;
}

// ---------------------------------------------------------------------------- build

function collectFiles(root) {
  const files = [];
  const walk = (dir, prefix) => {
    const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    for (const e of entries) {
      if (e.name.startsWith(".")) continue;
      const full = path.join(dir, e.name);
      const relp = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) walk(full, relp);
      else if ((e.isFile() || (e.isSymbolicLink() && isFile(full))) && e.name.endsWith(".md")) files.push(relp);
    }
  };
  walk(root, "");
  files.sort();
  return files;
}

function jsonForHtml(obj) {
  return JSON.stringify(obj)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

function build(root, quiet = false) {
  if (!isFile(VIEWER)) throw new CoachError(`No se encuentra la plantilla del cuaderno: ${VIEWER}`);
  if (!isDir(root)) throw new CoachError(`No existe ${rel(root)}. Crea un tema con: coach init <slug> --tema "..."`);
  const files = collectFiles(root);
  const archivos = {};
  for (const f of files) archivos[f] = readText(path.join(root, f));
  const data = {
    version: 1,
    generado: isoNow(),
    raiz: path.basename(realpath(root)),
    archivos,
  };
  const template = readText(VIEWER);
  if (!template.includes(DATA_PLACEHOLDER)) throw new CoachError("La plantilla del cuaderno no contiene el marcador de datos.");
  const json = jsonForHtml(data);
  const html = template.replace(DATA_PLACEHOLDER, () => json);
  const target = path.join(root, "cuaderno.html");
  writeText(target, html);
  if (!quiet) {
    out(`\u{1F4D3} Cuaderno actualizado: ${rel(target)} (${files.length} archivos)`);
    out(`   Abrir: ${pathToFileURL(realpath(target)).href}`);
  }
  return target;
}

// ---------------------------------------------------------------------------- comandos

function cmdInit(pos, opts) {
  if (!pos.length) throw new CoachError('Uso: coach init <slug> --tema "Título del tema" [--area android]');
  const raw = pos[0];
  const slug = slugify(raw, 0);
  if (!slug) throw new CoachError(`Slug inválido: ${raw}`);
  if (slug !== raw) out(`\u2139 Slug normalizado: '${raw}' -> '${slug}'`);
  const tema = (opts.tema || raw).trim();
  const root = rootDir(opts);
  const createdRoot = !isDir(root);
  fs.mkdirSync(root, { recursive: true });
  if (createdRoot) out(`\u{1F4C1} Creada la carpeta ${rel(root)}`);
  const readme = path.join(root, "README.md");
  if (!isFile(readme)) writeText(readme, renderTemplate("README-aprendizaje.md", { FECHA: today() }));
  const metodo = path.join(root, "METODO.md");
  if (!isFile(metodo)) {
    writeText(metodo, renderTemplate("METODO.md", { FECHA: today() }));
    out(`\u{1F91D} Acuerdo de método: ${rel(metodo)} (complétalo en la primera sesión)`);
  }
  excludeFromGit(root, opts);
  const tdir = path.join(root, slug);
  const values = {
    TEMA_YAML: yamlQuote(tema),
    TEMA: tema,
    SLUG: slug,
    AREA_YAML: fmtValue((opts.area || "general").trim()),
    NIVEL_OBJETIVO_YAML: fmtValue((opts["nivel-objetivo"] || "avanzado").trim()),
    FECHA: today(),
  };
  const plan = path.join(tdir, "PLAN.md");
  if (isFile(plan) && !opts.force) {
    out(`\u2139 ${rel(plan)} ya existe: no se sobrescribe (usa --force para reemplazarlo).`);
  } else {
    writeText(plan, renderTemplate("PLAN.md", values));
    out(`\u{1F5FA} Plan creado: ${rel(plan)}`);
  }
  for (const name of ["GLOSARIO.md", "DUDAS.md"]) {
    const p = path.join(tdir, name);
    if (!isFile(p)) writeText(p, renderTemplate(name, values));
  }
  fs.mkdirSync(path.join(tdir, "lecciones"), { recursive: true });
  out(`\u2714 Tema '${slug}' listo en ${rel(tdir)}`);
  if (!opts["no-build"]) build(root);
}

function cmdLeccion(pos, opts) {
  if (pos.length < 2) throw new CoachError("Uso: coach leccion <slug> <id>");
  const root = rootDir(opts);
  const topic = loadTopic(root, pos[0]);
  const lesson = findLesson(topic, pos[1]);
  const note = topic.notes[lesson.id];
  let notePath;
  if (note) {
    notePath = note.path;
    out(`\u{1F4DD} Nota existente de la lección ${lesson.id}: ${rel(notePath)}`);
  } else {
    const name = `${lesson.id}-${slugify(lesson.titulo) || "leccion"}.md`;
    notePath = path.join(topic.dir, "lecciones", name);
    const fm = topic.plan.fm || {};
    writeText(
      notePath,
      renderTemplate("LECCION.md", {
        LECCION: lesson.id,
        TITULO_YAML: yamlQuote(lesson.titulo),
        TITULO: lesson.titulo,
        MODULO_YAML: yamlQuote(moduleLabel(topic, lesson)),
        DESCRIPCION: stripLinks(lesson.descripcion),
        TEMA: fmStr(fm, "tema") || topic.slug,
        SLUG: topic.slug,
        FECHA: today(),
      })
    );
    out(`\u{1F4DD} Nota creada para la lección ${lesson.id}: ${rel(notePath)}`);
  }
  if (lesson.hecha) {
    out(`\u2139 La lección ${lesson.id} ya estaba completada: se usa como repaso (el progreso no cambia).`);
  } else {
    let text = setFm(topic.text, "leccion_actual", lesson.id);
    text = setFm(text, "actualizado", today());
    writeText(topic.planPath, text);
    if (!note || normState(fmStr(note.fm, "estado")) !== "en-curso") {
      writeText(notePath, setFm(readText(notePath), "estado", "en-curso"));
    }
    out(`\u25b6 Lección actual: ${lesson.id} ${lesson.titulo}`);
  }
  if (!opts["no-build"]) build(root);
}

function setLine(text, lineNo, fn) {
  const lines = text.split("\n");
  lines[lineNo] = fn(lines[lineNo]);
  return lines.join("\n");
}

function cmdCompletar(pos, opts) {
  if (pos.length < 2) throw new CoachError("Uso: coach completar <slug> <id> [--convalidada]");
  const root = rootDir(opts);
  const topic = loadTopic(root, pos[0]);
  const lesson = findLesson(topic, pos[1]);
  const conv = Boolean(opts.convalidada);
  const lessons = topic.plan.lecciones;
  const modIndex = lesson.modulo;
  const modBefore = lessons.filter((l) => l.modulo === modIndex).every((l) => l.hecha);
  const wasDone = lesson.hecha;
  const mark = (line) => {
    let r = line.replace(/\[[ xX]\]/, "[x]");
    if (conv && !CONV_RE.test(r)) r = r.replace(/\s+$/, "") + " (convalidada)";
    return r;
  };
  let text = setLine(topic.text, lesson.linea, mark);
  text = setFm(text, "actualizado", today());
  lesson.hecha = true;
  const idx = lessons.indexOf(lesson);
  const order = lessons.slice(idx + 1).concat(lessons.slice(0, idx));
  const nxt = order.find((l) => !l.hecha) || null;
  const fm = topic.plan.fm || {};
  const curId = fmStr(fm, "leccion_actual");
  const curObj = lessons.find((l) => l.id === curId) || null;
  if (curId === lesson.id || !curId || curObj === null || curObj.hecha) {
    text = setFm(text, "leccion_actual", nxt ? nxt.id : "");
  }
  writeText(topic.planPath, text);
  const note = topic.notes[lesson.id];
  if (note) {
    let ntext = setFm(note.text, "estado", conv ? "convalidada" : "completada");
    ntext = setFm(ntext, "fin", today());
    writeText(note.path, ntext);
  }
  const done = lessons.filter((l) => l.hecha).length;
  const total = lessons.length;
  const pct = total ? Math.floor((done * 100) / total) : 0;
  if (wasDone) out(`\u2139 La lección ${lesson.id} ya estaba completada.`);
  const label = conv ? "convalidada" : "completada";
  out(`\u2714 Lección ${lesson.id} ${label} · ${topic.slug} ${done}/${total} (${pct}%)`);
  const modAfter = lessons.filter((l) => l.modulo === modIndex).every((l) => l.hecha);
  if (modAfter && !modBefore) {
    const mod = topic.plan.modulos[modIndex];
    out(`\u{1F389} Módulo ${mod.id} completado: ${mod.titulo}`);
  }
  if (nxt) out(`\u25b6 Siguiente: ${nxt.id} ${nxt.titulo}`);
  else out("\u{1F3C1} Plan completado. Hora del proyecto final y de un repaso general.");
  if (!opts["no-build"]) build(root);
}

function cmdReabrir(pos, opts) {
  if (pos.length < 2) throw new CoachError("Uso: coach reabrir <slug> <id>");
  const root = rootDir(opts);
  const topic = loadTopic(root, pos[0]);
  const lesson = findLesson(topic, pos[1]);
  const unmark = (line) => line.replace(/\[[ xX]\]/, "[ ]").replace(/\s*\(convalidada\)|\s*\u23ed\ufe0f?/gi, "");
  let text = setLine(topic.text, lesson.linea, unmark);
  text = setFm(text, "leccion_actual", lesson.id);
  text = setFm(text, "actualizado", today());
  writeText(topic.planPath, text);
  const note = topic.notes[lesson.id];
  if (note) writeText(note.path, setFm(note.text, "estado", "en-curso"));
  out(`\u21ba Lección ${lesson.id} reabierta y marcada como actual.`);
  if (!opts["no-build"]) build(root);
}

const STATE_ICON = { completada: "\u2714", convalidada: "\u23ed", "en-curso": "\u25b6", pendiente: "·" };
const LEVEL_LABEL = { basico: "B\u00e1sico", intermedio: "Intermedio", avanzado: "Avanzado", experto: "Experto" };

function cmdEstado(pos, opts) {
  const root = rootDir(opts);
  const only = pos.length ? pos[0] : null;
  if (only && !isFile(path.join(root, only, "PLAN.md"))) {
    throw new CoachError(`No existe el tema '${only}' en ${rel(root)}.`);
  }
  const sums = sortedSummaries(root, only);
  if (opts.json) {
    out(JSON.stringify({ raiz: rel(root), temas: sums }, null, 2));
    return;
  }
  if (!isDir(root) || !sums.length) {
    out(`\u{1F4DA} Aún no hay temas en ${rel(root)}.`);
    out('   Crea uno con: coach init <slug> --tema "Título del tema"');
    return;
  }
  const n = sums.length;
  out(`\u{1F4DA} Aprendizaje · ${n} tema${n === 1 ? "" : "s"} · raíz: ${rel(root)}`);
  for (const s of sums) {
    out("");
    out(`\u25a0 ${s.slug} — ${s.tema}`);
    out(`  Progreso  ${bar(s.hechas, s.total)} ${s.hechas}/${s.total} · ${s.porcentaje}%`);
    const niv = `${s.nivel_actual || "?"} \u2192 ${s.nivel_objetivo || "?"}`;
    out(`  Nivel     ${niv} · área: ${s.area || "-"} · actualizado: ${s.actualizado || "-"}`);
    if (s.actual) out(`  Actual    ${s.actual.id} ${s.actual.titulo} (${s.actual.estado})`);
    else out("  Actual    — (todas las lecciones están hechas)");
    if (s.proximas.length) out("  Próximas  " + s.proximas.map((p) => `${p.id} ${p.titulo}`).join(" · "));
    out("  Módulos   " + s.modulos.map((m) => `M${m.id} ${m.hechas}/${m.total}`).join(" · "));
    if (s.huecos_abiertos.length) {
      const g = s.huecos_abiertos;
      const fechas = g.map((x) => x.proximo_repaso).filter((x) => x.trim()).sort();
      const extra = fechas.length ? ` \u00b7 próximo repaso: ${fechas[0]}` : "";
      out(`  Huecos    ${g.length} abierto${g.length === 1 ? "" : "s"}${extra} \u00b7 ${g[0].hueco}`);
    }
    if (s.ultima_sesion) out("  Sesión    " + s.ultima_sesion.filter((c) => c).join(" · "));
    out(`  Notas     ${s.notas} en ${rel(path.join(root, s.slug, "lecciones"))}`);
    if (only) {
      for (const m of s.modulos) {
        const nivel = m.nivel ? ` [${LEVEL_LABEL[m.nivel] || m.nivel}]` : "";
        out("");
        out(`  M${m.id} · ${m.titulo}${nivel} ${m.hechas}/${m.total}`);
        for (const l of s.lecciones) {
          if (l.modulo === m.id) {
            const extra = l.estado === "pendiente" || l.estado === "completada" ? "" : ` (${l.estado})`;
            out(`    ${STATE_ICON[l.estado]} ${l.id} ${l.titulo}${extra}`);
          }
        }
      }
    }
  }
  out("");
  out(`\u{1F4D3} Cuaderno: ${rel(path.join(root, "cuaderno.html"))}`);
}

const MERMAID_TYPES = new Set([
  "flowchart", "graph", "sequencediagram", "classdiagram", "classdiagram-v2", "statediagram",
  "statediagram-v2", "erdiagram", "journey", "gantt", "pie", "quadrantchart", "requirementdiagram",
  "gitgraph", "c4context", "c4container", "c4component", "c4dynamic", "c4deployment", "mindmap",
  "timeline", "zenuml", "sankey", "sankey-beta", "xychart", "xychart-beta", "block", "block-beta",
  "packet", "packet-beta", "kanban", "architecture", "architecture-beta", "radar", "radar-beta",
  "treemap", "treemap-beta",
]);
const LINK_RE = /\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const REQUIRED_NOTE_SECTIONS = [
  ["Resumen con tus palabras", /^#{2,3}\s+.*resumen con tus palabras/im],
  ["Fuentes", /^#{2,3}\s+.*fuentes/im],
];

function isClosingFence(line, mark) {
  const t = line.trim();
  return t.startsWith(mark) && t.split(mark[0]).join("") === "";
}

function proseOnly(text) {
  const t = text.replace(/<!--[\s\S]*?-->/g, "");
  const keep = [];
  let fence = null;
  for (const line of t.split("\n")) {
    const m = /^\s*(```+|~~~+)/.exec(line);
    if (fence === null) {
      if (m) { fence = m[1].slice(0, 3); continue; }
      keep.push(line.replace(/`[^`]*`/g, ""));
    } else if (isClosingFence(line, fence)) {
      fence = null;
    }
  }
  return keep.join("\n");
}

function slugText(value) {
  return slugify(value, 0);
}

function lintMarkdown(relp, text, root, report) {
  const body = text.replace(/<!--[\s\S]*?-->/g, "");
  let fence = null;
  let block = [];
  let longCode = 0;
  let longest = 0;
  let tableCode = 0;
  const headings = new Set();
  for (const line of body.split("\n")) {
    const m = /^\s*(```+|~~~+)\s*([\w-]*)/.exec(line);
    if (fence === null) {
      if (m) { fence = { mark: m[1].slice(0, 3), lang: m[2].toLowerCase() }; block = []; continue; }
      const hm = HEADING_RE.exec(line);
      if (hm) { headings.add(slugText(hm[2])); continue; }
      if (line.trim().startsWith("|")) {
        for (const cell of line.trim().replace(/^\|+|\|+$/g, "").split("|")) {
          for (const code of cell.match(/`[^`]+`/g) || []) {
            if (code.length - 2 > 40) tableCode += 1;
          }
        }
      }
      continue;
    }
    if (isClosingFence(line, fence.mark)) {
      if (fence.lang === "mermaid") lintMermaid(relp, block, report);
      else {
        for (const codeLine of block) {
          if (codeLine.length > 80) { longCode += 1; longest = Math.max(longest, codeLine.length); }
        }
      }
      fence = null;
      continue;
    }
    block.push(line);
  }
  if (fence !== null) report("error", relp, "bloque de código sin cerrar (falta ``` final)");
  if (longCode) {
    report("aviso", relp, `${longCode} línea(s) de código de más de 80 caracteres (la más larga: ${longest}): se desbordan en el cuaderno`);
  }
  if (tableCode) report("aviso", relp, `${tableCode} celda(s) de tabla con código largo: muévelo a un bloque de código`);
  const prose = proseOnly(text);
  const pending = (prose.match(/\[\[COMPLETAR/g) || []).length;
  if (pending) report("aviso", relp, `quedan ${pending} marcador(es) [[COMPLETAR]] sin rellenar`);
  const base = path.dirname(path.join(root, relp));
  for (const mm of prose.matchAll(LINK_RE)) {
    const href = mm[1];
    if (href.startsWith("#")) {
      const anchor = slugText(href.slice(1));
      if (anchor && !headings.has(anchor) && !(anchor.startsWith("s-") && headings.has(anchor.slice(2)))) {
        report("aviso", relp, `enlace interno «${href}» sin encabezado que coincida`);
      }
      continue;
    }
    if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith("/")) continue;
    let target = href.split("#")[0];
    if (!target.endsWith(".md")) continue;
    target = target.split("%20").join(" ");
    if (!isFile(path.join(base, target))) report("aviso", relp, `enlace roto a ${href}`);
  }
}

function lintMermaid(relp, block, report) {
  const lines = block.slice();
  let i = 0;
  if (lines.length && lines[0].trim() === "---") {
    i = 1;
    while (i < lines.length && lines[i].trim() !== "---") i++;
    i++;
  }
  let first = "";
  for (const l of lines.slice(i)) {
    const s = l.trim();
    if (s && !s.startsWith("%%")) { first = s; break; }
  }
  if (!first) {
    report("error", relp, "diagrama mermaid vacío");
    return;
  }
  const word = first.split(/\s+/)[0];
  if (!MERMAID_TYPES.has(word.toLowerCase())) report("aviso", relp, `tipo de diagrama mermaid desconocido: '${word}'`);
  const longLabels = [];
  for (const mm of lines.join("\n").matchAll(/\[([^\[\]]+)\]|\(([^()]+)\)|\{([^{}]+)\}/g)) {
    let label = (mm[1] !== undefined ? mm[1] : mm[2] !== undefined ? mm[2] : mm[3]).trim();
    label = label.replace(/^["']|["']$/g, "").trim();
    if (label.length > 24) longLabels.push(label);
  }
  if (longLabels.length) {
    const longestLabel = longLabels.reduce((a, b) => (b.length > a.length ? b : a));
    report("aviso", relp, `${longLabels.length} etiqueta(s) de Mermaid de más de 24 caracteres («${longestLabel.slice(0, 40)}»): acorta o usa <br/>`);
  }
}

function cmdCheck(pos, opts) {
  const root = rootDir(opts);
  const only = pos.length ? pos[0] : null;
  const counts = { error: 0, aviso: 0 };
  const report = (kind, where, msg) => {
    counts[kind] += 1;
    const icon = kind === "error" ? "\u2716" : "\u26a0";
    out(`  ${icon} ${where}: ${msg}`);
  };
  out(`\u{1F50E} Revisando ${rel(root)}`);
  if (!isDir(root)) {
    report("error", rel(root), "no existe; crea un tema con coach init");
    out(`\u2716 ${counts.error} error(es)`);
    return 1;
  }
  const slugs = listTopics(root);
  if (only && !slugs.includes(only)) report("error", only, `no existe ${rel(path.join(root, only, "PLAN.md"))}`);
  for (const name of listDir(root)) {
    const p = path.join(root, name);
    if (isDir(p) && !name.startsWith(".") && !slugs.includes(name) && (!only || name === only)) {
      if (fs.readdirSync(p).some((f) => f.endsWith(".md"))) report("aviso", name + "/", "carpeta con notas pero sin PLAN.md");
    }
  }
  let newest = 0;
  for (const slug of slugs) {
    if (only && slug !== only) continue;
    const topic = loadTopic(root, slug);
    const plan = topic.plan;
    const where = slug + "/PLAN.md";
    let fm = plan.fm;
    if (fm === null) {
      report("error", where, "falta el frontmatter (bloque --- al inicio)");
      fm = {};
    } else {
      if (!fmStr(fm, "tema")) report("error", where, "falta el campo 'tema' en el frontmatter");
      if (fmStr(fm, "slug") && fmStr(fm, "slug") !== slug) {
        report("aviso", where, `el slug '${fmStr(fm, "slug")}' no coincide con la carpeta '${slug}'`);
      }
    }
    const lessons = plan.lecciones;
    if (!lessons.length) report("error", where, "no hay lecciones con el formato `- [ ] **1.1 Título** — descripción`");
    const seen = new Set();
    for (const l of lessons) {
      if (seen.has(l.id)) report("error", where, `id de lección duplicado: ${l.id}`);
      seen.add(l.id);
    }
    for (let k = 0; k + 1 < lessons.length; k++) {
      const a = lessons[k];
      const b = lessons[k + 1];
      if (cmpIds(b.id, a.id) <= 0) report("aviso", where, `orden de ids inesperado: ${b.id} después de ${a.id}`);
    }
    const cur = fmStr(fm, "leccion_actual");
    if (cur && !seen.has(cur)) report("aviso", where, `leccion_actual '${cur}' no existe en el plan`);
    if (plan.modulos.length && !plan.modulos.some((m) => m.nivel)) {
      report("aviso", where, "ningún módulo indica nivel (Básico/Intermedio/Avanzado/Experto)");
    }
    if (!/^#{2,3}\s+.*huecos/im.test(topic.text)) {
      report("aviso", where, "falta la sección «Huecos abiertos» (aunque esté vacía)");
    }
    for (const name of ["GLOSARIO.md", "DUDAS.md"]) {
      if (!isFile(path.join(topic.dir, name))) report("aviso", slug + "/" + name, "no existe");
    }
    const ldir = path.join(topic.dir, "lecciones");
    if (isDir(ldir)) {
      for (const fname of listDir(ldir)) {
        if (!fname.endsWith(".md")) continue;
        const w = `${slug}/lecciones/${fname}`;
        const m = NOTE_ID_RE.exec(fname);
        if (!m) {
          report("aviso", w, "el nombre debe empezar con el id de la lección (p. ej. 1.2-titulo.md)");
          continue;
        }
        if (!seen.has(m[1])) report("aviso", w, `la lección ${m[1]} no existe en el plan`);
        const [nfm, nbody] = parseFrontmatter(readText(path.join(ldir, fname)));
        if (nfm === null) report("aviso", w, "falta el frontmatter");
        else if (!NOTE_STATES.includes(normState(fmStr(nfm, "estado")))) {
          report("aviso", w, `estado '${fmStr(nfm, "estado")}' no válido (usa en-curso, completada o convalidada)`);
        }
        if (nfm !== null && normState(fmStr(nfm, "estado")) === "completada") {
          const missing = REQUIRED_NOTE_SECTIONS.filter(([, rx]) => !rx.test(nbody)).map(([t]) => t);
          if (missing.length) report("aviso", w, `la nota está completada pero le faltan secciones: ${missing.join(", ")}`);
        }
      }
    }
  }
  for (const relp of collectFiles(root)) {
    if (only && !relp.startsWith(only + "/")) continue;
    const full = path.join(root, relp);
    newest = Math.max(newest, fs.statSync(full).mtimeMs / 1000);
    lintMarkdown(relp, readText(full), root, report);
  }
  const nb = path.join(root, "cuaderno.html");
  if (!isFile(nb)) report("aviso", "cuaderno.html", "no existe; ejecuta coach build");
  else if (fs.statSync(nb).mtimeMs / 1000 + 1 < newest) report("aviso", "cuaderno.html", "desactualizado; ejecuta coach build");
  if (counts.error) {
    out(`\u2716 ${counts.error} error(es), ${counts.aviso} aviso(s)`);
    return 1;
  }
  out(`\u2714 Sin errores (${counts.aviso} aviso${counts.aviso === 1 ? "" : "s"})`);
  return 0;
}

function readLibs() {
  const template = readText(VIEWER);
  const m = /<script id="coach-libs" type="application\/json">([\s\S]*?)<\/script>/.exec(template);
  if (!m) throw new CoachError("La plantilla del cuaderno no declara sus librerías (coach-libs).");
  return JSON.parse(m[1]);
}

async function cmdVendor(pos, opts) {
  const root = rootDir(opts);
  if (!isDir(root)) throw new CoachError(`No existe ${rel(root)}. Crea un tema primero con coach init.`);
  if (typeof fetch !== "function") throw new CoachError("Este Node no tiene fetch: usa Node 18+ o coach.py vendor.");
  const libs = readLibs();
  const base = (process.env.COACH_CDN || libs.jsdelivr).replace(/\/+$/, "");
  const vdir = path.join(root, ".vendor");
  fs.mkdirSync(vdir, { recursive: true });
  let failures = 0;
  for (const lib of libs.scripts) {
    const dest = path.join(vdir, lib.file);
    if (isFile(dest) && fs.statSync(dest).size > 0 && !opts.force) {
      out(`  = ${lib.file} (ya descargado)`);
      continue;
    }
    const url = `${base}/${lib.npm}`;
    try {
      const resp = await fetch(url, { headers: { "User-Agent": `hb-coach/${VERSION}` } });
      if (!resp.ok) throw new Error(`HTTP Error ${resp.status}: ${resp.statusText}`);
      const content = Buffer.from(await resp.arrayBuffer());
      fs.writeFileSync(dest, content);
      out(`  \u2193 ${lib.file} (${fmtKb(content.length)})`);
    } catch (e) {
      failures += 1;
      out(`  \u2716 ${lib.file}: ${e.message}`);
    }
  }
  if (failures) {
    out(`\u2716 ${failures} descarga(s) fallaron. Revisa tu conexión o prueba con la otra versión del script (coach.py / coach.mjs).`);
    return 1;
  }
  out(`\u2714 Librerías en ${rel(vdir)}: el cuaderno funciona sin conexión.`);
  return 0;
}

function parseArgs(argv) {
  const pos = [];
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--") && a.length > 2) {
      const key = a.slice(2);
      if (key.includes("=")) {
        const k = key.slice(0, key.indexOf("="));
        opts[k] = key.slice(key.indexOf("=") + 1);
      } else if (BOOL_FLAGS.has(key)) {
        opts[key] = true;
      } else {
        if (i + 1 >= argv.length) throw new CoachError(`Falta el valor de --${key}`);
        opts[key] = argv[i + 1];
        i += 1;
      }
    } else if (a === "-h") {
      opts.help = true;
    } else {
      pos.push(a);
    }
  }
  return [pos, opts];
}

const COMMANDS = {
  init: cmdInit,
  leccion: cmdLeccion,
  completar: cmdCompletar,
  reabrir: cmdReabrir,
  estado: cmdEstado,
  check: cmdCheck,
  vendor: cmdVendor,
};

async function main(argv) {
  try {
    const [pos, opts] = parseArgs(argv);
    if (!pos.length || opts.help || pos[0] === "ayuda" || pos[0] === "help") {
      out(AYUDA);
      return 0;
    }
    const [cmd, ...rest] = pos;
    if (cmd === "version") {
      out(`hb-coach ${VERSION}`);
      return 0;
    }
    if (cmd === "build") {
      build(rootDir(opts));
      return 0;
    }
    const fn = COMMANDS[cmd];
    if (!fn) throw new CoachError(`Comando desconocido: ${cmd}. Usa 'ayuda' para ver los comandos.`);
    const code = await fn(rest, opts);
    return code || 0;
  } catch (e) {
    if (e instanceof CoachError) {
      process.stderr.write(`\u2716 ${e.message}\n`);
      return 2;
    }
    throw e;
  }
}

process.stdout.on("error", (e) => {
  if (e && e.code === "EPIPE") process.exit(process.exitCode || 0);
  throw e;
});
process.exitCode = await main(process.argv.slice(2));
