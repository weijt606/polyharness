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
        elif "def generate" in text:
            updated, summary = self._improve_code_generator(text)
        elif "def route" in text:
            updated, summary = self._improve_api_router(text)
        elif "def retrieve_and_answer" in text:
            updated, summary = self._improve_rag(text)
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
        if "# polyharness-level: 3" in text:
            return text, "Already at max optimisation level."
        if "# polyharness-level: 2" in text:
            return _MATH_LEVEL_3, "Level 3: multi-item sums, rates, sequences."
        if "# polyharness-level: 1" in text:
            return _MATH_LEVEL_2, "Level 2: averages, percentages, unit conversion."
        return _MATH_LEVEL_1, "Level 1: keyword-based operation detection."

    # ------------------------------------------------------------------
    # Code-generation improvements (3 progressive levels)
    # ------------------------------------------------------------------

    def _improve_code_generator(self, text: str) -> tuple[str, str]:
        """Return (updated_code, summary) for code-generation harness."""
        if "# polyharness-level: 3" in text:
            return text, "Already at max optimisation level."
        if "# polyharness-level: 2" in text:
            return _CODEGEN_LEVEL_3, "Level 3: flatten, cumsum, counter, rotate, intersect, palindrome, fibonacci."
        if "# polyharness-level: 1" in text:
            return _CODEGEN_LEVEL_2, "Level 2: second-largest, is-sorted, capitalize, palindrome."
        return _CODEGEN_LEVEL_1, "Level 1: added min, product, filter-even, unique, double keywords."

    # ------------------------------------------------------------------
    # API-calling improvements (3 progressive levels)
    # ------------------------------------------------------------------

    def _improve_api_router(self, text: str) -> tuple[str, str]:
        """Return (updated_code, summary) for api-calling harness."""
        if "# polyharness-level: 3" in text:
            return text, "Already at max optimisation level."
        if "# polyharness-level: 2" in text:
            return _API_LEVEL_3, "Level 3: full parameter extraction with regex."
        if "# polyharness-level: 1" in text:
            return _API_LEVEL_2, "Level 2: added parameter extraction helpers."
        return _API_LEVEL_1, "Level 1: improved endpoint routing with more keywords."

    # ------------------------------------------------------------------
    # RAG-QA improvements (3 progressive levels)
    # ------------------------------------------------------------------

    def _improve_rag(self, text: str) -> tuple[str, str]:
        """Return (updated_code, summary) for rag-qa harness."""
        if "# polyharness-level: 3" in text:
            return text, "Already at max optimisation level."
        if "# polyharness-level: 2" in text:
            return _RAG_LEVEL_3, "Level 3: question-type answer extraction with sentence scoring."
        if "# polyharness-level: 1" in text:
            return _RAG_LEVEL_2, "Level 2: TF-IDF-like retrieval with bigrams."
        return _RAG_LEVEL_1, "Level 1: improved retrieval with stopword removal."


# ── replacement harness code for each level ──────────────────────────

