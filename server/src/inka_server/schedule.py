import math

MIN_SLEEP_S = 60
MARGIN_S = 30
DEBUG_SLEEP_S = 30  # ladicí režim: rámeček se ptá každých 30 s
DEBUG_DURATION_S = 3600  # a sám se po hodině vypne
LIGHT_MAX_SLEEP_S = 300  # ze sítě: ptát se aspoň každých 5 min, aby se „Zobrazit hned“ projevilo brzy


def slot_index(now: float, interval_s: int, count: int, offset: int) -> int:
    return (int(now // interval_s) + offset) % count


def sleep_seconds(now: float, interval_s: int) -> int:
    next_boundary = (math.floor(now / interval_s) + 1) * interval_s
    return max(MIN_SLEEP_S, math.ceil(next_boundary - now) + MARGIN_S)
