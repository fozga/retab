import re
from typing import List, Dict, Optional, Union, Tuple
from dataclasses import dataclass, field
from tuning import note_to_midi, get_tuning_midi

# --- Data Models ---

@dataclass
class Note:
    string_index: int       # Original string index (0 = top string)
    fret: Union[int, str]   # Fret number, or 'x' for dead note
    pitch_midi: Optional[int] = None # MIDI note calculated from tuning + fret
    technique_before: str = "" # e.g., 'h', 'p', '/' located before the note
    technique_after: str = ""  # e.g., '~', 'b' located after the note

@dataclass
class TimeSlice:
    """Represents a single vertical column in the tablature."""
    visual_index: int       # The horizontal character index in the original text
    notes: List[Note] = field(default_factory=list)
    is_empty: bool = True   # True if it's just '-' or spaces
    special_char: str = ""  # For bar lines '|'

# --- Parser Logic ---

DEFAULT_GUITAR_OCTAVES = [4, 3, 3, 3, 2, 2]
TECHNIQUE_CHARS = {'h', 'p', '/', '\\', 'b', 'r', '~'}
CONNECTING_TECHNIQUES = {'h', 'p', '/', '\\', 'r'}

def extract_line_prefix(line: str) -> str:
    """Return string prefix before first bar, e.g. 'E' in 'E|---' (or '' if absent)."""
    if '|' not in line:
        return ""
    return line.split('|', 1)[0].strip()

def sanitize_tab_line(line: str) -> str:
    """
    Remove trailing repeat annotations like 'x2' that are text markers,
    not dead-note content (e.g. '...|   x2').
    """
    cleaned = line.rstrip()
    cleaned = re.sub(r'\s+[xX]\d+\s*$', '', cleaned)
    return cleaned

def detect_source_prefixes_and_count(file_path: str) -> Tuple[List[str], int]:
    """
    Detect source string prefixes and expected number of strings from the first
    contiguous prefixed tab run.
    """
    prefixes: List[str] = []

    with open(file_path, 'r') as f:
        in_run = False
        for raw_line in f:
            line = raw_line.rstrip('\n')
            if not line.strip():
                if in_run and prefixes:
                    break
                continue

            if not is_tab_line(line):
                if in_run and prefixes:
                    break
                continue

            pref = extract_line_prefix(line)
            if pref:
                in_run = True
                prefixes.append(pref)
            elif in_run and prefixes:
                # Continuation without prefix after prefixed run; ignore for detection.
                continue

    if not prefixes:
        return ["e", "B", "G", "D", "A", "E"], 6

    return prefixes, len(prefixes)

def is_tab_line(line: str) -> bool:
    """Checks if a line looks like a guitar tab line."""
    # Standard prefixed line (e|... / B|... etc.)
    if re.search(r'[eBGDAE]\|.*[-0-9hpx/\\~]', line, re.IGNORECASE):
        return True

    # Wrapped continuation line without a string prefix (e.g. "---|----").
    # Require at least one bar marker so labels like "x6" are not parsed as tab.
    compact = line.strip()
    return (
        bool(compact)
        and '|' in compact
        and bool(re.fullmatch(r'[\-|0-9hpx/\\~()br]+', compact, re.IGNORECASE))
    )

def extract_tab_blocks(file_path: str) -> List[List[str]]:
    """
    Reads a file and extracts groups of 6 lines that form a tab block,
    ignoring extra text and empty lines.
    """
    blocks = []
    current_block = []
    _, expected_strings = detect_source_prefixes_and_count(file_path)
    
    with open(file_path, 'r') as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped:
                continue
                
            if is_tab_line(stripped):
                current_block.append(sanitize_tab_line(stripped).lstrip())
                if len(current_block) == expected_strings:
                    blocks.append(current_block)
                    current_block = []
            else:
                # If we encounter text, we ignore it, 
                # but we could add logic here to detect new section headers
                continue
                
    return blocks

