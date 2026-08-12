# -*- coding: utf-8 -*-
"""Auto-screenshot dedupe (_dedupe_shots): a byte-identical screen must not be
re-attached — the model already has that exact image in context, and re-sending it
costs measured seconds of TTFT on every message. These drive the REAL _send_or_stop
against the conftest Overlay/FakeWorker and assert on what worker.ask() received.

The safety edges matter more than the happy path: anything that may have cost the
conversation its previous screenshot (Clear, compaction, ANY error) must clear the
dedupe memory, because a wrong "screen unchanged" note makes the model trust an
image it no longer has."""
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


def _asks(ov):
    return [c for c in ov.worker.calls if c[0] == "ask"]


@pytest.fixture
def shooting(overlay):
    ov = overlay
    ov.auto_shot = True
    ov.worker.calls.clear()
    ov._sent_shot_hashes = {}
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
        _arm_precapture(ov, _shot_file(tmp_path, "m0_again.png"))
        _send(ov, "")
        _, second = _asks(ov)
        assert second[1][1] == []
        assert "previous message" in second[1][0]

    def test_per_monitor_partial_dedupe(self, shooting, tmp_path):
        ov = shooting
        p0 = _shot_file(tmp_path, "mon0.png", b"left-frame")
        p1 = _shot_file(tmp_path, "mon1.png", b"right-frame")
        ov._precaptured = ([{"path": str(p0), "index": 0, "primary": True},
                            {"path": str(p1), "index": 1, "primary": False}],
                           time.monotonic())
        _send(ov, "both screens")
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
        first, second = _asks(ov)
        assert first[1][1] == [str(p)]
        assert second[1][1] == [str(p)]


class TestDedupeMemoryClears:

    def _prime(self, ov, tmp_path):
        p = _shot_file(tmp_path, "m0.png")
        _arm_precapture(ov, p)
        _send(ov, "prime")
        ov.worker.calls.clear()

    def _resend_same(self, ov, tmp_path, name="resent.png"):
        _arm_precapture(ov, _shot_file(tmp_path, name))
        _send(ov, "after the event")
        (_, (text, paths)), = _asks(ov)
        return text, paths

    def test_clear_resets(self, shooting, tmp_path):
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("reset_done", None)                 # worker confirmed a fresh session
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_compact_resets(self, shooting, tmp_path):
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("compact_done", None)               # summary may have dropped the image
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text

    def test_any_error_resets(self, shooting, tmp_path):
        ov = shooting
        self._prime(ov, tmp_path)
        ov._handle("error", "transport died — reconnecting with a fresh session")
        text, paths = self._resend_same(ov, tmp_path)
        assert paths and "UNCHANGED" not in text
