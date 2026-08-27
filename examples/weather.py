#!/usr/bin/env python3
"""
Open-Meteo forecast stats, computed inside Shortcuts.

Fetches an hourly temperature series and reduces it to min / max / mean
without leaving the shortcut -- the arithmetic runs on device, not in the
API. Uses only actions harvested from real shortcuts.

  python3 examples/weather.py weather.plist
"""
import sys

from unqforge import *                                            # noqa: E402

A = "is.workflow.actions."
API = "https://api.open-meteo.com/v1/forecast"

s = SC()

# --- constants we reuse as inputs -------------------------------------
ZERO = s.text("0")
BIG = s.text("999")
SMALL = s.text("-999")

lat = s.action(A + "ask", WFAskActionPrompt="Latitude? (e.g. 52.52)")
lon = s.action(A + "ask", WFAskActionPrompt="Longitude? (e.g. 13.41)")

# --- fetch ------------------------------------------------------------
resp = s.action(A + "downloadurl",
                WFURL=ts(API + "?latitude=", lat,
                         "&longitude=", lon,
                         "&hourly=temperature_2m"))

# Dotted keys walk nested JSON in one action -- learned from UNQ MUSIC,
# where "data.results" and "artists.primary" both resolve.
temps = s.action(A + "getvalueforkey",
                 WFDictionaryKey="hourly.temperature_2m",
                 WFInput=att(resp))

# --- accumulators -----------------------------------------------------
s.setvar("total", ZERO)
s.setvar("n", ZERO)
s.setvar("hi", SMALL)
s.setvar("lo", BIG)

with s.foreach(temps) as hour:
    # Repeat Index doubles as the counter, so no Count action is needed
    s.setvar("n", hour.index)
    s.setvar("total", s.calc(E(var("total")) + E(hour.item)))

    # WFNumberValue has only ever been observed holding a literal, so
    # compare against zero via a subtraction rather than risking a token
    # in a slot nothing has confirmed accepts one.
    d_hi = s.calc(E(hour.item) - E(var("hi")))
    with s.if_(d_hi, ">", 0):
        s.setvar("hi", hour.item)

    d_lo = s.calc(E(var("lo")) - E(hour.item))
    with s.if_(d_lo, ">", 0):
        s.setvar("lo", hour.item)

mean = s.calc(E(var("total")) / E(var("n")))

s.show("Forecast for ", lat, ", ", lon, "\n\n",
       "hours   ", var("n"), "\n",
       "min     ", var("lo"), " C\n",
       "max     ", var("hi"), " C\n",
       "mean    ", mean, " C")

out = sys.argv[1] if len(sys.argv) > 1 else "weather.plist"
s.dump(out)
print("wrote %s -- %d actions" % (out, len(s.acts)))
