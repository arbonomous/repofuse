"""Choose the one card a straight build will spend on.

The page builds this card without a second confirmation. Any other card
stays visible and is not started. A failed or unknown safety check never
reaches this choice.
"""


def _usable(card):
    return (isinstance(card, dict) and card.get("runtime") == "python-wsgi"
            and card.get("id") and card.get("title"))


def eligible_card(cards):
    """First contained Python card.

    A card with no extra packages or services is preferred. When every
    Python card names some, the first one is still built: this app does
    not install those packages or open those services.
    """
    usable = [card for card in cards or [] if _usable(card)]
    for card in usable:
        if not card.get("dependencies") and not card.get("external_services"):
            return card
    return usable[0] if usable else None
