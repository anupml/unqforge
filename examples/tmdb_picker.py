#!/usr/bin/env python3
"""
TMDB search with a poster-thumbnail picker, via sclib's vcard_picker.

Same shortcut as tmdb_picker.py, but the fifteen actions of vCard
boilerplate now live in the library. Compare the two files to see what
the helper is worth.

  TMDB_KEY=xxx python3 examples/tmdb_pick2.py picker.plist
"""
import os
import sys

from unqforge import *                                            # noqa: E402

A = "is.workflow.actions."
KEY = os.environ.get("TMDB_KEY", "<API KEY>")
SEARCH = "https://api.themoviedb.org/3/search/movie?api_key=" + KEY
POSTER = "https://image.tmdb.org/t/p/w342"

s = SC()
_seen = {}


def field(item, key):
    """Fetch a key off the current item, once per key per iteration.

    The callbacks are independent, so title/date/score would each be
    fetched twice without this -- correct but wasteful.
    """
    hit = _seen.get(key)
    if hit is None:
        hit = s.action(A + "getvalueforkey",
                       WFDictionaryKey=key, WFInput=att(item))
        _seen[key] = hit
    return hit


query = s.action(A + "ask", WFAskActionPrompt="Movie name?")
q = s.action(A + "text.replace", WFInput=ts(query),
             WFReplaceTextFind=" ", WFReplaceTextReplace="+")
resp = s.action(A + "downloadurl", WFURL=ts(SEARCH + "&query=", q))
results = s.action(A + "getvalueforkey",
                   WFDictionaryKey="results", WFInput=att(resp))

_seen.clear()
chosen = s.vcard_picker(
    results,
    label=lambda m: field(m.item, "title"),
    subtitle=lambda m: [field(m.item, "release_date"), "     ",
                        field(m.item, "vote_average"), " / 10"],
    photo=lambda m: field(m.item, "poster_path"),
    photo_base=POSTER,
    detail=lambda m: [field(m.item, "title"), "  (",
                      field(m.item, "release_date"), ")\n",
                      "score ", field(m.item, "vote_average"),
                      " from ", field(m.item, "vote_count"), " votes\n\n",
                      field(m.item, "overview")],
    prompt="Pick a movie",
    filename="movies.vcf")

s.show("", chosen)

out_path = sys.argv[1] if len(sys.argv) > 1 else "picker.plist"
s.dump(out_path)
print("wrote %s -- %d actions" % (out_path, len(s.acts)))
