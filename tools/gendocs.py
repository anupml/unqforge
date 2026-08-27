#!/usr/bin/env python3
"""
Generate docs/actions.md from constructs/.

The action reference is data, not prose. Writing it by hand would be
worse than the JSON and stale the moment anyone decompiles another
shortcut, so it is generated instead.

  python3 tools/gendocs.py
"""

import os as _os
import sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)

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
         "Third-party (App Intents)"]

HEAD = {h: g for g, heads in GROUPS.items() for h in heads}


def group_of(ident):
    if not ident.startswith("is.workflow.actions."):
        return "Third-party (App Intents)"
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


def main():
    if not os.path.isdir("constructs"):
        sys.exit("no constructs/ -- see README")
    actions, enums, prov = load()

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
         "| **Confirmed by running only** | %d |" % n_ranok,
         "",
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
         "stronger.", "", "---", "", "## Index", ""]

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


if __name__ == "__main__":
    main()
