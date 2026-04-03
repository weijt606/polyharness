"""Naive math word problem solver — starting point for optimization.

This is intentionally simplistic to give the Proposer room to improve.
The harness extracts numbers and applies a basic heuristic.
"""

import re
import sys
import json


def solve(question: str) -> float:
    """Solve a math word problem. Returns a numeric answer."""
    numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", question)]

    if not numbers:
        return 0.0

    # Extremely naive: just return the product of the first two numbers,
    # or the single number if only one found.
    if len(numbers) == 1:
        return numbers[0]

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
