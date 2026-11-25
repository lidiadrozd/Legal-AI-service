"""Bounded chat history: user evidence and question context stay separate."""
from collections.abc import Mapping
import re


def requests_new_case(prompt):
    """Reset context only for an explicit assertion or drafting command."""
    assertion = (
        r"(?:^|[.!?;\n])\s*(?:(?:теперь|это|у меня)\s+){0,2}"
        r"(?:другой\s+случай|другое\s+дело|новая\s+ситуация)"
        r"(?=\s*(?:[:.!;,\n]|$))"
    )
    command = (
        r"(?:^|[.!?;\n])\s*(?:пожалуйста[, ]+)?"
        r"(?:составь(?:те)?|подготовь(?:те)?|оформи(?:те)?|напиши(?:те)?|сделай(?:те)?|создай(?:те)?)\s+"
        r"(?:(?:новый|новую|новое)\s+)?"
        r"(?:иск|исковое\s+заявление|претензию|документ)\s+по\s+другому\s+делу\b"
    )
    return bool(re.search(assertion, prompt, re.I) or re.search(command, prompt, re.I))


def build_chat_context(messages, *, max_chars=30000):
    """Return user-only text and whole chronological messages within a budget.

    ``messages`` must already belong to the authorized chat and be ordered
    oldest first. A preceding assistant message accompanies a user answer only
    to explain the question; it is never included in the evidence string.
    """
    if max_chars < 1:
        return "", []
    groups = []
    previous = None
    for message in messages:
        read = message.get if isinstance(message, Mapping) else lambda key, default=None: getattr(message, key, default)
        role, content = read("role"), read("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            previous = None
            continue
        row = {"role": role, "content": content}
        if type(read("id")) is int:
            row["id"] = read("id")
        if role == "user":
            groups.append(([previous] if previous and previous["role"] == "assistant" else []) + [row])
        previous = row
    selected, used = [], 0
    for group in reversed(groups):
        cost = sum(len(row["content"]) + 2 for row in group)
        if used + cost > max_chars:
            # Keep a complete user answer even if its preceding explanation
            # is too large, then stop at this boundary rather than skip facts.
            user = group[-1]
            if used + len(user["content"]) + 2 <= max_chars:
                selected.append([user])
            break
        selected.append(group)
        used += cost
    rows = [row for group in reversed(selected) for row in group]
    return "\n\n".join(row["content"] for row in rows if row["role"] == "user"), rows


def initial_user_sources(state, turns):
    """Merge saved facts and the new interview in chronological order."""
    _, rows = build_chat_context(state.get("source_messages") or ())
    history = [row["content"] for row in rows if row["role"] == "user"]
    if not history and state.get("context"):
        history = [state["context"]]
    current = [state.get("request", "")]
    current.extend(turns)
    current = [text for index, text in enumerate(current) if text and (not index or text != current[index - 1])]
    # API history may contain a prefix already captured in source_messages.
    overlap = next((size for size in range(min(len(history), len(current)), 0, -1)
                    if history[-size:] == current[:size]), 0)
    return history + current[overlap:]
