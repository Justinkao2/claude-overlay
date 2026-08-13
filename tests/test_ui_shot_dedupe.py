# -*- coding: utf-8 -*-
"""Auto-screenshot dedupe (_dedupe_shots): a byte-identical screen must not be
re-attached — the model already has that exact image in context, and re-sending it
costs measured seconds of TTFT on every message. These drive the REAL _send_or_stop
against the conftest Overlay/FakeWorker and assert on what worker.ask() received.

The safety edges matter more than the happy path. Two layers guard them:

- PENDING-COMMIT: a hash becomes a dedupe baseline only after its turn returns a CLEAN
  result. A turn that errors, is stopped, or never queries at all (/simerror) may never
  have shown the image to the model — its hash must die with the turn.
- INVALIDATION: anything that may have cost the context its screenshots — Clear and
  Compact (at CLICK time, not just on completion — a send can slip into the gap),
  the CLI's automatic compaction (auto_compacted), a fresh session standing in for a
  failed resume (session_replaced / resume_failed / resume_lost), and any error —
  clears the baselines, because a wrong "screen unchanged" note makes the model trust
  an image it does not have."""
import time

import pytest


def _shot_file(tmp_path, name, data=b"PNGbytes-1"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _arm_precapture(ov, path, index=0, primary=True, window=None):
    shot = {"path": str(path), "index": index, "primary": primary}
    if window is not None:
        shot["window"] = window
    ov._precaptured = ([shot], time.monotonic())


def _send(ov, text):
    ov.busy = False                      # FakeWorker never answers; re-arm the send path
    ov._ph_out()
    ov.entry.delete("1.0", "end")
    ov.entry.insert("1.0", text)
    ov._ph_active = False
    ov._send_or_stop()


def _finish_clean(ov):
    """What a successful turn does: clean result (promotes pending hashes) + turn_done."""
    ov._handle("result", {"is_error": False, "subtype": "success", "result": None,
                          "stop_reason": None, "cost": None})
    ov._handle("turn_done", None)


def _asks(ov):
    return [c for c in ov.worker.calls if c[0] == "ask"]


@pytest.fixture
def shooting(overlay):
    ov = overlay
    ov.auto_shot = True
    ov.worker.calls.clear()
    ov._sent_shot_hashes = {}
    ov._pending_shot_hashes = {}
    return ov


class TestDedupe:

    def test_first_send_attaches(self, shooting, tmp_path):
        ov = shooting
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "what's on screen?")
        (_, (text, paths)), = _asks(ov)
        assert paths == [str(p)]
        assert "UNCHANGED" not in text

    def test_identical_bytes_are_not_resent(self, shooting, tmp_path):
        ov = shooting
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "first")
        _finish_clean(ov)
        # A later capture of an unchanged screen: new file, same bytes (the encoder is
        # deterministic for identical pixels — this is exactly what dedupe keys on).
        p2 = _shot_file(tmp_path, "m0_later.png")
        _arm_precapture(ov, p2)
        _send(ov, "follow-up")
        first, second = _asks(ov)
        assert second[1][1] == []                      # no image re-attached
        assert "UNCHANGED" in second[1][0]             # …and the model is told why
        assert "follow-up" in second[1][0]

    def test_changed_bytes_are_attached_again(self, shooting, tmp_path):
        ov = shooting
        _arm_precapture(ov, _shot_file(tmp_path, "a.png", b"frame-1"))
        _send(ov, "first")
        _finish_clean(ov)
        p2 = _shot_file(tmp_path, "b.png", b"frame-2")
        _arm_precapture(ov, p2)
        _send(ov, "second")
        _, second = _asks(ov)
        assert second[1][1] == [str(p2)]
        assert "UNCHANGED" not in second[1][0]

    def test_empty_send_with_unchanged_screen_still_says_something(self, shooting, tmp_path):
        # Bare-Enter with auto-shot on means "look at my screen". With the screen deduped
        # away the request must still carry a usable instruction pointing at the context
        # copy — not the default "look at the ATTACHED screen" with nothing attached.
        ov = shooting
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "first")
        _finish_clean(ov)
        _arm_precapture(ov, _shot_file(tmp_path, "m0_again.png"))
        _send(ov, "")
        _, second = _asks(ov)
        assert second[1][1] == []
        assert "earlier in this conversation" in second[1][0]

    def test_note_never_claims_the_previous_message(self, shooting, tmp_path):
        # By the SECOND deduped turn the copy is two messages back, so the note must not
        # say "previous message" — a wrong location makes the model hunt in the wrong
        # turn (or conclude the screenshot is missing). It also carries an escape hatch:
        # if the image really is gone (e.g. compacted away in a gap no event covered),
        # the model should say so rather than answer from imagination.
        ov = shooting
        _arm_precapture(ov, _shot_file(tmp_path, "m0.png"))
        _send(ov, "first")
        _finish_clean(ov)
        for i, text in enumerate(("second", "third")):
            _arm_precapture(ov, _shot_file(tmp_path, f"same_{i}.png"))
            _send(ov, text)
            _finish_clean(ov)
        third = _asks(ov)[2]
        assert third[1][1] == []
        assert "previous message" not in third[1][0]
        assert "earlier in this conversation" in third[1][0]
        assert "say so" in third[1][0]                 # the anti-hallucination escape hatch

    def test_per_monitor_partial_dedupe(self, shooting, tmp_path):
        ov = shooting
        p0 = _shot_file(tmp_path, "mon0.png", b"left-frame")
        p1 = _shot_file(tmp_path, "mon1.png", b"right-frame")
        ov._precaptured = ([{"path": str(p0), "index": 0, "primary": True},
                            {"path": str(p1), "index": 1, "primary": False}],
                           time.monotonic())
        _send(ov, "both screens")
        _finish_clean(ov)
        p1b = _shot_file(tmp_path, "mon1_new.png", b"right-frame-CHANGED")
        ov._precaptured = ([{"path": str(p0), "index": 0, "primary": True},
                            {"path": str(p1b), "index": 1, "primary": False}],
                           time.monotonic())
        _send(ov, "again")
        _, second = _asks(ov)
        assert second[1][1] == [str(p1b)]              # only the changed monitor went out
        assert "monitor 0" in second[1][0] and "UNCHANGED" in second[1][0]

    def test_manual_snap_is_never_deduped(self, shooting, tmp_path):
        # Snap is an explicit "attach it": auto-shot OFF + pending_shot set. Sending the
        # same bytes twice must attach twice — the user asked for exactly that.
        ov = shooting
        ov.auto_shot = False
        p = _shot_file(tmp_path, "snap.png")
        for text in ("first", "second"):
            ov.pending_shot = [{"path": str(p), "index": 0, "primary": True}]
            _send(ov, text)
            _finish_clean(ov)
        first, second = _asks(ov)
        assert first[1][1] == [str(p)]
        assert second[1][1] == [str(p)]

    def test_legacy_read_mode_is_never_deduped(self, shooting, tmp_path, monkeypatch):
        # IMAGE_INPUT="read" sends PATHS the model must Read — the old file may already
        # be pruned from disk (KEEP_SHOTS), so "use the previous one" could dangle on a
        # path that no longer exists. Every send must name a live path.
        import claude_overlay as co
        monkeypatch.setattr(co, "IMAGE_INPUT", "read")
        ov = shooting
        p = _shot_file(tmp_path, "m0.png")
        for text in ("first", "second"):
            _arm_precapture(ov, p)
            _send(ov, text)
            _finish_clean(ov)
        first, second = _asks(ov)
        assert str(p) in first[1][0] and str(p) in second[1][0]
        assert "UNCHANGED" not in second[1][0]


