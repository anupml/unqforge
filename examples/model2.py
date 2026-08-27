"""The same linear model, rebuilt on sclib. Compare against linreg_gd.plist."""
import sys, os

from shortcutforge import *

DATA = "1,100,8;2,300,20;3,200,17;4,400,29"
LR, EPOCHS = 0.5, 200
EPS = None if False else 1e-9          # stop when the MSE improvement per epoch drops below this
                    # (set to None for a fixed EPOCHS run)
s = SC()

ZERO, ONE, BLANK, EMPTY = s.text("0"), s.text("1"), s.text(""), s.emptydict()
BIG = s.text("1000000000")
for d in ("X", "MU", "SD", "Z", "W", "G"):
    s.setvar(d, EMPTY)
s.setvar("b", ZERO); s.setvar("report", BLANK)
s.setvar("rows", s.split(s.text(DATA), ";"))

with s.foreach(var("rows")) as row:
    s.setvar("R", row.index)
    parts = s.split(row.item, ",")
    with s.foreach(parts) as col:
        s.setvar("Fp1", col.index)
        s.setvar("X", s.setval("X", [row.index, ":", col.index], [col.item]))

s.setvar("F", s.calc(E(var("Fp1")) - 1))
s.setvar("k", s.calc(E(LR) * 2 / E(var("R"))))

with s.repeat(var("F")) as j:
    s.setvar("s1", ZERO); s.setvar("s2", ZERO)
    with s.repeat(var("R")) as r:
        v = s.getval("X", [r.index, ":", j.index])
        s.setvar("s1", s.calc(E(var("s1")) + E(v)))
        s.setvar("s2", s.calc(E(var("s2")) + E(v) * E(v)))
    s.setvar("m", s.calc(E(var("s1")) / E(var("R"))))
    s.setvar("sdj", s.calc(
        (E(var("s2")) / E(var("R")) - E(var("m")) * E(var("m"))) ** 0.5))
    with s.if_gt(var("sdj"), 0) as br:
        s.setvar("sdf", var("sdj"))
        br.otherwise()
        s.setvar("sdf", ONE)
    s.setvar("MU", s.setval("MU", [j.index], [var("m")]))
    s.setvar("SD", s.setval("SD", [j.index], [var("sdf")]))

with s.repeat(var("R")) as r:
    with s.repeat(var("F")) as j:
        x = s.getval("X", [r.index, ":", j.index])
        mu = s.getval("MU", [j.index]); sd = s.getval("SD", [j.index])
        s.setvar("Z", s.setval("Z", [r.index, ":", j.index],
                               [s.calc((E(x) - E(mu)) / E(sd))]))

with s.repeat(var("F")) as j:
    s.setvar("W", s.setval("W", [j.index], "0"))

s.setvar("done", ZERO); s.setvar("prev", BIG); s.setvar("used", ZERO)

with s.repeat(EPOCHS) as ep:
    # Shortcuts has no break, so the epoch body is gated on a flag.
    # Skipped iterations cost 2 actions each. Conditionals do not
    # affect Repeat Item depth, so nothing inside needs renumbering.
    with s.if_(var("done"), "<", 1):
        s.setvar("used", ep.index)
        s.setvar("gb", ZERO); s.setvar("sse", ZERO)
        with s.repeat(var("F")) as j:
            s.setvar("G", s.setval("G", [j.index], "0"))
        with s.repeat(var("R")) as r:
            s.setvar("pred", var("b"))
            with s.repeat(var("F")) as j:
                zz = s.getval("Z", [r.index, ":", j.index])
                ww = s.getval("W", [j.index])
                s.setvar("pred", s.calc(E(var("pred")) + E(ww) * E(zz)))
            y = s.getval("X", [r.index, ":", var("Fp1")])
            s.setvar("err", s.calc(E(var("pred")) - E(y)))
            s.setvar("sse", s.calc(E(var("sse")) + E(var("err")) * E(var("err"))))
            with s.repeat(var("F")) as j:
                zb = s.getval("Z", [r.index, ":", j.index])
                gj = s.getval("G", [j.index])
                s.setvar("G", s.setval("G", [j.index],
                                       [s.calc(E(gj) + E(var("err")) * E(zb))]))
            s.setvar("gb", s.calc(E(var("gb")) + E(var("err"))))
        with s.repeat(var("F")) as j:
            wj = s.getval("W", [j.index]); gg = s.getval("G", [j.index])
            s.setvar("W", s.setval("W", [j.index],
                                   [s.calc(E(wj) - E(var("k")) * E(gg))]))
        s.setvar("b", s.calc(E(var("b")) - E(var("k")) * E(var("gb"))))

        s.setvar("mse", s.calc(E(var("sse")) / E(var("R"))))
        delta = s.calc(E(var("prev")) - E(var("mse")))
        with s.if_(delta, "<", EPS):
            s.setvar("done", ONE)
        s.setvar("prev", var("mse"))

s.setvar("acc", ZERO)
with s.repeat(var("F")) as j:
    wS = s.getval("W", [j.index]); sdS = s.getval("SD", [j.index])
    muS = s.getval("MU", [j.index])
    wo = s.calc(E(wS) / E(sdS))
    s.setvar("acc", s.calc(E(var("acc")) + E(wo) * E(muS)))
    s.setvar("report", s.text(ts(var("report"), "w", j.index, " = ", wo, "\n")))
s.setvar("bfin", s.calc(E(var("b")) - E(var("acc"))))
s.show(var("report"), "b  = ", var("bfin"), "\nMSE = ", var("mse"),
       "\nepochs = ", var("used"))

s.dump("linreg_es.plist")
print("emitted", len(s.acts), "actions, all parameters validated")
