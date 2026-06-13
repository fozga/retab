import argparse
import sys
import re
from typing import List

# Importy Twoich modułów
from tuning import get_tuning_midi, midi_to_note_name
from parser import parse_tab_blocks_with_sections, resolve_string_tunings, detect_source_prefixes
from translator import render_target_tab
from note_sequence import render_note_sequence, max_simultaneous_notes_in_timeline

HEURISTIC_PRESETS = {
    # Violin-family focused presets
    "violin-lyrical": {
        "strictness": "strict",
        "prefer_adjacent_strings": True,
        "max_target_fret": 17,
        "string_history_window": 5,
        "connector_jump_limit": 6,
        "run_lock_strength": 1.8,
    },
    "violin-playable": {
        "strictness": "balanced",
        "prefer_adjacent_strings": True,
        "max_target_fret": 10,
        "string_history_window": 4,
        "connector_jump_limit": 5,
        "run_lock_strength": 1.3,
    },
    "violin-aggressive": {
        "strictness": "strict",
        "prefer_adjacent_strings": False,
        "max_target_fret": 15,
        "string_history_window": 3,
        "connector_jump_limit": 8,
        "run_lock_strength": 0.8,
    },
    # Bass-focused presets
    "bass-tight": {
        "strictness": "balanced",
        "prefer_adjacent_strings": True,
        "max_target_fret": 9,
        "string_history_window": 5,
        "connector_jump_limit": 4,
        "run_lock_strength": 1.4,
    },
    "bass-smooth": {
        "strictness": "conservative",
        "prefer_adjacent_strings": True,
        "max_target_fret": 12,
        "string_history_window": 4,
        "connector_jump_limit": 5,
        "run_lock_strength": 1.1,
    },
}

def resolve_heuristics(args):
    """
    Resolve translation heuristic settings from defaults + optional preset + explicit CLI overrides.
    Explicit flags always win over preset values.
    """
    config = {
        "strictness": "strict",
        "prefer_adjacent_strings": False,
        "max_target_fret": None,
        "string_history_window": 4,
        "connector_jump_limit": 7,
        "run_lock_strength": 1.0,
        "open_string_jump_scale": None,
        "reversal_penalty": None,
    }

    if args.heuristic_preset:
        config.update(HEURISTIC_PRESETS[args.heuristic_preset])

    # Explicit CLI overrides (None means user did not set it).
    if args.strictness is not None:
        config["strictness"] = args.strictness
    if args.prefer_adjacent_strings is not None:
        config["prefer_adjacent_strings"] = args.prefer_adjacent_strings
    if args.max_target_fret is not None:
        config["max_target_fret"] = args.max_target_fret
    if args.string_history_window is not None:
        config["string_history_window"] = args.string_history_window
    if args.connector_jump_limit is not None:
        config["connector_jump_limit"] = args.connector_jump_limit
    if args.run_lock_strength is not None:
        config["run_lock_strength"] = args.run_lock_strength
    if args.open_string_jump_scale is not None:
        config["open_string_jump_scale"] = args.open_string_jump_scale
    if args.reversal_penalty is not None:
        config["reversal_penalty"] = args.reversal_penalty

    return config

def normalize_tab_line_start(line: str) -> str:
    """Replace leading dash-runs before first bar marker with '#|' for readability."""
    return re.sub(r'^-+\|', '#|', line)

def to_base_note(midi_number: int) -> str:
    """Convert MIDI pitch to base note name without octave, e.g. C4 -> C."""
    return re.sub(r'-?\d+$', '', midi_to_note_name(midi_number))

def concat_tab_chunks(left_chunk: str, right_chunk: str) -> str:
    """Concatenate two multi-line tab chunks horizontally, line by line."""
    left_lines = left_chunk.splitlines()
    right_lines = right_chunk.splitlines()

    max_rows = max(len(left_lines), len(right_lines))
    if len(left_lines) < max_rows:
        left_lines.extend([""] * (max_rows - len(left_lines)))
    if len(right_lines) < max_rows:
        right_lines.extend([""] * (max_rows - len(right_lines)))

    merged = [l + r for l, r in zip(left_lines, right_lines)]
    return "\n".join(merged)