class TestPendingCommit:
    """A hash may only become a dedupe baseline once its turn PROVED the model saw the
    image (clean result). Everything else must re-attach on the next send."""

    def _prime_unfinished(self, ov, tmp_path):
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "prime")
        ov.worker.calls.clear()

    def _resend_same(self, ov, tmp_path, name="resent.png"):
        _arm_precapture(ov, _shot_file(tmp_path, name))
        _send(ov, "after the event")
        (_, (text, paths)), = _asks(ov)
        return text, paths

    def test_errored_result_does_not_commit(self, shooting, tmp_path):
        # The /simerror-shaped flow: the worker emits an errored result WITHOUT any
        # "error" event and without ever querying Claude — the model never saw the image.
        ov = shooting
        self._prime_unfinished(ov, tmp_path)
        ov._handle("result", {"is_error": True, "subtype": "overloaded_error",
                              "result": None, "stop_reason": None, "cost": None})
        ov._handle("turn_done", None)
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_stopped_turn_does_not_commit(self, shooting, tmp_path):
        # Stop/interrupt ends a turn with turn_done but NO result at all.
        ov = shooting
        self._prime_unfinished(ov, tmp_path)
        ov._handle("turn_done", None)
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_errored_turn_keeps_earlier_committed_baselines(self, shooting, tmp_path):
        # An errored turn removes nothing from the conversation: screenshots committed by
        # EARLIER clean turns are still in context and must keep deduping.
        ov = shooting
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "prime")
        _finish_clean(ov)
        _arm_precapture(ov, _shot_file(tmp_path, "same.png"))
        _send(ov, "errored turn")                      # deduped — nothing new pending
        ov._handle("result", {"is_error": True, "subtype": "overloaded_error",
                              "result": None, "stop_reason": None, "cost": None})
        ov._handle("turn_done", None)
        ov.worker.calls.clear()
        text, paths = self._resend_same(ov, tmp_path)
        assert paths == [] and "UNCHANGED" in text


