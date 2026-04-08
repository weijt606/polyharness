"""Naive API-calling harness — starting point for optimization.

Given a user query, decide which API endpoint to call with what parameters.
This is intentionally simplistic to give the Proposer room to improve.
"""

import json
import sys

# Available API catalog
API_CATALOG = {
    "get_weather": {
        "description": "Get current weather for a city",
        "params": ["city"],
    },
    "search_products": {
        "description": "Search product catalog",
        "params": ["query", "max_results"],
    },
    "get_user_profile": {
        "description": "Get user profile by username",
        "params": ["username"],
    },
    "send_email": {
        "description": "Send an email",
        "params": ["to", "subject", "body"],
    },
    "create_calendar_event": {
        "description": "Create a calendar event",
        "params": ["title", "date", "time"],
    },
    "translate_text": {
        "description": "Translate text to another language",
        "params": ["text", "target_language"],
    },
    "get_stock_price": {
        "description": "Get current stock price",
        "params": ["symbol"],
    },
    "set_reminder": {
        "description": "Set a reminder",
        "params": ["message", "time"],
    },
}


def route(query: str) -> dict:
    """Route a user query to the correct API call.

    Returns: {"endpoint": str, "params": dict}
    """
    q = query.lower()

    # Extremely naive keyword matching
    if "weather" in q:
        return {"endpoint": "get_weather", "params": {"city": "unknown"}}
    if "product" in q or "buy" in q or "shop" in q:
        return {"endpoint": "search_products", "params": {"query": query, "max_results": 10}}
    if "email" in q or "send" in q:
        return {"endpoint": "send_email", "params": {"to": "unknown", "subject": query, "body": ""}}
    if "stock" in q or "price" in q:
        return {"endpoint": "get_stock_price", "params": {"symbol": "UNKNOWN"}}

    # Fallback: return first API
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
