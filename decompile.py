#!/usr/bin/env python3
"""
Decompile an iOS Shortcuts .plist export.

Purpose: turn any shortcut you built by hand into machine-checked facts
about the plist format, so the generator's whitelist grows from evidence
instead of from anyone's recall.

Produces:
  1. a readable pseudocode listing (human check that parsing is sane)
  2. a constructs JSON: action identifiers, parameter keys, value shapes,
     enum values, and OutputName-per-action learned from cross-references
  3. a repeat-depth audit of the "Repeat Item N" naming rule
  4. a diff against a previously known constructs file

Usage:
  python3 decompile.py export.plist [--json out.json] [--known prev.json]
"""
import argparse, json, plistlib, sys
from collections import defaultdict

OBJ = "\ufffc"

def u16_len(s):
    """UTF-16 code units in s. Shortcuts counts offsets in these, not in
    Python code points. Emoji and mathematical alphanumerics are non-BMP
    and take two units each."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def u16_to_py(s):
    """Map UTF-16 code unit offset -> Python string index."""
    m, u = {}, 0
    for i, ch in enumerate(s):
        m[u] = i
        u += 2 if ord(ch) > 0xFFFF else 1
    return m

CF_OPEN, CF_ELSE, CF_CLOSE = 0, 1, 2
REPEATS = {"is.workflow.actions.repeat.count",
           "is.workflow.actions.repeat.each"}


# ---------------------------------------------------------------- shapes

def shape_of(v):
    """Describe a parameter value's serialization shape."""
    if isinstance(v, dict):
        st = v.get("WFSerializationType")
        if st:
            return st
        # the conditional's odd double wrapper
        if set(v) == {"Type", "Variable"}:
            return "ConditionalInputWrapper"
        if "WFDictionaryFieldValueItems" in v:
            return "DictionaryFieldValueItems"
        return "dict{%s}" % ",".join(sorted(v))
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "real"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "array"
    return type(v).__name__


def walk_tokens(node, hit):
    """Call hit(token_dict) for every variable/output token anywhere inside."""
    if isinstance(node, dict):
        if node.get("Type") in ("Variable", "ActionOutput", "Ask",
                                "Clipboard", "CurrentDate", "ExtensionInput",
                                "DeviceDetails", "ShortcutInput"):
            hit(node)
        for v in node.values():
            walk_tokens(v, hit)
    elif isinstance(node, list):
        for v in node:
            walk_tokens(v, hit)


# ---------------------------------------------------------------- analysis

class Analysis:
    def __init__(self):
        self.actions = defaultdict(lambda: {
            "params": defaultdict(set), "output_names": set(), "count": 0})
        self.enums = defaultdict(set)
        self.token_types = set()
        self.aggrandizements = set()
        self.uuid_owner = {}        # UUID -> action identifier
        self.uuid_params = {}       # UUID -> that action's parameters
        self.depth_findings = []
        self.violations = []

    def to_json(self):
        return {
            "actions": {k: {"params": {p: sorted(s) for p, s
                                       in sorted(v["params"].items())},
                            "output_names": sorted(v["output_names"]),
                            "count": v["count"]}
                        for k, v in sorted(self.actions.items())},
            "enums": {k: sorted(v) for k, v in sorted(self.enums.items())},
            "token_types": sorted(self.token_types),
            "aggrandizements": sorted(self.aggrandizements),
        }


ENUM_KEYS = {"WFCondition", "WFControlFlowMode", "WFItemType",
             "WFTextSeparator", "WFItemSpecifier", "WFCountType",
             "WFGetDictionaryValueType", "WFMathOperation",
             "WFHTTPMethod", "WFHTTPBodyType", "WFInputType",
             "WFImageFormat", "WFEncodeMode", "WFHashType"}