class TestDedupeMemoryClears:
    """Events after which the context can no longer be trusted to hold the screenshot."""

    def _prime(self, ov, tmp_path):
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "prime")
        _finish_clean(ov)
        ov.worker.calls.clear()

    def _resend_same(self, ov, tmp_path, name="resent.png"):
        _arm_precapture(ov, _shot_file(tmp_path, name))
        _send(ov, "after the event")
        (_, (text, paths)), = _asks(ov)
        return text, paths

    def test_clear_resets_at_click_time(self, shooting, tmp_path):
        # The race that matters: Clear is queued (worker still reconnecting), the user
        # sends before reset_done lands. That send must already re-attach — clearing
        # only on reset_done would let an image-less "unchanged" prompt reach the
        # brand-new session.
        ov = shooting
        self._prime(ov, tmp_path)
        ov.reset()                                     # click time — no reset_done yet
        ov.worker.calls.clear()                        # drop the interrupt/reset records
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_compact_resets_at_click_time(self, shooting, tmp_path):
        # Same race for Compact: queued compaction hasn't produced "compacting" yet
        # (busy still False), a send slips in — it must attach, not point at an image
        # the imminent summary may drop.
        ov = shooting
        self._prime(ov, tmp_path)
        ov.compact_now()
        ov.worker.calls.clear()
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_compact_done_resets(self, shooting, tmp_path):
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("compact_done", None)               # summary may have dropped the image
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_auto_compaction_resets(self, shooting, tmp_path):
        # The CLI compacts on its own mid-stream (compact_boundary → worker emits
        # auto_compacted). Unlike explicit /compact there is no compact_done for it.
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("auto_compacted", None)
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_session_replaced_resets(self, shooting, tmp_path):
        # The worker stood up a FRESH session (resume unsupported by an old SDK).
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("session_replaced", None)
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_resume_failed_and_lost_reset(self, shooting, tmp_path):
        for event in ("resume_failed", "resume_lost"):
            ov = shooting
            ov._sent_shot_hashes = {}
            ov._pending_shot_hashes = {}
            ov.worker.calls.clear()
            self._prime(ov, tmp_path)
            ov._handle(event, None)
            text, paths = self._resend_same(ov, tmp_path, name=f"after_{event}.png")
            assert paths and "UNCHANGED" not in text, event

    def test_any_error_resets(self, shooting, tmp_path):
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("error", "transport died — reconnecting with a fresh session")
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text