def finalize_tab_chunk(chunk: str) -> str:
    """Apply final tab-line formatting before writing output."""
    return "\n".join(normalize_tab_line_start(line) for line in chunk.splitlines())

def finalize_target_tab_chunk(chunk: str, target_tuning_midi: List[int]) -> str:
    """Prefix translated tab lines with target base-note labels (e.g., C|...)."""
    labels = [to_base_note(m) for m in target_tuning_midi]
    lines = chunk.splitlines()

    # If tuning is strictly low->high, display high strings at the top.
    # This matches common tab reading direction for instruments like violin/guitar.
    if len(lines) == len(target_tuning_midi):
        is_strictly_ascending = all(
            target_tuning_midi[i] < target_tuning_midi[i + 1]
            for i in range(len(target_tuning_midi) - 1)
        )
        if is_strictly_ascending:
            lines = list(reversed(lines))
            labels = list(reversed(labels))

    formatted_lines = []

    for idx, line in enumerate(lines):
        label = labels[idx] if idx < len(labels) else "s"
        normalized_line = re.sub(r'^-+\|', '|', line)
        if normalized_line.startswith('|'):
            normalized_line = normalized_line[1:]
        formatted_lines.append(f"{label}|{normalized_line}")

    return "\n".join(formatted_lines)

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Retab: parse guitar-style ASCII tabs, preserve sections, and render either\n"
            "(1) an abstract note sequence or\n"
            "(2) translated tab for a target tuning/instrument."
        ),
        epilog=(
            "Examples:\n"
            "  python main.py song.txt -o output.txt\n"
            "  python main.py song.txt --show-octave -o output.txt\n"
            "  python main.py song.txt -t ukulele -o output.txt\n"
            "  python main.py song.txt -t violin-drop-c --heuristic-preset violin-lyrical -o output.txt\n"
            "  python main.py song.txt -t bass --heuristic-preset bass-tight --max-target-fret 10 -o output.txt"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    # Obsługa przypadku bez argumentów
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    parser.add_argument("input_file", help="Path to the source .txt tab file")
    parser.add_argument("-t", "--target", 
                        help=(
                            "Target tuning preset (e.g. 'ukulele', 'bass', 'violin', 'violin-drop-c')\n"
                            "or custom tuning string like 'G4-C4-E4-A4'.\n"
                            "If omitted, renders abstract note sequence."
                        ))
    parser.add_argument(
        "--heuristic-preset",
        choices=sorted(HEURISTIC_PRESETS.keys()),
        help=(
            "Apply a preset bundle of translation heuristics. "
            "Any explicitly provided heuristic flags override preset values."
        ),
    )
    parser.add_argument(
        "--strictness",
        choices=["strict", "balanced", "conservative"],
        default=None,
        help=(
            "Translation strictness for melodic-contour preservation: "
            "strict, balanced, or conservative. Default: preset/default value."
        ),
    )
    parser.add_argument(
        "--show-octave",
        action="store_true",
        help="In note-sequence mode, include octave numbers (e.g., C#4). Default is off.",
    )
    parser.add_argument(
        "--prefer-adjacent-strings",
        action="store_true",
        default=None,
        help=(
            "In translation mode, prefer same/adjacent string movement over wider jumps "
            "using a short melodic history window."
        ),
    )
    parser.add_argument(
        "--max-target-fret",
        type=int,
        default=None,
        help="Override max fret considered playable during translation (default: auto per instrument).",
    )
    parser.add_argument(
        "--string-history-window",
        type=int,
        default=None,
        help="How many recent melodic notes influence adjacent-string preference (default: preset/default value).",
    )
    parser.add_argument(
        "--connector-jump-limit",
        type=int,
        default=None,
        help="Max same-string fret jump to keep connectors (h/p/s/r) in translated tab (default: preset/default value).",
    )
    parser.add_argument(
        "--run-lock-strength",
        type=float,
        default=None,
        help="Scale for phrase register lock penalty in monophonic runs (default: preset/default value).",
    )
    parser.add_argument(
        "--open-string-jump-scale",
        type=float,
        default=None,
        help="Scale factor for jump penalties when one of the notes is open string (0.0 disables those penalties).",
    )
    parser.add_argument(
        "--reversal-penalty",
        type=float,
        default=None,
        help="Override penalty for long-distance back-and-forth position reversals.",
    )
    parser.add_argument("-o", "--output", help="Path to save the output file (optional)")
    
    args = parser.parse_args()

    # try:
    # 1. Resolve source tuning (assuming standard guitar if not specified)
    source_prefixes = detect_source_prefixes(args.input_file)
    base_tunings = resolve_string_tunings(source_prefixes)
    
    # 2. Parse the input tab file into a timeline of TimeSlices
    print(f"[*] Parsing {args.input_file}...")
    parsed_blocks, trailing_metadata = parse_tab_blocks_with_sections(args.input_file, base_tunings)

    if not parsed_blocks:
        print("[!] No tablature blocks found. Check your file format.")
        return

    # 3. Render blocks while preserving original section/part metadata
    rendered_chunks = []
    pending_tab_chunk = ""
    pending_chunk_ends_with_bar = True

    if args.target:
        print(f"[*] Translating to {args.target}...")
        target_tuning_midi = get_tuning_midi(args.target)
        heuristic_config = resolve_heuristics(args)
        for metadata_lines, block_timeline, ends_with_bar in parsed_blocks:
            if metadata_lines and pending_tab_chunk:
                rendered_chunks.append(finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
                pending_tab_chunk = ""

            if metadata_lines:
                rendered_chunks.extend(metadata_lines)

            current_render = render_target_tab(
                block_timeline,
                target_tuning_midi,
                strictness=heuristic_config["strictness"],
                prefer_adjacent_strings=heuristic_config["prefer_adjacent_strings"],
                max_target_fret=heuristic_config["max_target_fret"],
                string_history_window=heuristic_config["string_history_window"],
                connector_jump_limit=heuristic_config["connector_jump_limit"],
                run_lock_strength=heuristic_config["run_lock_strength"],
                open_string_jump_scale=heuristic_config["open_string_jump_scale"],
                reversal_penalty=heuristic_config["reversal_penalty"],
            )
            if pending_tab_chunk:
                pending_tab_chunk = concat_tab_chunks(pending_tab_chunk, current_render)
            else:
                pending_tab_chunk = current_render

            pending_chunk_ends_with_bar = ends_with_bar
            if pending_chunk_ends_with_bar:
                rendered_chunks.append(finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
                pending_tab_chunk = ""
    else:
        print("[*] No target provided. Rendering abstract note sequence...")
        # Keep all blocks at the same vertical height for readability.
        file_max_height = max(
            (max_simultaneous_notes_in_timeline(block_timeline) for _, block_timeline, _ in parsed_blocks),
            default=1,
        )

        for metadata_lines, block_timeline, ends_with_bar in parsed_blocks:
            if metadata_lines and pending_tab_chunk:
                rendered_chunks.append(finalize_tab_chunk(pending_tab_chunk))
                pending_tab_chunk = ""

            if metadata_lines:
                rendered_chunks.extend(metadata_lines)

            current_render = render_note_sequence(
                block_timeline,
                fixed_height=max(3, file_max_height),
                show_octave=args.show_octave,
            )
            if pending_tab_chunk:
                pending_tab_chunk = concat_tab_chunks(pending_tab_chunk, current_render)
            else:
                pending_tab_chunk = current_render

            pending_chunk_ends_with_bar = ends_with_bar
            if pending_chunk_ends_with_bar:
                rendered_chunks.append(finalize_tab_chunk(pending_tab_chunk))
                pending_tab_chunk = ""

    if pending_tab_chunk:
        if args.target:
            rendered_chunks.append(finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
        else:
            rendered_chunks.append(finalize_tab_chunk(pending_tab_chunk))

    if trailing_metadata:
        rendered_chunks.extend(trailing_metadata)

    output_tab = "\n\n".join(chunk for chunk in rendered_chunks if chunk is not None)
        
    # 4. Output the result
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_tab)
        print(f"[+] Successfully saved to {args.output}")
    else:
        print("\n--- Result ---\n")
        print(output_tab)

    # except FileNotFoundError:
    #     print(f"[!] Error: File '{args.input_file}' not found.")
    #     sys.exit(1)
    # except Exception as e:
    #     print(f"[!] An unexpected error occurred: {e}")
    #     sys.exit(1)

if __name__ == "__main__":
    main()