_MATH_LEVEL_1 = textwrap.dedent('''\
    """Math word problem solver — level 1: basic operation detection."""

    import re
    import sys
    import json


    def solve(question: str) -> float:
        # polyharness-level: 1
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
        # polyharness-level: 2
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
        # polyharness-level: 3
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


# ── Code-generation level replacements ────────────────────────────────

_CODEGEN_LEVEL_1 = textwrap.dedent('''\
"""Code generation harness — level 1: more keyword patterns."""

import sys
import json


def generate(description: str) -> str:
    # polyharness-level: 1
    desc = description.lower()

    if "sum" in desc and "cumul" not in desc:
        return "return sum(args)"
    if "max" in desc and "second" not in desc:
        return "return max(args)"
    if "min" in desc:
        return "return min(args)"
    if "reverse" in desc:
        return "return args[::-1]"
    if "sort" in desc and "is" not in desc and "check" not in desc:
        return "return sorted(args)"
    if "length" in desc or "count" in desc or "number of" in desc:
        return "return len(args)"
    if "product" in desc or "multiply" in desc:
        return "r = 1\\nfor x in args:\\n    r *= x\\nreturn r"
    if "even" in desc:
        return "return [x for x in args if x % 2 == 0]"
    if "unique" in desc:
        return (
            "seen = set()\\nresult = []\\nfor x in args:\\n"
            "    if x not in seen:\\n        seen.add(x)\\n        result.append(x)\\nreturn result"
        )
    if "double" in desc:
        return "return [x * 2 for x in args]"
    return "return args"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = generate(data["description"])
        print(json.dumps({"code": result}))
    else:
        description = input("Describe the function: ")
        print(generate(description))
''')

_CODEGEN_LEVEL_2 = textwrap.dedent('''\
"""Code generation harness — level 2: more patterns + composite logic."""

import sys
import json


def generate(description: str) -> str:
    # polyharness-level: 2
    desc = description.lower()

    if "sum" in desc and "cumul" not in desc:
        return "return sum(args)"
    if "second largest" in desc or "second biggest" in desc:
        return "s = sorted(set(args), reverse=True)\\nreturn s[1] if len(s) > 1 else s[0]"
    if "max" in desc or "largest" in desc:
        return "return max(args)"
    if "min" in desc or "smallest" in desc:
        return "return min(args)"
    if "reverse" in desc:
        return "return args[::-1]"
    if ("sorted" in desc or "ascending" in desc) and ("is" in desc or "check" in desc or "true" in desc):
        return "return all(args[i] <= args[i+1] for i in range(len(args)-1)) if len(args) > 1 else True"
    if "sort" in desc:
        return "return sorted(args)"
    if "length" in desc or "count" in desc or "number of" in desc:
        return "return len(args)"
    if "product" in desc or "multiply" in desc:
        return "r = 1\\nfor x in args:\\n    r *= x\\nreturn r"
    if "even" in desc:
        return "return [x for x in args if x % 2 == 0]"
    if "unique" in desc:
        return (
            "seen = set()\\nresult = []\\nfor x in args:\\n"
            "    if x not in seen:\\n        seen.add(x)\\n        result.append(x)\\nreturn result"
        )
    if "double" in desc:
        return "return [x * 2 for x in args]"
    if "capitalize" in desc or "capitaliz" in desc:
        return "return args.title()"
    if "palindrome" in desc:
        return "s = ''.join(c.lower() for c in str(args) if c.isalnum())\\nreturn s == s[::-1]"
    return "return args"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = generate(data["description"])
        print(json.dumps({"code": result}))
    else:
        description = input("Describe the function: ")
        print(generate(description))
''')

_CODEGEN_LEVEL_3 = textwrap.dedent('''\
"""Code generation harness — level 3: comprehensive patterns."""

import sys
import json


def generate(description: str) -> str:
    # polyharness-level: 3
    desc = description.lower()

    if "fibonacci" in desc:
        return (
            "n = args\\n"
            "if n <= 0: return []\\n"
            "if n == 1: return [0]\\n"
            "fib = [0, 1]\\n"
            "for _ in range(2, n):\\n"
            "    fib.append(fib[-1] + fib[-2])\\n"
            "return fib"
        )
    if "flatten" in desc:
        return (
            "def _flat(lst):\\n"
            "    result = []\\n"
            "    for item in lst:\\n"
            "        if isinstance(item, list):\\n"
            "            result.extend(_flat(item))\\n"
            "        else:\\n"
            "            result.append(item)\\n"
            "    return result\\n"
            "return _flat(args)"
        )
    if "cumul" in desc and "sum" in desc:
        return (
            "result = []\\n"
            "s = 0\\n"
            "for x in args:\\n"
            "    s += x\\n"
            "    result.append(s)\\n"
            "return result"
        )
    if "count" in desc and "occur" in desc:
        return (
            "d = {}\\n"
            "for x in args:\\n"
            "    k = str(x)\\n"
            "    d[k] = d.get(k, 0) + 1\\n"
            "return d"
        )
    if "rotat" in desc and "left" in desc:
        return "return args[1:] + args[:1] if len(args) > 1 else args"
    if "intersection" in desc:
        return "a, b = args\\nreturn [x for x in a if x in b]"
    if "sum" in desc:
        return "return sum(args)"
    if "second largest" in desc or "second biggest" in desc:
        return "s = sorted(set(args), reverse=True)\\nreturn s[1] if len(s) > 1 else s[0]"
    if "max" in desc or "largest" in desc:
        return "return max(args)"
    if "min" in desc or "smallest" in desc:
        return "return min(args)"
    if "reverse" in desc:
        return "return args[::-1]"
    if ("sorted" in desc or "ascending" in desc) and ("is" in desc or "check" in desc or "true" in desc):
        return "return all(args[i] <= args[i+1] for i in range(len(args)-1)) if len(args) > 1 else True"
    if "sort" in desc:
        return "return sorted(args)"
    if "length" in desc or "number of" in desc:
        return "return len(args)"
    if "product" in desc or "multiply" in desc:
        return "r = 1\\nfor x in args:\\n    r *= x\\nreturn r"
    if "even" in desc:
        return "return [x for x in args if x % 2 == 0]"
    if "unique" in desc:
        return (
            "seen = set()\\nresult = []\\nfor x in args:\\n"
            "    if x not in seen:\\n        seen.add(x)\\n        result.append(x)\\nreturn result"
        )
    if "double" in desc:
        return "return [x * 2 for x in args]"
    if "capitalize" in desc or "capitaliz" in desc:
        return "return args.title()"
    if "palindrome" in desc:
        return "s = ''.join(c.lower() for c in str(args) if c.isalnum())\\nreturn s == s[::-1]"
    return "return args"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = generate(data["description"])
        print(json.dumps({"code": result}))
    else:
        description = input("Describe the function: ")
        print(generate(description))
''')


# ── API-calling level replacements ────────────────────────────────────

_API_LEVEL_1 = textwrap.dedent('''\
"""API-calling harness — level 1: better endpoint routing."""

import re
import sys
import json


def route(query: str) -> dict:
    # polyharness-level: 1
    q = query.lower()

    if "weather" in q or "temperature" in q:
        return {"endpoint": "get_weather", "params": {"city": "unknown"}}
    shop_words = ["product", "buy", "shop", "headphone", "laptop", "shoes", "find me", "show me option", "need a"]
    if any(w in q for w in shop_words):
        return {"endpoint": "search_products", "params": {"query": query, "max_results": 10}}
    if "profile" in q or "user" in q:
        return {"endpoint": "get_user_profile", "params": {"username": "unknown"}}
    if "email" in q:
        return {"endpoint": "send_email", "params": {"to": "unknown", "subject": query, "body": ""}}
    if any(w in q for w in ["schedul", "calendar", "book", "appointment", "add a"]):
        return {"endpoint": "create_calendar_event", "params": {"title": "event", "date": "unknown", "time": "unknown"}}
    if "translat" in q or ("say" in q and "in" in q) or ("convert" in q and "to" in q):
        return {"endpoint": "translate_text", "params": {"text": query, "target_language": "unknown"}}
    if "stock" in q or "price" in q:
        return {"endpoint": "get_stock_price", "params": {"symbol": "UNKNOWN"}}
    if "remind" in q:
        return {"endpoint": "set_reminder", "params": {"message": query, "time": "unknown"}}

    return {"endpoint": "get_weather", "params": {"city": "unknown"}}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = route(data["query"])
        print(json.dumps(result))
    else:
        query = input("Enter query: ")
        print(json.dumps(route(query), indent=2))
''')

_API_LEVEL_2 = textwrap.dedent('''\
"""API-calling harness — level 2: endpoint routing + basic param extraction."""

import re
import sys
import json


def _extract_email(q: str) -> str:
    match = re.search(r"[\\w.+-]+@[\\w-]+\\.[\\w.]+", q)
    return match.group(0) if match else "unknown"

def _extract_stock_symbol(q: str) -> str:
    match = re.search(r"\\b([A-Z]{1,5})\\b", q)
    return match.group(1) if match else "UNKNOWN"

def _extract_time(q: str) -> str:
    match = re.search(r"\\b(\\d{1,2}(?::\\d{2})?\\s*(?:am|pm)|noon|midnight)\\b", q.lower())
    return match.group(0) if match else "unknown"

def _extract_city(q: str) -> str:
    match = re.search(r"in\\s+([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)", q)
    return match.group(1) if match else "unknown"


def route(query: str) -> dict:
    # polyharness-level: 2
    q = query.lower()

    if "weather" in q or "temperature" in q:
        city = _extract_city(query)
        return {"endpoint": "get_weather", "params": {"city": city}}

    shop_words = [
        "product", "buy", "shop", "headphone", "laptop",
        "shoes", "find me", "show me option", "need a",
    ]
    if any(w in q for w in shop_words):
        return {"endpoint": "search_products", "params": {"query": query, "max_results": 10}}

    if "profile" in q or ("look up" in q and "user" in q):
        words = query.split()
        name = words[-1] if words else "unknown"
        return {"endpoint": "get_user_profile", "params": {"username": name}}

    if "email" in q:
        to = _extract_email(query)
        return {"endpoint": "send_email", "params": {"to": to, "subject": query, "body": ""}}

    if any(w in q for w in ["schedul", "calendar", "book", "appointment", "add a"]):
        time = _extract_time(query)
        return {"endpoint": "create_calendar_event", "params": {"title": "event", "date": "unknown", "time": time}}

    if "translat" in q or ("say" in q and "in" in q) or ("convert" in q and "to" in q):
        return {"endpoint": "translate_text", "params": {"text": query, "target_language": "unknown"}}

    if "stock" in q or "price" in q:
        symbol = _extract_stock_symbol(query)
        return {"endpoint": "get_stock_price", "params": {"symbol": symbol}}

    if "remind" in q:
        time = _extract_time(query)
        return {"endpoint": "set_reminder", "params": {"message": query, "time": time}}

    return {"endpoint": "get_weather", "params": {"city": "unknown"}}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = route(data["query"])
        print(json.dumps(result))
    else:
        query = input("Enter query: ")
        print(json.dumps(route(query), indent=2))
''')

_API_LEVEL_3 = textwrap.dedent('''\
"""API-calling harness — level 3: full parameter extraction."""

import re
import sys
import json


def _extract_email(q: str) -> str:
    match = re.search(r"[\\w.+-]+@[\\w-]+\\.[\\w.]+", q)
    return match.group(0) if match else "unknown"

def _extract_stock_symbol(q: str) -> str:
    match = re.search(r"\\b([A-Z]{1,5})\\b", q)
    return match.group(1) if match else "UNKNOWN"

def _extract_time(q: str) -> str:
    match = re.search(r"\\b(\\d{1,2}(?::\\d{2})?\\s*(?:am|pm)|noon|midnight)\\b", q.lower())
    return match.group(0) if match else "unknown"

def _extract_city(q: str) -> str:
    match = re.search(r"in\\s+([A-Z][a-z]+(?:\\s+[A-Z][a-z]+)*)", q)
    return match.group(1) if match else "unknown"

def _extract_day(q: str) -> str:
    days_pat = (
        r"\\b(Monday|Tuesday|Wednesday|Thursday|Friday"
        r"|Saturday|Sunday|today|tomorrow)\\b"
    )
    match = re.search(days_pat, q, re.IGNORECASE)
    return match.group(0) if match else "unknown"

def _extract_quoted(q: str) -> str:
    match = re.search(r"['\\"](.*?)['\\"']", q)
    return match.group(1) if match else ""

def _extract_language(q: str) -> str:
    lang_pat = (
        r"(?:to|in)\\s+(Spanish|French|Japanese|German|Chinese"
        r"|Korean|Italian|Portuguese|Russian|Arabic)"
    )
    match = re.search(lang_pat, q, re.IGNORECASE)
    return match.group(1) if match else "unknown"

def _extract_subject(q: str) -> str:
    match = re.search(r"(?:about|regarding)\\s+(?:the\\s+)?(.+?)$", q.lower())
    if match:
        return match.group(1).strip()
    match = re.search(r"email\\s+\\S+\\s+(?:the\\s+)?(.+?)$", q.lower())
    return match.group(1).strip() if match else ""


def route(query: str) -> dict:
    # polyharness-level: 3
    q = query.lower()

    if "weather" in q or "temperature" in q:
        city = _extract_city(query)
        return {"endpoint": "get_weather", "params": {"city": city}}

    shop_words = [
        "product", "buy", "shop", "headphone", "laptop",
        "shoes", "find me", "show me option", "need a",
    ]
    if any(w in q for w in shop_words):
        cleaned = re.sub(r"^(find me|show me|i need|search for)\\s+", "", q).strip()
        return {"endpoint": "search_products", "params": {"query": cleaned, "max_results": 10}}

    if "profile" in q or ("look up" in q and ("user" in q or "profile" in q)):
        match = re.search(r"(?:for\\s+|profile\\s+)(?:user\\s+)?([\\w_]+)", q, re.IGNORECASE)
        name = match.group(1) if match else "unknown"
        return {"endpoint": "get_user_profile", "params": {"username": name}}

    if "email" in q:
        to = _extract_email(query)
        subject = _extract_subject(query)
        return {"endpoint": "send_email", "params": {"to": to, "subject": subject, "body": ""}}

    if any(w in q for w in ["schedul", "calendar", "book", "appointment", "add a"]):
        time = _extract_time(query)
        day = _extract_day(query)
        title_match = re.search(r"(?:schedule|book|add)\\s+(?:a\\s+)?(.+?)\\s+(?:on|at|for)", q, re.IGNORECASE)
        title = title_match.group(1) if title_match else "event"
        return {"endpoint": "create_calendar_event", "params": {"title": title, "date": day, "time": time}}

    if "translat" in q or ("say" in q and "in" in q) or ("how do you say" in q):
        text = _extract_quoted(query)
        lang = _extract_language(query)
        return {"endpoint": "translate_text", "params": {"text": text, "target_language": lang}}

    if "stock" in q or "price" in q:
        symbol = _extract_stock_symbol(query)
        return {"endpoint": "get_stock_price", "params": {"symbol": symbol}}

    if "remind" in q:
        time = _extract_time(query)
        msg_match = re.search(r"remind(?:er)?[:\\s]+(.+?)\\s+at\\s+", q, re.IGNORECASE)
        if not msg_match:
            msg_match = re.search(r"remind\\s+me\\s+(?:to\\s+)?(.+?)\\s+at\\s+", q, re.IGNORECASE)
        message = msg_match.group(1) if msg_match else query
        return {"endpoint": "set_reminder", "params": {"message": message, "time": time}}

    return {"endpoint": "get_weather", "params": {"city": "unknown"}}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = route(data["query"])
        print(json.dumps(result))
    else:
        query = input("Enter query: ")
        print(json.dumps(route(query), indent=2))
''')


# ── RAG-QA level replacements ─────────────────────────────────────────

_RAG_LEVEL_1 = textwrap.dedent('''\
"""RAG QA harness — level 1: improved retrieval with stopword removal."""

import sys
import json


_KNOWLEDGE_BASE = []

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "not", "with", "by", "from", "that",
    "this", "it", "its", "what", "which", "who", "whom", "how", "when",
    "where", "do", "does", "did", "has", "have", "had", "be", "been",
    "being", "will", "would", "can", "could", "should", "may", "might",
}

