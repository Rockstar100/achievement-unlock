"""Slack message formatters for pet trend digests."""
from datetime import date
from typing import Any, Dict, List


def format_daily_pulse(products: List[Dict[str, Any]]) -> List[dict]:
    """Format top trending products as Slack Block Kit blocks."""
    today = date.today().isoformat()
    blocks: List[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Daily Pet Trends Pulse — {today}"},
        },
        {"type": "divider"},
    ]

    if not products:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_No trending products found for today. Check pipeline run status._",
                },
            }
        )
        return blocks

    lines = []
    for i, p in enumerate(products, start=1):
        tier_emoji = {"breakout": ":fire:", "rising": ":chart_with_upwards_trend:", "stable": ":white_check_mark:", "declining": ":chart_with_downwards_trend:"}
        emoji = tier_emoji.get(p.get("trend_tier", ""), ":dog:")
        lines.append(
            f"{i}. {emoji} *{p.get('canonical_title', 'Unknown')}* "
            f"({p.get('normalized_brand', '')}) — "
            f"Score: *{p.get('trend_score', 0):.1f}* | "
            f"{p.get('category', '')}"
        )
        reasons = str(p.get("reason_codes", "") or "").replace("|", ", ")
        action = p.get("recommended_action", "")
        if reasons or action:
            lines.append(f"   _{action or 'MONITOR'}_ · {reasons or 'no signals'}")

    blocks.append(
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}
    )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Source: gold_dim_trending_pet_products | Updated daily at 7:30 AM IST",
                }
            ],
        }
    )
    return blocks


def format_weekly_digest(
    top_products: List[Dict[str, Any]],
    category_summary: List[Dict[str, Any]],
    rising_keywords: List[Dict[str, Any]],
) -> List[dict]:
    """Format weekly digest with products, categories, and rising keywords."""
    blocks: List[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Weekly Pet Trends Digest"},
        },
        {"type": "divider"},
    ]

    # Top products
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:trophy: Top 10 Trending Products (7 days)*"},
        }
    )
    if top_products:
        product_lines = []
        for i, p in enumerate(top_products, start=1):
            action = p.get("recommended_action", "")
            suffix = f" · {action}" if action else ""
            product_lines.append(
                f"{i}. *{p.get('canonical_title', '')}* — "
                f"Score {p.get('trend_score', 0):.1f} ({p.get('trend_tier', '')}){suffix}"
            )
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(product_lines[:10])}}
        )
    else:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "_No product data this week._"}}
        )

    blocks.append({"type": "divider"})

    # Category summary
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:bar_chart: Category Performance*"},
        }
    )
    if category_summary:
        cat_lines = [
            f"• *{c.get('category', '')}*: avg score {c.get('avg_score', 0):.1f} ({c.get('product_count', 0)} products)"
            for c in category_summary
        ]
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(cat_lines)}}
        )

    blocks.append({"type": "divider"})

    # Rising keywords
    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*:mag: Rising Search Keywords*"},
        }
    )
    if rising_keywords:
        kw_lines = [
            f"• `{k.get('keyword', '')}` ({k.get('category', '')}) — +{k.get('rising_score', 0)}%"
            for k in rising_keywords[:10]
        ]
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(kw_lines)}}
        )
    else:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": "_No rising keywords detected._"}}
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "Weekly digest | Mondays 9:00 AM IST | Pet Trend Intelligence"},
            ],
        }
    )
    return blocks
