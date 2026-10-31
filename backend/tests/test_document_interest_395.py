from datetime import date
from decimal import Decimal

from app.services.document_interest_395 import normalize_rate_history, rate_periods


def test_daily_cbr_observations_with_the_same_rate_form_one_interest_period():
    history = normalize_rate_history([
        (date(2026, 10, 1), Decimal("14.00")),
        (date(2026, 10, 2), Decimal("14.00")),
        (date(2026, 10, 3), Decimal("14.00")),
        (date(2026, 10, 4), Decimal("14.00")),
    ])

    periods = rate_periods(date(2026, 10, 1), date(2026, 10, 4), history)

    assert history == [(date(2026, 10, 1), Decimal("14.00"))]
    assert [(item.start, item.end, item.annual_rate) for item in periods] == [
        (date(2026, 10, 1), date(2026, 10, 4), Decimal("14.00")),
    ]


def test_rate_history_keeps_each_verified_rate_change():
    history = normalize_rate_history([
        (date(2026, 9, 1), Decimal("14.00")),
        (date(2026, 9, 2), Decimal("14.00")),
        (date(2026, 10, 1), Decimal("15.00")),
        (date(2026, 10, 2), Decimal("15.00")),
    ])

    assert history == [
        (date(2026, 9, 1), Decimal("14.00")),
        (date(2026, 10, 1), Decimal("15.00")),
    ]
