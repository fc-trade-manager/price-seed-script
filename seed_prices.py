import csv
import math
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

DAYS = 30
SEED = 42
BOOST_MIN_OVERALL = 86  # 86+ cards get a boost on Friday 00:00 UTC
BOOST_PEAK = 0.08       # +8% on Friday 00:00 UTC
RARITY = {"gold common": 0.6, "hero": 1.6, "icon": 2.2}  # the rest are worth 1.0
# Adjustments per card (key = ExternalRef). Options: base, trend, noise, boost, end (see the README). Example:
# OVERRIDES = {"cards-030": {"base": 40000, "trend": 0.25, "noise": 2, "boost": False, "end": 54000}}
OVERRIDES = {}
_OPTIONS = {"base", "trend", "noise", "boost", "end"}


def nice(price):
    """Limit a 200..15.000.000 and round to 3 significant digits (1.234 -> 1.230)."""
    price = min(max(price, 200), 15_000_000)
    return int(round(price, 2 - math.floor(math.log10(price))))


def history(card, times, rng):
    """Base price (overall and rarity) + monthly trend + friday boost + gentle noise."""
    opt = OVERRIDES.get(card["ExternalRef"], {})
    overall = int(card["Overall"])
    base = opt.get("base") or 2000 * 1.4 ** (overall - 80) * RARITY.get(card["Rarity"].strip().lower(), 1.0)
    trend = math.log1p(opt["trend"]) if "trend" in opt else rng.gauss(0, 0.06)  # rises/falls ~6% per month
    use_boost = opt.get("boost", True) and overall >= BOOST_MIN_OVERALL
    noise, path = 0.0, []
    for i, t in enumerate(times):
        noise = 0.97 * noise + rng.gauss(0, 0.006) * opt.get("noise", 1)  # oscillates but returns to center
        since_friday = ((t.weekday() - 4) % 7) * 24 + t.hour  # hours since Friday 00:00 UTC
        boost = BOOST_PEAK * (1 - since_friday / 72) if use_boost and since_friday < 72 else 0
        path.append(math.log(base) + trend * i / (len(times) - 1) + math.log1p(boost) + noise)

    if "end" in opt:  # in the last 48 hours, adjust the price to reach the target end price
        n, delta = len(path), math.log(opt["end"]) - path[-1]
        for i in range(n - 48, n):
            path[i] += delta * (i - (n - 48) + 1) / 48
    return [nice(math.exp(x)) for x in path]


def main():
    cards_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "price_seed.sql"
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [now - timedelta(hours=h) for h in range(DAYS * 24, -1, -1)]  # one price per hour for the last 30 days

    with open(cards_file, newline="", encoding="utf-8-sig") as f:
        cards = list(csv.DictReader(f))
    refs = [c["ExternalRef"] for c in cards]
    assert len(refs) == len(set(refs)), "ExternalRef repetido no CSV"
    for ref, opt in OVERRIDES.items():  # this is a sanity check for the overrides
        assert ref in refs, f"OVERRIDES: ExternalRef inexistente no CSV: {ref}"
        assert set(opt) <= _OPTIONS, f"OVERRIDES[{ref}]: opção desconhecida: {set(opt) - _OPTIONS}"
        assert opt.get("trend", 0) > -1, f"OVERRIDES[{ref}]: trend deve ser maior que -1"

    rows = []
    for card in cards:
        ref = card["ExternalRef"]
        safe = ref.replace("'", "''")
        for t, price in zip(times, history(card, times, random.Random(f"{SEED}:{ref}"))):
            rid = uuid.uuid5(uuid.NAMESPACE_URL, f"{ref}|{t:%Y-%m-%dT%H}")  # fixo: reimportar não duplica
            rows.append(f"('{rid}', '{safe}', {price}, '{t:%Y-%m-%d %H:%M}+00')")

    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write('BEGIN;\nDELETE FROM "PriceSnapshots" WHERE "Source" = \'simulated\';\n')
        for i in range(0, len(rows), 1000):
            f.write(
                'INSERT INTO "PriceSnapshots" ("Id", "CardId", "Price", "Source", "RecordedAt")\n'
                "SELECT v.id::uuid, c.\"Id\", v.price, 'simulated', v.ts::timestamptz\n"
                "FROM (VALUES\n  " + ",\n  ".join(rows[i:i + 1000]) + "\n) AS v(id, ref, price, ts)\n"
                'JOIN "Cards" c ON c."ExternalRef" = v.ref ON CONFLICT ("Id") DO NOTHING;\n'
            )
        f.write("COMMIT;\n")
    print(f"{len(cards)} cartas, {len(rows)} preços -> {out_file}")


if __name__ == "__main__":
    main()
