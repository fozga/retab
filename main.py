import argparse
import sys
import re
from typing import List

# Importy Twoich modułów
from tuning import get_tuning_midi, midi_to_note_name
from parser import parse_tab_blocks_with_sections, resolve_string_tunings
from translator import render_target_tab
from note_sequence import render_note_sequence, max_simultaneous_notes_in_timeline

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
        normalized_line = line[1:] if line.startswith('|') else line
        formatted_lines.append(f"{label}|{normalized_line}")

    return "\n".join(formatted_lines)

def main():
    parser = argparse.ArgumentParser(
        description="TabTranslator: Translate guitar tablatures to any string instrument.",
        epilog="Example: python main.py song.txt -t ukulele"
    )
    
    # Obsługa przypadku bez argumentów
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
        
    parser.add_argument("input_file", help="Path to the source .txt tab file")
    parser.add_argument("-t", "--target", 
                        help="Target tuning (preset name like 'ukulele' or custom like 'G4-C4-E4-A4'). "
                             "If omitted, renders abstract note sequence.")
    parser.add_argument("-o", "--output", help="Path to save the output file (optional)")
    
    args = parser.parse_args()

    # try:
    # 1. Resolve source tuning (assuming standard guitar if not specified)
    source_prefixes = ["e", "B", "G", "D", "A", "E"]
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
        for metadata_lines, block_timeline, ends_with_bar in parsed_blocks:
            if metadata_lines and pending_tab_chunk:
                rendered_chunks.append(finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
                pending_tab_chunk = ""

            if metadata_lines:
                rendered_chunks.extend(metadata_lines)

            current_render = render_target_tab(block_timeline, target_tuning_midi)
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

            current_render = render_note_sequence(block_timeline, fixed_height=file_max_height)
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