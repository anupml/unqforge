#!/usr/bin/env python3
"""
Turn a .plist / .wflow shortcut into runnable sclib Python.

The listing that decompile.py prints is for reading. This emits code:
run it and you get the shortcut back. That makes the corpus a test suite
(regenerate, compare) and makes any downloaded shortcut editable.

Rule: correctness beats prettiness. Anything that can't be expressed with
a helper falls back to a literal dict, so the round trip stays exact.

Usage:
  python3 topython.py shortcut.plist            # print
  python3 topython.py shortcut.plist -o out.py  # write
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_sys.argv = [_sys.argv[0]] + [_os.path.abspath(a) if _os.path.exists(a) else a
                              for a in _sys.argv[1:]]
_os.chdir(_ROOT)

import argparse, plistlib, re, sys

OBJ = "\ufffc"
SIMPLE = (str, int, float, bool, type(None))


def u16_iter(s):
    """Yield (utf16_offset, char) -- Shortcuts counts offsets in UTF-16."""
    u = 0
    for ch in s:
        yield u, ch
        u += 2 if ord(ch) > 0xFFFF else 1


class Gen:
    def __init__(self, acts):
        self.acts = acts
        self.names = {}       # UUID -> python variable name
        self.made = {}        # UUID -> index of the action producing it
        self.cur = -1         # index being rendered
        self.outname = {}     # UUID -> OutputName as referenced
        self.used = set()

    # ---------- discovery ----------
    def scan(self):
        """Find which UUIDs are referenced, and under what name."""
        def walk(n):
            if isinstance(n, dict):
                if n.get("Type") == "ActionOutput" and n.get("OutputUUID"):
                    self.used.add(n["OutputUUID"])
                    if n.get("OutputName"):
                        self.outname[n["OutputUUID"]] = n["OutputName"]
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)
        for a in self.acts:
            walk(a["WFWorkflowActionParameters"])

        for i, a in enumerate(self.acts):
            u = a["WFWorkflowActionParameters"].get("UUID")
            if u and u in self.used:
                short = a["WFWorkflowActionIdentifier"].rsplit(".", 1)[-1]
                short = re.sub(r"[^a-z0-9]", "", short.lower())[:14] or "act"
                self.names[u] = "%s%d" % (short, i)
                self.made[u] = i

    # ---------- value rendering ----------
    def tok(self, t):
        """A single variable/output token."""
        if not isinstance(t, dict):
            return repr(t)
        extra = set(t) - {"Type", "VariableName", "OutputUUID", "OutputName"}
        if extra:
            return repr(t)                       # aggrandizements etc.
        ty = t.get("Type")
        if ty == "Variable":
            return "var(%r)" % t.get("VariableName")
        if ty == "ActionOutput":
            u = t.get("OutputUUID")
            # A reference can precede its producer -- legal inside a loop,
            # since the value exists from the second iteration on. Python
            # has no such grace, so fall back to an explicit token.
            if u in self.names and self.made.get(u, 1 << 30) < self.cur:
                return self.names[u]
            return "out(%r, %r)" % (u, t.get("OutputName"))
        return repr(t)

    def token_string(self, v):
        """WFTextTokenString -> ts(...) with the literal text split apart."""
        val = v.get("Value", {})
        s = val.get("string", "")
        at = val.get("attachmentsByRange", {})
        byoff = {}
        for k, t in at.items():
            try:
                byoff[int(k.strip("{}").split(",")[0])] = t
            except ValueError:
                return repr(v)
        parts, buf = [], ""
        for u, ch in u16_iter(s):
            if ch == OBJ and u in byoff:
                if buf:
                    parts.append(repr(buf))
                    buf = ""
                parts.append(self.tok(byoff[u]))
            else:
                buf += ch
        if buf:
            parts.append(repr(buf))
        if not parts:
            return "ts('')"
        return "ts(%s)" % ", ".join(parts)

    def value(self, v):
        if isinstance(v, dict):
            st = v.get("WFSerializationType")
            if st == "WFTextTokenString":
                return self.token_string(v)
            if st == "WFTextTokenAttachment":
                inner = v.get("Value", {})
                r = self.tok(inner)
                return "att(%s)" % r if not r.startswith("{") else repr(v)
        if isinstance(v, SIMPLE):
            return repr(v)
        return repr(v)

    # ---------- emit ----------
    def run(self, meta):
        self.scan()
        L = ["from unqforge import *", "", "s = SC()"]

        drop = {"WFWorkflowActions", "WFQuickActionSurfaces",
                "WFWorkflowClientVersion", "WFWorkflowHasOutputFallback",
                "WFWorkflowHasShortcutInputVariables", "WFWorkflowIcon",
                "WFWorkflowImportQuestions", "WFWorkflowInputContentItemClasses",
                "WFWorkflowMinimumClientVersion",
                "WFWorkflowMinimumClientVersionString",
                "WFWorkflowOutputContentItemClasses", "WFWorkflowTypes"}
        keep = {k: v for k, v in meta.items() if k != "WFWorkflowActions"}
        if keep:
            L += ["", "s.meta = " + fmt_dict(keep, 0)]
        L.append("")

        depth = 0
        for i, a in enumerate(self.acts):
            self.cur = i
            ident = a["WFWorkflowActionIdentifier"]
            p = dict(a["WFWorkflowActionParameters"])
            uuid = p.pop("UUID", None)
            cf = p.get("WFControlFlowMode")

            if cf in (1, 2):
                depth = max(0, depth - 1)
            pad = "  " * depth
            body = ",\n    ".join("%r: %s" % (k, self.value(v))
                                  for k, v in sorted(p.items()))
            args = "{\n    %s,\n}" % body if body else "{}"

            lhs = ""
            kw = ""
            if uuid and uuid in self.names:
                lhs = "%s = " % self.names[uuid]
                kw = ", uuid=%r, output=%r" % (uuid, self.outname.get(uuid))
            elif uuid:
                kw = ", uuid=%r" % uuid

            L.append("# %s%d %s" % (pad, i, ident.rsplit(".", 1)[-1]))
            L.append("%ss.raw(%r, %s%s)" % (lhs, ident, args, kw))
            L.append("")
            if cf in (0, 1):
                depth += 1

        L += ["import sys",
              "s.dump(sys.argv[1] if len(sys.argv) > 1 else 'regenerated.plist')",
              "print('%d actions' % len(s.acts))"]
        return "\n".join(L)


def fmt_dict(d, indent):
    pad = " " * (indent + 4)
    items = ",\n".join("%s%r: %r" % (pad, k, v) for k, v in sorted(d.items()))
    return "{\n%s,\n%s}" % (items, " " * indent)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plist")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    pl = plistlib.load(open(args.plist, "rb"))
    code = Gen(pl["WFWorkflowActions"]).run(pl)
    if args.out:
        open(args.out, "w").write(code + "\n")
        print("wrote %s (%d actions)" % (args.out, len(pl["WFWorkflowActions"])))
    else:
        print(code)


if __name__ == "__main__":
    main()
