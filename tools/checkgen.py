#!/usr/bin/env python3
"""
Static-check a generated script before running it.

A script written against sclib fails at the first bad line, so surveying
one with six problems takes six round trips -- and fixing them by hand as
you go destroys whatever you were trying to measure. This walks the AST
and reports every call to something that does not exist, without
executing anything.

Useful mainly for scripts an LLM wrote: inventing a plausible method is a
far more common failure than misusing a real one.

  python3 tools/checkgen.py path/to/script.py
"""
import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)

import ast                                                   # noqa: E402
import inspect                                               # noqa: E402
import sys                                                   # noqa: E402
from collections import Counter                              # noqa: E402

import unqforge                                              # noqa: E402
from unqforge import SC                                      # noqa: E402


def sig(name):
    try:
        return "%s%s" % (name, inspect.signature(getattr(SC, name)))
    except (TypeError, ValueError):
        return name


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: checkgen.py <script.py>")
    path = sys.argv[1]
    if not _os.path.exists(path):
        sys.exit("no such file: %s" % path)

    tree = ast.parse(open(path).read(), path)
    methods = {m for m in dir(SC) if not m.startswith("_")}
    module = {m for m in dir(unqforge) if not m.startswith("_")}

    calls = Counter()
    bad_method, bad_func = [], []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            # <builder>.method(...) -- the builder is conventionally s
            if f.value.id == "s":
                calls[f.attr] += 1
                if f.attr not in methods:
                    bad_method.append((node.lineno, "s.%s" % f.attr))
        elif isinstance(f, ast.Name) and f.id in ("var", "att", "ts", "out",
                                                  "E", "num", "U"):
            if f.id not in module:
                bad_func.append((node.lineno, f.id))

    print("methods used")
    for m, n in sorted(calls.items()):
        ok = m in methods
        print("  %s %-14s %3dx  %s" % ("  " if ok else "!!", m, n,
                                       sig(m) if ok else "DOES NOT EXIST"))

    bad = bad_method + bad_func
    print("\ninvented API")
    if bad:
        for lineno, name in sorted(bad):
            print("  line %-5d %s" % (lineno, name))
        print("\n%d call site%s to something that does not exist."
              % (len(bad), "" if len(bad) == 1 else "s"))
    else:
        print("  none")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
