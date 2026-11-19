#!/usr/bin/env python3
"""Corre los tests de unittest en paralelo: reparte las clases de test entre varios procesos y resume como unittest.

Da el mismo resultado que `python3 -m unittest discover -s tests`, en menos tiempo: cada clase corre entera en un
proceso, en el mismo orden interno, y los procesos toman la clase siguiente apenas terminan la suya (primero las clases
con más tests). Los tracebacks de lo que falla salen al final, completos.

Uso: scripts/run_tests.py [-s tests] [-j PROCESOS] [-v] [CLASE…]
     (CLASE es un nombre como test_perf.CompareTest; sin clases, corre todas)
Python 3.8 o superior, solo librería estándar.
"""
import argparse
import io
import multiprocessing
import os
import sys
import time
import unittest


def iter_cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_cases(item)
        else:
            yield item


def collect(start, names):
    """{"módulo.Clase": cantidad de tests} en el orden en que unittest las descubre, y los módulos que no importan."""
    sys.path.insert(0, start)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(names) if names else loader.discover(start, top_level_dir=start)
    groups, broken = {}, []
    for case in iter_cases(suite):
        cls = type(case)
        if cls.__module__ == "unittest.loader":  # un módulo que no se pudo importar: se corre aquí para mostrar el error
            broken.append(case)
            continue
        name = "%s.%s" % (cls.__module__, cls.__qualname__)
        groups[name] = groups.get(name, 0) + 1
    return groups, broken


def run_group(job):
    """Corre una clase entera en este proceso. Devuelve (nombre, corridos, fallos, errores, omitidos, salida, segundos)."""
    start, name, verbosity = job
    if start not in sys.path:
        sys.path.insert(0, start)
    began = time.time()
    stream = io.StringIO()
    try:
        suite = unittest.TestLoader().loadTestsFromName(name)
    except Exception as error:  # la clase desapareció o su módulo no importa en este proceso
        return name, 0, 0, 1, 0, "ERROR al cargar %s: %r\n" % (name, error), time.time() - began
    result = unittest.TextTestRunner(stream=stream, verbosity=verbosity).run(suite)
    failed = len(result.failures) + len(result.unexpectedSuccesses)
    return (name, result.testsRun, failed, len(result.errors), len(result.skipped), stream.getvalue(),
            time.time() - began)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-s", "--start", default="tests", help="la carpeta de los tests (por defecto tests)")
    parser.add_argument("-j", "--procesos", type=int, default=0,
                        help="cuántos procesos (por defecto, uno por núcleo, hasta 8)")
    parser.add_argument("-v", "--verbose", action="store_true", help="una línea por test, como unittest -v")
    parser.add_argument("clases", nargs="*", help="solo estas clases (módulo.Clase)")
    args = parser.parse_args(argv)
    start = os.path.abspath(args.start)
    began = time.time()
    groups, broken = collect(start, args.clases)
    workers = max(1, min(args.procesos or min(os.cpu_count() or 2, 8), len(groups) or 1))
    verbosity = 2 if args.verbose else 1
    ran = failures = errors = skipped = 0
    reports = []
    if broken:
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=verbosity).run(unittest.TestSuite(broken))
        ran, errors = result.testsRun, len(result.errors)
        reports.append(stream.getvalue())
    jobs = [(start, name, verbosity) for name in sorted(groups, key=lambda item: -groups[item])]
    done = 0
    with multiprocessing.get_context("spawn").Pool(workers) as pool:
        for name, count, failed, erred, omitted, output, seconds in pool.imap_unordered(run_group, jobs):
            done += 1
            ran, failures, errors, skipped = ran + count, failures + failed, errors + erred, skipped + omitted
            if failed or erred:
                reports.append(output)
                mark = "✖"
            else:
                mark = "·"
            if args.verbose:
                print(output.split("\n----------------------------------------------------------------------")[0].rstrip())
            print("%s %s (%d tests, %.1f s) [%d/%d]" % (mark, name, count, seconds, done, len(jobs)), flush=True)
    for output in reports:
        print("\n" + output.rstrip())
    print("\n" + "-" * 70)
    print("Ran %d tests in %.3fs (%d procesos)" % (ran, time.time() - began, workers))
    if not ran:
        print("\nNO TESTS RAN")
        return 5
    if failures or errors:
        parts = ["failures=%d" % failures] if failures else []
        parts += ["errors=%d" % errors] if errors else []
        parts += ["skipped=%d" % skipped] if skipped else []
        print("\nFAILED (%s)" % ", ".join(parts))
        return 1
    print("\nOK" + (" (skipped=%d)" % skipped if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
