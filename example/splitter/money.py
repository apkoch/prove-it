"""Money as whole cents (int). Splitting uses the largest-remainder method, so the shares always
add back up to the total."""

from decimal import Decimal, InvalidOperation


def parse_cents(text: str) -> int:
    """'12.34' → 1234. Rejects anything with more than two decimal places."""
    try:
        amount = Decimal(text.strip())
    except InvalidOperation as e:
        raise ValueError(f"not an amount: {text!r}") from e
    cents = amount * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"more than two decimal places: {text!r}")
    return int(cents)


def split(total: int, weights: list[int]) -> list[int]:
    """Split `total` cents in proportion to `weights` (each > 0).

    Everyone gets the floor of their exact share; the cents left over go one each to the largest
    remainders, earliest payer first on a tie.
    """
    if not weights or any(w <= 0 for w in weights):
        raise ValueError("weights must be positive")
    whole = sum(weights)
    shares = [total * w // whole for w in weights]
    remainders = [total * w % whole for w in weights]
    leftover = total - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        shares[i] += 1
    return shares
