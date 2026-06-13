import re
from typing import List

# Standard MIDI standard sets C4 (Middle C) to 60.
# The formula for MIDI note is: (Octave + 1) * 12 + Note_Index
NOTE_TO_INDEX = {
    'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3,
    'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7, 'G#': 8,
    'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11
}

PRESET_TUNINGS = {
    # Guitar tunings (6 strings)
    "standard": ["E2", "A2", "D3", "G3", "B3", "E4"],
    "drop-d": ["D2", "A2", "D3", "G3", "B3", "E4"],
    "drop-c": ["C2", "G2", "C3", "F3", "A3", "D4"],
    "open-g": ["D2", "G2", "D3", "G3", "B3", "D4"],
    
    # Other instruments
    "ukulele": ["G4", "C4", "E4", "A4"],     # Standard re-entrant tuning (high G)
    "ukulele-low-g": ["G3", "C4", "E4", "A4"],
    "bass": ["E1", "A1", "D2", "G2"],
    "violin": ["G3", "D4", "A4", "E5"],
    "mandolin": ["G3", "D4", "A4", "E5"],
}

INDEX_TO_NOTE_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_to_midi(note_str: str) -> int:
    """
    Converts a scientific pitch notation string (e.g., 'C#4', 'Eb3') to a MIDI note number.
    """
    note_str = note_str.strip().upper()
    
    # Regex to separate the note name (with optional # or B) from the octave number
    match = re.match(r"^([A-G](?:#|B)?)(-?\d+)$", note_str)
    if not match:
        raise ValueError(f"Invalid note format: '{note_str}'. Expected format like 'C4' or 'D#3'.")
        
    note_name, octave_str = match.groups()
    
    if note_name not in NOTE_TO_INDEX:
         raise ValueError(f"Unknown note name: '{note_name}'")
         
    octave = int(octave_str)
    note_index = NOTE_TO_INDEX[note_name]
    
    # Calculate MIDI note number
    midi_number = (octave + 1) * 12 + note_index
    return midi_number

def midi_to_note_name(midi_number: int) -> str:
    """
    Converts a MIDI note number to scientific pitch notation (e.g., 60 -> C4).
    """
    if not isinstance(midi_number, int):
        raise ValueError(f"MIDI note must be an integer, got: {midi_number!r}")
    if midi_number < 0 or midi_number > 127:
        raise ValueError(f"MIDI note out of range (0-127): {midi_number}")

    note_name = INDEX_TO_NOTE_SHARP[midi_number % 12]
    octave = (midi_number // 12) - 1
    return f"{note_name}{octave}"

def get_tuning_midi(tuning_input: str) -> List[int]:
    """
    Returns a list of MIDI note numbers for a given tuning.
    Input can be a preset name (e.g., 'drop-c') or a custom string (e.g., 'E2-A2-D3-G3-B3-E4').
    """
    tuning_input = tuning_input.strip().lower()
    
    # Check if it's a known preset
    if tuning_input in PRESET_TUNINGS:
        note_strings = PRESET_TUNINGS[tuning_input]
    else:
        # Treat as custom tuning separated by dashes
        note_strings = tuning_input.upper().split("-")
        
    # Convert each note string to its MIDI equivalent
    midi_notes = [note_to_midi(note) for note in note_strings]
    return midi_notes

# --- Quick tests for the module ---
if __name__ == "__main__":
    print("Standard Guitar MIDI:", get_tuning_midi("standard"))
    print("Ukulele MIDI:", get_tuning_midi("ukulele"))
    print("Custom E-A-D-G-B-A:", get_tuning_midi("E2-A2-D3-G3-B3-A4"))