def extract_tab_blocks_with_metadata(file_path: str) -> Tuple[List[Tuple[List[str], List[str]]], List[str]]:
    """
    Reads a file and extracts 6-line tab blocks together with preceding text lines
    (sections/parts/instructions). The text lines are preserved as metadata and do
    not participate in note parsing.

    Returns:
    - list of tuples: (metadata_lines, tab_block_lines)
    - trailing metadata lines that appear after the last block
    """
    blocks_with_meta: List[Tuple[List[str], List[str]]] = []
    pending_meta: List[str] = []
    current_block: List[str] = []
    _, expected_strings = detect_source_prefixes_and_count(file_path)

    with open(file_path, 'r') as f:
        for raw_line in f:
            stripped = raw_line.rstrip('\n')
            compact = stripped.strip()

            if not compact:
                # Keep visual spacing between metadata chunks, but collapse repeats.
                if pending_meta and pending_meta[-1] != "":
                    pending_meta.append("")
                continue

            if is_tab_line(stripped):
                current_block.append(sanitize_tab_line(stripped).lstrip().rstrip())

                if len(current_block) == expected_strings:
                    # Remove trailing empty metadata rows to keep output tidy.
                    while pending_meta and pending_meta[-1] == "":
                        pending_meta.pop()

                    blocks_with_meta.append((pending_meta.copy(), current_block.copy()))
                    pending_meta.clear()
                    current_block.clear()
            else:
                # Non-tab text is treated as section/part metadata.
                if current_block:
                    # Defensive reset for malformed blocks; we only parse complete 6-line groups.
                    current_block.clear()
                pending_meta.append(compact)

    while pending_meta and pending_meta[-1] == "":
        pending_meta.pop()

    return blocks_with_meta, pending_meta

def resolve_string_tunings(line_prefixes: List[str]) -> List[int]:
    """Resolves string prefixes into MIDI base pitches."""
    midi_tunings = []
    assume_guitar = (len(line_prefixes) == 6)
    
    for index, prefix in enumerate(line_prefixes):
        clean_prefix = re.sub(r'[^a-zA-Z0-9#]', '', prefix).strip()
        if not clean_prefix:
            # Fallback for completely empty prefixes (assuming standard E)
            standard = ["E4", "B3", "G3", "D3", "A2", "E2"]
            clean_prefix = standard[index] if assume_guitar else "C3"
            
        if re.search(r'\d+$', clean_prefix):
            note_str = clean_prefix
        else:
            note_str = f"{clean_prefix}{DEFAULT_GUITAR_OCTAVES[index]}" if assume_guitar else f"s{clean_prefix}3"
            
        midi_tunings.append(note_to_midi(note_str))
    return midi_tunings

def parse_tab_block(lines: List[str], base_tunings_midi: List[int], time_offset: int = 0) -> List[TimeSlice]:
    """
    Parses a block of tablature (e.g., 6 lines) vertically.
    Correlates characters across strings using their string index to build TimeSlices.
    """
    if not lines:
        return []

    num_strings = len(lines)
    max_length = max(len(line) for line in lines)
    
    # Pad strings to equal length to avoid index out of bounds during vertical scan
    padded_lines = [line.ljust(max_length) for line in lines]
    
    timeline: List[TimeSlice] = []
    
    # Trackers to skip characters when we process multi-digit numbers (like '12')
    # index maps to string_index
    skip_chars = [0] * num_strings
    last_note_on_string: List[Optional[Note]] = [None] * num_strings
    pending_technique_before = ["" for _ in range(num_strings)]
    in_parentheses = [False] * num_strings
    
    # Start scanning from left to right (visual columns)
    for col_idx in range(max_length):
        current_slice = TimeSlice(visual_index=col_idx + time_offset)
        column_has_symbol = False
        
        # Check if the entire column is a bar line
        col_chars = [padded_lines[s][col_idx] for s in range(num_strings)]
        if all(c == '|' for c in col_chars):
            current_slice.special_char = '|'
            current_slice.is_empty = False
            timeline.append(current_slice)
            continue

        for string_idx in range(num_strings):
            if skip_chars[string_idx] > 0:
                skip_chars[string_idx] -= 1
                continue
                
            char = padded_lines[string_idx][col_idx]

            if char == '(':
                in_parentheses[string_idx] = True
                column_has_symbol = True
                continue

            if char == ')':
                in_parentheses[string_idx] = False
                column_has_symbol = True
                continue

            if in_parentheses[string_idx] and (char.isdigit() or char.lower() == 'x'):
                # Ghost notes in brackets (e.g., (7)) should not become playable notes.
                column_has_symbol = True
                continue
            
            if char.isdigit():
                # Extract full number (look ahead)
                fret_str = char
                look_ahead = 1
                while (col_idx + look_ahead < max_length and 
                       padded_lines[string_idx][col_idx + look_ahead].isdigit()):
                    fret_str += padded_lines[string_idx][col_idx + look_ahead]
                    look_ahead += 1
                
                fret_num = int(fret_str)
                skip_chars[string_idx] = len(fret_str) - 1
                
                # Calculate MIDI pitch (Base string MIDI + fret)
                pitch = base_tunings_midi[string_idx] + fret_num
                
                note = Note(string_index=string_idx, fret=fret_num, pitch_midi=pitch)
                if pending_technique_before[string_idx]:
                    note.technique_before = pending_technique_before[string_idx]
                    pending_technique_before[string_idx] = ""

                current_slice.notes.append(note)
                current_slice.is_empty = False
                last_note_on_string[string_idx] = note
                
            elif char.lower() == 'x':
                 # Handle dead notes
                 note = Note(string_index=string_idx, fret='x')
                 if pending_technique_before[string_idx]:
                     note.technique_before = pending_technique_before[string_idx]
                     pending_technique_before[string_idx] = ""

                 current_slice.notes.append(note)
                 current_slice.is_empty = False
                 last_note_on_string[string_idx] = note

            elif char in TECHNIQUE_CHARS:
                # Technique symbols occupy visual space and should be preserved in timing.
                column_has_symbol = True

                if last_note_on_string[string_idx] is not None:
                    last_note_on_string[string_idx].technique_after += char

                # Some techniques connect previous and next note (e.g., 5h7, 8/10).
                # Attach to upcoming note too so articulation remains clearly visible.
                if char in CONNECTING_TECHNIQUES:
                    pending_technique_before[string_idx] += char

            elif char not in {'-', ' ', '|'}:
                # Preserve unknown tab symbols in timeline spacing to avoid drift.
                column_has_symbol = True
            
            # NOTE: For techniques (h, p, /, ~, etc.), a more advanced look-around 
            # would be implemented here to attach them to the 'Note' objects.
                
        # Only add the slice if there's actually a note, or if we want to preserve spacing.
        # For mapping purposes, preserving empty slices (dashes) helps reconstruct the tab later.
        if (
            not current_slice.is_empty
            or all(padded_lines[s][col_idx] in ['-', ' '] for s in range(num_strings))
            or column_has_symbol
        ):
            timeline.append(current_slice)

    return timeline

