#!/usr/bin/env python3
"""
Measure how much of Shortcuts the constructs database actually covers.

spec/action_ids.txt is the denominator: every is.workflow.actions.*
identifier found in the Shortcuts binary. constructs/*.json is what has
been observed on a real device and is therefore safe to emit.

Usage:
  python3 coverage.py              # summary
  python3 coverage.py --missing    # every unharvested identifier
  python3 coverage.py --rank       # unharvested actions, by how often
                                   # they appear in shortcuts/
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_sys.argv = [_sys.argv[0]] + [_os.path.abspath(a) if _os.path.exists(a) else a
                              for a in _sys.argv[1:]]
_os.chdir(_ROOT)

import collections, glob, json, os, plistlib, sys

IDS = "spec/action_ids.txt"


def harvested():
    have = set()
    for f in sorted(glob.glob("constructs/*.json")):
        have |= set(json.load(open(f)).get("actions", {}))
    return have


def known_ids():
    if not os.path.exists(IDS):
        sys.exit("no %s -- see README, 'Extracting the identifier list'" % IDS)
    return {l.strip() for l in open(IDS) if l.strip()}


def main():
    have, all_ids = harvested(), known_ids()
    builtin = {i for i in have if i.startswith("is.workflow.actions.")}
    third = sorted(have - builtin)
    covered = all_ids & builtin
    missing = sorted(all_ids - builtin)

    print("built-in actions   %d / %d   (%.0f%%)"
          % (len(covered), len(all_ids), 100 * len(covered) / len(all_ids)))
    print("third-party/intents %d   %s"
          % (len(third), ", ".join(t.split(".")[-1] for t in third[:4])))
    unknown = sorted(builtin - all_ids)
    if unknown:
        print("harvested but not in the binary list: %s" % unknown)

    if "--missing" in sys.argv:
        print()
        for m in missing:
            print("  " + m)

    if "--rank" in sys.argv:
        freq, where = collections.Counter(), collections.defaultdict(set)
        files = sorted(glob.glob("shortcuts/*"))
        for f in files:
            try:
                d = plistlib.load(open(f, "rb"))
            except Exception:
                continue
            for a in d.get("WFWorkflowActions", []):
                i = a["WFWorkflowActionIdentifier"]
                if i in missing:
                    freq[i] += 1
                    where[i].add(os.path.basename(f))
        print("\nunharvested actions present in shortcuts/ (%d files):" % len(files))
        if not freq:
            print("  none -- every action in the corpus is already covered")
        for i, n in freq.most_common(30):
            print("  %-48s %3d  %s" % (i, n, sorted(where[i])[0]))


if __name__ == "__main__":
    main()
