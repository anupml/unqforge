#!/usr/bin/env python3
"""
sclib — generate iOS Shortcuts plists from Python.

Design rule: the library refuses to emit any action identifier, parameter
key, or serialization shape that has not been observed on a real device.
Evidence lives in constructs/*.json, produced by decompile.py.

Filename convention encodes provenance:
    *.native.json   Shortcuts itself wrote this shape (strongest)
    *.ranok.json    we generated it and it executed correctly

Set IF_COUNTS_DEPTH once the probe answers whether a conditional block
increments the Repeat Item suffix. Currently assumed False.
"""
import glob, json, os, plistlib, uuid
from decimal import Decimal
from contextlib import contextmanager

OBJ = "\ufffc"

def u16_len(s):
    """UTF-16 code units in s. Shortcuts counts offsets in these, not in
    Python code points. Emoji and mathematical alphanumerics are non-BMP
    and take two units each."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)

IF_COUNTS_DEPTH = False        # VERIFIED: Repeat>If>Repeat gives 'Repeat Index 2'
SKIP = {"UUID", "GroupingIdentifier"}

# WFCondition values, read off a native export where each operator was
# picked from the Shortcuts UI in a known order.
def num(v):
    """Render a number in plain decimal. str(1e-9) gives '1e-09', and
    nothing in evidence says Shortcuts parses exponent notation."""
    if isinstance(v, float):
        return format(Decimal(repr(v)), "f")
    return str(v)


COND = {"<": 0, "<=": 1, ">": 2, ">=": 3, "==": 4, "!=": 5, "between": 1003}


# ------------------------------------------------------------- evidence

class Constructs:
    def __init__(self, folder="constructs"):
        self.params = {}       # ident -> {param: set(shapes)}
        self.outputs = {}      # ident -> set(canonical output names)
        self.provenance = {}   # ident -> set(sources)
        self.enums = {}
        for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
            src = os.path.basename(path).split(".")[-2]
            d = json.load(open(path))
            for ident, rec in d.get("actions", {}).items():
                slot = self.params.setdefault(ident, {})
                for p, shapes in rec["params"].items():
                    slot.setdefault(p, set()).update(shapes)
                self.outputs.setdefault(ident, set()).update(
                    rec.get("output_names", []))
                self.provenance.setdefault(ident, set()).add(src)
            for k, vals in d.get("enums", {}).items():
                self.enums.setdefault(k, set()).update(vals)
        if not self.params:
            raise RuntimeError("no constructs found in %s/" % folder)

    def check(self, ident, params):
        if ident not in self.params:
            raise Unverified("action %r never observed on device" % ident)
        known = self.params[ident]
        for k, v in params.items():
            if k in SKIP:
                continue
            if k not in known:
                raise Unverified("%s: parameter %r never observed "
                                 "(known: %s)" % (ident, k, sorted(known)))
            sh = shape_of(v)
            if sh not in known[k]:
                raise Unverified("%s.%s: shape %r never observed "
                                 "(known: %s)" % (ident, k, sh,
                                                  sorted(known[k])))

    def output_name_for(self, ident):
        """Canonical OutputName for an action, or None if never observed.

        Several names can show up for one action across iOS versions
        (choosefromlist yields both 'Chosen Item' and 'Selected Item').
        OutputUUID does the actual linking, so any observed name works;
        pick deterministically and let the caller override.
        """
        names = sorted(self.outputs.get(ident, ()))
        return names[0] if names else None

    def find(self, *words):
        """Action identifiers containing all the given substrings."""
        return sorted(i for i in self.params
                      if all(w.lower() in i.lower() for w in words))

    def describe(self, ident):
        if ident not in self.params:
            near = self.find(ident.rsplit(".", 1)[-1])
            raise Unverified("%r not in evidence%s" % (
                ident, ("; did you mean %s?" % near) if near else ""))
        out = ["%s   [%s]" % (ident, ",".join(sorted(self.provenance[ident])))]
        name = self.output_name_for(ident)
        out.append("   output -> %s" % (name or "(none observed)"))
        for k, shapes in sorted(self.params[ident].items()):
            if k not in SKIP:
                out.append("   %-28s %s" % (k, " | ".join(sorted(shapes))))
        return "\n".join(out)

    def report(self):
        out = []
        for ident in sorted(self.params):
            out.append("  %-46s %s" % (
                ident, ",".join(sorted(self.provenance[ident]))))
        return "\n".join(out)


class Unverified(Exception):
    pass


def shape_of(v):
    if isinstance(v, dict):
        st = v.get("WFSerializationType")
        if st:
            return st
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


# ------------------------------------------------------------- tokens

def U():
    return str(uuid.uuid4()).upper()


def var(n):
    return {"Type": "Variable", "VariableName": n}


def out(u, name):
    return {"Type": "ActionOutput", "OutputUUID": u, "OutputName": name}


def att(tok):
    return {"Value": tok, "WFSerializationType": "WFTextTokenAttachment"}


def ts(*parts):
    """WFTextTokenString with offsets computed, never typed by hand.

    Offsets are UTF-16 code units, which is NOT the same as Python string
    index once any non-BMP character (emoji, mathematical alphanumerics)
    appears in the literal text.
    """
    s, at, u16 = "", {}, 0
    for p in parts:
        if isinstance(p, str):
            s += p
            u16 += u16_len(p)
        else:
            at["{%d, 1}" % u16] = p
            s += OBJ
            u16 += 1
    v = {"string": s}
    if at:
        v["attachmentsByRange"] = at
    return {"Value": v, "WFSerializationType": "WFTextTokenString"}


# ------------------------------------------------------- expressions

PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "**": 3}


class Expr:
    """Builds Calculate Expression strings with correct parenthesisation."""

    def __init__(self, parts, prec=9):
        self.parts, self.prec = parts, prec

    @staticmethod
    def wrap(x):
        if isinstance(x, Expr):
            return x
        if isinstance(x, (int, float)):
            return Expr([num(x)])
        return Expr([x])          # a token dict

    def _paren(self, need):
        if self.prec >= need:
            return self.parts
        return ["("] + self.parts + [")"]

    def _bin(self, other, op, rightassoc=False):
        o = Expr.wrap(other)
        p = PREC[op]
        left = self._paren(p)
        right = o._paren(p + (0 if rightassoc else 1))
        return Expr(left + [" %s " % op] + right, p)

    def __add__(self, o):
        return self._bin(o, "+")

    def __sub__(self, o):
        return self._bin(o, "-")

    def __mul__(self, o):
        return self._bin(o, "*")

    def __truediv__(self, o):
        return self._bin(o, "/")

    def __pow__(self, o):
        return self._bin(o, "**", rightassoc=True)

    def __radd__(self, o):
        return Expr.wrap(o) + self

    def __rsub__(self, o):
        return Expr.wrap(o) - self

    def __rmul__(self, o):
        return Expr.wrap(o) * self

    def __rtruediv__(self, o):
        return Expr.wrap(o) / self


def E(x):
    return Expr.wrap(x)


# --------------------------------------------------------- loop scope

class Loop:
    """Resolves Repeat Item / Repeat Index for the depth it was opened at."""

    def __init__(self, depth):
        self.depth = depth

    def _n(self, base):
        return var(base if self.depth == 1 else "%s %d" % (base, self.depth))

    @property
    def item(self):
        return self._n("Repeat Item")

    @property
    def index(self):
        return self._n("Repeat Index")


# ------------------------------------------------------------- builder

class SC:
    def __init__(self, constructs=None):
        self.acts = []
        self.k = constructs or Constructs()
        self.depth = 0
        self.meta = {}          # overrides for top-level plist keys

    def _add(self, ident, params):
        self.k.check(ident, params)
        self.acts.append({"WFWorkflowActionIdentifier": ident,
                          "WFWorkflowActionParameters": params})

    def action(self, ident, output_name=None, **params):
        """Emit any harvested action.

        Every identifier, parameter key and serialization shape is checked
        against constructs/, so an action learned from a decompiled shortcut
        is usable immediately with no wrapper written for it.

        Returns the action's output token, or None when the action has no
        observed output (Set Variable, Alert, Exit).
        """
        name = output_name or self.k.output_name_for(ident)
        if name is None:
            self._add(ident, params)
            return None
        u = U()
        params["UUID"] = u
        self._add(ident, params)
        return out(u, name)

    def raw(self, ident, params, uuid=None, output=None):
        """Emit an action with exactly these parameters.

        Unlike action(), nothing is inferred: the UUID is supplied by the
        caller and no output name is looked up. This is what decompiled
        code uses, so a regenerated plist matches the original.
        """
        p = dict(params)
        if uuid:
            p["UUID"] = uuid
        self._add(ident, p)
        return out(uuid, output) if (uuid and output) else None

    # --- leaves ---
    def text(self, t):
        u = U()
        self._add("is.workflow.actions.gettext",
                  {"UUID": u, "WFTextActionText": t})
        return out(u, "Text")

    def setvar(self, name, tok):
        self._add("is.workflow.actions.setvariable",
                  {"WFVariableName": name, "WFInput": att(tok)})

    def calc(self, expr):
        u = U()
        parts = expr.parts if isinstance(expr, Expr) else list(expr)
        self._add("is.workflow.actions.calculateexpression",
                  {"UUID": u, "Input": ts(*parts)})
        return out(u, "Calculation Result")

    def split(self, tok, sep):
        u = U()
        self._add("is.workflow.actions.text.split",
                  {"UUID": u, "text": ts(tok), "WFTextSeparator": "Custom",
                   "WFTextCustomSeparator": sep})
        return out(u, "Split Text")

    def emptydict(self):
        u = U()
        self._add("is.workflow.actions.dictionary",
                  {"UUID": u, "WFItems": {
                      "Value": {"WFDictionaryFieldValueItems": []},
                      "WFSerializationType": "WFDictionaryFieldValue"}})
        return out(u, "Dictionary")

    def getval(self, dname, key):
        u = U()
        self._add("is.workflow.actions.getvalueforkey",
                  {"UUID": u, "WFInput": att(var(dname)),
                   "WFDictionaryKey": ts(*key)})
        return out(u, "Dictionary Value")

    def setval(self, dname, key, value):
        u = U()
        p = {"UUID": u, "WFDictionary": att(var(dname)),
             "WFDictionaryKey": ts(*key),
             "WFDictionaryValue": value if isinstance(value, str)
             else ts(*value)}
        self._add("is.workflow.actions.setvalueforkey", p)
        return out(u, "Dictionary")

    def show(self, *parts):
        self._add("is.workflow.actions.showresult", {"Text": ts(*parts)})

    # --- control flow as context managers ---
    @contextmanager
    def repeat(self, count):
        g = U()
        p = {"GroupingIdentifier": g, "WFControlFlowMode": 0,
             "WFRepeatCount": (float(count)
                               if isinstance(count, (int, float))
                               else att(count))}
        self._add("is.workflow.actions.repeat.count", p)
        self.depth += 1
        try:
            yield Loop(self.depth)
        finally:
            self.depth -= 1
            self._add("is.workflow.actions.repeat.count",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2})

    @contextmanager
    def foreach(self, tok):
        g = U()
        self._add("is.workflow.actions.repeat.each",
                  {"GroupingIdentifier": g, "WFControlFlowMode": 0,
                   "WFInput": att(tok)})
        self.depth += 1
        try:
            yield Loop(self.depth)
        finally:
            self.depth -= 1
            self._add("is.workflow.actions.repeat.each",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2})

    @contextmanager
    def if_(self, tok, op, value, upper=None):
        """If <tok> <op> <value>.  op is one of COND's keys.
        'between' additionally needs upper."""
        if op not in COND:
            raise Unverified("unknown operator %r" % op)
        code = COND[op]
        if code not in self.k.enums.get("WFCondition", set()):
            raise Unverified("WFCondition %d (%r) not in evidence" % (code, op))
        g = U()
        coerced = dict(tok)
        coerced["Aggrandizements"] = [{
            "CoercionItemClass": "WFNumberContentItem",
            "Type": "WFCoercionVariableAggrandizement"}]
        p = {"GroupingIdentifier": g, "WFCondition": code,
             "WFControlFlowMode": 0,
             "WFInput": {"Type": "Variable", "Variable": {
                 "Value": coerced,
                 "WFSerializationType": "WFTextTokenAttachment"}},
             "WFNumberValue": num(value)}
        if op == "between":
            if upper is None:
                raise ValueError("'between' needs upper")
            p["WFAnotherNumber"] = num(upper)
        self._add("is.workflow.actions.conditional", p)
        if IF_COUNTS_DEPTH:
            self.depth += 1
        try:
            yield _Else(self, g)
        finally:
            if IF_COUNTS_DEPTH:
                self.depth -= 1
            self._add("is.workflow.actions.conditional",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2})

    def if_gt(self, tok, number):
        return self.if_(tok, ">", number)

    def plist(self):
        pl = {
            "WFQuickActionSurfaces": [],
            "WFWorkflowActions": self.acts,
            "WFWorkflowClientVersion": "3607.0.2",
            "WFWorkflowHasOutputFallback": False,
            "WFWorkflowHasShortcutInputVariables": False,
            "WFWorkflowIcon": {"WFWorkflowIconGlyphNumber": 61440,
                               "WFWorkflowIconStartColor": -23508481},
            "WFWorkflowImportQuestions": [],
            "WFWorkflowInputContentItemClasses": [],
            "WFWorkflowMinimumClientVersion": 900,
            "WFWorkflowMinimumClientVersionString": "900",
            "WFWorkflowOutputContentItemClasses": [],
            "WFWorkflowTypes": [],
        }
        pl.update(self.meta)
        pl["WFWorkflowActions"] = self.acts
        return pl

    def dump(self, path):
        return write_plist(self.plist(), path)


class _Else:
    def __init__(self, sc, g):
        self.sc, self.g = sc, g

    def otherwise(self):
        self.sc._add("is.workflow.actions.conditional",
                     {"GroupingIdentifier": self.g, "WFControlFlowMode": 1})


def write_plist(pl, path):
    """Emit pure-ASCII XML.

    plistlib writes U+FFFC as raw UTF-8 bytes (EF BF BC). That is valid,
    but any step in the chain that guesses Latin-1 turns it into the
    three characters 'i-bf-quarter' and every math field breaks.
    Shortcuts' own exports use the &#xFFFC; entity, which is ASCII and
    cannot be mangled. Match that, escape anything else non-ASCII too,
    then prove the file parses back to what we built.
    """
    # plistlib rewrites CR to LF while serialising, and XML parsers
    # normalise CR again on the way back in, so a carriage return cannot
    # survive as a literal in either direction. Classic AppleScript uses CR
    # as its line ending, so losing it silently rewrites scripts. Swap CR
    # for a private-use sentinel before dumping, then emit it as a
    # character reference, which parsers must NOT normalise.
    shielded, n_cr = _shield_cr(pl)
    txt = plistlib.dumps(shielded, sort_keys=True).decode("utf-8")
    txt = txt.replace(OBJ, "&#xFFFC;")
    txt = txt.replace(CR_SENTINEL, "&#xD;")
    data = txt.encode("ascii", "xmlcharrefreplace")

    assert all(c < 128 for c in data), "non-ASCII survived"
    back = plistlib.loads(data)
    if back != pl:
        raise AssertionError("emitted file differs from what we built: %s"
                             % _where(pl, back))
    n = sum(1 for a in back["WFWorkflowActions"]
            for _ in [0] if _check_obj(a))
    with open(path, "wb") as f:
        f.write(data)
    return data


CR_SENTINEL = "\ue000"          # private use area, never in real content


def _shield_cr(node, count=None):
    """Replace CR with a sentinel so plistlib cannot eat it."""
    top = count is None
    if top:
        count = [0]
    if isinstance(node, dict):
        out_ = {k: _shield_cr(v, count)[0] for k, v in node.items()}
    elif isinstance(node, list):
        out_ = [_shield_cr(v, count)[0] for v in node]
    elif isinstance(node, str):
        if CR_SENTINEL in node:
            raise ValueError("content already contains the CR sentinel")
        if "\r" in node:
            count[0] += node.count("\r")
            out_ = node.replace("\r", CR_SENTINEL)
        else:
            out_ = node
    else:
        out_ = node
    return (out_, count[0]) if top else (out_, 0)


def _unshield_cr(node):
    if isinstance(node, dict):
        return {k: _unshield_cr(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_unshield_cr(v) for v in node]
    if isinstance(node, str):
        return node.replace(CR_SENTINEL, "\r")
    return node


def _where(a, b, path="plist"):
    """First point where two plist structures differ, for error messages."""
    if type(a) is not type(b):
        return "%s: %s vs %s" % (path, type(a).__name__, type(b).__name__)
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return "%s: key %r on one side only" % (path, k)
            w = _where(a[k], b[k], "%s.%s" % (path, k))
            if w:
                return w
        return ""
    if isinstance(a, list):
        if len(a) != len(b):
            return "%s: length %d vs %d" % (path, len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            w = _where(x, y, "%s[%d]" % (path, i))
            if w:
                return w
        return ""
    return "" if a == b else "%s: %r != %r" % (path, str(a)[:60], str(b)[:60])


def _check_obj(node):
    """Confirm attachment offsets still land on U+FFFC after round-trip."""
    if isinstance(node, dict):
        if node.get("WFSerializationType") == "WFTextTokenString":
            v = node["Value"]
            s = v.get("string", "")
            m, u = {}, 0
            for i, ch in enumerate(s):
                m[u] = i
                u += 2 if ord(ch) > 0xFFFF else 1
            for rng in v.get("attachmentsByRange", {}):
                off = int(rng.strip("{}").split(",")[0])
                idx = m.get(off)
                assert idx is not None and s[idx] == OBJ, \
                    "offset %d lost its OBJ char" % off
        return any(_check_obj(x) for x in node.values())
    if isinstance(node, list):
        return any(_check_obj(x) for x in node)
    return False
