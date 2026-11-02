"""Utilidades compartidas por los tests: rutas del repo y repos git temporales aislados."""
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Git aislado de la configuración de la máquina (firma de commits, hooks, plantillas).
ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL=os.devnull,
    GIT_CONFIG_NOSYSTEM="1",
    GIT_AUTHOR_NAME="test",
    GIT_AUTHOR_EMAIL="test@example.com",
    GIT_COMMITTER_NAME="test",
    GIT_COMMITTER_EMAIL="test@example.com",
)


def run(args, cwd):
    return subprocess.run([str(a) for a in args], cwd=str(cwd), env=ENV, capture_output=True,
                          text=True, encoding="utf-8")


def git(cwd, *args):
    result = run(["git", *args], cwd)
    if result.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), result.stderr))
    return result.stdout


def init_repo(path):
    git(path, "init", "-q")
    git(path, "checkout", "-q", "-b", "main")
    return path


def commit_all(path, message="cambio"):
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
