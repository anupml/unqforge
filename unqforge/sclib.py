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

BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "constructs")


class Constructs:
    """The evidence database.

    Loads the constructs shipped with the package, then anything in a
    local constructs/ directory on top -- so an installed copy works out
    of the box, and decompiling a shortcut in your own project extends it
    without touching the install.
    """

    def __init__(self, folder=None):
        if folder is not None:
            sources = [folder]
        else:
            sources = [BUNDLED]
            if os.path.isdir("constructs"):
                sources.append("constructs")
        self.params = {}       # ident -> {param: set(shapes)}
        self.outputs = {}      # ident -> set(canonical output names)
        self.provenance = {}   # ident -> set(sources)
        self.enums = {}
        self.token_types = set()   # legal Type values inside an attachment
        seen_any = False
        for d_ in sources:
          for path in sorted(glob.glob(os.path.join(d_, "*.json"))):
            seen_any = True
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
            self.token_types.update(d.get("token_types", ()))
        if not self.token_types:
            # constructs files written before harvestdb recorded the key
            self.token_types = set(TOKEN_TYPES)
        if not self.params:
            raise RuntimeError("no constructs found in %s" % ", ".join(sources))

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
            errs = check_tokens(v, self.token_types, "%s.%s" % (ident, k))
            if errs:
                raise Unverified(errs[0])

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


TOKEN_TYPES = {"Variable", "ActionOutput", "Ask", "Clipboard",
               "CurrentDate", "ExtensionInput", "DeviceDetails",
               "ShortcutInput"}


def _is_bare_token(v):
    """A raw token dict that hasn't been wrapped for a slot yet.

    Excludes the conditional's {Type, Variable} wrapper, which has the
    same Type key but is already a complete serialization.
    """
    return (isinstance(v, dict)
            and "WFSerializationType" not in v
            and v.get("Type") in TOKEN_TYPES
            and set(v) != {"Type", "Variable"})


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


def check_tokens(v, token_types, path):
    """Verify every token slot holds a real token.

    shape_of() reports the serialization envelope and stops there, so an
    attachment wrapping the integer 0 comes back as
    "WFTextTokenAttachment" and validates clean against the corpus. On
    device that variable is nil and every later arithmetic reading it is
    garbage. Round-trip cannot catch this: the decoder reads the bad
    shape back the same way it was written, so encoder and decoder agree
    with each other while both disagree with Shortcuts.

    Returns a list of messages; empty means nothing wrong.
    """
    errs = []

    def walk(node, p):
        if isinstance(node, dict):
            st = node.get("WFSerializationType")
            if st == "WFTextTokenAttachment":
                inner = node.get("Value")
                if not isinstance(inner, dict):
                    errs.append(
                        "%s: attachment wraps the literal %r. Every token "
                        "slot needs a variable or an action output -- put a "
                        "Text action in front" % (p, inner))
                elif inner.get("Type") not in token_types:
                    errs.append("%s: token Type %r never observed "
                                "(evidence: %s)"
                                % (p, inner.get("Type"),
                                   ", ".join(sorted(token_types))))
                else:
                    # A legal Type is not enough. var() given a token
                    # instead of a name yields VariableName holding a
                    # dict, which is the right shape around the wrong
                    # content -- exactly what the Type check misses.
                    t = inner.get("Type")
                    if t == "Variable" and \
                            not isinstance(inner.get("VariableName"), str):
                        errs.append(
                            "%s: Variable token has VariableName %r, not a "
                            "string -- var() was given a token instead of a "
                            "name" % (p, inner.get("VariableName")))
                    elif t == "ActionOutput" and \
                            not isinstance(inner.get("OutputUUID"), str):
                        errs.append(
                            "%s: ActionOutput token has OutputUUID %r, not "
                            "a string" % (p, inner.get("OutputUUID")))
                return
            if st == "WFTextTokenString":
                val = node.get("Value")
                if isinstance(val, dict):
                    ranges = val.get("attachmentsByRange") or {}
                    for rng, tok in ranges.items():
                        if not isinstance(tok, dict):
                            errs.append("%s: attachment at %s is the literal "
                                        "%r" % (p, rng, tok))
                        elif tok.get("Type") not in token_types:
                            errs.append("%s: attachment at %s has Type %r, "
                                        "never observed"
                                        % (p, rng, tok.get("Type")))
                return
            for k, x in node.items():
                walk(x, "%s.%s" % (p, k))
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk(x, "%s[%d]" % (p, i))

    walk(v, path)
    return errs


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
        elif isinstance(p, dict) and \
                p.get("WFSerializationType") == "WFTextTokenString":
            # Already a token string. Splice its text in and shift its
            # attachment offsets, so ts() composes instead of nesting a
            # serialization dict where a token belongs.
            v = p.get("Value", {})
            inner = v.get("string", "")
            for rng, tok in v.get("attachmentsByRange", {}).items():
                at["{%d, 1}" % (u16 + int(rng.strip("{}").split(",")[0]))] = tok
            s += inner
            u16 += u16_len(inner)
        else:
            if isinstance(p, dict) and \
                    p.get("WFSerializationType") == "WFTextTokenAttachment":
                p = p["Value"]          # unwrap a content-slot token
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