def parse_full_tab(file_path: str, base_tunings_midi: List[int]) -> List[TimeSlice]:
    """
    Reads the whole file, finds all blocks, parses them, 
    and returns one continuous timeline.
    """
    blocks = extract_tab_blocks(file_path)
    total_timeline = []
    current_time_offset = 0
    
    for block in blocks:
        block_timeline = parse_tab_block(block, base_tunings_midi, time_offset=current_time_offset)
        total_timeline.extend(block_timeline)
        
        if block_timeline:
            current_time_offset = total_timeline[-1].visual_index + 1
            
    return total_timeline

def parse_tab_blocks_with_sections(file_path: str, base_tunings_midi: List[int]) -> Tuple[List[Tuple[List[str], List[TimeSlice], bool]], List[str]]:
    """
    Parses the tab file into independent timeline blocks and keeps the textual
    section/part lines that appear before each block.

    This preserves original structure in output while keeping translation logic
    focused only on parsed notes.
    """
    blocks_with_meta, trailing_meta = extract_tab_blocks_with_metadata(file_path)
    parsed_blocks: List[Tuple[List[str], List[TimeSlice], bool]] = []

    for metadata_lines, block_lines in blocks_with_meta:
        block_timeline = parse_tab_block(block_lines, base_tunings_midi, time_offset=0)
        ends_with_bar = all(line.rstrip().endswith('|') for line in block_lines)
        parsed_blocks.append((metadata_lines, block_timeline, ends_with_bar))

    return parsed_blocks, trailing_meta

def detect_source_prefixes(file_path: str) -> List[str]:
    """Public helper used by CLI to derive source tuning from tab itself."""
    prefixes, _ = detect_source_prefixes_and_count(file_path)
    return prefixes



# --- Quick Test ---
if __name__ == "__main__":
    sample_tab = [
        "e|---12---7h9---|",
        "B|---12---8-----|",
        "G|--------7-----|",
        "D|--------------|",
        "A|--------------|",
        "E|--------------|"
    ]
    
    tunings = resolve_string_tunings(['e', 'B', 'G', 'D', 'A', 'E'])
    slices = parse_tab_block(sample_tab, tunings)
    
    # Print parsed notes to verify time alignment
    for ts in slices:
        if not ts.is_empty:
            if ts.special_char:
                print(f"Col {ts.visual_index}: {ts.special_char}")
            else:
                notes_info = [f"Str {n.string_index} Fret {n.fret} (MIDI {n.pitch_midi})" for n in ts.notes]
                print(f"Col {ts.visual_index}: {', '.join(notes_info)}")