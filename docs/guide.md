# Guide

```bash
pip install -e .
```

```python
from unqforge import *
```

Action reference: [actions.md](actions.md) — generated from the evidence
database, so it never drifts.

API reference for `sclib`, plus the command-line tools.

---

## A whole one

Everything below is a fragment of this. Paste it, run it, and open the
result in Shortcuts.

```python
from unqforge import *

s = SC()

s.setvar("total", 0)                    # a literal, so a Text action
                                        # is emitted in front of it
with s.repeat(5) as i:
    s.setvar("total", s.calc(E(var("total")) + E(i.index)))

with s.if_(var("total"), ">", 10) as br:
    s.show("big: ", var("total"))
    br.otherwise()
    s.show("small: ", var("total"))

s.dump("sum.plist")
```

Later examples use `A` as shorthand for the identifier prefix:

```python
A = "is.workflow.actions."
```

---

## Concepts

**A shortcut is a flat list.** The Shortcuts UI shows nesting, but
`WFWorkflowActions` is a flat array. Blocks are reconstructed from a
shared `GroupingIdentifier` plus `WFControlFlowMode` — `0` opens, `1` is
the middle (Otherwise, or a menu case), `2` closes.

**Two kinds of variable.** Named variables are a name lookup
(`var("total")`). Magic variables are a pointer to another action's
output (`OutputUUID`). Every action method returns its own output token,
so magic variables are just Python values.

**Two serialization shapes.** Text fields take `WFTextTokenString` —
a string with `U+FFFC` placeholders plus an offset map. Content slots
take `WFTextTokenAttachment` — the token *is* the value. The field
decides, not the token count.

**The evidence database.** `constructs/*.json` records, per action, which
parameter keys have been observed and what shape each accepted. Nothing
outside it can be emitted.

---

## Building

### `SC()`

The builder. Loads the evidence database on construction: the constructs
bundled with the package first, then anything in a local `constructs/`
directory on top. So an installed copy works immediately, and decompiling
a shortcut in your own project extends what can be emitted without
reinstalling.

```python
s = SC()
s.dump("out.plist")
```

`s.meta` overrides top-level plist keys (icon, `WFWorkflowTypes`, input
classes) if you need something other than the defaults.

### Parameters are optional

Pass only what you want to change. Shortcuts omits anything left at its
default, which has two consequences worth knowing:

* A parameter you leave out gets its default. `downloadurl` without
  `WFHTTPMethod` is a GET request.
* Because defaults are never written to a file, they never appear in the
  corpus. The values in `actions.md` are a **lower bound** on what is
  legal, not the full set. `WFHTTPMethod` lists only `POST` for that
  reason.

So an action with no observed parameters is not necessarily an action
that takes none — it may just be one nobody has configured yet.

### `s.action(identifier, output_name=None, **params)`

Emit any harvested action. Returns its output token, or `None` when the
action has no observed output (Set Variable, Alert, Exit).

Bare values are wrapped automatically into whichever shape the evidence
records for that slot, so `WFInput=token` works without `att(...)` and
`Input="1+1"` works without `ts(...)`. Explicit wrapping is still
accepted, and a slot that accepts both shapes raises rather than
guessing.

```python
r = s.action("is.workflow.actions.downloadurl",
             WFURL=ts("https://example.com/", q),
             WFHTTPMethod="POST")
```

The output name is looked up in the database. Pass `output_name=` to
override when an action has several.

### `s.raw(identifier, params, uuid=None, output=None)`

Emit exactly these parameters, inferring nothing. Used by decompiled
code, where the UUID must be preserved. Prefer `action()` for authoring.

### Convenience methods

```python
s.text(t)              # Text action; t is a str or ts(...)
s.setvar(name, value)  # Set Variable; a literal gets a Text action first
s.calc(expr)           # Calculate Expression; takes an E(...) expression
s.split(token, sep)    # Split Text on a custom separator
s.emptydict()          # empty Dictionary
s.getval(d, key)       # Get Value for Key; d is a dict token or a variable name
s.setval(d, key, value)  # key and value take a str, a token, or ts parts
s.show(*parts)         # Show Result
```

