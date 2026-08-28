#!/usr/bin/env python3
"""
Static-check a generated unqforge script before running it.

Running a model's script fails at the first bad line, so a script with six
problems takes six round trips to survey -- and every fix you make on its
behalf contaminates the result. This walks the AST instead and reports
everything at once, without executing anything.

    python3 checkgen.py gemini.py
"""
import ast
import inspect
import sys

sys.path.insert(0, ".")
from unqforge import SC  # noqa: E402
import unqforge  # noqa: E402


def sig(name):
    try:
        return "%s%s" % (name, inspect.signature(getattr(SC, name)))
    except (TypeError, ValueError):
        return name


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "gemini.py"
    tree = ast.parse(open(path).read(), path)

    real = {m for m in dir(SC) if not m.startswith("_")}
    module = {m for m in dir(unqforge) if not m.startswith("_")}

    invented, calls, name_slots = [], {}, []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        # s.method(...)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            if f.value.id == "s":
                m = f.attr
                calls[m] = calls.get(m, 0) + 1
                if m not in real:
                    invented.append((node.lineno, "s.%s" % m))
                # getval/setval take a VARIABLE NAME, not a token
                if m in ("getval", "setval") and node.args:
                    a0 = node.args[0]
                    if not isinstance(a0, ast.Constant) or \
                            not isinstance(a0.value, str):
                        name_slots.append((node.lineno, m,
                                           ast.dump(a0)[:60]))
        # bare module-level function
        elif isinstance(f, ast.Name):
            if f.id not in module and f.id not in dir(__builtins__) \
                    and f.id not in {"print", "len", "range", "sorted",
                                     "sum", "max", "min", "set", "list",
                                     "dict", "float", "int", "str"}:
                pass  # locals and stdlib; not worth flagging

    print("=== methods called on s ===")
    for m in sorted(calls):
        mark = "  " if m in real else "??"
        print(" %s %-14s %3d×   %s" % (mark, m, calls[m],
                                       sig(m) if m in real else "NOT IN SC"))

    print("\n=== invented API ===")
    if invented:
        for ln, name in invented:
            print("  line %-5d %s" % (ln, name))
    else:
        print("  none")

    print("\n=== getval/setval first argument ===")
    print("  signature: %s" % sig("getval"))
    print("             %s" % sig("setval"))
    print("  These take a variable NAME (a str). A token passed here ends up")
    print("  as att(var(<dict>)) -- VariableName holding a dict, which the")
    print("  token validator cannot see because Type is still 'Variable'.")
    if name_slots:
        for ln, m, dump in name_slots:
            print("  line %-5d s.%s(%s...)" % (ln, m, dump))
    else:
        print("  all call sites pass a literal string -- fine")

    print("\n%d invented, %d suspect name slots"
          % (len(invented), len(name_slots)))


if __name__ == "__main__":
    main()
