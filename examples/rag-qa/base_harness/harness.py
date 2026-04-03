"""Naive RAG (Retrieval-Augmented Generation) harness — starting point for optimization.

Given a question and a knowledge base of documents, retrieve the most relevant
document and extract the answer. Intentionally simplistic.
"""

import sys
import json


# Built-in knowledge base (loaded at import time or overridden via set_knowledge_base)
_KNOWLEDGE_BASE = []


def set_knowledge_base(documents: list[dict]):
    """Set the knowledge base. Each doc: {"id": str, "title": str, "content": str}."""
    global _KNOWLEDGE_BASE
    _KNOWLEDGE_BASE = documents


def retrieve_and_answer(question: str) -> dict:
    """Retrieve a relevant document and extract an answer.

    Returns: {"answer": str, "source_id": str}
    """
    if not _KNOWLEDGE_BASE:
        return {"answer": "", "source_id": ""}

    q_words = set(question.lower().split())

    # Extremely naive retrieval: count word overlap between query and doc content
    best_doc = None
    best_overlap = -1

    for doc in _KNOWLEDGE_BASE:
        doc_words = set(doc["content"].lower().split())
        overlap = len(q_words & doc_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_doc = doc

    if best_doc is None:
        return {"answer": "", "source_id": ""}

    # Extremely naive answer extraction: return the first sentence of the document
    content = best_doc["content"]
    first_sentence = content.split(".")[0].strip()

    return {"answer": first_sentence, "source_id": best_doc["id"]}


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
