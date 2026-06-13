import re
from typing import List, Optional, Union
from dataclasses import dataclass, field

# --- Helper logic from tuning.py (simplified for this step) ---
def midi_to_note_name(midi_number: int) -> str:
    """Converts a MIDI note number back to a string like 'C4' or 'D#3'."""
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_number // 12) - 1
    note_name = notes[midi_number % 12]
    return f"{note_name}{octave}"

def format_note_name(midi_number: int, show_octave: bool = False) -> str:
    """Return note name with optional octave suffix."""
    full_name = midi_to_note_name(midi_number)
    if show_octave:
        return full_name
    return re.sub(r'-?\d+$', '', full_name)

def normalize_technique_symbols(text: str) -> str:
    """Normalize technique symbols for readability (slides '/' and '\\' -> 's')."""
    return text.replace('/', 's').replace('\\', 's')

def center_duplicate_connectors(line: str) -> str:
    """
    Convert duplicated connectors to a single centered connector while preserving width.
    Example: p---p -> --p--, h--h -> --h-.
    """
    for symbol in ['h', 'p', 's', 'r']:
        escaped = re.escape(symbol)
        pattern = re.compile(rf'{escaped}(-+){escaped}')

        def repl(match):
            total_len = len(match.group(0))
            left = total_len // 2
            right = total_len - left - 1
            return ('-' * left) + symbol + ('-' * right)

        line = pattern.sub(repl, line)

    return line

# --- Data Models ---
@dataclass
class Note:
    string_index: int
    fret: Union[int, str]
    pitch_midi: Optional[int] = None
    
    # =========================================================================
    # TODO: ARTICULATION AND TECHNIQUES PARSING
    # =========================================================================
    # Tablatures often contain techniques like hammer-ons (h), pull-offs (p), 
    # slides (/ or \), bends (b), and vibratos (~).
    # 
    # Challenges to solve in future iterations:
    # 1. Look-around logic: A symbol like 'h' connects two notes (e.g., 5h7). 
    #    The parser needs to know if 'h' is 'technique_after' for 5 or 
    #    'technique_before' for 7.
    # 2. Timing offset: Symbols take up visual space (characters). If a chord 
    #    is played on other strings while a slide happens, we must ensure 
    #    the visual indices don't misalign the time slices.
    # 3. Instrument constraints: A 2-fret bend on a guitar is easy. Translating 
    #    that exact bend to a ukulele nylon string might be physically impossible. 
    #    We'll need logic to decide whether to keep the bend or translate it 
    #    to a slide/hammer-on on the target instrument.
    # =========================================================================
    technique_before: str = ""
    technique_after: str = ""

@dataclass
class TimeSlice:
    visual_index: int
    notes: List[Note] = field(default_factory=list)
    is_empty: bool = True
    special_char: str = ""

# --- Rendering Logic ---

def max_simultaneous_notes_in_timeline(timeline: List[TimeSlice]) -> int:
    """Return max number of simultaneous note events in this timeline."""
    if not timeline:
        return 1

    return max(
        (len(ts.notes) for ts in timeline if not ts.is_empty and not ts.special_char),
        default=1
    )

def render_note_sequence(
    timeline: List[TimeSlice],
    fixed_height: Optional[int] = None,
    show_octave: bool = False,
) -> str:
    """
    Takes the parsed timeline and renders an intermediate ASCII representation 
    using actual note names (e.g., C4, D#3) instead of frets.
    The number of lines adapts dynamically based on the maximum number of 
    simultaneous notes played in any given time slice.
    """
    if not timeline:
        return ""

    # Use file-global fixed height when provided, otherwise derive from this block.
    if fixed_height is not None and fixed_height > 0:
        max_simultaneous_notes = fixed_height
    else:
        max_simultaneous_notes = max(3,max_simultaneous_notes_in_timeline(timeline))
    
    # Initialize empty string builders for our lines
    lines = ["" for _ in range(max_simultaneous_notes)]

    for ts in timeline:
        # Handle bar lines and layout separators
        if ts.special_char:
            for i in range(max_simultaneous_notes):
                lines[i] += ts.special_char
            continue
            
        # Handle empty time (just passing time with dashes)
        if ts.is_empty:
            for i in range(max_simultaneous_notes):
                lines[i] += "-"
            continue
            
        # Extract notes and sort them by pitch (highest pitch on top line)
        valid_notes = [n for n in ts.notes if n.pitch_midi is not None]
        dead_notes = [n for n in ts.notes if n.fret == 'x']
        
        # Sort descending so highest note is line 0
        sorted_notes = sorted(valid_notes, key=lambda n: n.pitch_midi, reverse=True)
        
        # Convert to text with techniques (e.g., '/C4~', 'x', 'hD5').
        note_strings = [
            f"{normalize_technique_symbols(n.technique_before)}"
            f"{format_note_name(n.pitch_midi, show_octave=show_octave)}"
            f"{normalize_technique_symbols(n.technique_after)}"
            for n in sorted_notes
        ]
        note_strings.extend([
            f"{normalize_technique_symbols(n.technique_before)}x{normalize_technique_symbols(n.technique_after)}"
            for n in dead_notes
        ])
        
        # Find the max width required in this specific vertical column.
        # Add 1 extra char so adjacent note tokens are always separated by '-'.
        # This prevents unreadable runs like: B5F#5D5B4...
        slice_width = max([len(s) for s in note_strings] + [1]) + 1
        
        for i in range(max_simultaneous_notes):
            if i < len(note_strings):
                # Write the note and pad the remaining space with dashes to maintain alignment
                lines[i] += note_strings[i].ljust(slice_width, '-')
            else:
                # If this line has no note playing, fill it completely with dashes
                lines[i] += '-' * slice_width

    centered_lines = [center_duplicate_connectors(line) for line in lines]
    return "\n".join(centered_lines)

# --- Quick Test ---
if __name__ == "__main__":
    # Simulating a parsed timeline of a short sequence:
    # 1. A single note (E4)
    # 2. A 3-note C major chord (C4, E4, G4)
    # 3. A bar line
    # 4. A 2-note power chord with a dead note
    
    mock_timeline = [
        TimeSlice(0, [Note(0, 0, 64)], is_empty=False), # E4
        TimeSlice(1, [], is_empty=True),
        TimeSlice(2, [Note(1, 1, 60), Note(2, 0, 64), Note(3, 2, 67)], is_empty=False), # C4, E4, G4
        TimeSlice(3, [], is_empty=True),
        TimeSlice(4, [], is_empty=False, special_char='|'),
        TimeSlice(5, [], is_empty=True),
        TimeSlice(6, [Note(4, 3, 53), Note(5, 5, 60), Note(6, 'x')], is_empty=False), # F2, C4, dead note
        TimeSlice(7, [], is_empty=True)
    ]
    
    print("Note Sequence Tablature:")
    print(render_note_sequence(mock_timeline))