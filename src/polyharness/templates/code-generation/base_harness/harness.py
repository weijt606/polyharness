"""Naive code generation harness — starting point for optimization.

Given a natural-language description, generate a Python function body.
This is intentionally simplistic to give the Proposer room to improve.
"""

import json
import sys


def generate(description: str) -> str:
    """Generate a Python function body from a natural-language description.

    Returns a string of Python code (function body only, no def line).
    """
    desc = description.lower()

    # Extremely naive: pattern-match a few keywords and emit boilerplate.
    if "sum" in desc or "add" in desc:
        return "return sum(args)"
    if "max" in desc or "largest" in desc:
        return "return max(args)"
    if "reverse" in desc:
        return "return args[::-1]"
    if "sort" in desc:
        return "return sorted(args)"
    if "length" in desc or "count" in desc or "len" in desc:
        return "return len(args)"

    # Fallback: identity
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
