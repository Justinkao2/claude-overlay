"""Tests for the .cmd launchers -- the code that runs before any Python does.

v1.15.1 added a check that `pythonw` was a real interpreter before launching it, and the
check verified the wrong file: the `python.exe` next to it. That is a different binary,
so a machine where `python.exe` was missing or blocked had its perfectly good `pythonw`
thrown away and got `[X] No working Python was found` instead of an app. Nothing in the
Python test suite could see it, because the failure happened before Python started.

So the invariants here are behavioural -- the launcher is actually run against fabricated
PATHs -- rather than assertions about its text. The one that matters is the one that
broke: *the launcher must not dead-end while a usable `pythonw` is sitting on PATH.*
Wording changes freely; that property must not.
"""
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "Start Claude Overlay.cmd")

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe launchers")


def cmd_files():
    return sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".cmd"))


# --------------------------------------------------------------------------------------
# File-format conventions. These .cmd files are shipped and double-clicked, so the two
# things below are not cosmetic: cmd.exe reads a BOM as part of the first command, and it
# decodes the file in the machine's OEM codepage, where a non-ASCII byte can mean
# something different than it did on the author's machine.
#
# Line endings are deliberately NOT asserted. Git translates them per checkout (the
# Windows CI runner and every Windows clone get CRLF from the same LF blobs), so pinning
# them would be pinning an artifact of how the repo was cloned rather than a property of
# the shipped script -- and cmd.exe is happy with either.
# --------------------------------------------------------------------------------------

def test_every_cmd_file_is_ascii_and_bom_free():
    for name in cmd_files():
        raw = open(os.path.join(ROOT, name), "rb").read()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{name}: UTF-8 BOM"
        assert all(b < 128 for b in raw), f"{name}: non-ASCII byte"


def test_interpreter_probes_have_no_parentheses_in_the_payload():
    """cmd counts parentheses when it parses a block and does not reliably respect quotes,
    so `-c "sys.exit(0)"` inside `if ... ( ... )` can break the whole block. `-c "pass"`
    is paren-free on purpose; this keeps the next person from "improving" it."""
    for name in cmd_files():
        text = open(os.path.join(ROOT, name), encoding="ascii").read()
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("rem ") or ' -c "' not in line:
                continue
            payload = line.split(' -c "', 1)[1].split('"', 1)[0]
            assert "(" not in payload and ")" not in payload, (
                f"{name}:{lineno} probe payload {payload!r} contains a parenthesis")


def test_every_interpreter_invocation_goes_through_call():
    """Running a .bat/.cmd from a batch file WITHOUT `call` transfers control and never
    returns, ending the script silently, mid-check. `where pythonw` really can return a
    shim -- pyenv-win and several conda wrappers install one -- so an un-`call`ed probe
    is a launcher that dies with no window and no message on those machines.

    Asserted structurally, because the failure is invisible on any machine whose Python
    is a plain .exe: it would pass every manual test the author could think to run."""
    tokens = ("python ", "pythonw ", "pyw ", "py -3 ", "%PY%", "!PY!", "%%i", "!PYW!",
              "!SIB!", "!RAW!")
    offenders = []
    for name in cmd_files():
        text = open(os.path.join(ROOT, name), encoding="ascii").read()
        for lineno, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            low = s.lower()
            if low.startswith(("rem ", "echo", "::", "where ", "set ", "if ")) or not s:
                continue
            # `start` spawns a new process, so control transfer is not a concern there.
            if low.startswith(("start ", "call ", "for ")) or "start \"\"" in low:
                continue
            if any(t.lower() in low for t in tokens):
                offenders.append(f"{name}:{lineno}: {s}")
    assert not offenders, "interpreter invoked without `call`:\n" + "\n".join(offenders)


def test_the_launcher_never_decides_usability_from_a_different_binary():
    """The defect itself, pinned. The launcher launches `pythonw`, so only `pythonw` can
    tell it whether `pythonw` works. (`update.cmd` may still derive the sibling
    `python.exe` -- pip's output is unreadable under pythonw -- but see the test below:
    it may not let that decide whether an interpreter was found.)"""
    for name in ("Start Claude Overlay.cmd", "Diagnose.cmd"):
        text = open(os.path.join(ROOT, name), encoding="ascii").read()
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("rem "):
                continue
            assert "pythonw.exe=python.exe" not in line, (
                f"{name}:{lineno} judges pythonw by the python.exe beside it")


def test_update_can_fall_back_to_pythonw_itself():
    """update.cmd prefers the sibling python.exe for readable pip output. That preference
    must stay a preference: if the sibling doesn't run, the launcher's own pythonw is
    still the right environment to install into, and refusing is how these machines got
    stuck un-updatable."""
    text = open(os.path.join(ROOT, "update.cmd"), encoding="ascii").read()
    body = [l for l in text.splitlines() if not l.lstrip().startswith("rem ")]
    sibling_line = next(i for i, l in enumerate(body) if "pythonw.exe=python.exe" in l)
    later = "\n".join(body[sibling_line:])
    assert 'if not defined PY if defined PYW set PY="!PYW!"' in later, (
        "update.cmd derives the sibling python.exe but has no fallback to pythonw itself")


# --------------------------------------------------------------------------------------
# Behavioural: run the real launcher against a fabricated PATH.
# --------------------------------------------------------------------------------------