---

## Tokens

```python
var("total")            # named variable
out(uuid, "Text")       # another action's output
att(token)              # wrap for a content slot
ts("hi ", token, "!")   # text field: literal parts and tokens interleaved
```

`ts()` computes the `U+FFFC` offsets. **Never write one by hand** —
they are UTF-16 code units, so any emoji or mathematical alphanumeric in
the literal text shifts everything after it.

---

## Expressions

```python
s.calc(E(var("total")) + E(x) * 2)
s.calc((E(a) - E(mu)) / E(sd))
s.calc(E(var("s2")) ** 0.5)
```

`E()` wraps a token or number; the operators build a Calculate
Expression string with correct precedence and minimal parentheses.
`**` is right-associative.

---

## Control flow

### Loops

```python
with s.repeat(10) as i:            # Repeat N times; N may be a token
    s.setvar("n", i.index)

with s.foreach(items) as it:       # Repeat with Each
    s.text(ts(it.item))

cards = s.text(ts(it.results))     # the loop's own collected output
```

`i.index` and `i.item` resolve to `Repeat Index` / `Repeat Item` with the
right suffix for their nesting depth — you never write `Repeat Item 2`.
Outer loop variables stay visible inside inner loops.

`loop.results` is `Repeat Results`, every iteration's output collected.
Shortcuts attaches it to the *closing* action of the block.

### Conditionals

```python
with s.if_(token, ">", 5) as br:
    s.show("big")
    br.otherwise()
    s.show("small")
```

Operators: `<` `<=` `>` `>=` `==` `!=` `between` (the last also takes
`upper=`). Each refuses to emit unless its `WFCondition` integer is in
your evidence.

```python
with s.if_has_value(token) as got:
    img = s.action(A + "downloadurl", WFURL=ts(token))
# `got` is the block's output -- how you get a value out of a conditional
```

Conditionals do **not** affect repeat depth numbering.

**Comparing against a variable works.** `WFNumberValue` holds either a
literal or a `WFTextTokenAttachment`, so both forms emit correctly:

```python
with s.if_(z, ">", var("best")):
    s.setvar("best", z)
```

**Text or numeric is chosen by the value you compare against.** A `str`
or a `ts(...)` writes `WFConditionalActionString`; a number writes
`WFNumberValue`. The operator is the same either way -- `==` is
`WFCondition` 4 on both paths, and it is the field that selects the
comparison, not the code.

```python
with s.if_(label, "==", "done"):        # text
    ...
with s.if_(count, ">", 5):              # numeric
    ...
```

A bare token is ambiguous and stays numeric, since that is what it meant
before the text path existed. Pass `text=True` to force it:

```python
with s.if_(label, "==", var("wanted"), text=True):
    ...
```

The numeric path coerces its input to `WFNumberContentItem`; the text
path emits no coercion at all, matching the string conditionals in the
corpus. `between` is numeric only -- it has never been observed with a
string right-hand side.

---

## `s.vcard_picker(...)`

A picker with thumbnails, from any list of dictionaries.

```python
chosen = s.vcard_picker(
    items,
    label=lambda it: ...,        # display name; parts or a token
    detail=lambda it: [...],     # text stored and returned on selection
    subtitle=lambda it: [...],   # optional ORG line
    photo=lambda it: ...,        # optional; the RAW field, not a URL
    photo_base="https://...",    # prefixed inside the null guard
    prompt="Choose",
    filename="items.vcf",
    number=True)                 # prefix labels with the index
```

Returns the token holding the chosen item's detail text.

Each callback receives the loop, so it can call `getvalueforkey` on
`it.item`. Callbacks are independent — if two of them fetch the same
field you get two lookups. Memoize if that matters:

```python
_seen = {}
def field(item, key):
    if key not in _seen:
        _seen[key] = s.action(A + "getvalueforkey",
                              WFDictionaryKey=key, WFInput=att(item))
    return _seen[key]
```

Pass `photo` the raw field, never a constructed URL: a prefix makes the
string non-empty even when the field is null, so the guard would always
pass and the download would 404.

