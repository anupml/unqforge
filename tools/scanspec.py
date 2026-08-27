#!/usr/bin/env python3
"""
Scan every .intentdefinition on this Mac and extract the enum vocabulary.

Why this matters: harvesting decompiled shortcuts gives you the enum values
people happened to use. These files give the COMPLETE set, with the display
strings Shortcuts actually writes into the plist.

Cross-checked twice against the corpus:
    ChangeCaseType  titleCase -> "Capitalize with Title Case"
    AskForInputType number    -> "Number"
both appear verbatim in harvested shortcuts, so INEnumValueDisplayName is
the literal plist value.

Run:  python3 scanspec.py            # scan default system paths
      python3 scanspec.py /some/dir  # scan somewhere specific
Writes spec_enums.json next to itself.
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_sys.argv = [_sys.argv[0]] + [_os.path.abspath(a) if _os.path.exists(a) else a
                              for a in _sys.argv[1:]]
_os.chdir(_ROOT)

import json, os, plistlib, sys

ROOTS = [
    "/System/Library/PrivateFrameworks",
    "/System/Library/Frameworks",
    "/System/Library/CoreServices",
    "/System/Applications",
    "/Applications",
]


def find_defs(roots):
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root, followlinks=False):
            for f in files:
                if f.endswith(".intentdefinition"):
                    yield os.path.join(dirpath, f)


def main():
    roots = sys.argv[1:] or ROOTS
    enums = {}       # enum name -> {"values": {internal: display}, "files": []}
    intents = {}     # intent name -> {"params": [...], "file": ...}
    bad = 0
    paths = sorted(set(find_defs(roots)))

    for p in paths:
        try:
            d = plistlib.load(open(p, "rb"))
        except Exception:
            bad += 1
            continue
        short = p.replace("/System/Library/PrivateFrameworks/", "PF/")

        for e in d.get("INEnums", []):
            name = e.get("INEnumName")
            if not name:
                continue
            slot = enums.setdefault(name, {"values": {}, "files": []})
            for v in e.get("INEnumValues", []):
                vn = v.get("INEnumValueName")
                dn = v.get("INEnumValueDisplayName")
                if vn and dn and dn != "unknown":
                    slot["values"][vn] = dn
            if short not in slot["files"]:
                slot["files"].append(short)

        for i in d.get("INIntents", []):
            name = i.get("INIntentName")
            if not name:
                continue
            intents[name] = {
                "title": i.get("INIntentTitle"),
                "description": i.get("INIntentDescription"),
                "class_prefix": i.get("INIntentClassPrefix"),
                "params": [
                    {"name": p.get("INIntentParameterName"),
                     "type": p.get("INIntentParameterType"),
                     "display": p.get("INIntentParameterDisplayName"),
                     "enum": p.get("INIntentParameterEnumType")}
                    for p in i.get("INIntentParameters", [])
                ],
                "file": short,
            }

    out = {"enums": enums, "intents": intents,
           "scanned_files": len(paths), "unreadable": bad}
    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "spec_enums.json")
    json.dump(out, open(dest, "w"), indent=1, ensure_ascii=False)

    print("scanned %d .intentdefinition files (%d unreadable)" % (len(paths), bad))
    print("enums:   %d" % len(enums))
    print("intents: %d" % len(intents))
    print("wrote", dest)
    print()
    print("=== enums whose values look like Shortcuts plist strings ===")
    for name in sorted(enums):
        vals = list(enums[name]["values"].values())
        if vals:
            print("  %-34s %s" % (name, vals[:6]))


if __name__ == "__main__":
    main()
