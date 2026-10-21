"""Mortgage, land transfer tax and qualifying math for Ontario buyers.

Everything here is a pure function so the search can turn a buyer's financing
into SQL (a constant payment factor times the loan amount) and the listing
page can show the same numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

# OSFI stress test (Guideline B-20): qualify at the greater of the contract rate
# plus 2 points and the 5.25% floor.
STRESS_TEST_SPREAD = 2.0
STRESS_TEST_FLOOR = 5.25
# Standard lender ratios: gross debt service and total debt service.
GDS_LIMIT = 0.39
TDS_LIMIT = 0.44
# Lenders add half of expected rent to the borrower's income when the home will be rented.
RENTAL_INCOME_ADD_BACK = 0.5
# Heating allowance lenders use in debt service ratios; half of condo fees count.
HEAT_ALLOWANCE_MONTHLY = 150
CONDO_FEE_SHARE = 0.5
# Legal fees, title insurance and adjustments, on top of land transfer tax.
OTHER_CLOSING_COSTS = 2500

# Minimum down payment. A home the buyer will not live in needs 20% down; an
# owner-occupied home can be insured with 5% on the first $500k, 10% on the
# rest up to $1.5M, and needs 20% above that.
INVESTMENT_MIN_DOWN = 0.20
INSURED_TIER_1 = 500_000
INSURED_TIER_1_RATE = 0.05
INSURED_TIER_2_RATE = 0.10
INSURED_MAX_PRICE = 1_500_000

Occupancy = str  # "rent_out" | "live_in"


@dataclass(frozen=True)
class Financing:
    down_payment_pct: float = 20.0
    down_payment: int | None = None  # a dollar amount overrides the percentage
    interest_rate: float = 4.25  # annual, percent
    amortization_years: int = 25

    def loan(self, price: int) -> float:
        if self.down_payment is not None:
            return max(price - self.down_payment, 0.0)
        return price * (1 - self.down_payment_pct / 100)

    def down(self, price: int) -> float:
        return price - self.loan(price)


def payment_factor(annual_rate_pct: float, amortization_years: int) -> float:
    """Monthly payment per dollar borrowed.

    Canadian fixed-rate mortgages compound semi-annually, so the monthly rate
    is derived from the semi-annual one rather than being annual / 12.
    """
    if annual_rate_pct <= 0:
        return 1 / (amortization_years * 12)
    monthly = (1 + annual_rate_pct / 200) ** (1 / 6) - 1
    n = amortization_years * 12
    return monthly / (1 - (1 + monthly) ** -n)


def monthly_payment(loan: float, annual_rate_pct: float, amortization_years: int) -> float:
    return loan * payment_factor(annual_rate_pct, amortization_years)


def qualifying_rate(contract_rate_pct: float) -> float:
    return max(contract_rate_pct + STRESS_TEST_SPREAD, STRESS_TEST_FLOOR)


# (upper bound of bracket, marginal rate); None = no upper bound.
ONTARIO_LTT = [
    (55_000, 0.005),
    (250_000, 0.01),
    (400_000, 0.015),
    (2_000_000, 0.02),
    (None, 0.025),
]
# Toronto's Municipal Land Transfer Tax, with the graduated top brackets added in 2024.
TORONTO_LTT = [
    (55_000, 0.005),
    (250_000, 0.01),
    (400_000, 0.015),
    (2_000_000, 0.02),
    (3_000_000, 0.025),
    (4_000_000, 0.035),
    (5_000_000, 0.045),
    (10_000_000, 0.055),
    (20_000_000, 0.065),
    (None, 0.075),
]


def _bracket_tax(price: float, brackets: list[tuple[int | None, float]]) -> float:
    tax = 0.0
    lower = 0
    for upper, rate in brackets:
        if upper is None or price <= upper:
            tax += (price - lower) * rate
            break
        tax += (upper - lower) * rate
        lower = upper
    return tax


def land_transfer_tax(price: int, city: str | None) -> float:
    """Ontario LTT, doubled by the municipal LTT inside the City of Toronto. No first-time-buyer rebates."""
    tax = _bracket_tax(price, ONTARIO_LTT)
    if city == "Toronto":
        tax += _bracket_tax(price, TORONTO_LTT)
    return tax


def closing_costs(price: int, city: str | None) -> float:
    return land_transfer_tax(price, city) + OTHER_CLOSING_COSTS


def min_down_payment(price: int, occupancy: Occupancy) -> float:
    if occupancy != "live_in" or price > INSURED_MAX_PRICE:
        return price * INVESTMENT_MIN_DOWN
    tier1 = min(price, INSURED_TIER_1) * INSURED_TIER_1_RATE
    return tier1 + max(price - INSURED_TIER_1, 0) * INSURED_TIER_2_RATE


def max_price_for_down_payment(down: float, occupancy: Occupancy) -> float:
    """The most expensive home this down payment can buy (inverse of `min_down_payment`)."""
    if occupancy == "live_in":
        tier1_down = INSURED_TIER_1 * INSURED_TIER_1_RATE
        if down <= tier1_down:
            return down / INSURED_TIER_1_RATE
        insured = INSURED_TIER_1 + (down - tier1_down) / INSURED_TIER_2_RATE
        if insured <= INSURED_MAX_PRICE:
            return insured
    return down / INVESTMENT_MIN_DOWN


def max_monthly_payment(
    annual_income: float,
    monthly_debts: float,
    tax_annual: float,
    condo_fee_monthly: float,
    rent_monthly: float,
    occupancy: Occupancy,
) -> float:
    """Largest mortgage payment that keeps GDS under 39% and TDS under 44%.

    Negative when the taxes, heat and fees alone break the ratios.
    """
    income = annual_income + (RENTAL_INCOME_ADD_BACK * rent_monthly * 12 if occupancy == "rent_out" else 0)
    monthly_income = income / 12
    housing = tax_annual / 12 + HEAT_ALLOWANCE_MONTHLY + CONDO_FEE_SHARE * condo_fee_monthly
    gds_room = GDS_LIMIT * monthly_income - housing
    tds_room = TDS_LIMIT * monthly_income - housing - monthly_debts
    return min(gds_room, tds_room)