def analyse(acts, A):
    # pass 1: who owns which UUID
    for a in acts:
        p = a["WFWorkflowActionParameters"]
        u = p.get("UUID")
        if u:
            A.uuid_owner[u] = a["WFWorkflowActionIdentifier"]
            A.uuid_params[u] = p

    # pass 2: everything else, tracking repeat nesting depth
    depth = 0
    for i, a in enumerate(acts):
        ident = a["WFWorkflowActionIdentifier"]
        p = a["WFWorkflowActionParameters"]
        rec = A.actions[ident]
        rec["count"] += 1

        for k, v in p.items():
            rec["params"][k].add(shape_of(v))
            if k in ENUM_KEYS and isinstance(v, (int, str)):
                A.enums[k].add(v)
            # dictionary item types live one level down
            if isinstance(v, dict):
                items = v.get("Value", {})
                if isinstance(items, dict):
                    for it in items.get("WFDictionaryFieldValueItems", []):
                        if "WFItemType" in it:
                            A.enums["WFItemType"].add(it["WFItemType"])

        cf = p.get("WFControlFlowMode")
        is_repeat = ident in REPEATS

        # references are resolved at the depth *inside* an open block
        cur = depth + (1 if (is_repeat and cf == CF_OPEN) else 0)

        def hit(tok, _cur=cur, _i=i):
            A.token_types.add(tok["Type"])
            if tok["Type"] == "ActionOutput":
                uu = tok.get("OutputUUID")
                owner = A.uuid_owner.get(uu)
                # A renamed magic variable carries the user's label, not the
                # action's canonical output name. Only learn from actions that
                # were not renamed.
                renamed = "CustomOutputName" in A.uuid_params.get(uu, {})
                if owner and tok.get("OutputName") and not renamed:
                    A.actions[owner]["output_names"].add(tok["OutputName"])
            if tok["Type"] == "Variable":
                name = tok.get("VariableName", "")
                for base in ("Repeat Item", "Repeat Index"):
                    if name == base:
                        ref = 1
                    elif name.startswith(base + " "):
                        try:
                            ref = int(name[len(base) + 1:])
                        except ValueError:
                            continue
                    else:
                        continue
                    A.depth_findings.append((_i, name, ref, _cur))
                    if ref > _cur:
                        A.violations.append(
                            "action %d: %r referenced at repeat depth %d"
                            % (_i, name, _cur))
            for ag in tok.get("Aggrandizements", []) or []:
                A.aggrandizements.add(ag.get("Type", "?"))

        walk_tokens(p, hit)

        if is_repeat and cf == CF_OPEN:
            depth += 1
        elif is_repeat and cf == CF_CLOSE:
            depth -= 1

    if depth != 0:
        A.violations.append("unbalanced repeat nesting: ends at %d" % depth)


def check_offsets(node, A, path="root"):
    """Every attachment offset must land on a U+FFFC in its own string.
    A harvested file that fails this is corrupt, and anything learned from
    it would poison the constructs database."""
    if isinstance(node, dict):
        if node.get("WFSerializationType") == "WFTextTokenString":
            v = node.get("Value", {})
            s = v.get("string", "")
            for rng in v.get("attachmentsByRange", {}):
                try:
                    off = int(rng.strip("{}").split(",")[0])
                except ValueError:
                    A.violations.append("bad range key %r at %s" % (rng, path))
                    continue
                idx = u16_to_py(s).get(off)
                if idx is None or s[idx] != OBJ:
                    A.violations.append(
                        "offset %d does not land on U+FFFC at %s" % (off, path))
        for k, x in node.items():
            check_offsets(x, A, path + "." + str(k))
    elif isinstance(node, list):
        for i, x in enumerate(node):
            check_offsets(x, A, path + "[%d]" % i)


# ---------------------------------------------------------------- listing

def render_token(tok, owner):
    t = tok.get("Type")
    if t == "Variable":
        return "$" + tok.get("VariableName", "?")
    if t == "ActionOutput":
        who = owner.get(tok.get("OutputUUID"), "?")
        short = who.rsplit(".", 1)[-1]
        return "@%s" % short
    return "<%s>" % t


def render_value(v, owner):
    if isinstance(v, dict):
        st = v.get("WFSerializationType")
        if st == "WFTextTokenString":
            val = v["Value"]
            s = val.get("string", "")
            at = val.get("attachmentsByRange", {})
            byoff = {int(k.strip("{}").split(",")[0]): t for k, t in at.items()}
            out, n = [], 0
            for ch in s:
                if ch == OBJ:
                    out.append("{%s}" % render_token(byoff.get(n, {}), owner))
                else:
                    out.append(ch)
                n += 2 if ord(ch) > 0xFFFF else 1
            return '"%s"' % "".join(out).replace("\n", "\\n")
        if st == "WFTextTokenAttachment":
            return render_token(v.get("Value", {}), owner)
        if st == "WFDictionaryFieldValue":
            items = v["Value"].get("WFDictionaryFieldValueItems", [])
            return "{dict: %d item(s)}" % len(items)
        if set(v) == {"Type", "Variable"}:
            return render_value(v["Variable"], owner)
    if isinstance(v, str):
        return '"%s"' % (v if len(v) < 40 else v[:37] + "...")
    return repr(v)


