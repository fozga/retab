from typing import List, Dict, Optional
from dataclasses import dataclass, field
# Assuming Note and TimeSlice are imported from your models file (e.g., pitch_timeline)
from pitch_timeline import TimeSlice, Note

def get_pitch_in_range(pitch: int, target_tuning: List[int], max_fret: int = 24) -> int:
    """
    Attempts to shift the pitch by octaves until it fits within the instrument's range.
    """
    min_string = min(target_tuning)
    max_string = max(target_tuning) + max_fret
    
    # If pitch is too low, shift up
    while pitch < min_string:
        pitch += 12
    # If pitch is too high, shift down
    while pitch > max_string:
        pitch -= 12
        
    return pitch

def find_best_fingering(pitches_midi: List[int], target_tuning_midi: List[int], max_fret: int = 24) -> Dict[int, int]:
    """
    Finds a playable string/fret combination for a set of pitches on a target instrument.
    Returns a dictionary mapping string_index to fret_number.
    Uses backtracking to find the combination with the lowest sum of frets.
    """
    # If there are more pitches than strings, we must drop some notes.
    # Heuristic: keep the highest notes, as they carry the melody, and drop the lowest.
    # (In a more advanced version, we might prioritize root notes).
    
    # 1. Transpose out-of-range notes to nearest playable octave
    adjusted_pitches = [get_pitch_in_range(p, target_tuning_midi, max_fret) for p in pitches_midi]
    
    # 2. Continue with original logic (Backtracking)
    if len(pitches_midi) > len(target_tuning_midi):
        pitches_to_play = sorted(pitches_midi, reverse=True)[:len(target_tuning_midi)]
    else:
        pitches_to_play = pitches_midi

    best_fingering = None
    min_fret_sum = float('inf')

    def dfs(pitch_idx: int, current_fingering: Dict[int, int], used_strings: set):
        nonlocal best_fingering, min_fret_sum

        # Base case: all pitches have been successfully mapped to strings
        if pitch_idx == len(pitches_to_play):
            fret_sum = sum(current_fingering.values())
            if fret_sum < min_fret_sum:
                min_fret_sum = fret_sum
                best_fingering = current_fingering.copy()
            return

        pitch = pitches_to_play[pitch_idx]

        # Try placing the current pitch on every available string
        for string_idx, string_midi in enumerate(target_tuning_midi):
            if string_idx in used_strings:
                continue
            
            fret = pitch - string_midi
            
            # Check if the fret is physically playable
            if 0 <= fret <= max_fret:
                current_fingering[string_idx] = fret
                used_strings.add(string_idx)
                
                # Recurse to the next pitch
                dfs(pitch_idx + 1, current_fingering, used_strings)
                
                # Backtrack to try other combinations
                used_strings.remove(string_idx)
                del current_fingering[string_idx]

    dfs(0, {}, set())
    return best_fingering or {}

def render_target_tab(timeline: List[TimeSlice], target_tuning_midi: List[int]) -> str:
    """
    Translates the abstract timeline to the target instrument and renders the final ASCII tab.
    """
    if not timeline:
        return ""

    num_strings = len(target_tuning_midi)
    lines = ["" for _ in range(num_strings)]

    for ts in timeline:
        if ts.special_char:
            for i in range(num_strings):
                lines[i] += ts.special_char
            continue

        if ts.is_empty:
            for i in range(num_strings):
                lines[i] += "-"
            continue

        # Extract pitches, ignoring dead notes ('x') for this basic implementation
        valid_pitches = [n.pitch_midi for n in ts.notes if n.pitch_midi is not None and n.fret != 'x']
        
        # Calculate fingering
        fingering = find_best_fingering(valid_pitches, target_tuning_midi)
        
        # Dead notes fallback: if there are dead notes but no valid pitches, just put 'x' on the lowest string
        dead_notes_count = sum(1 for n in ts.notes if n.fret == 'x')
        if dead_notes_count > 0 and not fingering:
            fingering = {num_strings - 1: 'x'}

        # Calculate max width required for this column (e.g., '12' takes 2 chars)
        fret_strings = {s_idx: str(fret) for s_idx, fret in fingering.items()}
        slice_width = max([len(f) for f in fret_strings.values()] + [1]) if fret_strings else 1

        for i in range(num_strings):
            if i in fret_strings:
                # Add the fret number and pad with dashes
                lines[i] += fret_strings[i].ljust(slice_width, '-')
            else:
                # Empty string at this time slice
                lines[i] += '-' * slice_width

    return "\n".join(lines)