#!/usr/bin/env python3
"""
Join the spec enum vocabulary to the harvested constructs database.

The corpus tells you which enum values people happened to use.
spec_enums.json tells you the complete legal set. Where a harvested value
appears in exactly one spec enum, the two are the same field and the
sampled set can be upgraded to the full one.

Confirmed twice against real shortcuts:
    WFCaseType  "Capitalize with Title Case"  -> ChangeCaseType
    WFInputType "Number", "URL"               -> AskForInputType

Run:  python3 joinspec.py [--write]
Without --write it only reports. With --write it emits
constructs/enums.spec.json, a stronger provenance tier than harvesting.
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_sys.argv = [_sys.argv[0]] + [_os.path.abspath(a) if _os.path.exists(a) else a
                              for a in _sys.argv[1:]]
_os.chdir(_ROOT)

import glob, json, os, re, sys

CONSTRUCTS = "constructs"
SPEC = "spec_enums.json"


def tokens(s):
    """Lowercase word tokens from camelCase or dotted identifiers."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    return {t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t}


def load_corpus():
    """param key -> {value, ...} and param key -> {action ids using it}"""
    sampled, owners = {}, {}
    for path in sorted(glob.glob(os.path.join(CONSTRUCTS, "*.json"))):
        d = json.load(open(path))
        for key, vals in d.get("enums", {}).items():
            strs = {v for v in vals if isinstance(v, str)}
            if strs:
                sampled.setdefault(key, set()).update(strs)
        for ident, rec in d.get("actions", {}).items():
            for p in rec.get("params", {}):
                owners.setdefault(p, set()).add(ident)
    return sampled, owners


def main():
    if not os.path.exists(SPEC):
        sys.exit("no %s -- run scanspec.py first" % SPEC)
    spec = json.load(open(SPEC))["enums"]
    sampled, owners = load_corpus()

    resolved, ambiguous, unmatched = {}, {}, {}

    for key, seen in sorted(sampled.items()):
        cands = [name for name, e in spec.items()
                 if seen <= set(e["values"].values())]
        if not cands:
            unmatched[key] = sorted(seen)
            continue
        if len(cands) > 1:
            # Tie-break on name overlap with the actions that use this param.
            # WFTextSeparator appears in both Split and Combine; the action
            # identifier says which.
            ctx = set()
            for ident in owners.get(key, ()):
                ctx |= tokens(ident)
            scored = sorted(cands, key=lambda n: -len(tokens(n) & ctx))
            best = len(tokens(scored[0]) & ctx)
            runner = len(tokens(scored[1]) & ctx) if len(scored) > 1 else -1
            if best > runner:
                cands = [scored[0]]
            else:
                ambiguous[key] = {"candidates": sorted(cands),
                                  "sampled": sorted(seen)}
                continue
        name = cands[0]
        full = sorted(spec[name]["values"].values())
        resolved[key] = {"enum": name, "values": full,
                         "sampled": sorted(seen),
                         "gained": sorted(set(full) - seen)}

    print("=== RESOLVED (sampled -> complete) ===")
    for key, r in sorted(resolved.items()):
        print("  %-22s %s" % (key, r["enum"]))
        print("     had  %s" % r["sampled"])
        print("     now  %s" % r["values"])
    if not resolved:
        print("  (none)")

    print("\n=== AMBIGUOUS (needs a human) ===")
    for key, a in sorted(ambiguous.items()):
        print("  %-22s %s   sampled %s"
              % (key, a["candidates"], a["sampled"]))
    if not ambiguous:
        print("  (none)")

    print("\n=== NO SPEC MATCH (corpus is the only source) ===")
    for key, v in sorted(unmatched.items()):
        print("  %-22s %s" % (key, v))

    if "--write" in sys.argv and resolved:
        out = {"actions": {},
               "enums": {k: r["values"] for k, r in resolved.items()},
               "token_types": [], "aggrandizements": []}
        dest = os.path.join(CONSTRUCTS, "enums.spec.json")
        json.dump(out, open(dest, "w"), indent=1, ensure_ascii=False)
        print("\nwrote %s (%d enums)" % (dest, len(resolved)))


if __name__ == "__main__":
    main()