def listing(acts, owner):
    lines, ind = [], 0
    for i, a in enumerate(acts):
        ident = a["WFWorkflowActionIdentifier"]
        p = dict(a["WFWorkflowActionParameters"])
        short = ident.rsplit(".", 1)[-1] if ident.startswith("is.workflow") \
            else ident
        cf = p.pop("WFControlFlowMode", None)
        p.pop("UUID", None)
        p.pop("GroupingIdentifier", None)
        if cf in (CF_ELSE, CF_CLOSE):
            ind = max(0, ind - 1)
        args = ", ".join("%s=%s" % (k, render_value(v, owner))
                         for k, v in sorted(p.items()))
        if cf == CF_ELSE:
            # for a conditional this is Otherwise; for a menu it starts a case
            label = "} else {" if "conditional" in ident else "} case:"
            lines.append("%4d  %s%s%s" % (
                i, "    " * ind, label, (" " + args) if args else ""))
        else:
            tag = {CF_OPEN: " {", CF_CLOSE: "}"}.get(cf, "")
            lines.append("%4d  %s%s%s%s" % (
                i, "    " * ind, short if cf != CF_CLOSE else "end " + short,
                (" " + args) if args else "", tag))
        if cf in (CF_OPEN, CF_ELSE):
            ind += 1
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plist")
    ap.add_argument("--json")
    ap.add_argument("--known")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(args.plist, "rb") as f:
        raw = f.read()
    pl = plistlib.loads(raw)
    acts = pl["WFWorkflowActions"]

    A = Analysis()
    if b"\xc3\xaf\xc2\xbf\xc2\xbc" in raw or "\u00ef\u00bf\u00bc" in \
            raw.decode("utf-8", "replace"):
        A.violations.append(
            "file contains mojibake (U+FFFC decoded as Latin-1) -- "
            "constructs from it would be wrong; do not harvest")
    analyse(acts, A)
    check_offsets(acts, A)

    if not args.quiet:
        print("=" * 70)
        print("LISTING  (%d actions)" % len(acts))
        print("=" * 70)
        print(listing(acts, A.uuid_owner))

    print()
    print("=" * 70)
    print("CONSTRUCTS")
    print("=" * 70)
    for ident, rec in sorted(A.actions.items()):
        print("\n%s   x%d" % (ident, rec["count"]))
        if rec["output_names"]:
            print("   output -> %s" % ", ".join(sorted(rec["output_names"])))
        for k, shapes in sorted(rec["params"].items()):
            if k in ("UUID", "GroupingIdentifier"):
                continue
            print("   %-24s %s" % (k, " | ".join(sorted(shapes))))

    print("\nENUM VALUES OBSERVED")
    for k, vals in sorted(A.enums.items()):
        print("   %-26s %s" % (k, sorted(vals)))
    print("\ntoken types    :", ", ".join(sorted(A.token_types)) or "-")
    print("aggrandizements:", ", ".join(sorted(A.aggrandizements)) or "-")

    print("\n" + "=" * 70)
    print("REPEAT-DEPTH AUDIT")
    print("=" * 70)
    if A.depth_findings:
        seen = defaultdict(set)
        for _, name, ref, cur in A.depth_findings:
            seen[ref].add(cur)
        for ref in sorted(seen):
            print("   suffix %-4s referenced at repeat depth(s) %s"
                  % (ref, sorted(seen[ref])))
        print("   rule: suffix N is addressable at depth >= N "
              "(depth 1 == bare name)")
    else:
        print("   no repeat variables in this shortcut")

    if A.violations:
        print("\n!! VIOLATIONS")
        for v in A.violations:
            print("   " + v)
    else:
        print("\n   no violations")

    if args.known:
        with open(args.known) as f:
            known = json.load(f)
        new_a = sorted(set(A.actions) - set(known.get("actions", {})))
        print("\n" + "=" * 70)
        print("NEW SINCE %s" % args.known)
        print("=" * 70)
        print("   new actions: %s" % (", ".join(new_a) or "none"))
        for ident, rec in sorted(A.actions.items()):
            kp = set(known.get("actions", {}).get(ident, {})
                     .get("params", {}))
            np_ = set(rec["params"]) - kp - {"UUID", "GroupingIdentifier"}
            if np_ and ident in known.get("actions", {}):
                print("   %s: new params %s" % (ident, sorted(np_)))
        for k, vals in sorted(A.enums.items()):
            kv = set(known.get("enums", {}).get(k, []))
            nv = set(vals) - kv
            if nv:
                print("   %s: new values %s" % (k, sorted(nv)))

    if args.json:
        with open(args.json, "w") as f:
            json.dump(A.to_json(), f, indent=2)
        print("\nwrote %s" % args.json)

    return 1 if A.violations else 0


if __name__ == "__main__":
    sys.exit(main())
