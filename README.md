<div align="center">

# ⚒️ shortcutforge

**Build iOS Shortcuts from Python — from evidence, not guesswork.**

[![python](https://img.shields.io/badge/python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![license](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![actions covered](https://img.shields.io/badge/actions-86%2F402-8b5cf6?style=flat-square)](docs/actions.md)
[![round trip](https://img.shields.io/badge/round--trip-1290%2F1290-06b6d4?style=flat-square)](tools/roundtrip.py)

[Guide](docs/guide.md) · [Action reference](docs/actions.md) · [Examples](examples/)

</div>

---

```python
from shortcutforge import *

A = "is.workflow.actions."
s = SC()

q = s.action(A + "ask", WFAskActionPrompt="Search term?")
r = s.action(A + "downloadurl",
             WFURL=ts("https://api.example.com/search?q=", q))
items = s.action(A + "getvalueforkey", WFDictionaryKey="data.results",
                 WFInput=r)
s.action(A + "setclipboard", WFInput=items)

s.dump("search.plist")
```

Import the result into the Shortcuts app and it runs.

## Your first shortcut

**1. Install**

```bash
git clone https://github.com/anupml/shortcutforge
cd shortcutforge
pip install -e .
```

Python 3.8+, standard library only, no dependencies. Works on macOS,
Linux, Windows, and on iOS itself through a-Shell.

**2. Write it**

```python
# hello.py
from shortcutforge import *

A = "is.workflow.actions."
s = SC()

name = s.action(A + "ask", WFAskActionPrompt="What's your name?")
s.show("Hello ", name, " 👋")

s.dump("hello.plist")
```

```bash
python3 hello.py
```

**3. Get it onto your phone**

The output is a plain `.plist`. To turn it into an installable shortcut,
use [Shortcut Source Tool](https://routinehub.co/shortcut/5256/) by
gluebyte — it converts both ways, plist to shortcut and back.

AirDrop `hello.plist` to your phone, open Shortcut Source Tool, pick the
file, and it hands you a shortcut you can add.

> Shortcuts made outside the app are unsigned, so you need
> **Settings → Shortcuts → Allow Untrusted Shortcuts** turned on. Every
> tool in this space has the same requirement.

**4. Build something real**

Every action's parameters are in [docs/actions.md](docs/actions.md), with
a copy-pasteable snippet for each. `s.action()` returns that action's
output, so you chain them by passing the value along:

```python
q = s.action(A + "ask", WFAskActionPrompt="City?")
r = s.action(A + "downloadurl",
             WFURL=ts("https://api.open-meteo.com/v1/forecast?...", q))
temp = s.action(A + "getvalueforkey",
                WFDictionaryKey="current.temperature_2m", WFInput=r)
s.show("", temp)
```

`ts(...)` builds a text field out of literal text and values mixed
together. Loops, conditions and the rest are in
[docs/guide.md](docs/guide.md).

### Letting an AI write it

The reference is structured for this. Paste
[docs/guide.md](docs/guide.md) and [docs/actions.md](docs/actions.md)
into ChatGPT or Claude, then describe what you want:

> Here are the docs for a Python library that generates iOS Shortcuts.
> Write me one that asks for a city and shows the current temperature.

Run what comes back. If it uses something unsupported you get a clear
error naming the correct parameters, which the model can usually fix in
one turn — rather than a shortcut that imports and quietly does nothing.

## Why this exists

Other libraries hand-write a wrapper per action: read the format,
transcribe a definition, repeat a few hundred times. It works, it is
slow, and it rots whenever Apple changes something.

Here the definitions are **harvested**. Point `decompile.py` at any
shortcut and it extracts the action identifiers, parameter keys and
serialization shapes that shortcut actually uses. The emitter then
refuses to produce anything not backed by that evidence:

```
>>> s.action("is.workflow.actions.count", WFInput=x)
Unverified: is.workflow.actions.count: parameter 'WFInput'
            never observed (known: ['Input', 'WFCountType'])
```

Count really does take `Input`, not `WFInput`. Nobody would guess that.
The corpus knows it.

> **Adding support for an action means decompiling a shortcut that uses
> it.** No code change, no pull request.

## Status

| | |
| --- | --- |
| Built-in actions covered | **86 / 402** |
| Round-trip suite | **1290 / 1290** actions across 13 shortcuts |
| Dependencies | none |

402 is every `is.workflow.actions.*` identifier found in the Shortcuts
binary, so coverage is measured rather than claimed. Around 80 of those
are dead 2017-era integrations (Dropbox, Evernote, Pocket, Trello) and
deprecated ancestors, so the live figure is nearer 320.

The round-trip suite takes each shortcut to Python and back and compares,
including two 500-action production shortcuts with nested menus, HTTP
calls and embedded AppleScript.

<details>
<summary><b>What's covered</b></summary>

Text · dictionaries · lists · control flow · HTTP · files · clipboard ·
prompts · menus · contacts · base64 · images · dates · device details ·
`askllm` (Apple Intelligence)

Full list with parameters and shapes: **[docs/actions.md](docs/actions.md)**

</details>

## A real example

A movie search with poster thumbnails — [`examples/tmdb_picker.py`](examples/tmdb_picker.py):

```python
chosen = s.vcard_picker(
    results,
    label=lambda m: field(m.item, "title"),
    subtitle=lambda m: [field(m.item, "release_date"), "     ",
                        field(m.item, "vote_average"), " / 10"],
    photo=lambda m: field(m.item, "poster_path"),
    photo_base="https://image.tmdb.org/t/p/w342",
    detail=lambda m: [field(m.item, "title"), "\n\n",
                      field(m.item, "overview")],
    prompt="Pick a movie")

s.show("", chosen)
```

Shortcuts has no image-list UI, so `vcard_picker` builds one vCard per
result with the artwork base64'd into the PHOTO field, names the blob
`.vcf`, and runs it through Get Contacts from Input — which Choose from
List renders with photos.

| Example | What it does | Needs a key |
| --- | --- | --- |
| [`weather.py`](examples/weather.py) | Open-Meteo forecast, min/max/mean computed on device | no |
| [`tmdb_picker.py`](examples/tmdb_picker.py) | Movie search with poster thumbnails | TMDB |
| [`model2.py`](examples/model2.py) | Linear regression by gradient descent, in Shortcuts actions | no |
| [`apidemo.py`](examples/apidemo.py) | Minimal ask → HTTP → clipboard | no |

## Tools

| | |
| --- | --- |
| `tools/decompile.py` | plist → constructs database + readable listing |
| `tools/topython.py` | plist → runnable Python |
| `tools/roundtrip.py` | plist → Python → plist, compared; the test suite |
| `tools/coverage.py` | what is covered, and what to harvest next |
| `tools/gendocs.py` | regenerate `docs/actions.md` from `constructs/` |
| `tools/scanspec.py` | scan Apple's `.intentdefinition` files for enums |
| `tools/joinspec.py` | complete sampled enums using that scan |

```bash
python3 tools/roundtrip.py shortcuts/*
python3 tools/coverage.py --rank
```

## Reading and editing an existing shortcut

```bash
python3 tools/decompile.py downloaded.plist            # what does this do?
python3 tools/topython.py downloaded.plist -o edit.py  # editable Python
python3 edit.py rebuilt.plist
```

Useful for shortcuts too large to comfortably edit on a phone.

<details>
<summary><b>Project layout</b></summary>

```
shortcutforge/       the package: sclib.py plus bundled constructs
tools/         command-line tools
docs/          guide.md (API) and actions.md (generated reference)
examples/      runnable shortcut generators
constructs/    working evidence database; decompile.py writes here
shortcuts/     test corpus for the round-trip suite
spec/          action_ids.txt and enum vocabulary (not committed)
```

`constructs/` exists twice on purpose. `shortcutforge/constructs/` is what ships
to people who install the package; the top-level one is your working copy.
Sync before releasing:

```bash
cp constructs/*.json shortcutforge/constructs/
```

At runtime the library loads its bundled constructs first, then anything
in a local `constructs/` directory on top — so an installed copy works out
of the box, and decompiling a shortcut in your own project extends it
without reinstalling.

</details>

<details>
<summary><b>Notes on the plist format</b> — things that cost real debugging time</summary>

* Attachment offsets are **UTF-16 code units**, not Python string
  indices. Emoji and mathematical alphanumerics take two units each.
* `U+FFFC` must be written as `&#xFFFC;`. Emitted as raw UTF-8 it
  survives most paths and gets mangled by the rest.
* Carriage returns cannot survive as literals — plistlib rewrites CR to
  LF on write, and XML normalises it on read. They need a character
  reference, or every AppleScript in the file is silently rewritten.
* Conditionals do not affect `Repeat Item` depth numbering; the suffix
  counts repeat nesting only.
* `OutputName` is cosmetic; `OutputUUID` does the linking.
* Shortcuts omits defaults, so an unconfigured action serialises with an
  empty parameter dict — a corpus only teaches you about parameters
  somebody actually changed.
* Naming conventions are not reliable. `lowpowermode.set` takes lowercase
  `operation` and `OnValue`, no `WF` prefix, despite an
  `is.workflow.actions.*` identifier.

</details>

<details>
<summary><b>Limitations</b></summary>

* Decompiled Python uses flat `raw()` calls; control flow keeps its
  grouping identifiers but does not become `with` blocks.
* Third-party App Intent actions can be emitted but have no wrapper.
* Enum values are whatever the corpus sampled, except the few
  `joinspec.py` completed from Apple's own definitions.
* `WFCondition` integers 8, 9, 99, 101 and 999 are inferred from usage
  rather than labelled. 100 ("has any value") is confirmed behaviourally.
* Generated shortcuts are unsigned, so importing them needs "Allow
  Untrusted Shortcuts" enabled. That applies to every tool in this space.

</details>

<details>
<summary><b>Extracting the identifier list</b></summary>

`spec/action_ids.txt` is the coverage denominator, and is not committed.
On a Mac:

```bash
cd /System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/
cat dyld_shared_cache_arm64e* 2>/dev/null | strings -n 8 \
  | grep -oE 'is\.workflow\.actions\.[a-z0-9.]+' | sort -u \
  > /path/to/shortcutforge/spec/action_ids.txt
```

A few minutes; the cache is tens of GB.

</details>

## Licence

MIT. The evidence in `constructs/` was extracted from shortcuts built in
the Shortcuts app; no Apple resources are redistributed here.

Built with help from Claude.

🐈 *no cats were harmed in the reverse-engineering of this plist format*