def _working_shim():
    """A `pythonw.bat` that really runs Python -- i.e. exactly the shape pyenv-win and
    several conda wrappers put on PATH, which is also the shape that used to kill the
    launcher outright when the probe was not `call`ed.

    Copying a real pythonw.exe into the temp dir would be more literal, but a
    freshly-written .exe is refused outright on locked-down machines ("Access is
    denied."), and a test that depends on the local endpoint-protection mood is worse
    than no test.

    The last two lines matter: `start` runs a batch file as `cmd /K`, so the console
    would stay open forever and leak a window per run. The probe passes `-c` and needs
    control back (`exit /b`); the real launch gets the script path and closes its window
    (`exit`)."""
    return (f'@"{sys.executable}" %*\n'
            '@if "%~1"=="-c" exit /b %errorlevel%\n'
            '@exit %errorlevel%\n')


def _sandbox(tmp_path, shim_dir, shim_body=None):
    """A copy of the launcher next to a stub app, plus one `pythonw` on a bare PATH.

    `shim_body` defaults to a shim that works; pass one that fails for the cases where
    the launcher is supposed to refuse."""
    app = tmp_path / "app"
    app.mkdir()
    marker = tmp_path / "LAUNCHED.txt"
    (app / "claude_overlay.py").write_text(
        "import os, sys\n"
        "p = os.environ.get('OVERLAY_MARKER')\n"
        "open(p, 'w').write(sys.executable) if p else None\n", encoding="ascii")
    (app / "Start Claude Overlay.cmd").write_bytes(open(LAUNCHER, "rb").read())

    shim = tmp_path / shim_dir
    shim.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    (shim / "pythonw.bat").write_text(shim_body or _working_shim(), encoding="ascii")

    # A bare PATH: System32 only, so `where` and friends still resolve but no real
    # python / py / pyw can rescue the run and blur what is being tested.
    env["PATH"] = f"{shim};{os.path.join(os.environ['SystemRoot'], 'System32')}"
    env["OVERLAY_MARKER"] = str(marker)
    return app, marker, env


_EDR_REFUSAL = "Access is denied."


def _run(app, env, tmp_path):
    """Collect output through a FILE, not a pipe: the launcher's `start` hands its stdout
    handle to the process it spawns, so waiting for pipe EOF would mean waiting for the
    overlay itself to exit.

    The retry is for endpoint protection, not for flaky assertions. Some managed Windows
    machines refuse to execute a .cmd that was written seconds ago until a scan finishes,
    and answer with exactly "Access is denied." and nothing else. That string is
    unambiguous -- the launcher never produces it -- so retrying on it cannot paper over a
    real failure, and if it never clears the test FAILS rather than skipping."""
    log = tmp_path / "out.txt"
    for attempt in range(6):
        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            p = subprocess.run(["cmd", "/c", "call", str(app / "Start Claude Overlay.cmd")],
                               cwd=str(app), env=env, stdin=subprocess.DEVNULL,
                               stdout=fh, stderr=subprocess.STDOUT, timeout=90)
        out = log.read_text(encoding="utf-8", errors="replace")
        if out.strip() != _EDR_REFUSAL:
            return p.returncode, out
        time.sleep(0.5 * (attempt + 1))
    pytest.fail("endpoint protection kept refusing to run the copied launcher "
                f"({_EDR_REFUSAL!r}) -- the launcher itself was never reached")


def _wait_for(marker, seconds=20):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if marker.exists():
            return True
        time.sleep(0.1)
    return False


@windows_only
def test_a_pythonw_with_no_python_exe_beside_it_still_launches(tmp_path):
    """THE regression. This PATH has a working `pythonw` and nothing else -- no
    `python.exe` sibling, no `py`, no `pyw`. v1.15.1 printed "No working Python was
    found" here and started nothing."""
    app, marker, env = _sandbox(tmp_path, "onlypythonw")
    rc, out = _run(app, env, tmp_path)
    assert _wait_for(marker), f"launcher refused a usable pythonw\n--- output ---\n{out}"


@windows_only
def test_the_app_execution_alias_stub_is_still_refused(tmp_path):
    """The case the check was added for, which must keep working: a `pythonw` under
    \\WindowsApps\\ that runs nothing must NOT be launched blind, and the user must be
    told what was found rather than left with a window that never appears."""
    app, marker, env = _sandbox(
        tmp_path, os.path.join("Microsoft", "WindowsApps"), "@exit /b 9009\n")
    rc, out = _run(app, env, tmp_path)
    assert not _wait_for(marker, seconds=3), "launched the alias stub"
    assert "Could not start Claude Overlay" in out
    assert "WindowsApps" in out, (
        "the failure message must show what it actually found, not just that it failed\n"
        f"--- output ---\n{out}")


@windows_only
def test_no_python_at_all_reports_what_it_looked_at(tmp_path):
    app, marker, env = _sandbox(tmp_path, "empty", "@exit /b 9009\n")
    os.remove(tmp_path / "empty" / "pythonw.bat")
    rc, out = _run(app, env, tmp_path)
    assert not _wait_for(marker, seconds=3)
    assert "Could not start Claude Overlay" in out
    assert "(nothing found)" in out, f"give-up path printed no evidence\n{out}"
