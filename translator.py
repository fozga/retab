from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from note_sequence import TimeSlice, Note, normalize_technique_symbols, center_duplicate_connectors

CONNECTOR_SYMBOLS = {'h', 'p', 's', 'r'}

def _split_connector_and_other(tech: str) -> tuple[str, str]:
    connectors = ''.join(ch for ch in tech if ch in CONNECTOR_SYMBOLS)
    others = ''.join(ch for ch in tech if ch not in CONNECTOR_SYMBOLS)
    return connectors, others

def get_strictness_profile(strictness: str) -> Dict[str, float]:
    """Return scoring knobs for melodic contour handling."""
    strictness = (strictness or "strict").lower()

    if strictness == "conservative":
        return {
            "fret_weight": 0.55,
            "string_change_penalty": 2.5,
            "jump_threshold": 4.0,
            "jump_penalty": 1.3,
            "direction_mismatch_penalty": 10.0,
            "source_same_string_penalty": 2.0,
            "source_string_direction_mismatch_penalty": 6.0,
            "source_string_static_penalty": 5.0,
            "interval_distortion_penalty": 0.9,
            "post_top_string_drop_penalty": 2.5,
            "octave_penalty": 2.0,
            "downward_non_bass_shift_penalty": 4.0,
            "allow_plus_24": 0.0,
            "run_shift_change_penalty": 10.0,
        }

    if strictness == "balanced":
        return {
            "fret_weight": 0.45,
            "string_change_penalty": 4.0,
            "jump_threshold": 3.5,
            "jump_penalty": 1.7,
            "direction_mismatch_penalty": 18.0,
            "source_same_string_penalty": 3.5,
            "source_string_direction_mismatch_penalty": 10.0,
            "source_string_static_penalty": 8.0,
            "interval_distortion_penalty": 1.3,
            "post_top_string_drop_penalty": 4.0,
            "octave_penalty": 1.4,
            "downward_non_bass_shift_penalty": 4.0,
            "allow_plus_24": 1.0,
            "run_shift_change_penalty": 18.0,
        }

    # strict (default)
    return {
        "fret_weight": 0.35,
        "string_change_penalty": 6.0,
        "jump_threshold": 3.0,
        "jump_penalty": 2.0,
        "direction_mismatch_penalty": 32.0,
        "source_same_string_penalty": 5.0,
        "source_string_direction_mismatch_penalty": 16.0,
        "source_string_static_penalty": 12.0,
        "interval_distortion_penalty": 2.1,
        "post_top_string_drop_penalty": 7.0,
        "octave_penalty": 1.0,
        "downward_non_bass_shift_penalty": 6.0,
        "allow_plus_24": 1.0,
        "run_shift_change_penalty": 35.0,
    }

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

def apply_uniform_octave_shift(
    pitches_midi: List[int],
    semitone_shift: int,
    target_tuning_midi: List[int],
    max_fret: int = 24,
) -> List[int]:
    """Shift all pitches by a fixed amount, then fold each into target range."""
    return [
        get_pitch_in_range(p + semitone_shift, target_tuning_midi, max_fret)
        for p in pitches_midi
    ]

