"""Tests for the .cmd launchers -- the code that runs before any Python does.

v1.15.1 added a check that `pythonw` was a real interpreter before launching it, and the
check verified the wrong file: the `python.exe` next to it. That is a different binary,
so a machine where `python.exe` was missing or blocked had its perfectly good `pythonw`
thrown away and got `[X] No working Python was found` instead of an app. Nothing in the
Python test suite could see it, because the failure happened before Python started.

v1.15.2 fixed that and still walled machines that had Python, because it only ever looked
at PATH -- while setup.cmd installs Python into %LOCALAPPDATA%\\Programs\\Python\\Python3xx\\
and finds it there by SCANNING, since the PATH in its own window is stale. So setup could
print "[OK] The app loads." on a machine the launcher then declared Pythonless.

So the invariants here are behavioural -- the launcher is actually run against fabricated
PATHs -- rather than assertions about its text. The two that matter are the two that
broke: *the launcher must not dead-end while a usable interpreter exists*, on PATH or in
the folder setup.cmd installs into. Wording changes freely; those properties must not.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(ROOT, "Start Claude Overlay.cmd")

# The .cmd files that have to agree about where Python can be found. They are separate
# scripts on purpose (a user may copy just one out of a ZIP), so the shared block is
# duplicated text -- and duplicated text is what drifts. See the identity test below.
SHARES_DISCOVERY = ("Start Claude Overlay.cmd", "Diagnose.cmd", "update-finish.cmd")
BEGIN = "rem ---- BEGIN find-pythonw"
END = "rem ---- END find-pythonw"

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe launchers")


def cmd_files():
    return sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".cmd"))


def read(name):
    return open(os.path.join(ROOT, name), encoding="ascii").read()


def discovery_block(name):
    text = read(name)
    assert BEGIN in text and END in text, f"{name}: missing the find-pythonw markers"
    return text.split(BEGIN, 1)[1].split(END, 1)[0]


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
    tokens = ("python ", "pythonw ", "pyw ", "py -3 ", "%PY%", "!PY!", "%%i", "%%p",
              "%%d", "!PYW!", "!SIB!", "!RAW!")
    # `if`/`for`/`(` only decide WHETHER a command runs, so strip them and judge the
    # command underneath. Skipping such lines wholesale -- as this test first did -- left
    # every probe in the new directory-scanning block unexamined, which is precisely
    # where an un-`call`ed invocation would hide next.
    _if = r'if\s+(?:not\s+)?'
    prefixes = (_if + r'defined\s+\S+', _if + r'errorlevel\s+\d+',
                _if + r'(?:/i\s+)?\S+==\S+',
                r'for\s+/\S+\s+(?:"[^"]*"\s+)?%%\w+\s+in\s+\(.*?\)\s+do',
                r'\(')
    # `start` spawns a new process, so control transfer is not a concern there. `set`,
    # `echo`, `where` and `dir` never execute the interpreter, they only name it.
    harmless = ("call ", "start ", "set ", "echo", "where ", "dir ", "rem ", "::")
    offenders = []
    for name in cmd_files():
        for lineno, line in enumerate(read(name).splitlines(), 1):
            s = line.strip()
            while True:
                m = re.match("(?:%s)\\s*" % "|".join(prefixes), s, re.IGNORECASE)
                if not m or not m.end():
                    break
                s = s[m.end():]
            low = s.lower()
            if not s or low.startswith(harmless):
                continue
            if any(t.lower() in low for t in tokens):
                offenders.append(f"{name}:{lineno}: {s}")
    assert not offenders, "interpreter invoked without `call`:\n" + "\n".join(offenders)


def test_every_script_that_finds_python_finds_it_the_same_way():
    """Three scripts, one question. When they answered it differently the answers were
    silently inconsistent: v1.15.1's sibling-python bug shipped in all three, and
    update.cmd's copy meant an affected machine could not even refresh packages into the
    interpreter its launcher would use. They are separate files (someone may copy just
    one out of a ZIP), so the block is duplicated -- and duplicated text drifts unless
    something compares it."""
    blocks = {name: discovery_block(name) for name in SHARES_DISCOVERY}
    reference = blocks[SHARES_DISCOVERY[0]]
    for name, block in blocks.items():
        assert block == reference, (
            f"{name}'s find-pythonw block has drifted from "
            f"{SHARES_DISCOVERY[0]}'s.\n--- {name} ---\n{block}\n--- reference ---\n{reference}")


def test_the_launcher_searches_where_setup_installs():
    """The v1.15.3 defect, pinned as a contract between two files rather than as a magic
    string. setup.cmd both installs Python into this folder and scans it to find what it
    installed; a launcher that does not look there can refuse to start an install setup
    just declared healthy -- and no message on screen connects the two."""
    setup = read("setup.cmd")
    installdir = r"%LOCALAPPDATA%\Programs\Python"
    assert installdir in setup, (
        "setup.cmd no longer references %s -- update this test and the launcher "
        "together, because the point is that they agree" % installdir)
    for name in SHARES_DISCOVERY:
        assert installdir in discovery_block(name), (
            f"{name} never looks in {installdir}, which is where setup.cmd puts Python")


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


def test_update_does_not_run_git_pull_from_the_file_git_is_replacing():
    """`git pull` overwrites update.cmd while it is running, and cmd.exe reads the script
    it is executing from disk by byte offset -- so afterwards it resumes at that offset
    inside whatever now lives there. It came out right the two times it was watched,
    because the line numbers happened to line up. So the pull must not happen in the copy
    that git can replace: update.cmd re-execs itself out of %TEMP% first."""
    text = read("update.cmd")
    lines = text.splitlines()
    guard = next((i for i, l in enumerate(lines) if '"%~1"=="--from-temp"' in l), None)
    assert guard is not None, "update.cmd no longer re-execs itself from outside the repo"
    pull = next(i for i, l in enumerate(lines)
                if l.strip().startswith("git pull") and not l.lstrip().startswith("rem "))
    assert guard < pull, (
        f"update.cmd:{pull + 1} runs `git pull` before handing off to the copy in %TEMP% "
        f"(guard at line {guard + 1}), so git can rewrite the script mid-run again")


def test_the_post_pull_half_is_a_separate_file():
    """update.cmd's own body cannot be trusted after the pull, and the post-pull work
    should run the version that was just DOWNLOADED rather than the one being replaced.
    Both of those need it to live in its own file."""
    finish = os.path.join(ROOT, "update-finish.cmd")
    assert os.path.exists(finish), "update-finish.cmd is gone; update.cmd calls it"
    text = read("update.cmd")
    assert 'call "%REPO%\\update-finish.cmd"' in text, (
        "update.cmd no longer hands off to update-finish.cmd")
    # The hand-off must be ABSOLUTE. The driver runs from %TEMP%, so %~dp0 is the wrong
    # folder there, and `call "update-finish.cmd"` fails outright: cmd looks up a quoted
    # bare filename as a literal program name.
    assert '%~dp0update-finish.cmd' not in text, (
        "update.cmd resolves update-finish.cmd via %~dp0, which is %TEMP% for the driver")


def test_nothing_installs_a_hardcoded_package_list():
    """requirements.txt is the single source of the version list. It used to say
    `claude-agent-sdk>=0.2.87` while setup.cmd and update.cmd both ran
    `pip install --upgrade claude-agent-sdk pillow keyboard` -- so the file constrained
    nobody, every user got whatever PyPI shipped that morning, and this machine stayed on
    the floor version. A pin that the install path ignores is decoration."""
    pattern = re.compile(r"pip\s+install[^\r\n]*?(claude-agent-sdk|pillow|keyboard)")
    offenders = []
    for name in sorted(os.listdir(ROOT)):
        if not name.lower().endswith((".cmd", ".py")) or name == os.path.basename(__file__):
            continue
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        for lineno, line in enumerate(
                open(path, encoding="utf-8").read().splitlines(), 1):
            if pattern.search(line) and "-r " not in line:
                offenders.append(f"{name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "install command names packages instead of -r requirements.txt:\n"
        + "\n".join(offenders))


def test_the_sdk_is_pinned_not_floored():
    """The asymmetry this closes: with a bare `>=` plus `--upgrade`, every colleague gets
    whatever PyPI published this morning while the author's machine sits on the version it
    first installed -- so a breaking release hits all of them at once, on a machine that
    cannot reproduce it. Colleagues are not the canary."""
    lines = [l.strip() for l in read("requirements.txt").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    sdk = next((l for l in lines if l.lower().startswith("claude-agent-sdk")), None)
    assert sdk, "claude-agent-sdk is missing from requirements.txt"
    assert "==" in sdk, (
        f"claude-agent-sdk must be pinned, got {sdk!r}. The SDK is pre-1.0 and ships "
        "several releases a week; upgrading has to be a deliberate, tested act.")


def test_update_can_fall_back_to_pythonw_itself():
    """update-finish.cmd prefers the sibling python.exe for readable pip output. That
    preference must stay a preference: if the sibling doesn't run, the launcher's own
    pythonw is still the right environment to install into, and refusing is how these
    machines got stuck un-updatable."""
    text = read("update-finish.cmd")
    body = [l for l in text.splitlines() if not l.lstrip().startswith("rem ")]
    sibling_line = next(i for i, l in enumerate(body) if "pythonw.exe=python.exe" in l)
    later = "\n".join(body[sibling_line:])
    assert 'if not defined PY if defined PYW set PY="!PYW!"' in later, (
        "update-finish.cmd derives the sibling python.exe but has no fallback to pythonw")


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

    # The launcher also searches OFF PATH now, so point every one of those roots at an
    # empty folder. Otherwise the author's own C:\Python3xx would satisfy the tests that
    # assert a refusal, and they would pass for a reason that has nothing to do with the
    # case under test -- on the CI runner, where no such folder exists, they would fail.
    for var in ("LOCALAPPDATA", "ProgramFiles", "SystemDrive"):
        blank = tmp_path / ("no_" + var.lower())
        blank.mkdir(exist_ok=True)
        env[var] = str(blank)
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
    # "No Python on PATH" and "no Python on this PC" need different fixes, and the report
    # is the only thing that separates them for whoever is reading it.
    assert "OFF PATH" in out, f"report cannot distinguish PATH from install\n{out}"


def _fabricate_offpath_python(tmp_path):
    """A real, working interpreter at the exact path setup.cmd installs to, reachable
    ONLY by scanning that folder -- never through PATH.

    It is a copy of pythonw.exe with its DLLs plus a `pythonw._pth` naming the real
    stdlib, which is the documented way to pin a relocated interpreter's search path.
    Copying the whole install would be more literal and costs ~100 MB per run; a junction
    to the real one would let a stray rmtree walk into somebody's Python installation.

    `sys.base_prefix`, not `dirname(sys.executable)`: inside a virtualenv the latter is
    `.../Scripts`, whose `pythonw.exe` is a stub that redirects to the base interpreter.
    Copying that stub next to a `._pth` produced a process that hung until the timeout --
    a test failure that said nothing about the launcher."""
    home = sys.base_prefix
    pyw = os.path.join(home, "pythonw.exe")
    if not os.path.exists(pyw):
        pytest.fail(f"test premise unavailable: no pythonw.exe in {home}")
    dst = tmp_path / "lad" / "Programs" / "Python" / os.path.basename(home)
    dst.mkdir(parents=True)
    shutil.copy2(pyw, str(dst / "pythonw.exe"))
    for dll in (glob.glob(os.path.join(home, "python3*.dll"))
                + glob.glob(os.path.join(home, "vcruntime*.dll"))):
        shutil.copy2(dll, str(dst))
    (dst / "pythonw._pth").write_text(
        "%s\n%s\n%s\n" % (os.path.join(home, "Lib"), os.path.join(home, "DLLs"),
                          os.path.join(home, "Lib", "site-packages")), encoding="ascii")
    return dst / "pythonw.exe"


@windows_only
def test_python_where_setup_installs_it_but_not_on_path_still_launches(tmp_path):
    """THE v1.15.3 regression, reproduced end to end: PATH holds nothing but dead
    App-execution-alias stubs, and a working Python sits where setup.cmd puts it.
    v1.15.2 printed "no Python on PATH ran" here and started nothing -- on a machine
    where setup.cmd had already reported success."""
    app, marker, env = _sandbox(
        tmp_path, os.path.join("Microsoft", "WindowsApps"), "@exit /b 9009\n")
    fabricated = _fabricate_offpath_python(tmp_path)
    try:
        rc = subprocess.run([str(fabricated), "-c", "pass"], timeout=30).returncode
    except subprocess.TimeoutExpired:
        rc = "hung"
    if rc != 0:
        pytest.fail("test premise unavailable: the relocated interpreter at "
                    f"{fabricated} came back {rc!r}, so this test cannot say anything "
                    "about the launcher either way")

    env["LOCALAPPDATA"] = str(tmp_path / "lad")
    # Neutralise the launcher's OTHER off-PATH candidates, so only the folder setup.cmd
    # installs into can rescue this run and a pass cannot come from the test machine
    # happening to have C:\Python3xx.
    env["ProgramFiles"] = str(tmp_path / "noprogs")
    env["SystemDrive"] = str(tmp_path / "nodrive")

    rc, out = _run(app, env, tmp_path)
    assert _wait_for(marker), (
        "launcher walled a machine whose Python is exactly where setup.cmd puts it"
        f"\n--- output ---\n{out}")
    assert marker.read_text().lower() == str(fabricated).lower(), (
        f"launched something other than the discovered interpreter: {marker.read_text()}")
