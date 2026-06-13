# retab

Translate ASCII tablature into:

1. abstract note-sequence view (note names), or
2. target-instrument tablature (custom/preset tunings).

The parser preserves section labels (for example `[Intro]`, `x6`, comments) and keeps bar structure where possible.

## Quick Start

Run abstract note sequence:

```bash
python3 main.py tab.txt -o output.txt
```

Run note sequence with octave numbers:

```bash
python3 main.py tab.txt --show-octave -o output.txt
```

Translate to target tuning preset:

```bash
python3 main.py tab.txt -t ukulele -o output.txt
python3 main.py tab.txt -t bass -o output.txt
python3 main.py tab.txt -t violin-drop-c -o output.txt
```

Translate using custom tuning:

```bash
python3 main.py tab.txt -t G4-C4-E4-A4 -o output.txt
```

## CLI

```text
usage: main.py [-h] [-t TARGET]
							 [--heuristic-preset {bass-smooth,bass-tight,violin-aggressive,violin-lyrical,violin-playable}]
							 [--strictness {strict,balanced,conservative}] [--show-octave]
							 [--prefer-adjacent-strings] [--max-target-fret MAX_TARGET_FRET]
							 [--string-history-window STRING_HISTORY_WINDOW]
							 [--connector-jump-limit CONNECTOR_JUMP_LIMIT]
							 [--run-lock-strength RUN_LOCK_STRENGTH]
							 [-o OUTPUT]
							 input_file
```

### Arguments

- `input_file`: source `.txt` tab.
- `-o`, `--output`: output file path.

### Mode Selection

- `-t`, `--target`: target tuning preset or custom tuning string.
	- If omitted, output is abstract note sequence.

### Note-Sequence Option

- `--show-octave`: include octave numbers in note sequence (default off).

### Heuristic Presets

- `--heuristic-preset`:
	- `violin-lyrical`
	- `violin-playable`
	- `violin-aggressive`
	- `bass-tight`
	- `bass-smooth`

Preset values can always be overridden by explicit flags below.

Preset intent:

- `violin-lyrical`: prioritizes melodic continuity and expressive legato flow.
	- Strong contour lock, adjacent-string preference, larger usable upper register.
- `violin-playable`: keeps melody musical while favoring easier hand positions.
	- More conservative max fret and gentler continuity pressure.
- `violin-aggressive`: allows riskier motion and wider positional changes.
	- Weaker run lock and less adjacent-string bias.
- `bass-tight`: emphasizes compact, practical bass fingering.
	- Lower max fret and stronger anti-jump behavior.
- `bass-smooth`: balanced bass phrasing with smoother movement.
	- Slightly wider register than `bass-tight`, still movement-aware.

Tip:

- Start with a preset closest to your instrument and style.
- Then override one or two flags (instead of all flags) for predictable tuning.

### Heuristic Overrides

- `--strictness {strict,balanced,conservative}`
	- Global weighting profile for contour vs convenience.
	- `strict` preserves phrase shape most aggressively.
	- `conservative` prefers easier fingering and fewer forced contour constraints.

- `--prefer-adjacent-strings`
	- Biases melody toward same or neighboring strings.
	- Helps reduce large cross-string jumps.

- `--max-target-fret N`
	- Hard cap on allowed translated frets.
	- Useful to keep output within comfort range for a player/instrument.

- `--string-history-window N`
	- Number of recent melodic notes used for string-flow smoothing.
	- Higher values enforce longer-range consistency, lower values react more locally.

- `--connector-jump-limit N`
	- Max same-string fret jump where legato connectors (`h`, `p`, `s`, `r`) are preserved.
	- If jump is above this limit, connector display is reduced/omitted.

- `--run-lock-strength X`
	- Scales how strongly monophonic phrases resist mid-run register/shift changes.
	- Higher values keep phrases in one register; lower values allow more adaptation.

- `--open-string-jump-scale X`
	- Scales jump penalties when one side of the jump is fret `0`.
	- Lower values treat open-string transitions as easier.

- `--reversal-penalty X`
	- Extra penalty for long-distance back-and-forth position reversals.
	- Increase to suppress zig-zag hand movement.

## Practical Examples

Violin melodic/lyrical mapping:

```bash
python3 main.py tab.txt -t violin-drop-c \
	--heuristic-preset violin-lyrical \
	--prefer-adjacent-strings \
	-o output.txt
```

Bass tighter playability window:

```bash
python3 main.py tab.txt -t bass \
	--heuristic-preset bass-tight \
	--max-target-fret 10 \
	-o output.txt
```

Manual override on top of preset:

```bash
python3 main.py tab.txt -t violin-drop-c \
	--heuristic-preset violin-lyrical \
	--run-lock-strength 2.0 \
	--connector-jump-limit 5 \
	-o output.txt
```

## Recommended Starting Presets

Use this as a quick starting point, then fine-tune with overrides.

| Instrument / Goal | Suggested preset | Typical extra flags |
|---|---|---|
| Violin / expressive lead | `violin-lyrical` | `--prefer-adjacent-strings --run-lock-strength 1.5` |
| Violin / easier fingering | `violin-playable` | `--max-target-fret 10` |
| Violin / more aggressive motion | `violin-aggressive` | `--run-lock-strength 0.8` |
| Bass / compact practical lines | `bass-tight` | `--max-target-fret 9 --connector-jump-limit 4` |
| Bass / smoother phrasing | `bass-smooth` | `--open-string-jump-scale 0.2` |
| Ukulele / general translation | no preset (start manual) | `--strictness balanced --prefer-adjacent-strings` |
| Mandolin / lead continuity | no preset (start manual) | `--strictness strict --prefer-adjacent-strings --run-lock-strength 1.3` |

Quick adjustment guide:

- Too much zig-zag movement:
	- increase `--reversal-penalty`
	- enable `--prefer-adjacent-strings`

- Phrase jumps register mid-run:
	- increase `--run-lock-strength`
	- reduce `--max-target-fret` only if upper register is actually unplayable

- Too many connectors on hard jumps:
	- lower `--connector-jump-limit`

- Open-string transitions feel over-penalized:
	- lower `--open-string-jump-scale`