def score_fingering(
    fingering: Dict[int, int],
    previous_fingering: Optional[Dict[int, int]] = None,
) -> float:
    """
    Lower score is better.
    Penalizes very high frets and large fret jumps between consecutive slices.
    """
    if not fingering:
        return 0.0

    score = 0.0
    frets = list(fingering.values())

    # Base preference for low/mid fret positions.
    score += sum(frets)

    # Strong penalty when notes drift high up the neck.
    high_frets = [f for f in frets if f > 12]
    score += sum((f - 12) * 3.0 for f in high_frets)
    if high_frets and len(high_frets) >= max(1, len(frets) // 2):
        score += 40.0
    if max(frets) > 15:
        score += (max(frets) - 15) * 6.0

    # Encourage compact hand shape in chords.
    if len(frets) > 1:
        score += (max(frets) - min(frets)) * 0.75

    # Penalize large movements on the same string from previous slice.
    if previous_fingering:
        for string_idx, fret in fingering.items():
            if string_idx in previous_fingering:
                jump = abs(fret - previous_fingering[string_idx])
                if jump > 5:
                    score += (jump - 5) * 2.0

    return score

def choose_single_note_fingering(
    pitch: int,
    target_tuning_midi: List[int],
    effective_max_fret: int,
    previous_target_note: Optional[Tuple[int, int, int]],
    previous_source_note: Optional[Note],
    source_note: Optional[Note],
    strictness_profile: Dict[str, float],
    prefer_adjacent_strings: bool = False,
    recent_target_strings: Optional[List[int]] = None,
    locked_octave_offset: Optional[int] = None,
) -> Tuple[Dict[int, int], int, int]:
    """
    Choose fingering for monophonic slices with melodic-contour preference.
    Prefers preserving phrase direction and same-string continuity when feasible.
    """
    candidates: List[Tuple[float, int, int, int]] = []  # (score, string_idx, fret, chosen_pitch)

    pitch_variants = [pitch, pitch + 12]
    if strictness_profile["allow_plus_24"] >= 1.0:
        pitch_variants.append(pitch + 24)

    def collect_candidates(variant_pitches: List[int]) -> List[Tuple[float, int, int, int]]:
        local_candidates: List[Tuple[float, int, int, int]] = []

        for chosen_pitch in variant_pitches:
            for string_idx, base_pitch in enumerate(target_tuning_midi):
                fret = chosen_pitch - base_pitch
                if not (0 <= fret <= effective_max_fret):
                    continue

                # Continuity is more important than absolute minimum fret for melody lines.
                score = float(fret) * strictness_profile["fret_weight"]

                # Small penalty for octave-alternative placement.
                score += (abs(chosen_pitch - pitch) / 12.0) * strictness_profile["octave_penalty"]

                if fret > 12:
                    score += (fret - 12) * 5.0

                if previous_target_note is not None:
                    prev_string, prev_fret, prev_pitch = previous_target_note

                    # Keep melody on the same string when possible.
                    if string_idx != prev_string:
                        score += strictness_profile["string_change_penalty"]

                    jump = abs(fret - prev_fret)
                    if jump > strictness_profile["jump_threshold"]:
                        score += (jump - strictness_profile["jump_threshold"]) * strictness_profile["jump_penalty"]

                    # Preserve melodic direction from source phrase when possible.
                    if source_note is not None and previous_source_note is not None:
                        src_delta = source_note.pitch_midi - previous_source_note.pitch_midi
                        dst_delta = chosen_pitch - prev_pitch
                        if src_delta != 0 and dst_delta != 0 and (src_delta > 0) != (dst_delta > 0):
                            score += strictness_profile["direction_mismatch_penalty"]

                        # Preserve interval shape: avoid target jumps much larger than source motion.
                        score += abs(abs(dst_delta) - abs(src_delta)) * strictness_profile["interval_distortion_penalty"]

                        # If source stays on same string, heavily prefer staying on same target string.
                        if source_note.string_index == previous_source_note.string_index and string_idx != prev_string:
                            score += strictness_profile["source_same_string_penalty"]

                        # Preserve source string-travel direction.
                        # Source indexing: smaller index = higher-pitched string (e.g., e=0, E=5).
                        # Target indexing in this app: larger index = higher-pitched string.
                        source_string_delta = source_note.string_index - previous_source_note.string_index
                        target_string_delta = string_idx - prev_string
                        if source_string_delta != 0:
                            if target_string_delta == 0:
                                score += strictness_profile["source_string_static_penalty"]
                            else:
                                source_moved_higher = source_string_delta < 0
                                target_moved_higher = target_string_delta > 0
                                if source_moved_higher != target_moved_higher:
                                    score += strictness_profile["source_string_direction_mismatch_penalty"]

                # Optional broader string-flow smoothing over recent melody notes.
                if prefer_adjacent_strings and recent_target_strings:
                    recent_window = recent_target_strings[-4:]
                    for age, hist_string in enumerate(reversed(recent_window), start=1):
                        weight = 1.0 / age
                        distance = abs(string_idx - hist_string)
                        if distance == 0:
                            score -= 0.8 * weight
                        elif distance == 1:
                            score += 0.5 * weight
                        else:
                            score += (distance - 1) * 3.5 * weight

                    # If the recent phrase reached the highest string, avoid dropping away
                    # unless that move is truly necessary.
                    highest_idx = len(target_tuning_midi) - 1
                    if highest_idx in recent_window and string_idx < highest_idx:
                        score += strictness_profile["post_top_string_drop_penalty"]

                local_candidates.append((score, string_idx, fret, chosen_pitch))

        return local_candidates

    if locked_octave_offset is not None:
        locked_pitch = pitch + locked_octave_offset
        candidates = collect_candidates([locked_pitch])
        if not candidates:
            # If lock is impossible, gracefully fall back to all variants.
            candidates = collect_candidates(pitch_variants)
    else:
        candidates = collect_candidates(pitch_variants)

    if not candidates:
        return {}, pitch, 0

    _, best_string, best_fret, best_pitch = min(candidates, key=lambda x: x[0])
    return {best_string: best_fret}, best_pitch, (best_pitch - pitch)

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
    if len(adjusted_pitches) > len(target_tuning_midi):
        pitches_to_play = sorted(adjusted_pitches, reverse=True)[:len(target_tuning_midi)]
    else:
        pitches_to_play = adjusted_pitches

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

def render_target_tab(
    timeline: List[TimeSlice],
    target_tuning_midi: List[int],
    strictness: str = "strict",
    prefer_adjacent_strings: bool = False,
) -> str:
    """
    Translates the abstract timeline to the target instrument and renders the final ASCII tab.
    """
    if not timeline:
        return ""

    num_strings = len(target_tuning_midi)
    lines = ["" for _ in range(num_strings)]
    previous_fingering: Dict[int, int] = {}
    is_bass_like = (num_strings == 4 and min(target_tuning_midi) <= 40)
    effective_max_fret = 12 if is_bass_like else 24
    strictness_profile = get_strictness_profile(strictness)
    previous_target_note: Optional[Tuple[int, int, int]] = None
    previous_source_note: Optional[Note] = None
    recent_target_strings: List[int] = []
    monophonic_shift_lock: Optional[int] = None
    monophonic_octave_offset_lock: Optional[int] = None

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
        source_notes = [n for n in ts.notes if n.pitch_midi is not None and n.fret != 'x']
        valid_pitches = [n.pitch_midi for n in source_notes]
        
        # Calculate fingering with adaptive octave transposition for playability.
        best_fingering: Dict[int, int] = {}
        best_adjusted_pitches: List[int] = []
        best_score = float('inf')

        # Try no shift first, then octave shifts that often help bass playability.
        default_shifts = [0, -12, 12, -24, 24]
        if is_bass_like:
            default_shifts = [0, -12, -24, 12, 24]

        is_monophonic_slice = (len(source_notes) == 1)
        if is_monophonic_slice and monophonic_shift_lock is not None:
            # Keep phrase in one register when possible.
            candidate_shifts = [monophonic_shift_lock] + [s for s in default_shifts if s != monophonic_shift_lock]
        else:
            candidate_shifts = default_shifts

        best_shift = 0
        best_octave_offset = 0
        for semitone_shift in candidate_shifts:
            chosen_offset = 0
            adjusted_pitches = apply_uniform_octave_shift(
                valid_pitches,
                semitone_shift,
                target_tuning_midi,
                max_fret=effective_max_fret,
            )

            if len(adjusted_pitches) == 1 and len(source_notes) == 1:
                candidate_fingering, chosen_pitch, chosen_offset = choose_single_note_fingering(
                    adjusted_pitches[0],
                    target_tuning_midi,
                    effective_max_fret,
                    previous_target_note,
                    previous_source_note,
                    source_notes[0],
                    strictness_profile,
                    prefer_adjacent_strings=prefer_adjacent_strings,
                    recent_target_strings=recent_target_strings,
                    locked_octave_offset=monophonic_octave_offset_lock if is_monophonic_slice else None,
                )
                adjusted_pitches = [chosen_pitch]
            else:
                candidate_fingering = find_best_fingering(
                    adjusted_pitches,
                    target_tuning_midi,
                    max_fret=effective_max_fret,
                )

            if adjusted_pitches and not candidate_fingering:
                continue

            # Small bias against octave shifts when equivalent, but allow them when better.
            shift_bias = (abs(semitone_shift) / 12.0) * 0.5
            if is_bass_like and semitone_shift < 0:
                # Encourage octave-down choices on bass when they improve playability.
                shift_bias -= (abs(semitone_shift) / 12.0) * 0.2
            elif (not is_bass_like) and semitone_shift < 0:
                # For non-bass targets, avoid dropping melodic lines an octave unless necessary.
                shift_bias += (abs(semitone_shift) / 12.0) * strictness_profile["downward_non_bass_shift_penalty"]

            candidate_score = score_fingering(candidate_fingering, previous_fingering) + shift_bias

            if is_monophonic_slice and monophonic_shift_lock is not None and semitone_shift != monophonic_shift_lock:
                candidate_score += strictness_profile["run_shift_change_penalty"]

            if candidate_score < best_score:
                best_score = candidate_score
                best_fingering = candidate_fingering
                best_adjusted_pitches = adjusted_pitches
                best_shift = semitone_shift
                if len(source_notes) == 1:
                    best_octave_offset = chosen_offset

        fingering = best_fingering

        # Hard continuity safeguard: if melody is on highest string and this slice
        # drops to a lower string, try octave-equivalent remap back to highest string.
        int_fingering_items = [(s, f) for s, f in fingering.items() if isinstance(f, int)]
        highest_idx = num_strings - 1
        if (
            prefer_adjacent_strings
            and previous_target_note is not None
            and previous_target_note[0] == highest_idx
            and len(int_fingering_items) == 1
        ):
            curr_string, curr_fret = int_fingering_items[0]
            if curr_string != highest_idx:
                rendered_pitch = target_tuning_midi[curr_string] + curr_fret
                prev_fret_on_highest = previous_target_note[1]

                high_string_candidates = []
                for shift in (-24, -12, 0, 12, 24):
                    candidate_pitch = rendered_pitch + shift
                    candidate_fret = candidate_pitch - target_tuning_midi[highest_idx]
                    if 0 <= candidate_fret <= effective_max_fret:
                        high_string_candidates.append((abs(candidate_fret - prev_fret_on_highest), candidate_fret, candidate_pitch))

                if high_string_candidates:
                    _, best_high_fret, best_high_pitch = min(high_string_candidates, key=lambda x: x[0])
                    fingering = {highest_idx: best_high_fret}

                    # Keep source-note mapping aligned with remapped rendered pitch.
                    if len(best_adjusted_pitches) == 1:
                        best_adjusted_pitches = [best_high_pitch]
        
        # Dead notes fallback: if there are dead notes but no valid pitches, just put 'x' on the lowest string
        dead_notes_count = sum(1 for n in ts.notes if n.fret == 'x')
        if dead_notes_count > 0 and not fingering:
            fingering = {num_strings - 1: 'x'}

        # Maintain phrase-level register lock through monophonic runs.
        if len(source_notes) == 1 and fingering:
            monophonic_shift_lock = best_shift
            monophonic_octave_offset_lock = best_octave_offset

        pitch_note_buckets: Dict[int, List[Note]] = {}
        for src_note, adjusted_pitch in zip(source_notes, best_adjusted_pitches):
            pitch_note_buckets.setdefault(adjusted_pitch, []).append(src_note)

        # Prefer same-string placement for notes that start with a connector
        # (hammer-on/pull-off/slide/release) when it is still playable.
        moved = True
        while moved:
            moved = False
            for s_idx, fret in list(fingering.items()):
                if not isinstance(fret, int):
                    continue

                rendered_pitch = target_tuning_midi[s_idx] + fret
                src_candidates = pitch_note_buckets.get(rendered_pitch, [])
                src_note = src_candidates[0] if src_candidates else None
                if src_note is None:
                    continue

                before_norm = normalize_technique_symbols(src_note.technique_before)
                before_connectors, _ = _split_connector_and_other(before_norm)
                if not before_connectors:
                    continue

                best_string = s_idx
                best_jump = float('inf')
                for prev_string, prev_fret in previous_fingering.items():
                    candidate_fret = rendered_pitch - target_tuning_midi[prev_string]
                    if not (0 <= candidate_fret <= effective_max_fret):
                        continue
                    jump = abs(candidate_fret - prev_fret)
                    if jump < best_jump:
                        best_jump = jump
                        best_string = prev_string

                if best_string != s_idx and best_jump <= 7 and best_string not in fingering:
                    fingering[best_string] = rendered_pitch - target_tuning_midi[best_string]
                    del fingering[s_idx]
                    moved = True
                    break

        # Calculate max width required for this column (e.g., '12' takes 2 chars)

        fret_strings: Dict[int, str] = {}
        for s_idx, fret in fingering.items():
            fret_text = str(fret)

            if isinstance(fret, int):
                rendered_pitch = target_tuning_midi[s_idx] + fret
                bucket = pitch_note_buckets.get(rendered_pitch, [])
                src_note = bucket.pop(0) if bucket else None

                if src_note is not None:
                    before_norm = normalize_technique_symbols(src_note.technique_before)
                    after_norm = normalize_technique_symbols(src_note.technique_after)

                    before_connectors, before_other = _split_connector_and_other(before_norm)
                    after_connectors, after_other = _split_connector_and_other(after_norm)

                    # Keep incoming connector only when previous note on this line
                    # can realistically connect (same string and moderate jump).
                    keep_before_connectors = ""
                    if s_idx in previous_fingering:
                        jump = abs(fret - previous_fingering[s_idx])
                        if jump <= 7:
                            keep_before_connectors = before_connectors

                    # Outgoing connectors are shown when this slice is effectively melodic
                    # (single sounding note), otherwise they are removed to avoid
                    # impossible cross-string connector notation.
                    sounding_int_notes = sum(1 for v in fingering.values() if isinstance(v, int))
                    keep_after_connectors = after_connectors if sounding_int_notes <= 1 else ""

                    fret_text = (
                        f"{before_other}{keep_before_connectors}"
                        f"{fret_text}"
                        f"{keep_after_connectors}{after_other}"
                    )

            fret_strings[s_idx] = fret_text

        # Keep at least one separator column so adjacent multi-digit frets don't merge.
        slice_width = (max([len(f) for f in fret_strings.values()] + [1]) + 1) if fret_strings else 1

        for i in range(num_strings):
            if i in fret_strings:
                # Add the fret number and pad with dashes
                lines[i] += fret_strings[i].ljust(slice_width, '-')
            else:
                # Empty string at this time slice
                lines[i] += '-' * slice_width

        if any(isinstance(f, int) for f in fingering.values()):
            previous_fingering = {s: f for s, f in fingering.items() if isinstance(f, int)}

            # Track melodic note state for contour-aware monophonic placement.
            if len(source_notes) == 1 and len(best_adjusted_pitches) == 1:
                melodic_pitch = best_adjusted_pitches[0]
                for s, f in fingering.items():
                    if isinstance(f, int):
                        previous_target_note = (s, f, melodic_pitch)
                        recent_target_strings.append(s)
                        if len(recent_target_strings) > 4:
                            recent_target_strings.pop(0)
                        break
                previous_source_note = source_notes[0]

    centered_lines = [center_duplicate_connectors(line) for line in lines]
    return "\n".join(centered_lines)