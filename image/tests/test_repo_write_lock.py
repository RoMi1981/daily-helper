"""Concurrent writes to one repo.

The write sequence is pull → change files → commit. Without a lock two writers
interleave: the second pull lands between the first writer's change and its
commit, and the resulting commit carries both — or, worse, the first change is
reverted before it was committed. The lock is what makes the sequence atomic
per repo; these tests fail without it rather than merely covering it.
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.storage import GitStorage  # noqa: E402


def _make_store(repo_id="r1"):
    store = GitStorage.__new__(GitStorage)
    store.repo_id = repo_id
    store._write_lock = threading.RLock()
    return store


def test_transactions_on_one_repo_do_not_interleave():
    store = _make_store()
    events: list[str] = []

    def transaction(name):
        with store.write_lock():
            events.append(f"{name}:start")
            time.sleep(0.02)  # the window a second writer would slip into
            events.append(f"{name}:end")

    threads = [threading.Thread(target=transaction, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every start is immediately followed by its own end.
    for i in range(0, len(events), 2):
        assert events[i].split(":")[0] == events[i + 1].split(":")[0], events


def test_two_repos_are_not_serialised_against_each_other():
    """One slow push must not block writes to an unrelated repo."""
    a, b = _make_store("a"), _make_store("b")
    b_done = threading.Event()

    with a.write_lock():
        t = threading.Thread(target=lambda: (b.write_lock().acquire(), b_done.set()))
        t.start()
        assert b_done.wait(timeout=1.0), "write to a second repo waited on the first repo's lock"
        t.join()


def test_lock_is_reentrant_within_one_transaction():
    """A storage method holding the lock may call another that takes it again."""
    store = _make_store()
    with store.write_lock():
        with store.write_lock():
            pass


def test_lock_is_released_when_the_transaction_raises():
    store = _make_store()
    try:
        with store.write_lock():
            raise RuntimeError("commit failed")
    except RuntimeError:
        pass
    assert store.write_lock().acquire(timeout=0.5), "lock leaked after a failed transaction"


def test_lock_prevents_a_lost_update():
    """The point of the lock, stated as the consequence rather than the
    mechanism: twenty concurrent writers must all end up in the committed
    state. Without it they all read the same base and the last commit wins."""
    store = _make_store()
    committed = {"value": 0}

    def read_state() -> int:
        current = committed["value"]
        time.sleep(0.005)  # the pull → change → commit window
        return current

    def transaction(locked: bool):
        if locked:
            with store.write_lock():
                committed["value"] = read_state() + 1
        else:
            committed["value"] = read_state() + 1

    def run(locked: bool) -> int:
        committed["value"] = 0
        threads = [threading.Thread(target=transaction, args=(locked,)) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return committed["value"]

    assert run(locked=True) == 20
    assert run(locked=False) < 20, "without the lock this test proves nothing"
