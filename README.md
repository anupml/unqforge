<div align="center">

# ⚒️ unqforge

**Write iOS Shortcuts in Python. Get a real, runnable shortcut.**

[![python](https://img.shields.io/badge/python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![license](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![actions covered](https://img.shields.io/badge/actions-307%2F365-8b5cf6?style=flat-square)](docs/actions.md)
[![round trip](https://img.shields.io/badge/round--trip-805%2F805-06b6d4?style=flat-square)](tools/roundtrip.py)
[![dependencies](https://img.shields.io/badge/dependencies-none-f59e0b?style=flat-square)](pyproject.toml)

[🌐 Website](https://unqx.site/sclib/) · [✨ Showcase](https://unqx.site/sclib/showcase.html) · [📖 Guide](docs/guide.md) · [📚 Actions](docs/actions.md) · [🧪 Examples](examples/)

</div>

---

**unqforge** turns short, readable Python into a [Shortcuts](https://apps.apple.com/app/shortcuts/id915249334) file you can install and run.
It only allows actions and parameters seen in shortcuts made on real iPhones, so a mistake is an error
on your screen, not a shortcut that imports and quietly does nothing.

```python
from unqforge import *

A = "is.workflow.actions."
s = SC()

name = s.action(A + "ask", WFAskActionPrompt="What's your name?")
s.show("Hello ", name, " 👋")

s.dump("hello.plist")
```

## 🌟 Features

- 🐍 **Plain Python**: variables, functions and loops to build shortcuts of any size
- ✅ **Checked against real devices**: every action, parameter and value shape is backed by evidence
- 🧭 **Helpful errors**: a wrong key tells you the right ones (`Count` takes `Input`, not `WFInput`)
- 🔁 **Control flow**: `with s.if_(...)`, `s.foreach(...)`, `s.repeat(...)`, `s.menu(...)`
- 🔄 **Works both ways**: decompile any shortcut into editable Python and rebuild it
- 🤖 **AI-friendly**: give the docs to ChatGPT or Claude and describe what you want
- 📱 **Runs anywhere Python runs**: Mac, Linux, or iPhone with a-Shell
- 🔏 **One-tap signing** in the [web editor](https://unqx.site/sclib/), or locally on a Mac
- 📦 **No dependencies**: standard library only

## ✨ Built with unqforge

| Shortcut | Actions | What it is |
| --- | ---: | --- |
| [ShortSQL](https://routinehub.co/shortcut/26893/) | 4,824 | A SQL database inside Shortcuts: joins, subqueries, transactions |
| [UNQ Clipforge](https://unqx.site/sclib/showcase.html) | 1,654 | Clipboard history, link cleaning, text tools |
| [ShortVM](https://unqx.site/sclib/showcase.html) | 788 | A tiny virtual CPU that runs small programs |
| [ML Classifier](https://unqx.site/sclib/showcase.html) | 574 | Trains a machine-learning classifier on-device |

More on the [showcase](https://unqx.site/sclib/showcase.html).

## 🚀 Quick start

**1. Install**

```bash
git clone https://github.com/anupml/unqforge
cd unqforge
pip install -e .
```

<details>
<summary><b>On iPhone or iPad (a-Shell)</b></summary>

[a-Shell](https://apps.apple.com/app/a-shell/id1473805438) has no `git` or working `pip`, so grab the zip:

```bash
curl -L -o uf.zip https://github.com/anupml/unqforge/archive/refs/heads/main.zip
python3 -c "import zipfile; zipfile.ZipFile('uf.zip').extractall('.')"
cd unqforge-main
```

Run your scripts from inside that folder and start them with:

```python
import sys; sys.path.insert(0, ".")
from unqforge import *
```

The test suite runs there too: `python3 tools/roundtrip.py shortcuts/*`.

</details>

**2. Write and run it**

```bash
python3 hello.py        # -> hello.plist
```

**3. Put it on your phone**

Paste your code into the [unqforge editor](https://unqx.site/sclib/): it builds, checks and signs it
in one tap, on any device. On a Mac you can also sign locally
([how](docs/guide.md#installing-what-you-built)).

**4. Build something real**

`s.action()` returns that action's output, so you chain actions by passing values along:

```python
q = s.action(A + "ask", WFAskActionPrompt="City?")
r = s.action(A + "downloadurl",
             WFURL=ts("https://api.open-meteo.com/v1/forecast?...", q))
temp = s.action(A + "getvalueforkey",
                WFDictionaryKey="current.temperature_2m", WFInput=r)
s.show("It's ", temp, "°")
```

`ts(...)` mixes text and values in one field. Every action, with a copy-paste snippet, is in
[docs/actions.md](docs/actions.md); loops, conditions and menus are in [docs/guide.md](docs/guide.md).

## 🤖 Let an AI write it

Paste [docs/guide.md](docs/guide.md) and [docs/actions.md](docs/actions.md) into ChatGPT or Claude, then describe
what you want:

> Here are the docs for a Python library that generates iOS Shortcuts.
> Write me one that asks for a city and shows the current temperature.

If it uses something that doesn't exist, the error names the correct parameters, and the model can
usually fix it in one turn. The [website](https://unqx.site/sclib/) and its companion shortcut can help with this too.

## 🔍 Why another Shortcuts tool?

Most libraries hand-write a definition for every action. It's slow, and it breaks when Apple changes
something.

unqforge **harvests** them instead. `decompile.py` reads any shortcut and records the action ids,
parameter keys and value shapes it really uses, and the builder refuses anything without that
evidence:

```
>>> s.action("is.workflow.actions.count", WFInput=x)
Unverified: is.workflow.actions.count: parameter 'WFInput'
            never observed (known: ['Input', 'WFCountType'])
```

> **Adding an action means decompiling a shortcut that uses it.** No code change.

| | |
| --- | --- |
| Built-in actions | **307 / 365** (84%), measured against the Shortcuts binary |
| App intent actions | **277** (Apple apps and third-party) |
| Round-trip suite | **805 / 805** actions across 12 shortcuts |

Most of the 58 missing are retired integrations (Dropbox, Evernote, Pocket…) and Mac-only actions.

## 🧪 Examples

| Example | What it does | Needs a key |
| --- | --- | --- |
| [`weather.py`](examples/weather.py) | Open-Meteo forecast, min/max/mean computed on device | no |
| [`tmdb_picker.py`](examples/tmdb_picker.py) | Movie search with poster thumbnails | TMDB |
| [`model2.py`](examples/model2.py) | Linear regression by gradient descent, in Shortcuts actions | no |
| [`apidemo.py`](examples/apidemo.py) | Minimal ask → HTTP → clipboard | no |

## 🛠️ Tools

| | |
| --- | --- |
| `tools/decompile.py` | shortcut → evidence + readable listing |
| `tools/topython.py` | shortcut → editable Python |
| `tools/harvestdb.py` | harvest your whole library at once (macOS) |
| `tools/roundtrip.py` | shortcut → Python → shortcut, compared (the test suite) |
| `tools/coverage.py` | what's covered, and what to harvest next |
| `tools/gendocs.py` | regenerate `docs/actions.md` |

```bash
python3 tools/topython.py downloaded.plist -o edit.py   # edit a shortcut as code
python3 edit.py rebuilt.plist
```

## 📂 More

<details>
<summary><b>Harvesting your whole library at once (macOS)</b></summary>

The Shortcuts app keeps its library in a Core Data store
at `~/Library/Shortcuts/Shortcuts.sqlite`, with each shortcut's actions
stored as a blob. So instead of exporting shortcuts one at a time, the
whole library can be read in a single pass:

```bash
python3 tools/harvestdb.py --list                            # see what's there
python3 tools/harvestdb.py --json constructs/library.native.json
python3 tools/gendocs.py
```

That database is protected by macOS, so Terminal needs permission first:

> **System Settings → Privacy & Security → Full Disk Access** → add
> Terminal (or iTerm) → toggle it on → **quit Terminal completely and
> reopen it.** The permission does not apply until you restart it.

Without that you get `authorization denied` when it tries to open the
database.

The database is opened **read-only**, so this never modifies your
library. Expect a few shortcuts to be skipped — signed imports can be
encrypted, and very old Workflow-era ones use a different layout.

Running this on my own library took coverage from 86 actions to 153:
296 of 306 shortcuts, 27,765 actions, 161 distinct types, one command.

There is no equivalent on iOS — the library there isn't reachable from
a-Shell — so on iPhone you still harvest by exporting individual
shortcuts and running `decompile.py`.

</details>

<details>
<summary><b>Project layout</b></summary>

```
unqforge/      the package: sclib.py plus bundled constructs
tools/         command-line tools
docs/          guide.md (API) and actions.md (generated reference)
examples/      runnable shortcut generators
constructs/    working evidence database; decompile.py writes here
shortcuts/     test corpus for the round-trip suite
spec/          action_ids.txt and enum vocabulary (not committed)
```

`constructs/` exists twice on purpose. `unqforge/constructs/` is what ships
to people who install the package; the top-level one is your working copy.
Sync before releasing:

```bash
cp constructs/*.json unqforge/constructs/
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

</details>

<details>
<summary><b>Extracting the identifier list</b></summary>

`spec/action_ids.txt` is the coverage denominator, and is not committed.
On a Mac:

```bash
cd /System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/
cat dyld_shared_cache_arm64e* 2>/dev/null | strings -n 8 \
  | grep -oE 'is\.workflow\.actions\.[a-z0-9.]+' | sort -u \
  > /path/to/unqforge/spec/action_ids.txt
```

A few minutes; the cache is tens of GB.

</details>

## 📜 Licence

MIT. The evidence in `constructs/` was extracted from shortcuts built in the Shortcuts app; no Apple
resources are redistributed here.

Built with help from Claude.

🐈 *no cats were harmed in the reverse-engineering of this plist format*
