# ENGG*4450 Assignment 2 — Lyrics and artwork change requests

## Scope and development process

- Investigated upstream [issue #5998](https://github.com/beetbox/beets/issues/5998), [issue #4452](https://github.com/beetbox/beets/issues/4452), and [proposed PR #7017](https://github.com/beetbox/beets/pull/7017).
- Starting commit: `ba4c68b09497f71371b4cbc13957316add2a5f83`. The working tree was clean on `main`.
- Created local branch `fix/engg4450-lyrics-artwork` before editing. No commits, pushes, pull requests, or merges were performed.
- Inspected package dependencies, existing tests, plugin interfaces, and shared HTTP/image helpers. Implemented and tested the lyrics fix before modifying artwork production code.
- Added regression tests and observed failures before each fix. Used mocked HTTP responses and generated image files, with no dependence on live lyrics or artwork sites.
- Installed development dependencies only into the repository's ignored `.venv`. Logs, XML results, baseline snapshot, and acceptance artifacts are in ignored `.reports`.
- AI disclosure: Codex investigated the code and upstream reports, authored these local changes and tests, ran validation, and drafted this report under the user's instructions. The group should review and understand the changes before submitting the assignment. The repository's upstream AI policy should be considered before any separate upstream contribution.

## Issue #5998 — Lyrics error handling

### Root cause

An HTTP 403 is raised by `TimeoutAndRetrySession.request()` through `raise_for_status()`. `RequestHandler.handle_http_error()` re-raises status codes without a special mapping. Lyrics providers run inside `LyricsRequestHandler.handle_request()` so request failures should be logged and fetching should continue.

However, the first exception clause referenced `requests.JSONDecodeError`. When that top-level attribute is unavailable, Python raises `AttributeError` while evaluating the exception handler. This masks the original HTTP failure and escapes the import stage. It can also mask timeouts and JSON parsing failures.

The issue was reported against an older environment. This checkout requires `requests>=2.32.5`, where the top-level alias normally exists. Regression tests deliberately remove that alias to reproduce the reported compatibility condition; they do not downgrade the whole application to an unsupported Requests release.

### Change

In `beetsplug/lyrics.py`, `LyricsRequestHandler.handle_request()` now catches `json.JSONDecodeError`, using the JSON implementation exposed by `requests.compat`. This matches Requests' selected decoder, whether standard-library JSON or optional simplejson, without depending on the top-level Requests alias. The existing `requests.RequestException` handler remains intact.

Malformed JSON still receives its specific warning. HTTP failures and timeouts receive request warnings, and `get_lyrics()` can try the next provider. This does not bypass a provider's 403 or guarantee that lyrics will be available.

### Regression tests

Added to `test/plugins/test_lyrics.py`, class `TestLyricsPlugin`:

- `test_import_request_error_without_top_level_json_error`: three cases invoke the actual lyrics import hook with a mocked 403, malformed JSON, or timeout. Assert that it returns without crashing, leaves missing lyrics empty, and logs the expected warning.
- `test_failed_provider_falls_back`: first provider returns 403; the next returns lyrics. Assert the result and provider identity.

Before the fix: **4 failed**, all with the missing `requests.JSONDecodeError` AttributeError. After the fix, the lyrics plugin and lyrics utility suites: **136 passed, 16 skipped**. The skipped cases use live providers and were intentionally not enabled.

## Issue #4452 — Artwork format conversion

### Investigation and root causes

`RemoteArtSource.fetch_image()` determines the downloaded file's type from its content, falling back to Content-Type only if detection fails. It already corrects misleading filename extensions and HTTP headers. That logic did not need changing.

`Candidate._validate()` then checks size and requested format, while `Candidate.resize()` performs the required operations. Unlike the older issue report, this checkout already loops through downscaling and reformatting. The new RGB download tests confirmed that combined operation worked before the fix.

Remaining defects reproduced locally:

1. Detected `JPEG` was compared literally with configuration values such as `jpeg` or `jpg`. This unnecessarily converted already-correct images.
2. `PILBackend.convert_format()` directly saved the source image as JPEG. Pillow cannot save RGBA, LA, or palette images directly as JPEG. The backend caught the error and returned the original PNG, leaving the requested conversion unfulfilled.
3. `ArtResizer.reformat()` derived an output filename beside the source and deleted the source following a successful conversion. It could overwrite existing sibling artwork. For same-extension conversion, the destination could even be the source; a partial write could corrupt it before failure was reported. Failed output files were not cleaned up.
4. ImageMagick conversion did not explicitly flatten alpha onto a chosen background, and an operating-system failure launching the converter escaped its error handler.

### Changes and exact production functions

| File | Function | Change |
|---|---|---|
| `beetsplug/fetchart.py` | `Candidate._validate()` | Compare uppercase format names, treating JPG and JPEG as equivalent. Undetected formats still request conversion. |
| `beets/util/artresizer.py` | `PILBackend.convert_format()` | For JPEG output, composite transparent images onto white and convert other unsupported modes to RGB. Keep existing JPEG-compatible RGB, L, and CMYK modes. |
| `beets/util/artresizer.py` | `IMBackend.convert_format()` | Explicitly flatten alpha onto white for JPEG; log and return the original path on command failure or OSError. |
| `beets/util/artresizer.py` | `ArtResizer.reformat()` | Write to a uniquely allocated temporary file with the requested extension. Preserve the source, and remove failed/partial temporary output, including when the backend raises. |

The proposed PR was used as a reference, not applied wholesale. Changes to candidate dimension caching, extra deinterlace passes, and intermediate-file deletion were not necessary for the reproduced conversion defects and were left out to keep the change focused.

### Regression tests

Added to `test/plugins/test_art.py`, class `TestCoverFormat`:

- `test_already_jpeg`: `jpg`, `jpeg`, `JPEG`, and mixed-case values must avoid reformatting and preserve the original bytes.
- `test_downloaded_png_to_jpeg`: real RGB/RGBA PNG bytes returned by mocked HTTP, deliberately with a JPEG filename and Content-Type. Verify PNG content detection followed by actual JPEG encoding, with and without downscaling.

Added to `test/util/test_art_resize.py`:

- `TestArtworkConversion.test_png_to_jpeg`: RGB, RGBA, LA, and transparent palette PNGs. Verify actual JPEG content, white transparent pixels, original preservation, and preservation of existing sibling artwork.
- `TestArtworkConversion.test_failed_conversion_preserves_files`: a backend writes partial output then returns failure or raises. Verify byte-for-byte preservation of the original and removal of the partial output, even for same-extension conversion.
- `TestImageMagickConversion.test_alpha_options`: JPEG gets explicit white/alpha-removal options; PNG does not.
- `TestImageMagickConversion.test_conversion_failure`: process exit failure and executable-launch OSError return the source path.

Before the fix: the first artwork regression run had **11 failed, 3 passed**; the additional ImageMagick command tests had **3 failed, 2 passed**. All **19** new artwork cases pass after the fix. Actual ImageMagick execution was unavailable; those new tests mock the process call. Pillow tests perform real encoding and decode the result to verify its contents.

## Validation results

Environment: Windows, Python 3.11.9, pytest 9.1.1, Requests 2.34.2, Pillow 13.0.0, mediafile 0.17.0. Dependencies satisfy the declared package constraints; this was not an exact `uv.lock` environment.

| Check | Actual result | Evidence in `.reports/` |
|---|---|---|
| Lyrics regressions before fix | 4 failed | `lyrics-before.xml` |
| Artwork regressions before fix | 11 failed, 3 passed | `art-before.xml` |
| ImageMagick regressions before fix | 3 failed, 2 passed | `im-before.xml` |
| Final focused suites | **238 passed, 18 skipped** | `focused-final.xml`, `focused-final.log` |
| Broader applicable suites | **1,122 passed, 53 skipped** | `broader-final.xml`, `broader-final.log` |
| Ruff lint and formatting | Passed for all six modified Python files | Command output |
| Complete offline import acceptance | Passed | `acceptance.py`, `acceptance.log` |

The broader run covers autotagging, database core, library models, utilities, importer behavior, shared HTTP handling, lyrics, fetchart, and embedart. Skips include live lyrics providers, unavailable ImageMagick/ffmpeg/archive tools, platform-specific functionality, and existing placeholder tests.

Initial wider runs failed color assertions because the host sets `NO_COLOR=1`. All 12 color failures were reproduced against an untouched archive of the starting commit. Unsetting that variable only for the test process made all of them pass, without source changes.

Full repository collection was attempted but stopped with eight collection errors due to absent optional dependencies: requests-oauthlib, python3-discogs-client, pylast, python-mpd2, pyxdg, titlecase, and Flask. The applicable subset above passed; the entire repository suite is not claimed to pass.

### Reproduce the final test runs

From the repository root, using PowerShell:

```powershell
# Setup on a fresh checkout; omit creation/install when .venv already exists.
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[lyrics,fetchart]' pytest pytest-mock pytest-factoryboy requests-mock responses ruff

# Isolate configuration; color tests expect color output to be available.
Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue
$env:BEETSDIR = Join-Path (Get-Location) '.reports\beets-config'
New-Item -ItemType Directory -Force $env:BEETSDIR | Out-Null

# Focused suites.
.\.venv\Scripts\python.exe -m pytest test/plugins/test_lyrics.py test/util/test_lyrics.py test/plugins/test_art.py test/plugins/test_fetchart.py test/util/test_art_resize.py -o cache_dir=.reports/pytest_cache

# Broader applicable suite.
.\.venv\Scripts\python.exe -m pytest test/autotag test/dbcore test/library test/util test/test_importer.py test/plugins/utils/test_requests.py test/plugins/test_lyrics.py test/plugins/test_art.py test/plugins/test_fetchart.py test/plugins/test_embedart.py -o cache_dir=.reports/pytest_cache
```

Do not set `LYRICS_UPDATED=true` or enable live integration tests for this offline verification.

## Customer acceptance tests

Use the setup above. Each command runs a reproducible scenario with controlled inputs, without relying on an external provider being online or returning a particular response.

| Scenario and reproducible command | Expected customer-visible result | Actual result |
|---|---|---|
| `python -m pytest test/plugins/test_lyrics.py -k without_top_level_json_error` | Import hook survives 403, timeout, and malformed JSON; missing lyrics stay empty and warnings explain the failure. | 3 passed |
| `python -m pytest test/plugins/test_lyrics.py -k failed_provider_falls_back` | A blocked first provider does not prevent lyrics from the next provider. | 1 passed |
| `python -m pytest test/plugins/test_art.py -k test_downloaded_png_to_jpeg` | Downloaded ordinary/transparent PNG becomes actual JPEG; requested downscaling also happens, even with misleading server headers. | 4 passed |
| `python -m pytest test/plugins/test_art.py -k test_already_jpeg` | Existing JPEG artwork is left intact for all supported JPEG spellings. | 4 passed |
| `python -m pytest test/util/test_art_resize.py -k test_png_to_jpeg` | Transparent PNGs convert to JPEG on white; source and existing sibling artwork remain intact. | 4 passed |
| `python -m pytest test/util/test_art_resize.py -k test_failed_conversion_preserves_files` | Failed conversion preserves original artwork and removes partial temporary output. | 2 passed |

In this table, replace `python` with `.\.venv\Scripts\python.exe` and add `-o cache_dir=.reports/pytest_cache` on Windows.

An additional end-to-end acceptance check invoked the actual `beet import` CLI entry point with both plugins enabled. It copied the repository's MP3 fixture into an isolated directory, generated transparent PNG artwork, disabled autotagging to avoid metadata network calls, and mocked LRCLib's search response as 403 while removing the Requests alias. The import completed, the database contained one song with no lyrics, the album artwork was a 16x16 JPEG with white pixels, and the source PNG was unchanged. To reproduce in this workspace:

```powershell
.\.venv\Scripts\python.exe .reports/acceptance.py
```

The harness and results are local, ignored artifacts. A self-contained copy of the harness is included below so the group can recreate it on another checkout.

## Limitations and risks

- HTTP 403 remains a provider-side refusal. The fix prevents a secondary crash; it does not make a blocked service accessible.
- Older Requests versions and the optional simplejson configuration were not installed and tested separately. The missing-alias condition is simulated, and the current supported dependency installation passes.
- Real ImageMagick execution and other Python/OS versions still need CI or another machine. ImageMagick command construction/error handling is covered with mocks.
- JPEG cannot preserve transparency. White compositing is deliberate, and JPEG compression is lossy.
- Source-preserving conversion creates temporary output instead of replacing/deleting the source. Callers receive the returned path; only fetchart calls this wrapper in this checkout. Existing intermediate-image cleanup behavior is otherwise unchanged, so additional temporary files can remain after successful multi-step operations.
- Conversion backends still fall back to the source on supported conversion failures. This preserves artwork but cannot guarantee the requested format when an encoder fails. Unexpected backend exceptions still propagate after temporary-output cleanup.
- The complete repository suite remains unverified because optional dependencies are missing. No unrelated source changes were made to accommodate the environment.

## Concise report summary

We investigated two Beets change requests independently and used regression tests to demonstrate the defects before modifying production code. For #5998, we removed the dependency on a missing Requests exception alias, allowing lyrics request failures to be logged without interrupting import or provider fallback. For #4452, we normalized JPEG format comparisons, handled transparency during JPEG encoding, and isolated conversion output in temporary files to preserve source artwork and clean up failures. Final focused validation passed 238 tests; broader applicable validation passed 1,122 tests, with documented skips and no failures. A complete offline import using both plugins also passed. Changes remain local on a dedicated feature branch.

## Offline import acceptance harness

Save the following as `.reports/acceptance.py` and run from the repository root after the setup above. Each run creates a new directory beneath `.reports`, leaving existing files alone.

```python
import os
import shutil
import tempfile
from pathlib import Path

import requests
import requests_mock
import yaml
from mediafile import MediaFile
from PIL import Image

from beets import ui
from beets.library import Library

root = Path(tempfile.mkdtemp(prefix="acceptance-", dir=".reports")).resolve()
os.environ["BEETSDIR"] = str(root)
source = root / "source"
source.mkdir()
song = source / "song.mp3"
shutil.copyfile("test/rsrc/full.mp3", song)
tags = MediaFile(song)
tags.artist = tags.albumartist = "Acceptance Artist"
tags.album = "Acceptance Album"
tags.title = "Acceptance Song"
tags.lyrics = ""
tags.save()
art = source / "cover.png"
Image.new("RGBA", (32, 32), (255, 0, 0, 0)).save(art)
original = art.read_bytes()
config_path = root / "config.yaml"
config_path.write_text(yaml.safe_dump({
    "plugins": ["lyrics", "fetchart"],
    "library": str(root / "library.db"),
    "directory": str(root / "music"),
    "import": {"copy": True, "write": True},
    "lyrics": {"sources": ["lrclib"]},
    "fetchart": {"sources": ["filesystem"], "cover_format": "jpeg", "maxwidth": 16},
}), encoding="utf-8")
if hasattr(requests, "JSONDecodeError"):
    del requests.JSONDecodeError
with requests_mock.Mocker() as http:
    http.get("https://lrclib.net/api/search", status_code=403)
    ui.main(["-c", str(config_path), "import", "-A", "-q", str(source)])
    assert http.called
library = Library(str(root / "library.db"), directory=str(root / "music"))
items = list(library.items())
assert len(items) == 1 and not items[0].lyrics
cover = list(library.albums())[0].art_filepath
with Image.open(cover) as result:
    assert result.format == "JPEG" and result.size == (16, 16)
    assert result.getpixel((0, 0)) == (255, 255, 255)
assert art.read_bytes() == original
print(f"PASS: import survived 403; JPEG artwork stored; source preserved. {root}")
```
