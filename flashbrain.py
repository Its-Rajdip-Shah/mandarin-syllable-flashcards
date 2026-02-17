"""
Adaptive scheduler for Mandarin flashcards.

The module selects the next question from `question_bank.jsonl` to optimize
active recall. It keeps a lightweight history file (`progress.jsonl`) where
each line stores {question_id, attempts, seconds, correct, timestamp}.

Priority scoring (higher = show sooner):
- Recent mistakes: higher weight for incorrect attempts.
- Speed: longer response times increase weight.
- Spacing: weight decays with time since last seen.
- Tricky questions: slight boost to ensure regular exposure.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).parent
QUESTION_BANK = ROOT / "question_bank.jsonl"
PROGRESS_LOG = ROOT / "progress.jsonl"


# ---------- Data models ----------


@dataclass
class Question:
    id: str
    type: str
    tags: List[str]
    payload: Dict

    @classmethod
    def from_dict(cls, raw: Dict) -> "Question":
        return cls(id=raw["id"], type=raw["type"], tags=raw.get("tags", []), payload=raw)


@dataclass
class History:
    question_id: str
    attempts: int
    seconds: float
    correct: bool
    timestamp: float

    @classmethod
    def from_dict(cls, raw: Dict) -> "History":
        return cls(
            question_id=raw["question_id"],
            attempts=int(raw.get("attempts", 1)),
            seconds=float(raw.get("seconds", 0.0)),
            correct=bool(raw.get("correct", False)),
            timestamp=float(raw.get("timestamp", time.time())),
        )


# ---------- IO helpers ----------


def load_questions(path: Path = QUESTION_BANK) -> List[Question]:
    questions = []
    if not path.exists():
        raise FileNotFoundError(f"Question bank not found at {path}. Run createFlash.py first.")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            questions.append(Question.from_dict(data))
    return questions


def load_history(path: Path = PROGRESS_LOG) -> List[History]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(History.from_dict(json.loads(line)))
    return records


def record_result(question_id: str, attempts: int, seconds: float, correct: bool, path: Path = PROGRESS_LOG) -> None:
    entry = {
        "question_id": question_id,
        "attempts": attempts,
        "seconds": seconds,
        "correct": correct,
        "timestamp": time.time(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------- Scoring ----------


def _last_seen(history: List[History], qid: str) -> Optional[History]:
    filtered = [h for h in history if h.question_id == qid]
    return max(filtered, key=lambda h: h.timestamp) if filtered else None


def compute_priority(question: Question, history: List[History], now: float) -> float:
    last = _last_seen(history, question.id)

    tricky_bonus = 0.25 if "tricky" in question.tags else 0.0

    if not last:
        return 5.0 + tricky_bonus  # unseen items float near the top

    attempts = sum(h.attempts for h in history if h.question_id == question.id)
    incorrect = sum(1 for h in history if h.question_id == question.id and not h.correct)

    miss_factor = 1.0 + incorrect * 1.2 + max(0, attempts - incorrect) * 0.2
    slow_penalty = min(1.5, (last.seconds / 4.0))  # normalize to ~4s baseline

    hours_since = (now - last.timestamp) / 3600.0
    decay = math.exp(hours_since * math.log(0.5) / 18.0)  # half-life 18h

    score = (1 + tricky_bonus + slow_penalty) * miss_factor * (1 - decay)
    return score


def select_next_question(questions: List[Question], history: List[History]) -> Question:
    now = time.time()
    scored: List[Tuple[float, Question]] = []
    for q in questions:
        score = compute_priority(q, history, now)
        scored.append((score, q))

    scored.sort(key=lambda x: x[0], reverse=True)  # highest score = show sooner
    return scored[0][1]


# ---------- CLI helper ----------


def main():
    questions = load_questions()
    history = load_history()
    choice = select_next_question(questions, history)
    print(json.dumps(choice.payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
