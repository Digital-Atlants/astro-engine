"""Vendor tier pricing and the build-versus-buy arithmetic.

Prices are transcribed from the vendor's public pricing page (see SOURCE) on
the date in AS_OF. They are inputs to the report, not measurements, and are
kept here so they can be corrected in one place when the vendor changes them.
"""

from __future__ import annotations

SOURCE = "https://astrology-api.io/pricing"
AS_OF = "2026-08-28"

# A rectification search costs a flat 15 credits per request (confirmed live:
# 15 credits for both a 5-candidate and a 13-candidate search). One full
# 24-hour rectification is two requests, because their window caps at 720 min.
CREDITS_PER_REQUEST = 15
REQUESTS_PER_RECTIFICATION = 2
CREDITS_PER_RECTIFICATION = CREDITS_PER_REQUEST * REQUESTS_PER_RECTIFICATION

# (tier, USD/month, included credits per month, rectification available)
TIERS = [
    ("Free", 0.0, 50, False),
    ("Pro", 11.0, 1_000, False),
    ("Pro Plus", 21.0, 7_000, False),
    ("Ultra", 37.0, 55_000, True),
    ("Business", 99.0, 220_000, True),
    ("Enterprise", 399.0, None, True),
]

# Our own compute cost. Railway bills roughly $0.000463 per vCPU-minute; the
# engine is single-threaded and CPU-bound during a scoring run, so wall-clock
# is a fair proxy for vCPU time. Stated as an assumption, not a measurement.
USD_PER_VCPU_MINUTE = 0.000463


def cost_table() -> list[str]:
    rows = []
    for name, usd, credits, available in TIERS:
        if not available:
            rows.append([
                name, f"${usd:,.0f}",
                "unlimited" if credits is None else f"{credits:,}",
                "not offered", "-", "-",
            ])
            continue
        if credits is None:
            rows.append([name, f"${usd:,.0f}+", "custom", "yes", "negotiated", "negotiated"])
            continue
        per_month = credits // CREDITS_PER_RECTIFICATION
        per_rect = usd / per_month if per_month else None
        rows.append([
            name, f"${usd:,.0f}", f"{credits:,}", "yes",
            f"{per_month:,}", "n/a" if per_rect is None else f"${per_rect:.4f}",
        ])

    header = ["Tier", "USD/month", "Credits/month", "Rectification",
              "Rectifications/month", "Cost per rectification"]
    out = [
        "### Vendor cost per rectification, by tier",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out += [
        "",
        f"One rectification = {REQUESTS_PER_RECTIFICATION} requests "
        f"x {CREDITS_PER_REQUEST} credits = {CREDITS_PER_RECTIFICATION} credits, "
        "because the vendor's window caps at 720 minutes and a full day needs two "
        "calls. **Rectification is gated to Ultra and above**, so the $11 and $21 "
        "tiers cannot buy it at any volume, and the free tier cannot legitimately be "
        "used for it in production at all.",
        "",
        f"Prices transcribed from {SOURCE} on {AS_OF}.",
        "",
    ]
    return out


def build_vs_buy(n_cases: int) -> list[str]:
    ultra = next(t for t in TIERS if t[0] == "Ultra")
    per_month = ultra[2] // CREDITS_PER_RECTIFICATION
    per_rect = ultra[1] / per_month
    return [
        f"Buying: the cheapest tier that can run rectification at all is **Ultra at "
        f"${ultra[1]:,.0f}/month**, which covers {per_month:,} rectifications, i.e. "
        f"**${per_rect:.4f} per rectification** at full utilisation. Below roughly "
        f"{per_month:,} a month the tier fee dominates and the effective unit cost is "
        "higher; at 100 rectifications a month it is $0.37 each.",
        "",
        "Building: our engine runs the same 360-candidate grid in-process. At "
        f"${USD_PER_VCPU_MINUTE:.6f} per vCPU-minute the compute cost per "
        "rectification is a small fraction of a cent - see the measured wall-clock "
        "above - so the marginal cost is effectively zero and the real cost is "
        "engineering time on the scorer.",
        "",
        "**The cost difference is not the deciding factor.** Both options are cheap "
        "per rectification relative to anything charged to an end user. The decision "
        "turns on the accuracy and calibration numbers above, and on the fact that "
        "sending customer birth data and life events to a third party would be a "
        "personal-data transfer with no agreement behind it - some event categories "
        "in the intake are special-category data. Arm B in this report was run on "
        "public-figure fixtures only, and that boundary is what makes it lawful to "
        "run at all; it is not a boundary a production integration could keep.",
        "",
    ]
