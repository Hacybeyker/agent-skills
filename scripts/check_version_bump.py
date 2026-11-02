#!/usr/bin/env python3
"""Comprueba que cada skill cambiada sube su metadata.version (SemVer).

Compara contra el punto en que la rama se separó de la base (merge-base), incluidos los cambios
sin commit y los archivos nuevos. Una skill nueva o eliminada no necesita subir versión.

Uso: scripts/check_version_bump.py [base]   (por defecto origin/main; en el CI, la rama base del PR)
"""
import os
import re
import subprocess
import sys

VERSION_RE = re.compile(r"^\s+version:\s*[\"']?(\d+)\.(\d+)\.(\d+)[\"']?\s*$", re.M)


def git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git %s falló" % " ".join(args))
    return result.stdout


def version(text):
    """Versión del frontmatter como tupla (MAJOR, MINOR, PATCH), o None si no tiene."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    match = VERSION_RE.search(text[3:end] if end != -1 else "")
    return tuple(int(n) for n in match.groups()) if match else None


def fmt(v):
    return ".".join(str(n) for n in v)


def changed_skills(merge_base):
    paths = git("diff", "--name-only", merge_base, "--", "skills/").splitlines()
    paths += git("ls-files", "--others", "--exclude-standard", "--", "skills/").splitlines()
    return sorted({p.split("/")[1] for p in paths if p.count("/") >= 2})


def main(argv):
    base = argv[1] if len(argv) > 1 else "origin/main"
    os.chdir(git("rev-parse", "--show-toplevel").strip())
    merge_base = git("merge-base", base, "HEAD").strip()
    errors, checked = [], 0
    for name in changed_skills(merge_base):
        path = "skills/%s/SKILL.md" % name
        if not os.path.isfile(path):
            continue  # skill eliminada
        try:
            before = version(git("show", "%s:%s" % (merge_base, path)))
        except RuntimeError:
            continue  # skill nueva
        with open(path, encoding="utf-8") as f:
            after = version(f.read())
        checked += 1
        if after is None:
            errors.append("%s: no tiene metadata.version" % name)
        elif before is not None and after <= before:
            errors.append("%s cambió, pero su versión sigue en %s (en %s: %s): súbela según SemVer"
                          % (name, fmt(after), base, fmt(before)))
    if errors:
        print("\n".join("✖ %s" % e for e in errors))
        return 1
    print("✔ Versiones al día (%d skill(s) cambiada(s) respecto de %s)" % (checked, base))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except RuntimeError as err:
        print("✖ %s" % err, file=sys.stderr)
        sys.exit(2)
