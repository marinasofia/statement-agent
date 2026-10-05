"""List prices per million tokens, used only to estimate what a run cost.

Prices change; the estimate is for the run summary and the eval table,
not for billing. Unknown models get None rather than a made-up number.
Order matters: the first prefix that matches wins.
"""

PRICES_PER_MILLION = [
    ("claude-haiku-4-5", 1.00, 5.00),
    ("claude-sonnet-5", 2.00, 10.00),
    ("claude-sonnet-4-6", 3.00, 15.00),
    ("claude-opus-5", 5.00, 25.00),
    ("claude-opus-4", 5.00, 25.00),
]


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int):
    for prefix, in_price, out_price in PRICES_PER_MILLION:
        if model and model.startswith(prefix):
            return round((input_tokens * in_price + output_tokens * out_price) / 1_000_000, 6)
    return None
