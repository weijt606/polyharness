"""Toy text classification harness — starting point for optimization.

This is intentionally naive to give the Proposer room to improve.
"""

import json
import sys


def classify(text: str) -> str:
    """Classify text sentiment. Returns: positive, negative, or neutral."""
    text_lower = text.lower()
    positive_words = ["good", "great", "love", "happy", "excellent"]
    negative_words = ["bad", "terrible", "hate", "sad", "awful"]

    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"


if __name__ == "__main__":
    # Read input from stdin or argument
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            data = json.load(f)
        result = classify(data["text"])
        print(json.dumps({"prediction": result}))
    else:
        text = input("Enter text: ")
        print(classify(text))
