"""Choose the one card a straight build will spend on.

The page builds this card without a second confirmation. Any other card
stays visible and is not started. A failed or unknown safety check never
reaches this choice.
"""


def eligible_card(cards):
    """First python-wsgi card with no extra dependencies or services."""
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        if card.get("runtime") != "python-wsgi":
            continue
        if card.get("dependencies") or card.get("external_services"):
            continue
        if not card.get("id") or not card.get("title"):
            continue
        return card
    return None
