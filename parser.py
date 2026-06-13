import re
from typing import List
from tuning import note_to_midi

# Default octaves for a 6-string guitar, from top line (1st string) to bottom line (6th string)
DEFAULT_GUITAR_OCTAVES = [4, 3, 3, 3, 2, 2]

def resolve_string_tunings(line_prefixes: List[str]) -> List[int]:
    """
    Takes a list of string prefixes from the tab (e.g., ['e', 'B', 'G', 'D', 'A', 'E'])
    and returns a list of corresponding MIDI note numbers.
    Applies default guitar octaves if numbers are missing and there are 6 strings.
    """
    midi_tunings = []
    
    # Check if we have exactly 6 strings to safely assume standard guitar layout
    assume_guitar = (len(line_prefixes) == 6)
    
    for index, prefix in enumerate(line_prefixes):
        # Remove any whitespace or separator characters like '|'
        clean_prefix = re.sub(r'[^a-zA-Z0-9#]', '', prefix).strip()
        
        if not clean_prefix:
            # If completely empty, we might need to fallback to standard E based on index,
            # but for now let's raise an error or handle it gracefully.
            raise ValueError(f"Empty tuning prefix at line {index + 1}")
            
        # Check if an octave digit is already present (e.g., 'E4', 'C#3')
        if re.search(r'\d+$', clean_prefix):
            note_str = clean_prefix
        else:
            if assume_guitar:
                # Append the default octave for this specific string index
                note_str = f"{clean_prefix}{DEFAULT_GUITAR_OCTAVES[index]}"
            else:
                # Fallback if not 6 strings and no octaves provided
                # Defaulting to octave 3 as a safe, neutral middle ground
                note_str = f"{clean_prefix}3"
                
        # Convert the resolved string (e.g., 'E4') to MIDI using the function from tuning.py
        midi_tunings.append(note_to_midi(note_str))
        
    return midi_tunings

# --- Quick tests for the parser module ---
if __name__ == "__main__":
    # Test 1: Exact notes provided
    print("Exact notes:", resolve_string_tunings(["E4", "B3", "G3", "D3", "A2", "E2"]))
    
    # Test 2: Standard guitar letters without octaves (notice lowercase 'e' is handled gracefully by tuning.py)
    print("Letters only:", resolve_string_tunings(["e", "B", "G", "D", "A", "E"]))
    
    # Test 3: Drop D letters only
    print("Drop D letters:", resolve_string_tunings(["E", "B", "G", "D", "A", "D"]))