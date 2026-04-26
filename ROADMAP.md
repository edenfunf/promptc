# Roadmap

Planned features and contribution opportunities for promptc beyond
v0.1.0. Each item below has scope, acceptance criteria, and the files
a contributor would need to touch — so anyone can pick one up without
grepping the codebase first.

The same items are also tracked as
[issues](https://github.com/edenfunf/promptc/issues) on the repo;
this file is the canonical narrative version. Discussions about the
*direction* of any item (rather than the implementation) belong in
[Discussions](https://github.com/edenfunf/promptc/discussions).

**Where to start:**
- New to the codebase? Look for items labelled `good first issue`
  on the issues page (typically Sources #5, Docs #11–13, Tooling #15).
- Want to influence v0.2 design? Open a Discussions thread.
- Found an actual bug in v0.1? File an issue using the bug template.

---

## Sources / format adapters

### 1. Add Cursor `.cursor/rules/*.mdc` walker [sources]

**Scope.** promptc currently *detects* a sibling `.cursor/rules/`
directory and prints a one-line warning, but it doesn't parse the
files. This issue asks for a full walker: extend `scanner.scan()` to
also read `.mdc` files under `.cursor/rules/`, parse them with the
existing `parser.parse_file`, and assign a new `FileRole.CURSOR_RULE`
(add to `models.FileRole`).

**Acceptance.** Running `promptc analyze /repo/with/cursor/` produces
a per-file row for every `.mdc` file with token counts. Cursor rules
appear in the dedup engine output. The cursor-warning banner
disappears once they are scanned.

**Files.** `src/promptc/scanner.py` (resolve_scan_root, walk),
`src/promptc/models.py` (FileRole), `src/promptc/parser.py`
(already accepts `.mdc`), `tests/test_scanner.py`.

**Out of scope for this issue.** Cursor's `alwaysApply` /
glob-scoped rule semantics in the exposure math — that's a separate
follow-up issue once the basic walker lands.

---

### 2. Add `AGENTS.md` parsing for non-`.claude/` setups [sources]

**Scope.** AGENTS.md is the cross-tool convention file
(<https://agents.md>). promptc already classifies `AGENTS.md` as
INSTRUCTIONS when it lives at the scan root, but a project that uses
AGENTS.md without any `.claude/` directory currently has nothing
worth analyzing. Extend the scanner so that if the scan root has an
`AGENTS.md` but no `.claude/`, the file is still surfaced and the
hero shows useful per-file token info instead of "Insufficient".

**Acceptance.** `promptc analyze /repo/with/just/agents.md` shows
the file, its body tokens, and either a clean grade or a meaningful
"Add more content" message rather than the current Insufficient
state that assumes `.claude/skills/`.

**Files.** `src/promptc/scanner.py`, `src/promptc/cli.py`
(insufficient-hero copy), `tests/test_scanner.py`.

---

### 3. Add Copilot `.github/instructions/*.instructions.md` support [sources]

**Scope.** GitHub Copilot reads instructions from
`.github/instructions/*.instructions.md`. Extend the scanner to walk
this path when present and classify these files as a new
`FileRole.INSTRUCTIONS` (or a finer-grained `COPILOT_INSTRUCTION`).

**Acceptance.** A repo with `.github/instructions/python.instructions.md`
gets that file in the per-file table when `promptc analyze .` is run
from the repo root.

**Files.** `src/promptc/scanner.py`, `src/promptc/models.py`,
`tests/test_scanner.py`.

---

### 4. Add OpenCode `.opencode/` directory walker [sources]

**Scope.** OpenCode (<https://opencode.dev>) uses `.opencode/` as its
root configuration directory. Add walker logic mirroring the existing
`.claude/` resolver so promptc auto-discovers `.opencode/` when
present.

**Acceptance.** `promptc analyze /repo/with/.opencode/` resolves to
the `.opencode/` subdirectory and surfaces its prompt files in the
report.

**Files.** `src/promptc/scanner.py` (resolve_scan_root logic),
`tests/test_scanner.py`.

---

### 5. Add Gemini `GEMINI.md` parsing [sources]

**Scope.** Gemini Code Assist reads from a top-level `GEMINI.md`
file. Add it to the `INSTRUCTION_FILES` set in `scanner.py` so it
is classified as INSTRUCTIONS when present at scan root.

**Acceptance.** `GEMINI.md` at scan root produces a row with role
`instructions` in the file table.

**Files.** `src/promptc/scanner.py` (one-line set addition),
`tests/test_scanner.py`.

---

## Features

### 6. `--watch` mode: re-analyze on file change [feature]

**Scope.** Add a `--watch` flag to `promptc analyze` that, after the
initial run, monitors the scanned directory for file modifications
(use `watchdog` as a new optional dep) and re-runs the analysis on
each change. Print a debounced summary to the terminal; if `--open`
is set, refresh the HTML report on disk and rely on the browser's
file-watcher / manual refresh.

**Acceptance.** `promptc analyze .claude/ --watch` runs once, then
re-runs each time any file under the path changes. `Ctrl-C` exits
cleanly. `watchdog` added as an optional `[watch]` extras_require.

**Files.** `src/promptc/cli.py`, `pyproject.toml`,
`tests/test_cli.py` (skip on CI for the loop test).

---

### 7. `--baseline path.json` — diff current run against a previous report [feature]

**Scope.** Add a `--baseline PATH` flag to `promptc analyze`. The
path points to a previously-generated JSON report
(`promptc analyze --format json > report.json`). The current run
compares against the baseline and surfaces "+N tokens of new bloat"
or "-N tokens reclaimed since baseline" in the terminal and HTML
hero subtitle.

**Acceptance.** `promptc analyze . --baseline last-week.json` shows
a delta line under the current grade. JSON output gains a
`vs_baseline` block. Tests cover identical / improved / worsened
scenarios.

**Files.** `src/promptc/cli.py`, new `src/promptc/baseline.py`,
`tests/test_baseline.py`.

---

### 8. `.promptcrc.yml` config file for default flags [feature]

**Scope.** Allow per-project defaults via a `.promptcrc.yml` file at
the scan root. Schema covers `threshold`, `min_words`, `excludes`,
and `output`. CLI flags override file values. Use the existing
`pyyaml` dependency.

**Acceptance.** A repo with a `.promptcrc.yml` setting
`threshold: 0.95` and `excludes: ["legacy/*"]` produces a run with
those values applied without flags. CLI flags still take precedence.

**Files.** `src/promptc/config.py` (new),
`src/promptc/cli.py` (load + merge), `tests/test_config.py`.

---

### 9. `--lang-segments` flag to extend the language-variant detector [feature]

**Scope.** The cross-language SDK detector has a hardcoded list of
~30 path segments (`/python/`, `/go/`, etc) at
`dedup.LANGUAGE_PATH_SEGMENTS`. Some users will have their own
internal-language tags (`/v1/`, `/legacy/`, project-specific dialects).
Add a repeatable `--lang-segments SEG` flag that extends the
default list at runtime. Also accept the same key from
`.promptcrc.yml` (after #8 lands).

**Acceptance.** `promptc analyze . --lang-segments v1 --lang-segments v2`
treats clusters that differ only in `/v1/` vs `/v2/` as language
variants too.

**Files.** `src/promptc/cli.py`, `src/promptc/dedup.py`
(parameter on `find_duplicates`), `tests/test_dedup.py`.

---

### 10. Broaden tokenizer calibration to CJK and pure-code corpora [research]

**Scope.** v0.1 ships a measured ~18% systematic underestimate from the
anthropics/skills corpus (n=20, English mixed prose+code). That bound
is the baseline shipped in `TOKENIZER_DISCLAIMER`. We need to extend
the calibration to:

  - CJK-heavy `.claude/` (Chinese / Japanese / Korean prose + code mix)
  - Pure-code `.md` (e.g. README files that are 90%+ fenced code)
  - Long-form prose with no code (e.g. design docs)

Run `scripts/validate_tokenizer.py` against representative samples of
each category, capture per-category bias / stdev, and update
`TOKENIZER_DISCLAIMER` + the methodology section in the HTML report
with the broader picture (e.g. a small table of bias-by-content-type).

**Acceptance.** `TOKENIZER_DISCLAIMER` cites at least 3 distinct
content categories with their measured bias bands, replacing the
single "anthropics/skills only" baseline.

**Files.** `src/promptc/tokens.py`, `src/promptc/templates/report.html.j2`
(methodology Token counts subsection), `scripts/validate_tokenizer.py`
(no changes expected, just re-run with different corpora).

---

## Documentation / community

### 11. Translate the README [docs]

**Scope.** Pick one of: 繁體中文, 简体中文, 日本語, Español,
Deutsch, Français. Translate the current `README.md` into a
`README.{lang-code}.md` and add a language-switcher line at the top
of the English `README.md`.

**Acceptance.** New file `README.zh-Hant.md` (or chosen language)
exists, contains the same content as English, and is linked from the
top of the English README.

**Files.** New `README.<lang>.md`; small edit to `README.md`.

---

### 12. Contribute a "real-world before & after" case study [docs]

**Scope.** Run `promptc analyze` on a real-world `.claude/` setup
of your own (anything with 5+ skills). Manually clean up one or two
flagged duplicates. Re-run promptc and capture the before/after
grade + token deltas. Write up the process as a markdown doc under
`docs/case-studies/<your-project>.md` and link it from the README.

**Acceptance.** New file under `docs/case-studies/` with at minimum:
- Project description (no personally-identifying details required)
- Initial grade + multiplier
- What you changed and why
- Final grade + multiplier
- One-paragraph reflection

**Files.** `docs/case-studies/<name>.md`; README link.

---

### 13. Document the language-variant detector with examples [docs]

**Scope.** The current `LANGUAGE_PATH_SEGMENTS` list and the
`is_language_variant` heuristic are explained in source-code
docstrings only. Write a user-facing docs page that:
- Lists the segments
- Shows a worked example (paths in / out)
- Explains how to extend with `--lang-segments` (after #9 lands)
- Explains when the detector might wrongly include / exclude

**Acceptance.** New `docs/language-variant-detector.md` with all
four sections; linked from the methodology section of the HTML
report and from the README's glossary.

**Files.** `docs/language-variant-detector.md`,
`src/promptc/templates/report.html.j2` (link), `README.md` (link).

---

## Quality / ecosystem

### 14. GitHub Action: `promptc/analyze-action@v1` [tooling]

**Scope.** A reusable composite GitHub Action (`action.yml` at the
repo root or `.github/actions/analyze/action.yml`) that:
1. Sets up Python.
2. Installs promptc from PyPI (or from this repo with `path:`).
3. Runs `promptc analyze <path>` and uploads the HTML report as a
   workflow artifact.
4. Optionally fails the job if the grade is below a configurable
   floor (input `min-grade: B`).

**Acceptance.** A consumer workflow can use the action with three
lines of YAML and get the report as an artifact. The action's
`README` documents inputs and outputs.

**Files.** New `action.yml`; example workflow under
`.github/workflows/example-action-usage.yml`; `docs/action.md`.

---

### 15. Pre-commit hook template [tooling]

**Scope.** Provide a sample `.pre-commit-hooks.yaml` so users can add
promptc to their pre-commit config. The hook runs
`promptc analyze --no-html --format json` and fails if any new
duplicate group appears compared to a baseline file checked into the
repo.

**Acceptance.** Documentation under `docs/pre-commit.md` explains
setup; the hook entry runs locally on a sample repo. (No need to
publish to <https://pre-commit.com>'s mirror in this issue — that's
a follow-up.)

**Files.** `.pre-commit-hooks.yaml` at repo root, `docs/pre-commit.md`,
small CLI helper if needed.

---

## Labelling on GitHub Issues

When the items above are mirrored as issues, they use these labels:

- `enhancement` — all source/feature/tooling items (1–10, 14, 15)
- `documentation` — docs items (11, 12, 13)
- `good first issue` — items genuinely scoped for a first contribution:
  #5 (Gemini, ~1-line addition), #11 (translate), #12 (case study),
  #13 (document the variant detector), #15 (pre-commit hook).
  The remaining items are larger and benefit from a Discussion
  thread before someone picks them up.
