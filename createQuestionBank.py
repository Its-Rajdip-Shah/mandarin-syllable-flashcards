"""
Generate three question-bank JSONL files in ./Qbank:
  - type1.json : Hear → identify syllable + tone (common syllables prioritized)
  - type2.json : Match audio cards to syllable cards using tricky sets
  - type3.json : Tone discrimination (4 tones + 1 duplicate) for selected syllables

Inputs:
  - syllables.json : audio/metadata index built from Tone Perfect
  - mostCommonSyllables.txt : comma/space separated syllables (higher priority)
  - trickySyllables.json : list of confusing syllable sets
  - tones.txt : syllables to use for tone discrimination

Each question includes an `attempts` array to log future performance:
    attempts: [ { "timestamp": ..., "time_taken_ms": ..., "attempts_to_correct": ... }, ... ]
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).parent
QBANK_DIR = ROOT / "Qbank"
SYLLABLE_INDEX = ROOT / "syllables.json"
COMMON_PATH = ROOT / "mostCommonSyllables.txt"
TRICKY_PATH = ROOT / "trickySyllables.json"
TONES_PATH = ROOT / "tones.txt"

SPEAKER_CYCLE = ["FV1", "MV1", "FV2", "MV2", "FV3", "MV3"]
TONES = ["1", "2", "3", "4"]
TONE_SYMBOL = {"1": "-", "2": "/", "3": "v", "4": "\\"}


# ---------- Loaders ----------


def load_syllable_index() -> Dict:
    return json.loads(SYLLABLE_INDEX.read_text(encoding="utf-8"))


def load_common() -> List[str]:
    raw = COMMON_PATH.read_text(encoding="utf-8")
    parts = [p.strip().lower() for p in raw.replace("\n", ",").split(",")]
    seen = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return seen


def load_tricky_sets() -> List[Dict]:
    return json.loads(TRICKY_PATH.read_text(encoding="utf-8"))


def load_tone_syllables() -> List[str]:
    lines = []
    for line in TONES_PATH.read_text(encoding="utf-8").splitlines():
        for part in line.replace(",", " ").split():
            part = part.strip().lower()
            if part:
                lines.append(part)
    return lines


# ---------- Audio helpers ----------


def pick_audio(entry: Dict, tone: str, speaker_order: List[str]) -> Optional[Dict]:
    """Return the audio dict for the first available speaker in order."""
    tone_bucket = entry.get(tone, {})
    for sp in speaker_order:
        if sp in tone_bucket and tone_bucket[sp]:
            return tone_bucket[sp]
    # fallback to any available
    for val in tone_bucket.values():
        if val:
            return val
    return None


def ensure_qbank_dir():
    QBANK_DIR.mkdir(exist_ok=True)


def write_jsonl(path: Path, items: List[Dict]):
    with path.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------- Generators ----------


def gen_type1(index: Dict, common: List[str]) -> List[Dict]:
    """Hear → identify syllable + tone. Options show full syllable list; commons flagged as important."""
    questions = []
    common_set = set(common)
    full_pool = sorted(index.keys())
    for syllable, tones in index.items():
        important = syllable in common_set
        for tone in TONES:
            audio = pick_audio(tones, tone, ["FV1", "MV1", "FV2", "MV2", "FV3", "MV3"])
            if not audio:
                continue
            q = {
                "id": f"hear_{syllable}_{tone}",
                "type": "hear_pick",
                "prompt": "What's the syllable and tone of this audio?",
                "audio": audio["audio"],
                "answer": {"syllable": syllable, "tone": tone, "tone_symbol": TONE_SYMBOL[tone]},
                "options": {"syllable_pool": full_pool, "tone_symbols": TONE_SYMBOL},
                "important": important,
                "attempts": [],
            }
            questions.append(q)
    return questions


def gen_type2(index: Dict, tricky_sets: List[Dict]) -> List[Dict]:
    """Match audio ↔ syllable using confusing sets; cycle speakers across items."""
    questions = []
    for set_idx, group in enumerate(tricky_sets):
        syllables = group.get("set", [])
        speaker_iter = SPEAKER_CYCLE * ((len(syllables) // len(SPEAKER_CYCLE)) + 2)
        pairs = []
        success = True
        for i, syll in enumerate(syllables):
            tones = index.get(syll)
            if not tones:
                success = False
                break
            speaker = speaker_iter[i]
            # prefer tone 1; fallback to 2,3,4
            audio = None
            for tone in TONES:
                audio = pick_audio(tones, tone, [speaker] + SPEAKER_CYCLE)
                if audio:
                    chosen_tone = tone
                    break
            if not audio:
                success = False
                break
            pairs.append(
                {
                    "id": f"{syll}_{chosen_tone}_{audio.get('meta', {}).get('speaker', '')}",
                    "audio": audio["audio"],
                    "label": syll,
                    "tone": chosen_tone,
                    "speaker": audio.get("meta", {}).get("speaker"),
                }
            )
        if not success or len(pairs) < 2:
            continue  # skip sets missing audio
        random.shuffle(pairs)
        q = {
            "id": f"match_{set_idx}",
            "type": "match_pairs",
            "prompt": "Match each audio card to the correct syllable.",
            "pairs": pairs,
            "attempts": [],
            "source_set": syllables,
            "score": group.get("score", None),
        }
        questions.append(q)
    return questions


def gen_type3(index: Dict, tone_syllables: List[str]) -> List[Dict]:
    """Tone discrimination: 4 distinct tones + 1 duplicate card."""
    questions = []
    for syll in tone_syllables:
        entry = index.get(syll)
        if not entry:
            continue
        # collect available tones
        available_tones = [t for t in TONES if pick_audio(entry, t, SPEAKER_CYCLE)]
        if len(available_tones) < 4:
            continue
        base_tones = available_tones[:4]  # assume full coverage
        dup_tone = random.choice(base_tones)
        tone_sequence = base_tones + [dup_tone]
        random.shuffle(tone_sequence)

        cards = []
        for idx, tone in enumerate(tone_sequence):
            audio = pick_audio(entry, tone, SPEAKER_CYCLE)
            cards.append(
                {
                    "card_id": f"{syll}_{tone}_{idx}",
                    "audio": audio["audio"],
                    "tone": tone,
                    "tone_symbol": TONE_SYMBOL[tone],
                    "speaker": audio.get("meta", {}).get("speaker"),
                }
            )
        q = {
            "id": f"tone_{syll}",
            "type": "tone_discrimination",
            "prompt": f"Identify the tone for each card of '{syll}'.",
            "syllable": syll,
            "cards": cards,
            "options": {"tone_symbols": TONE_SYMBOL, "include_same_tone": True},
            "answers": [c["tone"] for c in cards],
            "attempts": [],
        }
        questions.append(q)
    return questions


# ---------- Main ----------


def main():
    ensure_qbank_dir()
    index = load_syllable_index()
    common = load_common()
    tricky_sets = load_tricky_sets()
    tone_syllables = load_tone_syllables()

    type1 = gen_type1(index, common)
    type2 = gen_type2(index, tricky_sets)
    type3 = gen_type3(index, tone_syllables)

    write_jsonl(QBANK_DIR / "type1.json", type1)
    write_jsonl(QBANK_DIR / "type2.json", type2)
    write_jsonl(QBANK_DIR / "type3.json", type3)

    print(f"type1: {len(type1)} questions")
    print(f"type2: {len(type2)} questions")
    print(f"type3: {len(type3)} questions")
    print(f"Wrote files to {QBANK_DIR}")


if __name__ == "__main__":
    main()