def set_knowledge_base(documents: list[dict]):
    global _KNOWLEDGE_BASE
    _KNOWLEDGE_BASE = documents


def _tokenize(text: str) -> set[str]:
    words = set(text.lower().split())
    return words - _STOPWORDS


def retrieve_and_answer(question: str) -> dict:
    # polyharness-level: 1
    if not _KNOWLEDGE_BASE:
        return {"answer": "", "source_id": ""}

    q_tokens = _tokenize(question)

    best_doc = None
    best_score = -1

    for doc in _KNOWLEDGE_BASE:
        doc_tokens = _tokenize(doc["content"])
        title_tokens = _tokenize(doc["title"])
        overlap = len(q_tokens & doc_tokens) + len(q_tokens & title_tokens) * 2
        if overlap > best_score:
            best_score = overlap
            best_doc = doc

    if best_doc is None:
        return {"answer": "", "source_id": ""}

    sentences = [s.strip() for s in best_doc["content"].split(".") if s.strip()]
    best_sent = sentences[0] if sentences else ""
    best_sent_score = -1
    for sent in sentences:
        sent_tokens = _tokenize(sent)
        score = len(q_tokens & sent_tokens)
        if score > best_sent_score:
            best_sent_score = score
            best_sent = sent

    return {"answer": best_sent, "source_id": best_doc["id"]}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        if "knowledge_base" in data:
            set_knowledge_base(data["knowledge_base"])
        result = retrieve_and_answer(data["question"])
        print(json.dumps(result))
    else:
        question = input("Enter question: ")
        print(json.dumps(retrieve_and_answer(question), indent=2))
