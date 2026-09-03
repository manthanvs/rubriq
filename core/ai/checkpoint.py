"""Checkpointer setup and the thread-id scheme — §6.2, §6.3.

``SqliteSaver`` persists graph state per ``thread_id``, so when Streamlit
reruns the script mid-evaluation the graph resumes from its last completed node
instead of restarting. §6.2 calls this the cleanest available answer to
Streamlit's biggest weakness in this app.

**The checkpoint file is separate from ``rubriq.db`` on purpose.** §6.2:
*"Keep the checkpointer's database file separate from rubriq.db so a corrupt
graph checkpoint can be deleted without touching a single mark."* Deleting
``ai_checkpoints.db`` costs you resumability and nothing else.

**The thread id is what distinguishes a resume from a retry**, and fix item 9
warns not to collapse the two:

* a browser refresh re-enters with the *same* ``evaluation_version``, gets the
  same thread, and skips the nodes already done — no duplicate LLM calls;
* a genuine retry increments ``evaluation_version``, so it gets a *new* thread
  and starts clean rather than resuming a poisoned checkpoint forever.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from core.config import REPO_ROOT

#: Deliberately not rubriq.db. See the module docstring.
DEFAULT_CHECKPOINT_PATH = REPO_ROOT / "ai_checkpoints.db"


def thread_id(submission_id: int, evaluation_version: int) -> str:
    """``eval:{submission_id}:{evaluation_version}`` — §6.3, deterministic.

    Deterministic so a resumed run is provably the same run rather than a
    coincidentally similar one.
    """
    return f"eval:{int(submission_id)}:{int(evaluation_version)}"


@contextmanager
def checkpointer(path: Path | None = None) -> Iterator[SqliteSaver]:
    """Open the checkpoint store.

    A context manager because ``SqliteSaver`` owns a connection; leaving it
    open across Streamlit reruns is how you end up with a locked file.
    """
    target = Path(path or DEFAULT_CHECKPOINT_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)

    with SqliteSaver.from_conn_string(str(target)) as saver:
        yield saver
