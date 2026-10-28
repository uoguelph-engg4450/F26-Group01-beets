# Acceptance tests – Group 1

These are the customer acceptance tests for our two changes:

- CR1 (issue #4452): fetchart `cover_format` conversion from PNG to JPEG
- CR2 (issue #5998): the lyrics plugin crashing an import when a lyrics site fails

The full test cases (Given / When / Then) are in Section 5 of our report. This folder contains a helper script, `testkit.py`, that sets up each test, plus a sample song in `assets/`. The song is silent and tagged as "Supertramp - The Logical Song" so the lyrics sites can match it.

All tests run inside a workspace folder here, so they don't touch the users real music library.

## Setup

You need Python 3.11+ and Git.

Windows (PowerShell):

```
git clone https://github.com/uoguelph-engg4450/F26-Group01-beets
cd F26-Group01-beets
git checkout fix/engg4450-lyrics-artwork
py -m venv venv
venv\Scripts\Activate.ps1
pip install -e ".[lyrics,fetchart,embedart]"
cd acceptance-tests
$env:BEETSDIR = "$PWD\workspace"
```

`beet version` should now print a version number. If you open a new terminal, run the activate line and the BEETSDIR line again.

## Running the tests

Each test starts with `python testkit.py prepare <test ID>`. This resets the workspace and creates the album folder, cover image and beets config for that test. Then run the commands below and compare the result with the expected result. (On Windows, use `dir` in place of `ls`.)

| Test | Commands | Expected result |
|---|---|---|
| CR1-TC1 | `python testkit.py prepare CR1-TC1`<br>`beet -v import -A workspace/album1`<br>`python testkit.py check-cover` | `cover.jpg: format=JPEG size=1600x1600 top-left corner=white` |
| CR1-TC2 | `python testkit.py prepare CR1-TC2`<br>`beet -v import -A workspace/album2`<br>`ls workspace/album2`<br>`python testkit.py check-cover` | `front.png` is still in the album folder, and the cover is `format=JPEG` |
| CR1-TC3 | `python testkit.py prepare CR1-TC3`<br>`beet import -A workspace/album1`<br>`beet extractart -a -o workspace/embedded`<br>`python testkit.py check-cover workspace/embedded.jpg` | `embedded.jpg: format=JPEG size=1600x1600 top-left corner=white` |
| CR2-TC1 | `pip install "requests==2.26.0"`<br>`python testkit.py prepare CR2-TC1`<br>`beet -v import -A workspace/music`<br>`beet ls` | A "Request error" warning, then "Lyrics not found". No Traceback. `beet ls` lists the song |
| CR2-TC2 | `pip install -U "requests>=2.32.5"`<br>`python testkit.py prepare CR2-TC2`<br>`beet -v import -A workspace/music`<br>`beet ls -f '$lyrics'` | The song's lyrics are printed. Needs an internet connection |

CR2-TC1 uses an older version of the `requests` library (2.26.0), which is the setup from the original bug report. pip will warn about a dependency conflict when you install it. CR2-TC2 puts the current version back.

You can also run all five tests in one go with `python testkit.py run-all`. It prints PASS/FAIL for each test and saves the results to `results.txt`.

## If something goes wrong

- `beet` not found: the virtual environment isn't active.
- beets is using your normal library: BEETSDIR isn't set in this terminal. Run the BEETSDIR line again.
- No cover was saved: run `prepare` again, then re-run the import with `-v` and read the `fetchart:` lines.