''')
_RAG_LEVEL_2 = textwrap.dedent('''\
"""RAG QA harness — level 2: TF-IDF-like retrieval + bigrams."""

import sys
import json
import math


_KNOWLEDGE_BASE = []

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "not", "with", "by", "from", "that",
    "this", "it", "its", "what", "which", "who", "whom", "how", "when",
    "where", "do", "does", "did", "has", "have", "had", "be", "been",
    "being", "will", "would", "can", "could", "should", "may", "might",
}


def set_knowledge_base(documents: list[dict]):
    global _KNOWLEDGE_BASE
    _KNOWLEDGE_BASE = documents


def _tokenize(text: str) -> list[str]:
    return [w for w in text.lower().split() if w not in _STOPWORDS]


def _bigrams(tokens: list[str]) -> set[str]:
    return {f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)}


def retrieve_and_answer(question: str) -> dict:
    # polyharness-level: 2
    if not _KNOWLEDGE_BASE:
        return {"answer": "", "source_id": ""}

    q_tokens = _tokenize(question)
    q_set = set(q_tokens)
    q_bi = _bigrams(q_tokens)

    doc_freq = {}
    for doc in _KNOWLEDGE_BASE:
        words = set(_tokenize(doc["content"]))
        for w in words:
            doc_freq[w] = doc_freq.get(w, 0) + 1
    n_docs = len(_KNOWLEDGE_BASE)

    best_doc = None
    best_score = -1

    for doc in _KNOWLEDGE_BASE:
        doc_tokens = _tokenize(doc["content"])
        doc_set = set(doc_tokens)
        title_tokens = set(_tokenize(doc["title"]))
        score = 0.0
        for w in q_set & doc_set:
            idf = math.log(n_docs / (1 + doc_freq.get(w, 0)))
            score += idf
        score += len(q_set & title_tokens) * 3
        doc_bi = _bigrams(doc_tokens)
        score += len(q_bi & doc_bi) * 2
        if score > best_score:
            best_score = score
            best_doc = doc

    if best_doc is None:
        return {"answer": "", "source_id": ""}

    sentences = [s.strip() for s in best_doc["content"].split(".") if s.strip()]
    best_sent = sentences[0] if sentences else ""
    best_sent_score = -1
    for sent in sentences:
        sent_tokens = set(_tokenize(sent))
        score = sum(
            math.log(n_docs / (1 + doc_freq.get(w, 0)))
            for w in q_set & sent_tokens
        )
        if score > best_sent_score:
            best_sent_score = score
            best_sent = sent

    return {"answer": best_sent, "source_id": best_doc["id"]}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        if "knowledge_base" in data:
            set_knowledge_base(data["knowledge_base"])
        result = retrieve_and_answer(data["question"])
        print(json.dumps(result))
    else:
        question = input("Enter question: ")
        print(json.dumps(retrieve_and_answer(question), indent=2))
