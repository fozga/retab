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

### Heuristic Overrides

- `--strictness {strict,balanced,conservative}`
- `--prefer-adjacent-strings`
- `--max-target-fret N`
- `--string-history-window N`
- `--connector-jump-limit N`
- `--run-lock-strength X`
- `--open-string-jump-scale X`
- `--reversal-penalty X`

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