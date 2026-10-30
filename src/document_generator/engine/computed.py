"""Computed value functions (config ``computed:`` declarations -> plan §3.2).

Pure formatting helpers. Formats are matched to the golden document
(A4: docs/plan-template-master-backend.md):

- ``ordinal_date``   -> '1st October ,2026'   (verbatim golden cover date,
                        incl. the ' ,' separator before the year)
- ``financial_year`` -> '26-27'               (Indian FY, April-March; short
                        form as used in golden REF 'CNK/PROP/C/50/26-27')
- ``indian_format``  -> 'Rs. 20,25,000'       (grouped 3/2/2/2..., used for the
                        total-fee sentence)
- ``milestone_amounts`` -> rows with 'amount_indian' = 'Rs.   202500'
                        (ungrouped digits with the literal 'Rs.   ' prefix —
                        verbatim golden milestone-table cell text)
- ``list_phrase``    -> 'A, B and C'          (engine-generic joiner)
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from .errors import ConfigError

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Literal prefix used by the golden milestone table ('Rs.' + 3 spaces).
MILESTONE_AMOUNT_PREFIX = "Rs.   "


def _as_date(value):
    """Accept date/datetime or ISO string ('YYYY-MM-DD' possibly with time)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(text.split("T")[0], fmt).date()
            except ValueError:
                continue
    raise ConfigError(f"Cannot parse date value: {value!r}")


def _ordinal_suffix(day):
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def ordinal_date(value):
    """'1st October ,2026' — verbatim golden cover-letter date format."""
    d = _as_date(value)
    return f"{d.day}{_ordinal_suffix(d.day)} {_MONTHS[d.month - 1]} ,{d.year}"


def financial_year(value):
    """Indian financial year (April-March) as short '26-27' (golden REF form)."""
    d = _as_date(value)
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def indian_format(value, prefix=""):
    """Indian digit grouping: 2025000 -> 'Rs. 20,25,000' with prefix='Rs. '."""
    amount = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if amount < 0 else ""
    digits = str(abs(amount))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{prefix}{sign}{digits}"


def milestone_amounts(total_fee, milestones):
    """Milestone table rows for the computed ``milestones`` declaration.

    Returns [{label, percent, amount_indian}] where amount_indian reproduces
    the golden table cell text ('Rs.   202500' — ungrouped digits).
    """
    fee = Decimal(str(total_fee or 0))
    rows = []
    for item in milestones or []:
        percent = item.get("percent")
        amount = (fee * Decimal(str(percent)) / Decimal("100")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        rows.append(
            {
                "label": item.get("label", ""),
                "percent": percent,
                "amount_indian": f"{MILESTONE_AMOUNT_PREFIX}{int(amount)}",
            }
        )
    return rows


def list_phrase(list, fallback=""):
    """'A, B and C' joiner (config: entities_phrase / ai_industries_phrase).

    The first parameter is named ``list`` to match the config's declared
    arg name (``args: { list: client.entities, fallback: ... }``); computed
    args are passed as keyword arguments.
    """
    values = [str(item).strip() for item in (list or []) if str(item).strip()]
    if not values:
        return fallback
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " and " + values[-1]


# Registry consumed by manifest validation and context execution. The config's
# ``computed:`` entries reference functions by these names.
FUNCTIONS = {
    "ordinal_date": ordinal_date,
    "financial_year": financial_year,
    "indian_format": indian_format,
    "milestone_amounts": milestone_amounts,
    "list_phrase": list_phrase,
}