Needs `setvalueforkey`, `setitemname`, `detect.contacts`,
`choosefromlist`, `downloadurl` and `base64encode` in your evidence.

---

## Discovery

```python
k = Constructs()
k.find("url")                                   # matching identifiers
print(k.describe("is.workflow.actions.count"))  # params, shapes, output
k.output_name_for(ident)
```

```
is.workflow.actions.count   [native]
   output -> Count
   Input                        WFTextTokenAttachment
   WFCountType                  str
```

---

## Command line

```bash
python3 tools/decompile.py FILE [--json OUT] [--known PREV] [--quiet]
```
Readable listing, extracted constructs, and a repeat-depth audit.
`--known` reports only what is new. Flags corrupt files: bad attachment
offsets, mojibake, unbalanced control flow.

```bash
python3 tools/topython.py FILE [-o OUT.py]
```
Runnable `sclib` code. Run it to regenerate the shortcut.

```bash
python3 tools/roundtrip.py shortcuts/*
```
plist to Python to plist, compared semantically (UUIDs canonicalised).
A failure names the construct that broke it.

```bash
python3 tools/coverage.py [--missing] [--rank]
```
Coverage against `spec/action_ids.txt`. `--rank` orders unharvested
actions by how often they appear in your corpus.

```bash
python3 tools/scanspec.py            # scan Apple's .intentdefinition files
python3 tools/joinspec.py [--write]  # complete sampled enums from that scan
```

---

## Installing what you built

`dump()` writes a plist. To get it onto a device it has to be signed,
which needs a Mac:

```bash
plutil -convert binary1 -o out.shortcut out.plist
shortcuts sign -m anyone -i out.shortcut -o signed.shortcut
open signed.shortcut
```

**The input file must be named `.shortcut`.** `shortcuts sign` rejects a
`.plist` with "isn't in the correct format" no matter what is inside it,
so the conversion above writes to a `.shortcut` name rather than
converting in place. Whether the binary conversion is needed at all, or
only the extension, is untested.

`-m anyone` is what you want for anything shared. The default,
`people-who-know-me`, produces a file that installs for you and nobody
else.

---

## Adding an action

1. Build a shortcut in the Shortcuts app that uses it, configured — an
   unconfigured action serialises with no parameters and teaches nothing.
2. Export it.
3. `python3 tools/decompile.py it.plist --json constructs/name.native.json`
4. `s.action("is.workflow.actions.thing", ...)` now works.

No library change.

---

## Errors

```
Unverified: action 'x' never observed on device
```
Not in the evidence. Decompile a shortcut that uses it.

```
Unverified: x: parameter 'y' never observed (known: [...])
```
Wrong key name — check the list in the message.

```
Unverified: x.y: shape 'S' never observed (known: [...])
```
Right key, wrong wrapper. Usually `att()` vs `ts()`.

```
Unverified: x.y: attachment wraps the literal 0. Every token slot needs a
variable or an action output -- put a Text action in front
```
A content slot was handed a raw value. `s.setvar` does this for you; if
you built the attachment yourself, put a `s.text(...)` in front and pass
its output instead. On device an attachment with nothing in it makes the
variable nil, and every later calculation reading it is garbage — which
is why this is refused at emit time rather than left to fail quietly.

```
Unverified: x.y: token Type 'T' never observed (evidence: ...)
```
The wrapper is right but what is inside is not a token Shortcuts writes.
The legal set comes from `token_types` in your constructs, not from a
list in the library.

```
Unverified: x.y: Variable token has VariableName {...}, not a string --
var() was given a token instead of a name
```
`var()` takes a variable *name*. Passing a token yields `var(<dict>)`,
which has a legal `Type` and a meaningless payload. If you already hold a
token, use it directly — `getval` and `setval` accept either.

```
Unverified: x.y: ActionOutput token has OutputUUID ..., not a string
```
Same shape of mistake on the other token type, usually from building
`out(...)` by hand rather than using the value an action method returned.

```
AssertionError: emitted file differs from what we built: <path>
```
Serialization bug; the path points at the offending value.
