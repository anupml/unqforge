"""unqforge -- generate iOS Shortcuts from Python.

Every action, parameter key and serialization shape this library can
emit was observed in a real shortcut on a real device. Anything else
raises Unverified rather than producing a file that silently misbehaves.

    from unqforge import *

    s = SC()
    q = s.action("is.workflow.actions.ask", WFAskActionPrompt="Search?")
    s.action("is.workflow.actions.setclipboard", WFInput=q)
    s.dump("out.plist")
"""
from .sclib import *          # noqa: F401,F403
from .sclib import __doc__ as _core_doc     # noqa: F401

__version__ = "0.1.0"
