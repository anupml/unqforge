# shortcutpy

Generate iOS Shortcuts from Python, and learn the plist format from real
shortcuts instead of guesswork.

```python
from sclib import *

A = "is.workflow.actions."
s = SC()

q = s.action(A + "ask", WFAskActionPrompt="Search term?")
r = s.action(A + "downloadurl",
             WFURL=ts("https://api.example.com/search?q=", q))
items = s.action(A + "getvalueforkey",
                 WFDictionaryKey="data.results", WFInput=att(r))
s.action(A + "setclipboard", WFInput=att(items))

s.dump("search.plist")
```

Import the result into Shortcuts and it runs.

## The idea

Existing libraries hand-write a definition per action: someone reads the
format, writes a wrapper, repeats a few hundred times. That works, it is
slow, and it rots whenever Apple changes something.

Here the definitions are **harvested**. Point `decompile.py` at any
shortcut and it extracts the action identifiers, parameter keys, and
serialization shapes that shortcut actually uses. The emitter then
refuses to produce anything not in that evidence:

```
>>> s.action("is.workflow.actions.count", WFInput=att(x))
sclib.Unverified: is.workflow.actions.count: parameter 'WFInput'
                  never observed (known: ['Input', 'WFCountType'])
```

`count` really does take `Input`, not `WFInput`. Nobody would guess that;
the corpus knows it.

## Status

```
built-in actions covered    68 / 402   (17%)
round-trip suite            1120 / 1120 actions across 10 shortcuts
```

402 is every `is.workflow.actions.*` identifier in the Shortcuts binary,
so coverage is measured rather than asserted. The round-trip suite takes
each shortcut to Python and back and compares — including two 500-action
production shortcuts with nested menus, HTTP calls, and embedded
AppleScript.

Covered so far: text, dictionaries, lists, control flow, HTTP, files,
clipboard, prompts, menus, and `askllm` (Apple Intelligence).

## Tools

```
sclib.py        the emitter; validates every parameter against evidence
decompile.py    plist -> constructs database + readable listing
topython.py     plist -> runnable Python
roundtrip.py    plist -> Python -> plist, compared; the test suite
coverage.py     how much of Shortcuts is covered, and what to harvest next
scanspec.py     scan Apple's .intentdefinition files for enum vocabulary
joinspec.py     upgrade sampled enums to complete ones using that scan
```

## Workflow

```
build a shortcut in the Shortcuts app
        |
        v
   export it  ->  decompile.py --json constructs/name.native.json
        |
        v
   sclib can now emit those actions; anything else raises Unverified
```

Filename encodes provenance, and `sclib` reads it:

* `*.native.json` — Shortcuts itself wrote these shapes (strongest)
* `*.ranok.json`  — we generated them and they ran correctly on device

## Reading and editing an existing shortcut

```bash
python3 decompile.py downloaded.plist          # what does this do?
python3 topython.py downloaded.plist -o edit.py
# change a URL, a prompt, a loop count
python3 edit.py rebuilt.plist
```

## Running the tests

```bash
python3 roundtrip.py shortcuts/*
python3 coverage.py --rank
```

`--rank` lists unharvested actions by how often they appear in your
corpus, so the next thing to harvest is the one that matters rather than
whatever is alphabetically first.

## Extracting the identifier list

`spec/action_ids.txt` is the coverage denominator. On a Mac:

```bash
cd /System/Volumes/Preboot/Cryptexes/OS/System/Library/dyld/
cat dyld_shared_cache_arm64e* 2>/dev/null | strings -n 8 \
  | grep -oE 'is\.workflow\.actions\.[a-z0-9.]+' | sort -u \
  > /path/to/shortcutpy/spec/action_ids.txt
```

Takes a few minutes; the cache is tens of GB. The list includes
deprecated actions and a genuine Apple typo
(`is.workflow.actions.detect.dicionary`), so it is a ceiling rather than
a list of useful actions.

## Notes on the format

Things that cost real debugging time and are easy to get wrong:

* Attachment offsets are **UTF-16 code units**, not Python string
  indices. Emoji and mathematical alphanumerics take two units each.
* `U+FFFC` must be written as `&#xFFFC;`. Emitted as raw UTF-8 it
  survives most paths and gets mangled by the rest.
* Carriage returns cannot survive as literals — plistlib rewrites CR to
  LF on write and XML normalises it on read. They need a character
  reference, or every AppleScript in the file is silently rewritten.
* Conditionals do not affect `Repeat Item` depth numbering; the suffix
  counts repeat nesting only.
* `OutputName` is cosmetic; `OutputUUID` does the linking.

## Requirements

Python 3, standard library only. Runs in a-Shell on iOS.

## Not done yet

* No `with` blocks in decompiled output; control flow comes out as flat
  calls with grouping identifiers preserved.
* Third-party App Intent actions can be emitted but have no wrapper.
* Enum values are whatever the corpus sampled, except the few
  `joinspec.py` could complete from Apple's definitions.
