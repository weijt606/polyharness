"""Local proposer backend for offline development and smoke testing.

This backend applies lightweight deterministic edits to the candidate harness
without external API calls.  Supports both text-classification and
math-word-problem harness types.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from poly_harness.proposer.base import BaseProposer


class LocalProposer(BaseProposer):
    """Simple local proposer used for no-network / no-key development."""

    def propose(
        self,
        workspace_root: Path,
        candidate_dir: Path,
        iteration: int,
        parent: int | None,
    ) -> dict:
        harness_path = candidate_dir / "harness.py"
        if not harness_path.exists():
            marker = candidate_dir / "LOCAL_PROPOSER_NOTE.txt"
            marker.write_text(
                f"Local proposer ran on iteration {iteration}. "
                "No harness.py found; candidate left unchanged.\n"
            )
            return {
                "changes_summary": "Local proposer executed (no harness.py found).",
                "proposer_model": "local-rule-based",
                "tool_calls": 0,
            }

        text = harness_path.read_text()

        # Dispatch to the right improvement chain based on harness type.
        if "def solve" in text:
            updated, summary = self._improve_math_solver(text)
        elif "def classify" in text:
            updated = self._improve_text_classifier(text)
            summary = (
                "Local proposer updated heuristic sentiment lexicon "
                "for improved text classification coverage."
            )
        else:
            updated, summary = text, "Local proposer: unrecognised harness type."

        harness_path.write_text(updated)
        return {
            "changes_summary": summary,
            "proposer_model": "local-rule-based",
            "tool_calls": 0,
        }

    # ------------------------------------------------------------------
    # Text-classification improvements
    # ------------------------------------------------------------------

    def _improve_text_classifier(self, text: str) -> str:
        """Apply small deterministic improvements for the toy example harness."""
        additions = {
            "positive_words": ["wonderful", "fantastic", "amazing", "thrilled"],
            "negative_words": ["worst", "disappointing", "frustrating", "waste"],
        }

        updated = text
        for key, words in additions.items():
            anchor = f"{key} = ["
            if anchor in updated:
                for w in words:
                    if f'"{w}"' not in updated:
                        updated = updated.replace(anchor, anchor + f'"{w}", ', 1)

        return updated

    # ------------------------------------------------------------------
    # Math-word-problem improvements (3 progressive levels)
    # ------------------------------------------------------------------

    def _improve_math_solver(self, text: str) -> tuple[str, str]:
        """Return (updated_code, summary) for math word-problem harness."""
        if "# poly-harness-level: 3" in text:
            return text, "Already at max optimisation level."
        if "# poly-harness-level: 2" in text:
            return _MATH_LEVEL_3, "Level 3: multi-item sums, rates, sequences."
        if "# poly-harness-level: 1" in text:
            return _MATH_LEVEL_2, "Level 2: averages, percentages, unit conversion."
        return _MATH_LEVEL_1, "Level 1: keyword-based operation detection."


# ── replacement harness code for each level ──────────────────────────

_MATH_LEVEL_1 = textwrap.dedent('''\
    """Math word problem solver — level 1: basic operation detection."""

    import re
    import sys
    import json


    def solve(question: str) -> float:
        # poly-harness-level: 1
        """Solve a math word problem. Returns a numeric answer."""
        numbers = [float(n) for n in re.findall(r"-?\\d+\\.?\\d*", question)]
        if not numbers:
            return 0.0
        if len(numbers) == 1:
            return numbers[0]

        q = question.lower()

        # Subtraction keywords
        if any(w in q for w in ["left", "gives", "drops", "remaining", "fewer"]):
            result = numbers[0]
            for n in numbers[1:]:
                result -= n
            return result

        # Division keywords
        if any(w in q for w in ["equal pieces", "cut into", "divided"]):
            return numbers[0] / numbers[1] if numbers[1] != 0 else 0.0

        # Default: multiply first two
        return numbers[0] * numbers[1]


    if __name__ == "__main__":
        if len(sys.argv) > 1:
            with open(sys.argv[1]) as f:
                data = json.load(f)
            result = solve(data["question"])
            print(json.dumps({"answer": result}))
        else:
            question = input("Enter question: ")
            print(solve(question))
''')

_MATH_LEVEL_2 = textwrap.dedent('''\
    """Math word problem solver — level 2: averages, percentages, rates."""

    import re
    import math as _math
    import sys
    import json


    def solve(question: str) -> float:
        # poly-harness-level: 2
        """Solve a math word problem. Returns a numeric answer."""
        numbers = [float(n) for n in re.findall(r"-?\\d+\\.?\\d*", question)]
        if not numbers:
            return 0.0
        if len(numbers) == 1:
            return numbers[0]

        q = question.lower()

        # Average
        if "average" in q:
            if "test" in q or "score" in q:
                vals = numbers[:-1]
                return sum(vals) / len(vals) if vals else 0.0
            return sum(numbers) / len(numbers)

        # Percentage off
        if "% off" in q or "percent off" in q:
            price, pct = numbers[0], numbers[1]
            return price * (1 - pct / 100)

        # Perimeter → side
        if "perimeter" in q and "side" in q:
            return numbers[0] / 4

        # Rate with unit conversion (per day … weeks)
        if "per day" in q and "week" in q:
            return numbers[0] * numbers[1] * 7

        # Ceiling division ("how many … needed/full")
        if "how many" in q and ("needed" in q or "full" in q):
            return float(_math.ceil(numbers[1] / numbers[0]))

        # Subtraction keywords
        if any(w in q for w in ["left", "gives", "drops", "remaining", "fewer"]):
            result = numbers[0]
            for n in numbers[1:]:
                result -= n
            return result

        # Division keywords
        if any(w in q for w in ["equal pieces", "cut into", "divided"]):
            return numbers[0] / numbers[1] if numbers[1] != 0 else 0.0

        # Default: multiply first two
        return numbers[0] * numbers[1]


    if __name__ == "__main__":
        if len(sys.argv) > 1:
            with open(sys.argv[1]) as f:
                data = json.load(f)
            result = solve(data["question"])
            print(json.dumps({"answer": result}))
        else:
            question = input("Enter question: ")
            print(solve(question))
''')

_MATH_LEVEL_3 = textwrap.dedent('''\
    """Math word problem solver — level 3: multi-item, rates, sequences."""

    import re
    import math as _math
    import sys
    import json


    def solve(question: str) -> float:
        # poly-harness-level: 3
        """Solve a math word problem. Returns a numeric answer."""
        numbers = [float(n) for n in re.findall(r"-?\\d+\\.?\\d*", question)]
        if not numbers:
            return 0.0
        if len(numbers) == 1:
            return numbers[0]

        q = question.lower()

        # Average
        if "average" in q:
            if "test" in q or "score" in q:
                vals = numbers[:-1]
                return sum(vals) / len(vals) if vals else 0.0
            return sum(numbers) / len(numbers)

        # Percentage off
        if "% off" in q or "percent off" in q:
            price, pct = numbers[0], numbers[1]
            return price * (1 - pct / 100)

        # Perimeter → side
        if "perimeter" in q and "side" in q:
            return numbers[0] / 4

        # Rate with unit conversion (per day … weeks)
        if "per day" in q and "week" in q:
            return numbers[0] * numbers[1] * 7

        # Ceiling division ("how many … needed/full/buses")
        if "how many" in q and ("needed" in q or "full" in q or "buses" in q):
            return float(_math.ceil(numbers[1] / numbers[0]))

        # Multi-item purchase: "X at $Y … and Z at $W"
        if " at " in q and " and " in q and len(numbers) >= 4:
            return numbers[0] * numbers[1] + numbers[2] * numbers[3]

        # Fuel / consumable rate: "X per Y units … Z units"
        if "per" in q and ("liter" in q or "fuel" in q) and len(numbers) >= 3:
            rate = numbers[0] / numbers[1]
            return rate * numbers[2]

        # Fill/drain rate: "X per minute … Y-liter tank"
        if ("per minute" in q or "rate of" in q) and ("fill" in q or "tank" in q):
            return numbers[1] / numbers[0] if numbers[0] != 0 else 0.0

        # Earns per hour across multiple days
        if "per hour" in q and ("monday" in q or "tuesday" in q or "day" in q):
            rate = numbers[0]
            hours = sum(numbers[1:])
            return rate * hours

        # Arithmetic sequence: "first has X, each subsequent +Y, last"
        if "subsequent" in q or "more than the previous" in q:
            n_items = int(numbers[0])
            first = numbers[1]
            diff = numbers[2]
            return first + (n_items - 1) * diff

        # Subtraction keywords
        if any(w in q for w in ["left", "gives", "drops", "remaining", "fewer"]):
            result = numbers[0]
            for n in numbers[1:]:
                result -= n
            return result

        # Division keywords
        if any(w in q for w in ["equal pieces", "cut into", "divided"]):
            return numbers[0] / numbers[1] if numbers[1] != 0 else 0.0

        # Default: multiply first two
        return numbers[0] * numbers[1]


    if __name__ == "__main__":
        if len(sys.argv) > 1:
            with open(sys.argv[1]) as f:
                data = json.load(f)
            result = solve(data["question"])
            print(json.dumps({"answer": result}))
        else:
            question = input("Enter question: ")
            print(solve(question))
''')
