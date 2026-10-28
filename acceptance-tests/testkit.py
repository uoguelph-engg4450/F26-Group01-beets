"""ENGG4450 Group 1 - acceptance test kit for beets changes #4452 and #5998.

Run every command from inside this folder, with the beets virtual
environment activated. See README.md for the full walkthrough.

    python testkit.py prepare CR1-TC1   set up one test (fresh library + config)
    python testkit.py check-cover       inspect the cover art in the library
    python testkit.py check-cover FILE  inspect any image file
    python testkit.py run-all           run all 5 tests automatically (optional)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
WS = KIT / "workspace"
SONG = KIT / "assets" / "song.mp3"

# Tag used for the sample track. LRCLib matches on artist, title and length;
# assets/song.mp3 is 251 s long to match the studio recording.
ARTIST, TITLE, ALBUM = "Supertramp", "The Logical Song", "Breakfast in America"

CR1_CONFIG = """\
directory: {ws}/library
library: {ws}/library.db
plugins: fetchart embedart
fetchart:
  sources: filesystem
  cover_format: {fmt}
  maxwidth: 1600
embedart:
  auto: yes
"""

CR2_CONFIG = """\
directory: {ws}/library
library: {ws}/library.db
plugins: lyrics
lyrics:
  auto: yes
  sources: [{sources}]
