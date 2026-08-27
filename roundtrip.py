#!/usr/bin/env python3
"""
Round-trip test: plist -> Python -> plist, then compare.

This is the coverage metric. A shortcut that round-trips is one the
toolchain genuinely handles; a failure names the construct that broke it,
which becomes the next harvest target.

UUIDs are randomised on regeneration, so comparison canonicalises them by
first appearance rather than comparing bytes.

Usage:
  python3 roundtrip.py shortcuts/*.plist shortcuts/*.wflow
"""
import glob, plistlib, re, subprocess, sys, tempfile, os, collections

UUID_RE = re.compile(r"^[0-9A-Fa-f-]{36}$")


def canon(acts):
    """Replace UUIDs with sequence numbers so two runs compare equal."""
    ids = {}

    def r(o):
        if isinstance(o, dict):
            return {k: r(v) for k, v in o.items()}
        if isinstance(o, list):
            return [r(v) for v in o]
        if isinstance(o, str) and UUID_RE.match(o):
            return ids.setdefault(o, "ID%d" % len(ids))
        return o
    return [r(a) for a in acts]


def first_diff(a, b, path="acts"):
    if type(a) is not type(b):
        return "%s: type %s vs %s" % (path, type(a).__name__, type(b).__name__)
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return "%s: missing %r in original" % (path, k)
            if k not in b:
                return "%s: lost %r on regenerate" % (path, k)
            d = first_diff(a[k], b[k], "%s.%s" % (path, k))
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return "%s: length %d vs %d" % (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, "%s[%d]" % (path, i))
            if d:
                return d
        return None
    return None if a == b else "%s: %r != %r" % (path, a, b)


def one(path, here):
    src = plistlib.load(open(path, "rb"))
    n = len(src["WFWorkflowActions"])
    tmp = tempfile.mkdtemp()
    py = os.path.join(tmp, "gen.py")
    out = os.path.join(tmp, "out.plist")

    g = subprocess.run([sys.executable, os.path.join(here, "topython.py"),
                        path, "-o", py], capture_output=True, text=True)
    if g.returncode:
        return n, "codegen", g.stderr.strip().splitlines()[-1:]

    env = dict(os.environ)
    env["PYTHONPATH"] = here + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, py, out],
                       capture_output=True, text=True, cwd=here, env=env)
    if r.returncode:
        last = [l for l in r.stderr.strip().splitlines() if l.strip()][-1:]
        return n, "regenerate", last

    got = plistlib.load(open(out, "rb"))
    d = first_diff(canon(src["WFWorkflowActions"]),
                   canon(got["WFWorkflowActions"]))
    return (n, "ok", []) if not d else (n, "mismatch", [d])


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    files = []
    for a in sys.argv[1:] or ["shortcuts/*"]:
        files += sorted(glob.glob(a))
    if not files:
        sys.exit("no files")

    tally = collections.Counter()
    total_ok = total = 0
    for f in files:
        try:
            n, status, detail = one(f, here)
        except Exception as e:
            n, status, detail = 0, "unreadable", [str(e)[:90]]
        tally[status] += 1
        total += n
        if status == "ok":
            total_ok += n
        mark = "PASS" if status == "ok" else "FAIL"
        print("%-4s %-30s %4d actions  %s" % (mark, os.path.basename(f), n,
                                              status if status != "ok" else ""))
        for d in detail:
            print("       %s" % d[:150])

    print()
    print("%d/%d shortcuts round-trip, %d/%d actions"
          % (tally["ok"], len(files), total_ok, total))
    for k, v in tally.most_common():
        if k != "ok":
            print("   %-12s %d" % (k, v))


if __name__ == "__main__":
    main()
