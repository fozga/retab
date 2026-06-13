import re
from typing import List, Dict, Optional
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
            note_str = f"{clean_prefix}{DEFAULT_GUITAR_OCTAVES[index]}" if assume_guitar else f"{clean_prefix}3"
            
        midi_tunings.append(note_to_midi(note_str))
    return midi_tunings

def parse_tab_block(lines: List[str], base_tunings_midi: List[int]) -> List[TimeSlice]:
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
    
    # Start scanning from left to right (visual columns)
    for col_idx in range(max_length):
        current_slice = TimeSlice(visual_index=col_idx)
        
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
                current_slice.notes.append(note)
                current_slice.is_empty = False
                
            elif char.lower() == 'x':
                 # Handle dead notes
                 note = Note(string_index=string_idx, fret='x')
                 current_slice.notes.append(note)
                 current_slice.is_empty = False
            
            # NOTE: For techniques (h, p, /, ~, etc.), a more advanced look-around 
            # would be implemented here to attach them to the 'Note' objects.
                
        # Only add the slice if there's actually a note, or if we want to preserve spacing.
        # For mapping purposes, preserving empty slices (dashes) helps reconstruct the tab later.
        if not current_slice.is_empty or all(padded_lines[s][col_idx] in ['-', ' '] for s in range(num_strings)):
            timeline.append(current_slice)

    return timeline

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