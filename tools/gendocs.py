#!/usr/bin/env python3
"""
Generate docs/actions.md from constructs/.

The action reference is data, not prose. Writing it by hand would be
worse than the JSON and stale the moment anyone decompiles another
shortcut, so it is generated instead.

Actions that need a third-party app installed are left out by default.
They were harvested from whatever happened to be on this machine, so
documenting them advertises actions that do not exist for anyone else.

  python3 tools/gendocs.py
  python3 tools/gendocs.py --include-app-specific
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

OUT = "docs/actions.md"
SKIP = {"UUID", "GroupingIdentifier"}

GROUPS = {
    "Text": ("text", "gettext", "urlencode", "correctspelling",
             "detectlanguage"),
    "Dictionaries": ("getvalueforkey", "setvalueforkey", "dictionary",
                     "detect"),
    "Lists": ("list", "getitemfromlist", "count", "filter"),
    "Control flow": ("repeat", "conditional", "choosefrommenu", "exit",
                     "nothing", "runworkflow", "waittoreturn", "comment"),
    "Variables": ("setvariable", "getvariable"),
    "Maths": ("calculateexpression", "math", "number", "round",
              "statistics"),
    "Network": ("downloadurl", "url", "openurl", "showwebpage",
                "getipaddress"),
    "Files": ("file", "documentpicker", "gettypeaction", "setitemname",
              "previewdocument", "base64encode", "makepdf", "gettextfrompdf",
              "makezip", "unzip"),
    "Input & output": ("ask", "showresult", "alert", "choosefromlist",
                       "notification", "speaktext", "getclipboard",
                       "setclipboard", "share", "openin", "getmyworkflows"),
    "Media & images": ("image", "getrichtextfromhtml", "takephoto",
                       "savetocameraroll", "encodemedia"),
    "Dates": ("format", "adjustdate", "date", "currentdate",
              "converttimezone"),
    "Properties": ("properties",),
    "Device": ("getdevicedetails", "getbatterylevel", "wifi", "bluetooth",
               "lowpowermode", "airplanemode", "cellulardata", "dnd",
               "setbrightness", "setvolume", "vibrate"),
    "Contacts & calendar": ("addnewreminder", "addnewevent", "contacts"),
    "Weather": ("weather",),
    "Apple Intelligence": ("askllm",),
    "Scripting": ("runshellscript", "runapplescript",
                  "runjavascriptonwebpage", "runjavascriptforautomation"),
}
ORDER = ["Text", "Dictionaries", "Lists", "Control flow", "Variables",
         "Maths", "Network", "Files", "Input & output", "Media & images",
         "Dates", "Properties", "Device", "Contacts & calendar", "Weather",
         "Apple Intelligence", "Scripting", "Other",
         "Apple apps", "Requires a third-party app"]

HEAD = {h: g for g, heads in GROUPS.items() for h in heads}

# Third-party actions that are kept anyway. a-Shell is the documented way
# to run this toolchain on iOS, so its actions are the one case where a
# reader is likely to have the app.
KEEP_APP_SPECIFIC = ()


def availability(ident):
    """Which devices can actually run this action.

    builtin      ships inside Shortcuts itself; present on every device.
    apple_app    a stock Apple app. Present by default, but the user can
                 delete Notes or Reminders, so it is not guaranteed.
    requires_app needs a third-party app installed. Both modern App
                 Intents (UNQ.Lathe.*) and older Intents-framework
                 extensions (AsheKube.app.*) land here — they serialise
                 differently but have the same availability problem.

    The identifier prefix carries all of this. The AppIntentDescriptor
    parameter names the owning bundle, but only in its *value*, and the
    corpus records shapes rather than values — so it adds nothing here.
    """
    if ident.startswith("is.workflow.actions."):
        return "builtin"
    if ident.startswith("com.apple."):
        return "apple_app"
    return "requires_app"


def group_of(ident):
    avail = availability(ident)
    if avail == "apple_app":
        return "Apple apps"
    if avail == "requires_app":
        return "Requires a third-party app"
    return HEAD.get(ident[len("is.workflow.actions."):].split(".")[0],
                    "Other")


def slug(text):
    """GitHub heading anchor."""
    return re.sub(r"[^a-z0-9\-_]", "", text.lower().replace(" ", "-"))


def load():
    actions, enums, prov = {}, defaultdict(set), defaultdict(set)
    for path in sorted(glob.glob("constructs/*.json")):
        parts = os.path.basename(path).split(".")
        src = parts[-2] if len(parts) > 2 else "unknown"
        d = json.load(open(path))
        for ident, rec in d.get("actions", {}).items():
            slot = actions.setdefault(ident, {"params": defaultdict(set),
                                              "outputs": set(), "count": 0})
            for p, shapes in rec["params"].items():
                slot["params"][p].update(shapes)
            slot["outputs"].update(rec.get("output_names", []))
            slot["count"] += rec.get("count", 0)
            prov[ident].add(src)
        for k, vals in d.get("enums", {}).items():
            enums[k].update(vals)
    return actions, enums, prov


def snippet(ident, rec, enums):
    """A copy-pasteable call with plausible placeholders."""
    args = []
    for k in sorted(rec["params"]):
        if k in SKIP:
            continue
        shapes = rec["params"][k]
        strs = [v for v in sorted(enums.get(k, ())) if isinstance(v, str)]
        if strs:
            arg = '"%s"' % strs[0]
        elif "WFTextTokenAttachment" in shapes:
            arg = "att(x)"
        elif "WFTextTokenString" in shapes and "str" not in shapes:
            arg = 'ts("...")'
        elif "bool" in shapes:
            arg = "False"
        elif "int" in shapes or "real" in shapes:
            arg = "0"
        elif "array" in shapes:
            arg = "[]"
        else:
            arg = '"..."'
        args.append("%s=%s" % (k, arg))
    lead = "out = " if rec["outputs"] else ""
    if not args:
        return '%ss.action("%s")' % (lead, ident)
    return '%ss.action("%s",\n        %s)' % (lead, ident,
                                              ",\n        ".join(args))


def drop_app_specific(actions, enums):
    """Remove actions that need a third-party app, and any enum vocabulary
    that only those actions used.

    Enums are keyed by parameter name across the whole corpus, not per
    action, so filtering the action list alone would still leave a Lathe
    parameter's values sitting in the enum table. Only keys that an
    excluded action used and no surviving action uses are dropped —
    vocabulary from constructs/enums.spec.json, which comes from Apple's
    own definitions and may match no harvested action at all, is left
    alone.
    """
    gone = {i: r for i, r in actions.items()
            if availability(i) == "requires_app"
            and i not in KEEP_APP_SPECIFIC}
    for ident in gone:
        del actions[ident]

    dead = {p for r in gone.values() for p in r["params"]}
    live = {p for r in actions.values() for p in r["params"]}
    for key in dead - live:
        enums.pop(key, None)
    return gone


def main():
    ap = argparse.ArgumentParser(
        description="generate docs/actions.md from constructs/")
    ap.add_argument("--include-app-specific", action="store_true",
                    help="also document actions that need a third-party "
                         "app installed. Off by default: they come from "
                         "whatever is on the harvesting machine and do "
                         "not exist on anyone else's device.")
    args = ap.parse_args()

    if not os.path.isdir("constructs"):
        sys.exit("no constructs/ -- see README")
    actions, enums, prov = load()

    dropped = {}
    if not args.include_app_specific:
        dropped = drop_app_specific(actions, enums)

    by = defaultdict(list)
    for ident in sorted(actions):
        by[group_of(ident)].append(ident)
    groups = [g for g in ORDER if g in by]

    n_native = sum(1 for i in actions if "native" in prov[i])
    n_ranok = sum(1 for i in actions if prov[i] == {"ranok"})
    total_seen = sum(a["count"] for a in actions.values())

    L = ["# Action reference", "",
         "> Generated by `tools/gendocs.py` from `constructs/`. "
         "Do not edit by hand.", "",
         "| | |", "| --- | --- |",
         "| **Actions** | %d |" % len(actions),
         "| **Categories** | %d |" % len(groups),
         "| **Observed uses** | %d |" % total_seen,
         "| **Confirmed by Shortcuts itself** | %d |" % n_native,
         "| **Confirmed by running only** | %d |" % n_ranok]
    if dropped:
        L.append("| **Left out (need an app installed)** | %d |"
                 % len(dropped))
    L += ["",
         "Every parameter and shape below was observed on a device. "
         "`sclib` refuses to emit anything that is not here, which is why "
         "this file contains no invented keys.", "",
         "> **Parameters are optional, and the values listed are a lower "
         "bound.** Shortcuts omits anything left at its default, so a "
         "default never appears in a corpus. `WFHTTPMethod` lists only "
         "`POST` for exactly that reason — GET is the default, so leaving "
         "the parameter out gives you a GET request. Absence of a value "
         "here means nobody has been observed setting it, not that it is "
         "illegal.", "",
         "**Provenance** — `native` means Shortcuts wrote the shape itself, "
         "in a shortcut built through the app. `ranok` means we generated it "
         "and it ran correctly on device. Both are evidence; the first is "
         "stronger.", ""]

    if dropped:
        L += ["> **%d action%s that need a third-party app installed "
              "%s left out.** They were harvested from a real library, so "
              "the shapes are correct — but the app has to be on the "
              "device for the action to exist at all, and a shortcut "
              "referencing a missing one imports as a broken action. "
              "Regenerate with `--include-app-specific` if you want them."
              % (len(dropped), "" if len(dropped) == 1 else "s",
                 "is" if len(dropped) == 1 else "are"), ""]

    L += ["---", "", "## Index", ""]

    for g in groups:
        L.append("**[%s](#%s)** — %s" % (
            g, slug(g),
            " · ".join("[`%s`](#%s)" % (i.split(".")[-1], slug(i))
                       for i in by[g])))
        L.append("")
    L += ["---", ""]

    for g in groups:
        L += ["## %s" % g, ""]
        for ident in by[g]:
            rec = actions[ident]
            outs = sorted(rec["outputs"])
            L += ["### `%s`" % ident, "",
                  " · ".join(["`%s`" % p for p in sorted(prov[ident])]
                             + ["seen %d×" % rec["count"]]), ""]
            L += ["Returns `%s`." % "` or `".join(outs) if outs
                  else "No output.", ""]

            keys = [k for k in sorted(rec["params"]) if k not in SKIP]
            if keys:
                L += ["| Parameter | Accepts |", "| --- | --- |"]
                for k in keys:
                    shapes = " · ".join("`%s`" % s
                                        for s in sorted(rec["params"][k]))
                    note = ""
                    if enums.get(k):
                        vals = sorted(enums[k],
                                      key=lambda v: (isinstance(v, str), v))
                        note = "<br>values: %s" % ", ".join(
                            "`%s`" % v for v in vals[:8])
                    L.append("| `%s` | %s%s |" % (k, shapes, note))
                L.append("")
            else:
                L += ["No parameters observed — either it takes none, or "
                      "every sample was left at its defaults. Shortcuts "
                      "omits defaults entirely, so an unconfigured action "
                      "teaches nothing.", ""]
            L += ["```python", snippet(ident, rec, enums), "```", ""]
        L += ["<sub>[back to index](#index)</sub>", "", "---", ""]

    if enums:
        L += ["## Enum values", "",
              "Sampled from the corpus, except where `tools/joinspec.py` "
              "completed them from Apple's own definitions — so a legal "
              "value may still be missing. In particular, the default for "
              "any parameter is usually absent, because Shortcuts does not "
              "write defaults into the file.", "",
              "| Key | Observed values |", "| --- | --- |"]
        for k in sorted(enums):
            vals = sorted(enums[k], key=lambda v: (isinstance(v, str), v))
            L.append("| `%s` | %s |" % (k, ", ".join("`%s`" % v
                                                     for v in vals)))
        L.append("")

    os.makedirs("docs", exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote %s — %d actions in %d categories, %d enum keys"
          % (OUT, len(actions), len(groups), len(enums)))
    if dropped:
        print("left out %d action%s needing a third-party app: %s"
              % (len(dropped), "" if len(dropped) == 1 else "s",
                 ", ".join(sorted(dropped)[:4])
                 + (", ..." if len(dropped) > 4 else "")))
        print("pass --include-app-specific to document them anyway")


if __name__ == "__main__":
    main()