"""

TESTS = {
    "CR1-TC1": "Transparent PNG cover is saved as JPEG with a white background",
    "CR1-TC2": "The original cover image in the album folder is not deleted",
    "CR1-TC3": "The art embedded in the song file is also a correct JPEG",
    "CR2-TC1": "Import finishes when a lyrics site fails (older requests library)",
    "CR2-TC2": "Lyrics still download normally (current requests library)",
}


# ----------------------------------------------------------------- helpers
def posix(p: Path) -> str:
    return p.as_posix()


def requests_version() -> tuple[int, int]:
    import requests

    major, minor = requests.__version__.split(".")[:2]
    return int(major), int(minor)


def requests_is_old() -> bool:
    # requests.JSONDecodeError was added in requests 2.27
    return requests_version() < (2, 27)


def reset_workspace() -> None:
    if WS.exists():
        shutil.rmtree(WS)
    WS.mkdir()


def write_config(text: str) -> None:
    (WS / "config.yaml").write_text(text, encoding="utf-8")


def add_song(folder: Path, song: Path = SONG) -> None:
    from mediafile import MediaFile

    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "song.mp3"
    shutil.copy(song, dest)
    if song == SONG:
        mf = MediaFile(str(dest))
        mf.artist = mf.albumartist = ARTIST
        mf.title, mf.album, mf.track = TITLE, ALBUM, 1
        mf.save()


def make_png(path: Path, size: int, transparent_corner: bool) -> None:
    from PIL import Image

    if transparent_corner:
        im = Image.new("RGBA", (size, size), (200, 30, 30, 255))
        im.paste((0, 0, 0, 0), (0, 0, size // 4, size // 4))
    else:
        im = Image.new("RGB", (size, size), (200, 30, 30))
    im.save(path)


def describe(path: Path) -> str:
    from PIL import Image

    with Image.open(path) as im:
        corner = im.convert("RGB").getpixel((0, 0))
        colour = (
            "white" if min(corner) >= 245
            else "black" if max(corner) <= 10
            else f"rgb{corner}"
        )
        return (
            f"{path.name}: format={im.format}  size={im.size[0]}x{im.size[1]}"
            f"  top-left corner={colour}"
        )


def beetsdir_hint() -> None:
    current = os.environ.get("BEETSDIR")
    if current and Path(current).resolve() == WS.resolve():
        return
    print("\n  ! BEETSDIR is not pointing at this kit's workspace yet.")
    print("    Run this once in this terminal before any 'beet' command:")
    if os.name == "nt":
        print(f'      PowerShell:  $env:BEETSDIR = "{WS}"')
        print(f"      cmd.exe:     set BEETSDIR={WS}")
    else:
        print(f'      export BEETSDIR="{WS}"')


# ----------------------------------------------------------------- prepare
def prepare(test_id: str, song: Path = SONG, quiet: bool = False) -> str:
    """Create a fresh workspace for one test. Returns the command to run."""
    test_id = test_id.upper()
    if test_id not in TESTS:
        sys.exit(f"Unknown test {test_id}. Choose one of: {', '.join(TESTS)}")

    reset_workspace()
    ws = posix(WS)
    note = ""

    if test_id in ("CR1-TC1", "CR1-TC3"):
        write_config(CR1_CONFIG.format(ws=ws, fmt="JPEG"))
        add_song(WS / "album1", song)
        make_png(WS / "album1" / "front.png", 2000, transparent_corner=True)
        cmd = "beet -v import -A workspace/album1"
    elif test_id == "CR1-TC2":
        write_config(CR1_CONFIG.format(ws=ws, fmt="JPEG"))
        add_song(WS / "album2", song)
        make_png(WS / "album2" / "front.png", 1000, transparent_corner=False)
        cmd = "beet -v import -A workspace/album2"
    else:
        sources = {"CR2-TC1": "tekstowo", "CR2-TC2": "lrclib"}[test_id]
        write_config(CR2_CONFIG.format(ws=ws, sources=sources))
        add_song(WS / "music", song)
        cmd = "beet -v import -A workspace/music"
        wants_old = test_id == "CR2-TC1"
        if wants_old and not requests_is_old():
            note = (
                "  ! This test needs the OLDER requests library the bug report used.\n"
                '    Run:  pip install "requests==2.26.0"\n'
                "    (pip will print a dependency-conflict warning - that is expected.)"
            )
        if not wants_old and requests_is_old():
            note = (
                "  ! This test needs the CURRENT requests library.\n"
                '    Run:  pip install -U "requests>=2.32.5"'
            )

    if not quiet:
        print(f"Prepared {test_id}: {TESTS[test_id]}")
        print(f"  Workspace: {WS}")
        if note:
            print(note)
        beetsdir_hint()
        print(f"\n  Now run:\n    {cmd}")
    return cmd


# ------------------------------------------------------------- check-cover
def check_cover(arg: str | None) -> None:
    if arg:
        print(describe(Path(arg)))
        return
    covers = sorted((WS / "library").rglob("cover.*")) if (WS / "library").exists() else []
    if not covers:
        print("No cover.* file found in workspace/library (no cover art was saved).")
        return
    for c in covers:
        print(describe(c))


# ----------------------------------------------------------------- run-all
def run_all(song: Path) -> None:
    """Run every test automatically and print PASS/FAIL (optional helper)."""
    env = dict(os.environ, BEETSDIR=str(WS), PYTHONIOENCODING="utf-8")
    beet = [sys.executable, "-m", "beets"]
    results: list[tuple[str, str, str]] = []

    def run(cmd: list[str], extra_env: dict | None = None) -> tuple[int, str]:
        p = subprocess.run(
            cmd, cwd=KIT, env={**env, **(extra_env or {})},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout + p.stderr

    def pip(spec: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", spec],
            capture_output=True,
        )

    def record(tid: str, ok: bool, detail: str) -> None:
        results.append((tid, "PASS" if ok else "FAIL", detail))
        print(f"  {tid}: {'PASS' if ok else 'FAIL'} - {detail}")

    def cover() -> Path | None:
        found = sorted((WS / "library").rglob("cover.*"))
        return found[0] if found else None

    print("Running CR1 (#4452 artwork) ...")
    # CR1-TC1 + TC3
    prepare("CR1-TC1", song, quiet=True)
    code, out = run(beet + ["import", "-A", "workspace/album1"])
    c = cover()
    d = describe(c) if c else "no cover saved"
    record("CR1-TC1", bool(c) and c.suffix == ".jpg" and "format=JPEG" in d
           and "corner=white" in d and "Traceback" not in out, d)
    code, out = run(beet + ["extractart", "-a", "-o", "workspace/embedded"])
    emb = sorted(WS.glob("embedded.*"))
    d = describe(emb[0]) if emb else "no embedded art found"
    record("CR1-TC3", bool(emb) and "format=JPEG" in d and "corner=white" in d, d)
    # CR1-TC2
    prepare("CR1-TC2", song, quiet=True)
    run(beet + ["import", "-A", "workspace/album2"])
    left = sorted(p.name for p in (WS / "album2").iterdir())
    c = cover()
    ok = "front.png" in left and bool(c) and "format=JPEG" in describe(c)
    record("CR1-TC2", ok, f"source folder now holds {left}; "
           + (describe(c) if c else "no cover saved"))
    print("Running CR2 (#5998 lyrics) - switching to requests 2.26.0 ...")
    pip("requests==2.26.0")
    prepare("CR2-TC1", song, quiet=True)
    code, out = run(beet + ["-v", "import", "-A", "workspace/music"])
    _, listing = run(beet + ["ls"])
    crashed = "Traceback" in out or "AttributeError" in out
    imported = TITLE in listing
    record("CR2-TC1", imported and not crashed,
           f"imported={imported} crashed={crashed}")

    print("Restoring current requests ...")
    pip("requests>=2.32.5")
    prepare("CR2-TC2", song, quiet=True)
    code, out = run(beet + ["-v", "import", "-A", "workspace/music"])
    _, lyr = run(beet + ["ls", "-f", "$lyrics"])
    crashed = "Traceback" in out
    record("CR2-TC2", bool(lyr.strip()) and not crashed,
           "lyrics downloaded" if lyr.strip() else
           "no lyrics returned (check your internet connection)")

    passed = sum(r[1] == "PASS" for r in results)
    print(f"\n{passed}/{len(results)} passed")
    (KIT / "results.txt").write_text(
        "\n".join(f"{t}\t{s}\t{d}" for t, s, d in results) + "\n", encoding="utf-8"
    )
    print(f"Saved to {KIT / 'results.txt'}")


#main
def main(argv: list[str]) -> None:
    song = SONG
    if "--song" in argv:
        i = argv.index("--song")
        song = Path(argv[i + 1]).resolve()
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        return
    cmd, *rest = argv
    if cmd == "prepare" and rest:
        prepare(rest[0], song)
    elif cmd == "check-cover":
        check_cover(rest[0] if rest else None)
    elif cmd == "run-all":
        run_all(song)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
