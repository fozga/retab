import json
import re
from typing import Any, Dict, List, Optional

from note_sequence import max_simultaneous_notes_in_timeline, render_note_sequence
from parser import detect_source_prefixes, parse_tab_blocks_with_sections, resolve_string_tunings
from translator import render_target_tab
from tuning import get_tuning_midi, midi_to_note_name

HEURISTIC_PRESETS: Dict[str, Dict[str, Any]] = {
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


def _normalize_tab_line_start(line: str) -> str:
    return re.sub(r"^-+\|", "#|", line)


def _to_base_note(midi_number: int) -> str:
    return re.sub(r"-?\d+$", "", midi_to_note_name(midi_number))


def _concat_tab_chunks(left_chunk: str, right_chunk: str) -> str:
    left_lines = left_chunk.splitlines()
    right_lines = right_chunk.splitlines()

    max_rows = max(len(left_lines), len(right_lines))
    if len(left_lines) < max_rows:
        left_lines.extend([""] * (max_rows - len(left_lines)))
    if len(right_lines) < max_rows:
        right_lines.extend([""] * (max_rows - len(right_lines)))

    merged = [left + right for left, right in zip(left_lines, right_lines)]
    return "\n".join(merged)


def _finalize_tab_chunk(chunk: str) -> str:
    return "\n".join(_normalize_tab_line_start(line) for line in chunk.splitlines())


def _finalize_target_tab_chunk(chunk: str, target_tuning_midi: List[int]) -> str:
    labels = [_to_base_note(midi) for midi in target_tuning_midi]
    lines = chunk.splitlines()

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
        normalized_line = re.sub(r"^-+\|", "|", line)
        if normalized_line.startswith("|"):
            normalized_line = normalized_line[1:]
        formatted_lines.append(f"{label}|{normalized_line}")

    return "\n".join(formatted_lines)


def _parse_optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(value)


def _parse_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value)


def _resolve_heuristics(payload: Dict[str, Any]) -> Dict[str, Any]:
    config: Dict[str, Any] = {
        "strictness": "strict",
        "prefer_adjacent_strings": False,
        "max_target_fret": None,
        "string_history_window": 4,
        "connector_jump_limit": 7,
        "run_lock_strength": 1.0,
        "open_string_jump_scale": None,
        "reversal_penalty": None,
    }

    preset = payload.get("heuristic_preset")
    if preset in HEURISTIC_PRESETS:
        config.update(HEURISTIC_PRESETS[preset])

    strictness = payload.get("strictness")
    if strictness:
        config["strictness"] = strictness

    if payload.get("prefer_adjacent_strings") is True:
        config["prefer_adjacent_strings"] = True

    for key in ["max_target_fret", "string_history_window", "connector_jump_limit"]:
        if payload.get(key) not in (None, ""):
            config[key] = _parse_optional_int(payload.get(key))

    for key in ["run_lock_strength", "open_string_jump_scale", "reversal_penalty"]:
        if payload.get(key) not in (None, ""):
            config[key] = _parse_optional_float(payload.get(key))

    return config


def run_retab_from_json(payload_json: str) -> str:
    payload = json.loads(payload_json)

    input_text = (payload.get("input_text") or "").strip("\n")
    if not input_text.strip():
        raise ValueError("Input tab is empty. Paste a tab or upload a .txt file.")

    target = (payload.get("target") or "").strip()
    show_octave = bool(payload.get("show_octave", False))

    source_path = "/tmp/retab_input.txt"
    with open(source_path, "w", encoding="utf-8") as handle:
        handle.write(input_text + "\n")

    source_prefixes = detect_source_prefixes(source_path)
    base_tunings = resolve_string_tunings(source_prefixes)
    parsed_blocks, trailing_metadata = parse_tab_blocks_with_sections(source_path, base_tunings)

    if not parsed_blocks:
        raise ValueError("No tablature blocks were detected in the input text.")

    rendered_chunks: List[str] = []
    pending_tab_chunk = ""

    if target:
        target_tuning_midi = get_tuning_midi(target)
        heuristic_config = _resolve_heuristics(payload)

        for metadata_lines, block_timeline, ends_with_bar in parsed_blocks:
            if metadata_lines and pending_tab_chunk:
                rendered_chunks.append(_finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
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
                pending_tab_chunk = _concat_tab_chunks(pending_tab_chunk, current_render)
            else:
                pending_tab_chunk = current_render

            if ends_with_bar:
                rendered_chunks.append(_finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
                pending_tab_chunk = ""

        if pending_tab_chunk:
            rendered_chunks.append(_finalize_target_tab_chunk(pending_tab_chunk, target_tuning_midi))
    else:
        file_max_height = max(
            (max_simultaneous_notes_in_timeline(block_timeline) for _, block_timeline, _ in parsed_blocks),
            default=1,
        )

        for metadata_lines, block_timeline, ends_with_bar in parsed_blocks:
            if metadata_lines and pending_tab_chunk:
                rendered_chunks.append(_finalize_tab_chunk(pending_tab_chunk))
                pending_tab_chunk = ""

            if metadata_lines:
                rendered_chunks.extend(metadata_lines)

            current_render = render_note_sequence(
                block_timeline,
                fixed_height=max(3, file_max_height),
                show_octave=show_octave,
            )

            if pending_tab_chunk:
                pending_tab_chunk = _concat_tab_chunks(pending_tab_chunk, current_render)
            else:
                pending_tab_chunk = current_render

            if ends_with_bar:
                rendered_chunks.append(_finalize_tab_chunk(pending_tab_chunk))
                pending_tab_chunk = ""

        if pending_tab_chunk:
            rendered_chunks.append(_finalize_tab_chunk(pending_tab_chunk))

    if trailing_metadata:
        rendered_chunks.extend(trailing_metadata)

    return "\n\n".join(chunk for chunk in rendered_chunks if chunk is not None)