''')
_RAG_LEVEL_3 = textwrap.dedent('''\
"""RAG QA harness — level 3: question-type extraction + multi-sentence."""

import re
import sys
import json
import math


_KNOWLEDGE_BASE = []

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "for", "of", "and", "or", "but", "not", "with", "by", "from", "that",
    "this", "it", "its", "what", "which", "who", "whom", "how", "when",
    "where", "do", "does", "did", "has", "have", "had", "be", "been",
    "being", "will", "would", "can", "could", "should", "may", "might",
}


def set_knowledge_base(documents: list[dict]):
    global _KNOWLEDGE_BASE
    _KNOWLEDGE_BASE = documents


def _tokenize(text: str) -> list[str]:
    return [w for w in text.lower().split() if w not in _STOPWORDS]


def _bigrams(tokens: list[str]) -> set[str]:
    return {f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens)-1)}


def _detect_question_type(question: str) -> str:
    q = question.lower()
    if q.startswith("who"):
        return "person"
    if q.startswith("when"):
        return "time"
    if q.startswith("where"):
        return "place"
    if "how many" in q:
        return "count"
    return "fact"


def retrieve_and_answer(question: str) -> dict:
    # polyharness-level: 3
    if not _KNOWLEDGE_BASE:
        return {"answer": "", "source_id": ""}

    q_tokens = _tokenize(question)
    q_set = set(q_tokens)
    q_bi = _bigrams(q_tokens)
    q_type = _detect_question_type(question)

    doc_freq = {}
    for doc in _KNOWLEDGE_BASE:
        words = set(_tokenize(doc["content"]))
        for w in words:
            doc_freq[w] = doc_freq.get(w, 0) + 1
    n_docs = len(_KNOWLEDGE_BASE)

    best_doc = None
    best_score = -1

    for doc in _KNOWLEDGE_BASE:
        doc_tokens = _tokenize(doc["content"])
        doc_set = set(doc_tokens)
        title_tokens = set(_tokenize(doc["title"]))
        score = 0.0
        for w in q_set & doc_set:
            idf = math.log(n_docs / (1 + doc_freq.get(w, 0)))
            score += idf
        score += len(q_set & title_tokens) * 3
        doc_bi = _bigrams(doc_tokens)
        score += len(q_bi & doc_bi) * 2
        if score > best_score:
            best_score = score
            best_doc = doc

    if best_doc is None:
        return {"answer": "", "source_id": ""}

    content = best_doc["content"]
    sentences = [s.strip() for s in content.split(".") if s.strip()]

    scored = []
    for sent in sentences:
        sent_tokens = set(_tokenize(sent))
        score = sum(
            math.log(n_docs / (1 + doc_freq.get(w, 0)))
            for w in q_set & sent_tokens
        )
        if q_type == "person" and re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", sent):
            score += 2
        if q_type == "time" and re.search(r"\\b\\d{3,4}\\b", sent):
            score += 2
        if q_type == "count" and re.search(r"\\b\\d+\\b", sent):
            score += 1
        scored.append((score, sent))

    scored.sort(key=lambda x: -x[0])

    if len(scored) >= 2 and scored[1][0] > 0:
        answer = scored[0][1] + ". " + scored[1][1]
    elif scored:
        answer = scored[0][1]
    else:
        answer = content.split(".")[0]

    return {"answer": answer, "source_id": best_doc["id"]}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        if "knowledge_base" in data:
            set_knowledge_base(data["knowledge_base"])
        result = retrieve_and_answer(data["question"])
        print(json.dumps(result))
    else:
        question = input("Enter question: ")
        print(json.dumps(retrieve_and_answer(question), indent=2))
''')