def _parts(x):
    """Normalise a callback result into a list of ts() parts."""
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    return [x]


# --------------------------------------------------------- loop scope

class Loop:
    """Resolves Repeat Item / Repeat Index for the depth it was opened at."""

    def __init__(self, depth, close_uuid=None):
        self.depth = depth
        self.close_uuid = close_uuid

    @property
    def results(self):
        """The loop's own output: every iteration's result, collected.

        Shortcuts attaches this to the CLOSING action of the block, which
        is why the close carries the UUID rather than the open.
        """
        return out(self.close_uuid, "Repeat Results")

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

    def _autowrap(self, ident, params):
        """Wrap bare values into whichever shape the evidence expects.

        The database already records that WFInput on Set Variable takes a
        WFTextTokenAttachment and that Input on Calculate Expression takes
        a WFTextTokenString. There is no reason to make the caller repeat
        it. Wrapping is derived from what was observed, never guessed, and
        an ambiguous slot is reported rather than resolved.
        """
        known = self.k.params.get(ident)
        if not known:
            return params
        for key, v in list(params.items()):
            if key in SKIP:
                continue
            shapes = known.get(key)
            if not shapes:
                continue
            if _is_bare_token(v):
                a = "WFTextTokenAttachment" in shapes
                t = "WFTextTokenString" in shapes
                if a and t:
                    raise Unverified(
                        "%s.%s accepts both attachment and token string; "
                        "wrap it yourself with att(...) or ts(...)"
                        % (ident, key))
                if a:
                    params[key] = att(v)
                elif t:
                    params[key] = ts(v)
            elif isinstance(v, str) and "str" not in shapes \
                    and "WFTextTokenString" in shapes:
                params[key] = ts(v)
        return params

    def _add(self, ident, params):
        params = self._autowrap(ident, params)
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

    def _token(self, v):
        """Coerce v into something that can legally sit inside att().

        Shortcuts' UI has no literal field on Set Variable, which is why
        all 1798 in the corpus take a token: a literal always arrives via
        a Text action. So emit that action rather than wrapping the raw
        value, which produces an attachment with nothing inside it and a
        nil variable on device.
        """
        if _is_bare_token(v):
            return v
        if isinstance(v, dict):
            st = v.get("WFSerializationType")
            if st == "WFTextTokenAttachment":
                return v["Value"]            # already wrapped, unwrap once
            if st == "WFTextTokenString":
                return self.text(v)
            raise Unverified("cannot put shape %r in a token slot"
                             % shape_of(v))
        if isinstance(v, bool):
            raise Unverified(
                "no evidence for how Shortcuts stores a boolean literal in "
                "a variable; pass the text you want instead")
        if isinstance(v, (int, float)):
            return self.text(num(v))
        if isinstance(v, str):
            return self.text(v)
        raise Unverified("cannot put %r in a token slot" % (v,))

    def setvar(self, name, tok):
        """Set a variable from a token, or from a literal via a Text action."""
        self._add("is.workflow.actions.setvariable",
                  {"WFVariableName": name, "WFInput": att(self._token(tok))})

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

    @staticmethod
    def _dictarg(d):
        """The dictionary being read or written: a variable name or a token.

        Every other method on SC takes a token, so requiring a name here
        was a trap. A str is still treated as a variable name, which is
        what existing code passes.
        """
        return var(d) if isinstance(d, str) else d

    @staticmethod
    def _keyparts(key):
        """Normalise into ts() parts.

        ts(*key) on a bare string yields one part per character -- which
        happens to reassemble correctly -- and on a token dict yields its
        KEY NAMES, so a variable key silently became the text
        "TypeVariableName". A str or a token is one part, not a sequence.
        """
        if isinstance(key, (str, dict)):
            return [key]
        if isinstance(key, (int, float)) and not isinstance(key, bool):
            return [num(key)]        # a number is text, not a token
        return list(key)

    def getval(self, dname, key):
        u = U()
        self._add("is.workflow.actions.getvalueforkey",
                  {"UUID": u, "WFInput": att(self._dictarg(dname)),
                   "WFDictionaryKey": ts(*self._keyparts(key))})
        return out(u, "Dictionary Value")

    def setval(self, dname, key, value):
        u = U()
        p = {"UUID": u, "WFDictionary": att(self._dictarg(dname)),
             "WFDictionaryKey": ts(*self._keyparts(key)),
             "WFDictionaryValue": value if isinstance(value, str)
             else ts(*self._keyparts(value))}
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
        close = U()
        try:
            yield Loop(self.depth, close)
        finally:
            self.depth -= 1
            self._add("is.workflow.actions.repeat.count",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2,
                       "UUID": close})

    @contextmanager
    def foreach(self, tok):
        g = U()
        self._add("is.workflow.actions.repeat.each",
                  {"GroupingIdentifier": g, "WFControlFlowMode": 0,
                   "WFInput": att(tok)})
        self.depth += 1
        close = U()
        try:
            yield Loop(self.depth, close)
        finally:
            self.depth -= 1
            self._add("is.workflow.actions.repeat.each",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2,
                       "UUID": close})

    @contextmanager
    def if_(self, tok, op, value, upper=None, text=None):
        """If <tok> <op> <value>.  op is one of COND's keys.
        'between' additionally needs upper.

        Numeric or textual is decided by WHICH FIELD IS WRITTEN, not by
        the condition code: 4 and 5 both appear in the corpus against
        WFNumberValue and against WFConditionalActionString. So a text
        comparison is the same operator with a different right-hand side
        field and no numeric coercion on the input.

        text=True/False forces the path for a bare token, which is
        ambiguous on its own and stays numeric by default.
        """
        if op not in COND:
            raise Unverified("unknown operator %r" % op)
        code = COND[op]
        if code not in self.k.enums.get("WFCondition", set()):
            raise Unverified("WFCondition %d (%r) not in evidence" % (code, op))
        as_text = self._is_textval(value) if text is None else text
        if as_text and op == "between":
            raise Unverified("'between' has only ever been observed numeric")
        g = U()
        p = {"GroupingIdentifier": g, "WFCondition": code,
             "WFControlFlowMode": 0}
        if as_text:
            # No coercion. Several string conditionals in the corpus carry
            # no Aggrandizements at all, and WFNumberContentItem has never
            # been observed on this path -- coercing the input to a number
            # is exactly what made text comparison fail silently.
            p["WFInput"] = {"Type": "Variable", "Variable": att(tok)}
            p["WFConditionalActionString"] = self._cmpstring(value)
        else:
            coerced = dict(tok)
            coerced["Aggrandizements"] = [{
                "CoercionItemClass": "WFNumberContentItem",
                "Type": "WFCoercionVariableAggrandizement"}]
            p["WFInput"] = {"Type": "Variable", "Variable": {
                "Value": coerced,
                "WFSerializationType": "WFTextTokenAttachment"}}
            p["WFNumberValue"] = self._cmpvalue(value)
            if op == "between":
                if upper is None:
                    raise ValueError("'between' needs upper")
                p["WFAnotherNumber"] = self._cmpvalue(upper, "WFAnotherNumber")
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

    def _cmpvalue(self, v, key="WFNumberValue"):
        """Right-hand side of a comparison.

        num() is str() for anything that is not a float, so a token passed
        here used to serialise as the Python repr of a dict --
        "{'Type': 'Variable', 'VariableName': 'max_z'}" written into
        WFNumberValue. shape_of() calls that a str, which is legal, so it
        validated clean and compared against that text on device.

        Comparing against a variable is something Shortcuts supports, so
        honour it if the corpus says WFNumberValue takes a token string,
        and refuse rather than guess if it does not.
        """
        if not isinstance(v, dict):
            return num(v)
        shapes = self.k.params.get("is.workflow.actions.conditional",
                                   {}).get(key, set())
        if "WFTextTokenAttachment" in shapes:
            return att(v)
        raise Unverified(
            "if_ was given a token as the comparison value, but "
            "WFNumberValue has only ever been observed as %s. Decompile a "
            "shortcut that compares against a variable to learn the real "
            "shape before using this." % (sorted(shapes) or "nothing"))

    @staticmethod
    def _is_textval(v):
        """Does this comparison value select the string path?

        A str or a ts(...) is text; a number is numeric. A bare token is
        ambiguous -- it was numeric before this existed, so it stays
        numeric unless the caller passes text=True.
        """
        return isinstance(v, str) or (
            isinstance(v, dict)
            and v.get("WFSerializationType") == "WFTextTokenString")

    def _cmpstring(self, v):
        """Right-hand side of a text comparison.

        Written to WFConditionalActionString, which the corpus records as
        str | WFTextTokenString -- so an interpolated right-hand side
        works natively here, unlike WFNumberValue which needs the value
        wrapped in an attachment.
        """
        shapes = self.k.params.get("is.workflow.actions.conditional",
                                   {}).get("WFConditionalActionString", set())
        if _is_bare_token(v):
            v = ts(v)
        elif isinstance(v, dict) and \
                v.get("WFSerializationType") == "WFTextTokenAttachment":
            v = ts(v["Value"])
        sh = shape_of(v)
        if sh not in shapes:
            raise Unverified(
                "if_: WFConditionalActionString shape %r never observed "
                "(known: %s)" % (sh, sorted(shapes) or "nothing"))
        return v

    def if_gt(self, tok, number):
        return self.if_(tok, ">", number)

    # ------------------------------------------------------------------
    # higher-level patterns
    # ------------------------------------------------------------------
    @contextmanager
    def if_has_value(self, tok):
        """If <tok> has any value.

        WFCondition 100 was inferred from the corpus rather than a
        labelled probe, but a generated shortcut using it behaved
        correctly on device. Emitted with no WFNumberValue, matching the
        shape Shortcuts writes. Yields the block's own output (If
        Result), which is whatever the taken branch produced -- that is
        how you get a value out of a conditional.
        """
        if 100 not in self.k.enums.get("WFCondition", set()):
            raise Unverified("WFCondition 100 not in evidence")
        g, close = U(), U()
        self._add("is.workflow.actions.conditional", {
            "GroupingIdentifier": g, "WFCondition": 100,
            "WFControlFlowMode": 0,
            "WFInput": {"Type": "Variable", "Variable": att(tok)}})
        try:
            yield out(close, "If Result")
        finally:
            self._add("is.workflow.actions.conditional",
                      {"GroupingIdentifier": g, "WFControlFlowMode": 2,
                       "UUID": close})

    def vcard_picker(self, items, label, detail, subtitle=None, photo=None,
                     photo_base="", prompt="Choose", filename="items.vcf",
                     number=True):
        """A rich picker with thumbnails, from any list of dictionaries.

        Shortcuts has no image-list UI, but Choose from List renders
        contacts with their photos. So build one vCard per item with the
        artwork base64'd into PHOTO, name the blob .vcf, run it through
        Get Contacts from Input, and the picker comes back illustrated.

        Each callback receives the loop and returns text parts (a string,
        a token, or a list of either), so it can call getvalueforkey on
        the current item:

            s.vcard_picker(
                results,
                label=lambda m: s.action(GET, WFDictionaryKey="title",
                                         WFInput=att(m.item)),
                detail=lambda m: ["...", something],
                photo=lambda m: url_token)

        Returns the token holding the chosen item's detail text. The
        lookup table is assembled on device with Set Value for Key, so no
        server round trip is needed to merge it.
        """
        A = "is.workflow.actions."
        self._pickers = getattr(self, "_pickers", 0) + 1
        dvar = "_picked%d" % self._pickers
        self.setvar(dvar, self.emptydict())

        with self.foreach(items) as it:
            lbl_parts = _parts(label(it))
            if number:
                lbl_parts = [it.index, ". "] + lbl_parts
            lbl = self.text(ts(*lbl_parts))
            det = self.text(ts(*_parts(detail(it))))
            self.setvar(dvar, self._add_ret(
                A + "setvalueforkey", "Dictionary",
                WFDictionary=att(var(dvar)),
                WFDictionaryKey=ts(lbl), WFDictionaryValue=ts(det)))

            pic = None
            if photo is not None:
                # Guard the RAW field, not a URL built from it: a prefix
                # makes the string non-empty even when the field is null,
                # so the check would always pass and the fetch would 404.
                raw = photo(it)
                if raw is not None:
                    with self.if_has_value(raw) as got:
                        url = ts(photo_base, raw) if photo_base else ts(raw)
                        img = self._add_ret(A + "downloadurl",
                                            "Contents of URL", WFURL=url)
                        self._add_ret(A + "base64encode", "Base64 Encoded",
                                      WFInput=att(img),
                                      WFBase64LineBreakMode="None")
                    pic = got

            card = ["BEGIN:VCARD\nVERSION:3.0\n",
                    "N;CHARSET=utf-8:", lbl, ";\n"]
            if subtitle is not None:
                card += ["ORG;CHARSET=utf-8:"] + _parts(subtitle(it)) + [";\n"]
            if pic is not None:
                card += ["PHOTO;ENCODING=b:", pic, "\n"]
            card.append("END:VCARD")
            self.text(ts(*card))
            loop = it

        blob = self.text(ts(loop.results))
        named = self._add_ret(A + "setitemname", "Renamed Item",
                              WFInput=att(blob), WFName=filename)
        people = self._add_ret(A + "detect.contacts", "Contacts",
                               WFInput=att(named))
        chosen = self._add_ret(A + "choosefromlist", "Chosen Item",
                               WFInput=att(people),
                               WFChooseFromListActionPrompt=prompt)
        return self._add_ret(A + "getvalueforkey", "Dictionary Value",
                             WFDictionaryKey=ts(chosen),
                             WFInput=att(var(dvar)))

    def _add_ret(self, ident, output, **params):
        u = U()
        params["UUID"] = u
        self._add(ident, params)
        return out(u, output)

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
