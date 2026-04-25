# Recording the launch demo

This is the README for `record_demo.sh`. Two reasons it gets its own
doc instead of inline comments:

1. The Windows path is different (no asciinema), and
2. The choice of `agg` over `svg-term-cli` is a real footgun worth
   spelling out.

## Why agg, not svg-term-cli

The Day -1 plan originally said "asciinema → svg-term-cli". `svg-term`
produces an animated SVG. SVG animations don't play in Twitter cards,
LinkedIn previews, or GitHub README inline previews — which is exactly
where the launch demo needs to play. Use `agg` (asciinema-gif) instead.
It produces a real GIF, plays everywhere.

## macOS / Linux

```bash
brew install asciinema agg          # macOS
# or
apt install asciinema && cargo install --git https://github.com/asciinema/agg

bash scripts/record_demo.sh
```

The script writes `demo/promptc-demo.cast` and `demo/promptc-demo.gif`.

## Windows

`asciinema` does not support Windows natively. Two options that work:

### Option A — record on WSL (recommended)

```bash
# inside WSL
sudo apt install asciinema
cargo install --git https://github.com/asciinema/agg
cd /mnt/c/Users/Eden/Desktop/prompt
bash scripts/record_demo.sh
```

### Option B — use ScreenToGif and skip asciinema

If you don't have WSL, capture the terminal session with
[ScreenToGif](https://www.screentogif.com/) (free, Windows-native).

1. Open Windows Terminal at the repo root.
2. Maximize the window, or set it to ~96 cols / ~36 rows for a
   GitHub-friendly aspect ratio.
3. Start ScreenToGif's recorder over the terminal.
4. Run, in order:

   ```
   promptc analyze examples/bloated-demo --no-html
   promptc analyze examples/bloated-demo
   ```

5. Stop the recording, trim, and save as
   `demo/promptc-demo.gif` at ≤5 MB.

Either path produces the same artifact. Use whichever is faster.

## Embedding in the README

Once the GIF exists at `demo/promptc-demo.gif`:

```markdown
![promptc demo](demo/promptc-demo.gif)
```

Insert this near the top of the README, just under the tagline, so it
sits above-the-fold on GitHub.

## Re-record when

- Hero copy changes (Day 11+ rewrites)
- The bloated-demo fixture is re-seeded
- The terminal colour palette changes
- Major Grade or Multiplier number shifts (currently D+ / 23.7×)
