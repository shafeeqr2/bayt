import pytest

from app.strategy import finance
from app.strategy.finance import Financing


def test_monthly_payment_uses_semi_annual_compounding():
    # $500,000 at 5% over 25 years is the textbook $2,908/month in Canada
    # (a US-style monthly-compounded loan would be $2,923).
    assert finance.monthly_payment(500_000, 5.0, 25) == pytest.approx(2908.02, abs=0.5)


def test_zero_rate_spreads_principal_evenly():
    assert finance.monthly_payment(300_000, 0, 25) == pytest.approx(1000)


def test_qualifying_rate_has_floor_and_spread():
    assert finance.qualifying_rate(2.5) == 5.25
    assert finance.qualifying_rate(4.25) == 6.25


def test_land_transfer_tax_doubles_in_toronto():
    ontario = finance.land_transfer_tax(1_000_000, "Vaughan")
    assert ontario == pytest.approx(16_475)
    assert finance.land_transfer_tax(1_000_000, "Toronto") == pytest.approx(2 * ontario)


def test_toronto_graduated_brackets_above_two_million():
    # Ontario: 36,475 up to 2M + 2.5% on the next 1M. Toronto adds the same plus 2.5% on 2M-3M.
    assert finance.land_transfer_tax(3_000_000, "Toronto") == pytest.approx(36_475 + 25_000 + 36_475 + 25_000)


def test_investment_needs_twenty_percent_down():
    assert finance.min_down_payment(800_000, "rent_out") == 160_000
    assert finance.max_price_for_down_payment(160_000, "rent_out") == 800_000


def test_owner_occupied_insured_ladder():
    assert finance.min_down_payment(400_000, "live_in") == 20_000
    assert finance.min_down_payment(800_000, "live_in") == 25_000 + 30_000
    assert finance.min_down_payment(2_000_000, "live_in") == 400_000
    assert finance.max_price_for_down_payment(55_000, "live_in") == pytest.approx(800_000)
    assert finance.max_price_for_down_payment(20_000, "live_in") == pytest.approx(400_000)
    assert finance.max_price_for_down_payment(400_000, "live_in") == pytest.approx(2_000_000)


def test_max_payment_counts_half_the_rent_when_rented_out():
    rented = finance.max_monthly_payment(120_000, 0, 6_000, 0, 3_000, "rent_out")
    lived_in = finance.max_monthly_payment(120_000, 0, 6_000, 0, 3_000, "live_in")
    assert rented - lived_in == pytest.approx(0.39 * 0.5 * 3_000)
    assert lived_in == pytest.approx(0.39 * 10_000 - 500 - 150)


def test_debts_bind_through_tds():
    without = finance.max_monthly_payment(120_000, 0, 6_000, 0, 0, "live_in")
    with_debts = finance.max_monthly_payment(120_000, 1_500, 6_000, 0, 0, "live_in")
    assert with_debts < without
    assert with_debts == pytest.approx(0.44 * 10_000 - 650 - 1_500)


def test_financing_amount_overrides_percentage():
    assert Financing(down_payment_pct=20).loan(1_000_000) == 800_000
    assert Financing(down_payment=300_000).loan(1_000_000) == 700_000
    assert Financing(down_payment=2_000_000).loan(1_000_000) == 0
