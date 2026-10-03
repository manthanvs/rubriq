"""Entry point. Run this file, not ``app/main.py``.

It exists because of how Python decides what is importable.

``make run`` used to launch ``python -m streamlit run app/main.py``. The ``-m``
form puts the *working directory* on ``sys.path``, so ``app.navigation`` and
``core.config`` resolved and everything worked. A host does not launch it that
way: Streamlit Community Cloud runs the ``streamlit`` console script, which
adds only the directory holding the script it was given. Point that at
``app/main.py`` and the only thing on the path is ``app/`` — so the very first
``from app...`` or ``from core...`` line raises ModuleNotFoundError, and the
app never starts.

Keeping the entry point at the repository root fixes that without any
``sys.path`` manipulation at all: the script's own directory *is* the root, so
Streamlit puts the root on the path by itself. ``streamlit_app.py`` is also the
filename Community Cloud looks for by default.

Every launcher now points here — the Makefile, make.ps1 and the deployment
instructions — so what runs locally is what runs when it is hosted. That is
the actual fix. A deployment-only entry point would have left the two paths
different, which is the arrangement that hid this in the first place.
"""

from app.main import main

main()
