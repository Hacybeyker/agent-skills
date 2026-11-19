"""Corre un script como `python3 -I <script> …`, pero con su bytecode guardado (en tests/__pycache__).

Python nunca guarda el bytecode del script principal: compilar las más de 20 000 líneas de perf.py cuesta unos 150 ms
en cada llamada, y los tests lo lanzan miles de veces. Solo lo usan los tests (el usuario corre perf.py directo): el
código que se ejecuta es el mismo, compilado del mismo archivo, como módulo __main__ y con los mismos argumentos.

Uso: python3 -I tests/perf_rapido.py <script> [argumentos…]
"""
import hashlib
import marshal
import os
import sys
import types


def cache_dir():
    # Junto a los .pyc que Python ya escribe para los tests (tests/__pycache__, ignorado por git), no en una carpeta
    # temporal compartida: marshal carga código, así que solo se lee de una carpeta con la misma confianza que esos .pyc.
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "__pycache__", "perf_rapido")


def load_code(script):
    """El código compilado del script: de la carpeta temporal si el archivo y el Python son los mismos; si no, lo
    compila y lo guarda (sin fallar si no puede guardarlo)."""
    with open(script, "rb") as handle:
        source = handle.read()
    key = hashlib.sha256(source + sys.version.encode() + script.encode()).hexdigest()[:24]
    path = os.path.join(cache_dir(), key + ".bin")
    try:
        with open(path, "rb") as handle:
            return marshal.load(handle)
    except (OSError, EOFError, ValueError, TypeError):
        pass
    code = compile(source, script, "exec", dont_inherit=True)
    try:
        os.makedirs(cache_dir(), exist_ok=True)
        partial = "%s.%d" % (path, os.getpid())
        with open(partial, "wb") as handle:
            marshal.dump(code, handle)
        os.replace(partial, path)  # atómico: otro proceso de tests nunca lee un archivo a medias
    except OSError:
        pass
    return code


def main():
    script = os.path.abspath(sys.argv[1])
    code = load_code(script)
    here = os.path.dirname(os.path.abspath(__file__))
    if sys.path and sys.path[0] == here:  # como `python3 -I <script>` en 3.8 a 3.10: la carpeta del script primero
        sys.path[0] = os.path.dirname(script)
    sys.argv = [script] + sys.argv[2:]
    main_module = types.ModuleType("__main__")
    main_module.__file__ = script
    main_module.__builtins__ = __builtins__
    sys.modules["__main__"] = main_module
    exec(code, main_module.__dict__)


if __name__ == "__main__":
    main()
