"""Deterministic, explainable rules. No remote classification service."""
import unicodedata

import regex


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Cf").casefold().split())


def validate_rule(kind: str, pattern: str):
    if kind not in {"contains", "phrase", "regex", "allow_author"}:
        raise ValueError("Unknown rule type.")
    if not pattern.strip() or len(pattern) > 300:
        raise ValueError("A rule must contain 1 to 300 characters.")
    if kind in {'contains', 'phrase'} and not normalize(pattern):
        raise ValueError('A text rule must contain visible characters.')
    if kind == "regex":
        try:
            regex.compile(pattern, regex.IGNORECASE | regex.VERSION1)
        except regex.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc


class RuleBook:
    def __init__(self, rules):
        self.rules = [r for r in rules if r.get("enabled", True)]
        for rule in self.rules:
            validate_rule(rule["kind"], rule["pattern"])

    def match(self, text: str, author_id: str) -> list[str]:
        if any(r["kind"] == "allow_author" and r["pattern"] == author_id for r in self.rules):
            return []
        value = normalize(text[:30000])
        reasons = []
        for rule in self.rules:
            kind, pattern = rule["kind"], rule["pattern"]
            if kind == "allow_author":
                continue
            try:
                if kind == "contains":
                    found = normalize(pattern) in value
                elif kind == "phrase":
                    found = regex.search(r"(?<!\w)" + regex.escape(normalize(pattern)) + r"(?!\w)", value, timeout=0.03)
                else:
                    found = regex.search(pattern, value, regex.IGNORECASE | regex.VERSION1, timeout=0.03)
            except TimeoutError as exc:
                raise ValueError(f"Rule took too long; simplify this pattern: {pattern}") from exc
            if found:
                reasons.append(f"{kind}: {pattern}")
        return reasons
