#!/usr/bin/env python3
"""
Harvest constructs from every shortcut in your Shortcuts library.

macOS keeps the library in a Core Data store at
~/Library/Shortcuts/Shortcuts.sqlite, with each shortcut's actions in a
ZDATA blob. That means the whole library can be harvested in one pass
instead of exporting shortcuts by hand.

The database is opened READ-ONLY. This never writes to your library.

Terminal needs Full Disk Access:
  System Settings -> Privacy & Security -> Full Disk Access -> add
  Terminal, then quit and reopen it.

  python3 tools/harvestdb.py
  python3 tools/harvestdb.py --json constructs/library.native.json
  python3 tools/harvestdb.py --list        # just show what's in there
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.join(_ROOT, "tools"))
_os.chdir(_ROOT)

import argparse
import json
import os
import plistlib
import sqlite3
import sys
from collections import Counter

from decompile import Analysis, analyse, check_offsets      # noqa: E402

DB = os.path.expanduser("~/Library/Shortcuts/Shortcuts.sqlite")

QUERY = """
SELECT s.Z_PK, s.ZNAME, a.ZDATA
FROM ZSHORTCUT s
JOIN ZSHORTCUTACTIONS a ON a.ZSHORTCUT = s.Z_PK
WHERE a.ZDATA IS NOT NULL
"""


def actions_from(blob):
    """Pull WFWorkflowActions out of a ZDATA blob.

    The blob is a plist, but whether it holds the whole workflow dict or
    just the actions array is not documented, so handle both.
    """
    try:
        d = plistlib.loads(blob)
    except Exception:
        return None
    if isinstance(d, dict):
        for key in ("WFWorkflowActions", "actions"):
            if isinstance(d.get(key), list):
                return d[key]
        return None
    if isinstance(d, list):
        if d and isinstance(d[0], dict) and "WFWorkflowActionIdentifier" in d[0]:
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--json", help="write merged constructs here")
    ap.add_argument("--list", action="store_true",
                    help="list shortcuts and action counts, harvest nothing")
    ap.add_argument("--min-actions", type=int, default=1)
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit("no database at %s" % args.db)

    # read-only URI: this is a live library, never write to it
    try:
        con = sqlite3.connect("file:%s?mode=ro" % args.db, uri=True)
    except sqlite3.OperationalError as e:
        sys.exit("cannot open the database (%s).\nGrant Terminal Full Disk "
                 "Access in System Settings, then reopen Terminal." % e)

    rows = list(con.execute(QUERY))
    con.close()

    A = Analysis()
    ok = skipped = total_actions = 0
    per_shortcut = []
    unreadable = []

    for pk, name, blob in rows:
        acts = actions_from(blob)
        if not acts or len(acts) < args.min_actions:
            skipped += 1
            unreadable.append(name or "<%d>" % pk)
            continue
        try:
            analyse(acts, A)
            check_offsets(acts, A)
        except Exception as e:
            skipped += 1
            unreadable.append("%s (%s)" % (name or pk, type(e).__name__))
            continue
        ok += 1
        total_actions += len(acts)
        per_shortcut.append((len(acts), name or "<%d>" % pk))

    print("library: %d shortcuts, %d readable, %d skipped"
          % (len(rows), ok, skipped))
    print("harvested %d actions, %d distinct types"
          % (total_actions, len(A.actions)))

    if args.list:
        print()
        for n, name in sorted(per_shortcut, reverse=True)[:40]:
            print("  %5d  %s" % (n, name))
        return

    used = Counter({i: r["count"] for i, r in A.actions.items()})
    print("\nmost used:")
    for ident, n in used.most_common(15):
        print("  %-52s %d" % (ident, n))

    if A.violations:
        print("\n%d offset/consistency warnings (older shortcuts often "
              "have them; those entries were still harvested)"
              % len(A.violations))
        for v in A.violations[:3]:
            print("   " + v[:120])

    if args.json:
        with open(args.json, "w") as f:
            json.dump(A.to_json(), f, indent=2)
        print("\nwrote %s" % args.json)
        print("run: python3 tools/gendocs.py && python3 tools/coverage.py")


if __name__ == "__main__":
    main()
