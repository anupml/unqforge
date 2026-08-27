"""Ask -> HTTP -> parse JSON -> clipboard.

Not one of these actions has a hand-written method in sclib. All of them
came out of decompiled shortcuts.
"""
import sys, os

from shortcutforge import *

A = "is.workflow.actions."
s = SC()

query = s.action(A + "ask",
                 WFAskActionPrompt="Search term?",
                 WFAllowsMultilineText=False)

enc = s.action(A + "urlencode", WFInput=ts(query), WFEncodeMode="Decode")

resp = s.action(A + "downloadurl",
                WFURL=ts("https://api.example.com/search?q=", enc),
                WFHTTPMethod="POST",
                ShowHeaders=False)

# dotted keys walk nested JSON in one action -- learned from UNQ MUSIC
results = s.action(A + "getvalueforkey",
                   WFDictionaryKey="data.results",
                   WFInput=att(resp))

n = s.action(A + "count", Input=att(results), WFCountType="Lines")

with s.if_(n, "<", 1):
    s.action(A + "exit")

s.action(A + "setclipboard", WFInput=att(results))
s.show("Found ", n, " results, copied to clipboard")

s.dump("api_demo.plist")
print("emitted", len(s.acts), "actions -- every parameter validated")
