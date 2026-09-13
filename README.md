# bib-deduplicator

An interactive BibTeX deduplicator. Merges `.bib` files from a folder,
flags likely duplicates with a GUI prompt, and writes a clean
`merged_output.bib` alongside a `discarded_option_b.bib` for anything
you chose to drop.

## Features

- Detects exact duplicates (same author / year / first word / last word of title)
- Prompts for 3-of-4 matches via a themed Tkinter dialog
- On Windows: dialog appears on the monitor your mouse is on
- Writes three outputs into `results/`:
  - `merged_output.bib` — one winner per duplicate group
  - `discarded_option_b.bib` — losers, so nothing is lost
  - `duplicates_log.txt` — human-readable report with source files
- Final summary window with a "Copy merged .bib to clipboard" button
- Terminal fallback if Tkinter is unavailable

## Requirements

- Python 3.8+
- [`bibtexparser`](https://pypi.org/project/bibtexparser/) (`pip install -r requirements.txt`)
- Tkinter (bundled with Python on Windows/macOS; `sudo apt install python3-tk` on Debian/Ubuntu)
- On Linux/X11: `xdotool` and `xrandr` for multi-monitor centering (optional)

## Install

```bash
git clone https://github.com/<your-user>/bib-deduplicator.git
cd bib-deduplicator
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

1. Drop your `.bib` files into `./bib_files/`.
2. Run:

   ```bash
   python script.py
   ```

3. For each 3-of-4 match, a dialog appears:
   - `y` / `Enter` — merge
   - `n` / `Esc` — keep both
   - `X` — abort the whole script

4. When done, the summary window shows run stats and lets you copy
   the merged `.bib` to the clipboard.

## Output files

All outputs are written into `results/`.

| File | Contents |
|------|----------|
| `results/merged_output.bib` | Deduplicated entries (one per group) |
| `results/discarded_option_b.bib` | Entries that lost their group |
| `results/duplicates_log.txt` | Per-group report with source file names |

## Configuration

Edit the constants at the top of `script.py`:

```python
INPUT_FOLDER        = './bib_files'
OUTPUT_FILE         = 'results/merged_output.bib'
OPTION_B_FILE       = 'results/discarded_option_b.bib'
DUPLICATES_LOG_FILE = 'results/duplicates_log.txt'
```

## How duplicate detection works

Each entry is reduced to a 4-part signature:

```
(last_name, year, first_title_word, last_title_word)
```

- 4/4 match → automatic merge
- 3/4 match → you're prompted
- 2/4 or fewer → treated as distinct

The winner in each group is the entry with the highest year.

## How final keys are named

Every entry that ends up in `results/merged_output.bib` is given a
**normalized, human-readable citation key**, built from the same four
parts used for duplicate detection:

```
<LastName><Year><first-title-word>_<last-title-word>
```

Concretely:

| Part | Source | Transformation |
|------|--------|----------------|
| `LastName` | First author's surname | Capitalized, braces stripped |
| `Year` | `year` field | As-is (or `0000` if missing) |
| `first-title-word` | First significant word of the title | Lowercased |
| `last-title-word` | Last significant word of the title | Lowercased |

### Worked example

```bibtex
@article{Lee2016third_networks,
  author  = {Lee, Ji Young and Dernoncourt, Franck},
  journal = {arXiv preprint arXiv:1603.03827},
  old_keys = {lee2016sequedssddsfntial},
  title   = {THIRD Sequential short-text classification with
             recurrent and convolutional neural networks},
  year    = {2016}
}
```

Produces:

```
Lee2016third_networks
```

Breakdown:

| Component | Value | Why |
|-----------|-------|-----|
| `Lee` | First author's surname | `Lee, Ji Young` → `Lee` |
| `2016` | `year` field | Verbatim |
| `third` | First title word | `THIRD` is 5 chars → used alone, lowercased |
| `networks` | Last title word | `networks` is 8 chars → used alone, lowercased |

Note that in this case the generated key matches the original
`@article` key exactly — the naming scheme is **idempotent** for
entries that already follow the convention.

### Rules

- If the **first word of the title is shorter than 4 characters**, the
  first *two* words are used instead (e.g. `A Study of Foo` →
  `astudy`). The same rule applies to the last word, using the last
  two words if the final one is short.
- Non-alphanumeric characters in the title are stripped before
  tokenization, so `short-text` becomes `shorttext`.
- Words are joined with `_` between the title-derived halves. There
  is **no numeric prefix** on the final key — the prefixed keys you
  may see during processing (e.g. `290Lee2016third_networks`) are
  internal and only used while grouping entries.
- `old_keys` is added to each winner and lists every original
  citation key that was merged into it — useful for cross-referencing
  with your source `.bib` files.

### Discarded entries

Entries written to `results/discarded_option_b.bib` receive the same
normalized key format. If two discarded entries in the same run would
produce identical keys, the second one gets a numeric suffix
(`<key>_<n>`) to keep the file importable by BibTeX tooling.

### Why this format

- Deterministic — the same input always produces the same key.
- Readable — you can tell at a glance who wrote the paper and when.
- Collision-resistant — the year plus two title words is almost always
  unique within a bibliography.
- Tool-friendly — no `!`, `:`, or other separators that some BibTeX
  parsers reject.
- Idempotent — running the tool on its own output changes nothing.

### Rules

- If the **first word of the title is shorter than 4 characters**, the
  first *two* words are used instead (e.g. `A Study of Foo` →
  `astudy`). The same rule applies to the last word, using the last
  two words if the final one is short.
- Words are joined with `_` between the title-derived halves.
- There is **no numeric prefix** on the final key. The prefixed keys
  you may see during processing (e.g. `290Anderson2022credit_scoring`)
  are internal and are only used while grouping entries.
- `old_keys` is added to each winner and lists every original citation
  key that was merged into it — useful for cross-referencing with your
  original `.bib` files.

### Discarded entries

Entries written to `results/discarded_option_b.bib` receive the same
normalized key format. If two discarded entries in the same run would
produce identical keys, the second one gets a numeric suffix
(`<key>_<n>`) to keep the file importable by BibTeX tooling.

### Why this format

- Deterministic — the same input always produces the same key.
- Readable — you can tell at a glance who wrote the paper and when.
- Collision-resistant — the year plus two title words is almost always
  unique within a bibliography.
- Tool-friendly — no `!` or other separators that some parsers reject.

## License

MIT — see [LICENSE](LICENSE).
```
