"""Turn scraped Amazon listings into MACS catalogue records.

Usage:
  python enrich.py --in <scrape.json> [--in <more.json>] --out ../data/catalogue_scraped.json [--limit N] [--model claude-haiku-4-5]

What comes from the scrape: sku (ASIN), name, list_price, brand, rating, delivery text, weight, dimensions, url, image.
What Haiku infers from the title: type, suited_for, outcome_tags, description, durability, compatibility, materials,
and certifications only when the title names one.
What a scrape cannot know and is assigned by rule (stated in the README): cost = 60% of list, ship_days parsed from
the delivery text (default 3), stock = 25.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import Field, ValidationError

from macs.models import LenientModel

SCRAPE_DATE = date(2026, 9, 12)
BATCH = 10
CONCURRENCY = 6
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

SYSTEM = """You catalogue products for a retailer that sells to AI shopping agents. For each listing you are given only
an Amazon title, brand, price and category. Fill the structured record from what the title supports:
- type: a short snake_case product type (e.g. wireless_earbuds, led_face_mask, kindle_ebook, usb_c_cable).
- suited_for: who or what situation it fits (e.g. beginner, travel, gym, sensitive_skin, small_space, gift). 1 to 4 items.
- outcome_tags: what it delivers (e.g. noise_cancellation, fast_charging, hydration, long_battery). 2 to 5 items.
- description: one plain sentence, at most 25 words, no marketing superlatives.
- durability: low, medium or high, judged from materials and category.
- compatibility: devices, standards or skin/hair types it works with, if stated. Empty list otherwise.
- materials: only if the title states them. Empty list otherwise.
- certifications: only certification or ethics claims literally present in the title (vegan, cruelty-free, USDA Organic,
  FSC, Energy Star, Fair Trade, recycled). Never infer one. Empty list otherwise.
Return one record per asin, in the same order, using the record_products tool."""


class Enriched(LenientModel):
    asin: str
    type: str
    suited_for: list[str] = Field(default_factory=list)
    outcome_tags: list[str] = Field(default_factory=list)
    description: str = ""
    durability: str = "medium"
    compatibility: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class EnrichedBatch(LenientModel):
    products: list[Enriched]


def load_listings(paths: list[Path]) -> list[dict]:
    seen: dict[str, dict] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        groups = data.items() if isinstance(data, dict) else [("root", data)]
        for category, results in groups:
            for r in results if isinstance(results, list) else []:
                for p in (r.get("products", []) if isinstance(r, dict) else []):
                    asin, price = p.get("asin"), p.get("extractedPrice")
                    if not asin or not price or price <= 0 or asin in seen:
                        continue
                    seen[asin] = {**p, "_category": category}
    return list(seen.values())


def ship_days(delivery: Optional[str]) -> int:
    if not delivery:
        return 3
    if re.search(r"\b(Today|Tomorrow)\b", delivery):
        return 1
    m = re.search(r"[A-Z][a-z]{2}, ([A-Z][a-z]{2}) (\d{1,2})", delivery)
    if not m or m.group(1) not in MONTHS:
        return 3
    try:
        d = date(SCRAPE_DATE.year, MONTHS[m.group(1)], int(m.group(2)))
    except ValueError:
        return 3
    return max(1, min(14, (d - SCRAPE_DATE).days))


def short_name(title: str, limit: int = 90) -> str:
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,|-") + "…"


def to_record(p: dict, e: Optional[Enriched]) -> dict:
    price = float(p["extractedPrice"])
    e = e or Enriched(asin=p["asin"], type="general")
    return {
        "sku": p["asin"],
        "name": short_name(p["title"]),
        "title_full": p["title"],
        "type": e.type,
        "list_price": round(price, 2),
        "cost": round(price * 0.6, 2),
        "stock": 25,
        "ship_days": ship_days(p.get("delivery")),
        "specs": {k: v for k, v in (("weight", p.get("weight")), ("dimension", p.get("dimension"))) if v},
        "suited_for": e.suited_for,
        "sustainability": {"materials": e.materials, "certifications": e.certifications, "brand_practice": ""},
        "durability": e.durability,
        "compatibility": e.compatibility,
        "outcome_tags": e.outcome_tags,
        "description": e.description,
        "brand": p.get("brand") or "",
        "rating": p.get("rating"),
        "ratings": p.get("ratings"),
        "url": p.get("asinUrl") or "",
        "image_url": p.get("imageUrl") or "",
        "source_category": p.get("_category", ""),
    }


async def enrich_batch(client: anthropic.AsyncAnthropic, model: str, batch: list[dict], sem: asyncio.Semaphore) -> dict[str, Enriched]:
    listing = "\n".join(
        f"- asin {p['asin']} | category {p.get('_category','')} | brand {p.get('brand') or 'unknown'} | "
        f"price {p['extractedPrice']} | title: {p['title']}" for p in batch
    )
    schema = EnrichedBatch.model_json_schema()
    async with sem:
        for attempt in range(3):
            try:
                resp = await client.messages.create(
                    model=model, max_tokens=4000, system=SYSTEM,
                    messages=[{"role": "user", "content": f"Listings:\n{listing}"}],
                    tools=[{"name": "record_products", "description": "Record the enriched product records.", "input_schema": schema}],
                    tool_choice={"type": "tool", "name": "record_products"},
                )
                block = next(b for b in resp.content if b.type == "tool_use")
                parsed = EnrichedBatch.model_validate(block.input)
                return {e.asin: e for e in parsed.products}
            except (ValidationError, StopIteration, anthropic.APIConnectionError, anthropic.RateLimitError,
                    anthropic.InternalServerError) as exc:
                if attempt == 2:
                    print(f"  batch starting {batch[0]['asin']} failed: {type(exc).__name__}", file=sys.stderr)
                    return {}
                await asyncio.sleep(2)
    return {}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", action="append", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="claude-haiku-4-5")
    a = ap.parse_args()

    listings = load_listings(a.inputs)
    if a.limit:
        listings = listings[: a.limit]
    print(f"{len(listings)} priced, de-duplicated listings from {len(a.inputs)} file(s); enriching with {a.model}")

    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(CONCURRENCY)
    batches = [listings[i:i + BATCH] for i in range(0, len(listings), BATCH)]
    t0 = datetime.now()
    results = await asyncio.gather(*(enrich_batch(client, a.model, b, sem) for b in batches))
    enriched: dict[str, Enriched] = {}
    for r in results:
        enriched.update(r)
    records = [to_record(p, enriched.get(p["asin"])) for p in listings]
    missing = sum(1 for p in listings if p["asin"] not in enriched)
    a.out.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} records to {a.out} in {(datetime.now() - t0).seconds}s; "
          f"{missing} fell back to defaults; {len(batches)} model calls")


if __name__ == "__main__":
    asyncio.run(main())
