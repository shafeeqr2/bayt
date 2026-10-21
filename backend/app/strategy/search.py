"""Investment-strategy search: the SQL side of returns, affordability and value-add filters.

The buyer's financing becomes constants (a payment factor per dollar
borrowed), so cash flow and the stress-tested qualifying payment are plain
arithmetic on each listing's price, tax, fees and estimated rent.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Query
from sqlalchemy import ColumnElement, func
from sqlalchemy.sql import expression

from app.models import Listing, ListingInvestment
from app.schemas import (
    ExpenseBreakdown,
    FinancingOut,
    InvestmentDetail,
    InvestmentSummary,
    Potential,
    StrategyDefaults,
)
from app.strategy import estimate, finance, rents
from app.strategy.estimate import EXPENSE_ASSUMPTIONS, expenses
from app.strategy.finance import Financing

PotentialKey = Literal[
    "suite", "suite_potential", "separate_entrance", "garden_suite", "severance", "multiplex", "extra_bedroom"
]
Occupancy = Literal["rent_out", "live_in"]
StrategySort = Literal["cap_rate_desc", "cash_flow_desc", "yield_desc"]

POSITIVE_VERDICTS = ("likely", "possible")

POTENTIAL_LABELS: dict[str, str] = {
    "suite": "Rental suite",
    "suite_potential": "Suite potential",
    "separate_entrance": "Separate entrance",
    "garden_suite": "Garden suite",
    "severance": "Severance",
    "multiplex": "Multiplex zoning",
    "extra_bedroom": "Room for a bedroom",
}

EXAMPLE_STRATEGIES = [
    "Looking for a property with a 6-8% return under $900k",
    "I make $140k and have $150k saved. What can I afford that cash flows?",
    "A house in Toronto where I could add a garden suite",
    "Might want to turn a 2-bed into a 3-bed",
    "Condo under 600k with a tenant in place, 20% down",
]


def financing_params(
    down_payment_pct: Annotated[float, Query(ge=0, le=100)] = Financing.down_payment_pct,
    down_payment: Annotated[int | None, Query(ge=0)] = None,
    interest_rate: Annotated[float, Query(ge=0, le=25)] = Financing.interest_rate,
    amortization: Annotated[int, Query(ge=5, le=40)] = Financing.amortization_years,
) -> Financing:
    return Financing(down_payment_pct, down_payment, interest_rate, amortization)


def loan_expr(fin: Financing) -> ColumnElement:
    if fin.down_payment is not None:
        return func.greatest(Listing.price - fin.down_payment, 0)
    return Listing.price * (1 - fin.down_payment_pct / 100)


def cash_flow_expr(fin: Financing) -> ColumnElement:
    """Monthly cash flow after the mortgage, as SQL."""
    factor = finance.payment_factor(fin.interest_rate, fin.amortization_years)
    return ListingInvestment.noi_annual / 12.0 - loan_expr(fin) * factor


def potential_filter(key: str) -> ColumnElement:
    return {
        "suite": ListingInvestment.has_suite.is_(True),
        "suite_potential": ListingInvestment.suite_potential.is_(True),
        "separate_entrance": ListingInvestment.separate_entrance.is_not(None),
        "garden_suite": ListingInvestment.garden_suite.in_(POSITIVE_VERDICTS),
        "severance": ListingInvestment.severance.in_(POSITIVE_VERDICTS),
        "multiplex": ListingInvestment.multiplex_zone.is_(True),
        "extra_bedroom": ListingInvestment.extra_bedroom_room.is_not(None),
    }[key]


def strategy_filters(
    fin: Financing,
    *,
    min_cap_rate: float | None,
    min_gross_yield: float | None,
    min_cash_flow: int | None,
    income: int | None,
    monthly_debts: int,
    occupancy: str,
    potential: list[str] | None,
) -> list[ColumnElement]:
    filters: list[ColumnElement] = []
    if min_cap_rate is not None:
        filters.append(ListingInvestment.cap_rate_pct >= min_cap_rate)
    if min_gross_yield is not None:
        filters.append(ListingInvestment.gross_yield_pct >= min_gross_yield)
    if min_cash_flow is not None:
        filters.append(cash_flow_expr(fin) >= min_cash_flow)
    if fin.down_payment is not None:
        filters.append(Listing.price <= finance.max_price_for_down_payment(fin.down_payment, occupancy))
    if income is not None:
        filters.append(affordability_expr(fin, income, monthly_debts, occupancy))
    for key in potential or []:
        filters.append(potential_filter(key))
    return filters


def affordability_expr(fin: Financing, income: int, monthly_debts: int, occupancy: str) -> ColumnElement:
    """True when the stress-tested mortgage payment keeps the buyer within GDS/TDS limits."""
    rent_add_back = (
        finance.RENTAL_INCOME_ADD_BACK * func.coalesce(ListingInvestment.rent_monthly, 0) * 12
        if occupancy == "rent_out"
        else 0
    )
    monthly_income = (income + rent_add_back) / 12.0
    tax = func.coalesce(
        expression.case((Listing.tax_annual >= estimate.MIN_PLAUSIBLE_TAX, Listing.tax_annual), else_=None),
        Listing.price * estimate.DEFAULT_TAX_PCT / 100,
    )
    housing = tax / 12.0 + finance.HEAT_ALLOWANCE_MONTHLY + finance.CONDO_FEE_SHARE * func.coalesce(
        Listing.maintenance_fee_monthly, 0
    )
    room = func.least(
        finance.GDS_LIMIT * monthly_income - housing,
        finance.TDS_LIMIT * monthly_income - housing - monthly_debts,
    )
    q_factor = finance.payment_factor(finance.qualifying_rate(fin.interest_rate), fin.amortization_years)
    return loan_expr(fin) * q_factor <= room


def strategy_sort(sort: str, fin: Financing) -> ColumnElement | None:
    if sort == "cap_rate_desc":
        return ListingInvestment.cap_rate_pct.desc().nulls_last()
    if sort == "yield_desc":
        return ListingInvestment.gross_yield_pct.desc().nulls_last()
    if sort == "cash_flow_desc":
        return cash_flow_expr(fin).desc().nulls_last()
    return None


# --- Python-side shapes for responses ------------------------------------------------------


def potentials(row: ListingInvestment) -> list[Potential]:
    items: list[Potential] = []
    if row.has_suite:
        items.append(Potential(key="suite", label=POTENTIAL_LABELS["suite"], detail=row.suite_note or ""))
    elif row.suite_potential:
        items.append(Potential(key="suite_potential", label=POTENTIAL_LABELS["suite_potential"], detail=row.suite_note or ""))
    if row.separate_entrance:
        items.append(
            Potential(key="separate_entrance", label=POTENTIAL_LABELS["separate_entrance"], detail=row.separate_entrance)
        )
    if row.garden_suite in POSITIVE_VERDICTS:
        items.append(
            Potential(
                key="garden_suite",
                label=POTENTIAL_LABELS["garden_suite"],
                detail=f"The lot analysis rates a garden suite as {row.garden_suite}.",
            )
        )
    if row.severance in POSITIVE_VERDICTS:
        items.append(
            Potential(
                key="severance",
                label=POTENTIAL_LABELS["severance"],
                detail=f"The lot analysis rates splitting the lot in two as {row.severance}.",
            )
        )
    if row.multiplex_zone:
        units = row.as_of_right_units or 4
        items.append(
            Potential(
                key="multiplex",
                label=POTENTIAL_LABELS["multiplex"],
                detail=f"Toronto zoning allows up to {units} units here as-of-right.",
            )
        )
    if row.extra_bedroom_room:
        items.append(
            Potential(
                key="extra_bedroom",
                label=POTENTIAL_LABELS["extra_bedroom"],
                detail=f"{row.extra_bedroom_room} is big enough to close in as a bedroom.",
            )
        )
    return items


def cash_flow(row: ListingInvestment, price: int, fin: Financing) -> int:
    payment = finance.monthly_payment(fin.loan(price), fin.interest_rate, fin.amortization_years)
    return round(row.noi_annual / 12 - payment)


def summary(row: ListingInvestment | None, price: int, fin: Financing) -> InvestmentSummary | None:
    if row is None:
        return None
    return InvestmentSummary(
        rent_monthly=row.rent_monthly,
        rent_source=row.rent_source,
        gross_yield_pct=row.gross_yield_pct,
        cap_rate_pct=row.cap_rate_pct,
        cash_flow_monthly=cash_flow(row, price, fin),
        potential=potentials(row),
    )


def financing_out(fin: Financing) -> FinancingOut:
    return FinancingOut(
        down_payment_pct=fin.down_payment_pct,
        down_payment=fin.down_payment,
        interest_rate=fin.interest_rate,
        amortization=fin.amortization_years,
    )


def detail(listing: Listing, row: ListingInvestment, fin: Financing) -> InvestmentDetail:
    costs = expenses(listing, row.gross_annual)
    loan = fin.loan(listing.price)
    payment = finance.monthly_payment(loan, fin.interest_rate, fin.amortization_years)
    monthly_cash_flow = row.noi_annual / 12 - payment
    ltt = finance.land_transfer_tax(listing.price, listing.city)
    closing = finance.closing_costs(listing.price, listing.city)
    cash_needed = fin.down(listing.price) + closing

    # Income at which the stress-tested payment just fits the GDS limit, counting half the rent.
    q_payment = finance.monthly_payment(
        loan, finance.qualifying_rate(fin.interest_rate), fin.amortization_years
    )
    housing = costs.property_tax / 12 + finance.HEAT_ALLOWANCE_MONTHLY + finance.CONDO_FEE_SHARE * (
        listing.maintenance_fee_monthly or 0
    )
    income_to_qualify = (q_payment + housing) * 12 / finance.GDS_LIMIT - finance.RENTAL_INCOME_ADD_BACK * row.gross_annual

    return InvestmentDetail(
        rent_monthly=row.rent_monthly,
        rent_source=row.rent_source,
        rent_note=row.rent_note,
        units=row.units,
        gross_annual=row.gross_annual,
        expenses=ExpenseBreakdown(
            property_tax=costs.property_tax,
            condo_fees=costs.condo_fees,
            insurance=costs.insurance,
            maintenance=costs.maintenance,
            vacancy=costs.vacancy,
            total=costs.total,
            tax_estimated=costs.tax_estimated,
        ),
        noi_annual=row.noi_annual,
        gross_yield_pct=row.gross_yield_pct,
        cap_rate_pct=row.cap_rate_pct,
        financing=financing_out(fin),
        loan=round(loan),
        mortgage_monthly=round(payment),
        cash_flow_monthly=round(monthly_cash_flow),
        land_transfer_tax=round(ltt),
        closing_costs=round(closing),
        cash_needed=round(cash_needed),
        cash_on_cash_pct=round(monthly_cash_flow * 12 / cash_needed * 100, 2) if cash_needed > 0 else None,
        qualifying_rate=finance.qualifying_rate(fin.interest_rate),
        income_to_qualify=max(round(income_to_qualify), 0),
        potential=potentials(row),
        assumptions=assumptions(),
    )


def assumptions() -> list[str]:
    return [
        f"Rent is what the listing states, or the {rents.RENT_SOURCE} average for the city, home type and bedroom count.",
        *EXPENSE_ASSUMPTIONS,
        "Mortgage payments use Canadian semi-annual compounding.",
        f"Qualifying uses the stress test (contract rate + {finance.STRESS_TEST_SPREAD:g}%, floor {finance.STRESS_TEST_FLOOR}%), "
        f"GDS {finance.GDS_LIMIT:.0%}, TDS {finance.TDS_LIMIT:.0%}, and half of the rent as income when the home is rented out.",
        "Closing costs are Ontario land transfer tax (plus Toronto's inside the city) and about "
        f"${finance.OTHER_CLOSING_COSTS:,} in legal and title costs. No first-time-buyer rebates.",
        "Cap rate and cash flow ignore appreciation, principal paydown and income tax.",
    ]


def defaults() -> StrategyDefaults:
    return StrategyDefaults(
        financing=financing_out(Financing()),
        assumptions=assumptions(),
        rent_source=rents.RENT_SOURCE,
        examples=EXAMPLE_STRATEGIES,
    )
