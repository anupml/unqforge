#!/usr/bin/env python3
"""Harvest declared enum values from WorkflowKit's WFActions.plist.

Emits constructs/wfactions.declared.json -- a lowest-trust tier holding
enum Items that Apple DECLARES but that were never observed serialized on
device. The corpus remains the only source for wire-format shapes; this
only fills the picker-value sets nobody ever configured.

Skips any enum key already present from a .native/.ranok/.spec file, so
device-observed enums (WFCondition, operators, structural) always win and
are never overridden.
"""
import json, plistlib, sys, datetime
sys.path.insert(0, ".")
from unqforge import Constructs

PLIST = "/Users/anup/Downloads/WFActions.plist"
OUT   = "constructs/wfactions.declared.json"
IOS   = "16.7"

# Everything already known from higher-trust tiers is off-limits.
have = set(Constructs().enums)

d = plistlib.load(open(PLIST, "rb"))
declared = {}
skipped_known = set()
for ident, action in d.items():
    for p in action.get("Parameters", []):
        items = p.get("Items")
        key = p.get("Key")
        if not items or not key:
            continue
        if key in have:                 # device-observed already; leave it
            skipped_known.add(key)
            continue
        declared.setdefault(key, set()).update(
            str(x) for x in items)      # values are literal strings

out = {
    "_source": "WorkflowKit WFActions.plist",
    "_ios": IOS,
    "_device": "iPhone10,5 (8 Plus)",
    "_harvested": datetime.date.today().isoformat(),
    "_note": ("declared enum values only -- NOT observed serialized. "
              "Keys already present in .native/.ranok are skipped."),
    "enums": {k: sorted(v) for k, v in declared.items()},
}
json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)

print("wrote", OUT)
print("declared enum params added:", len(declared))
print("skipped (already device-observed):", len(skipped_known),
      "->", sorted(skipped_known))
