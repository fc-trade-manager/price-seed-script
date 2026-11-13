# Simulated Price Generator

[English](README.md) · [Português](README.pt-BR.md)

A single script (no dependencies) that creates **fictional price history** for FC Trade Manager, so the charts (24h / 7d / 30d) and the price alerts have data from day one. It reads the `cards.csv` the backend imports and writes a `.sql` file.

> All prices are fictional and meant for development and demos only. This project is not affiliated with or endorsed by EA. The documentation base was generated with Claude.

## Contents

1. [Quick start](#quick-start)
2. [What it generates](#what-it-generates)
3. [How the price is calculated](#how-the-price-is-calculated)
4. [Global settings](#global-settings)
5. [Tuning a specific card](#tuning-a-specific-card)
6. [Recipes](#recipes)
7. [Troubleshooting](#troubleshooting)
8. [Limitations](#limitations)

## Quick start

Requirements: Python 3.9 or newer (tested with 3.13), and the backend must have run at least once so the `Cards` table is filled.

**1. Generate the SQL**

```powershell
python seed_prices.py path\to\cards.csv
```

This creates `price_seed.sql` in the current folder. To pick another name: `python seed_prices.py cards.csv output.sql`.

**2. Import into PostgreSQL (Docker)**

Find the container name with `docker ps`, then:

```powershell
# PowerShell ("<" does not work there; pipe the file instead)
Get-Content price_seed.sql -Raw | docker exec -i <container> psql -U <user> -d <database>
```

```bash
# bash / Git Bash / Linux / macOS
docker exec -i <container> psql -U <user> -d <database> < price_seed.sql
```

**3. Check**

```sql
SELECT COUNT(*) FROM "PriceSnapshots" WHERE "Source" = 'simulated';
```

With 156 cards and 30 days the result is `112476` (721 points per card). Then open Swagger and call a card's price history (`24h`, `7d`, `30d`).

**Regenerating**: run the script and import as often as you like. The SQL first deletes only the rows with `Source = 'simulated'` (manual prices are never touched) and inserts the new history, with the window moved to "now".

## What it generates

| Item | Value |
|---|---|
| Window | last 30 days (`DAYS`), ending at the current full hour (UTC) |
| Frequency | one price per hour |
| Table | `"PriceSnapshots"` (`Id`, `CardId`, `Price`, `Source`, `RecordedAt`) |
| `Source` | `simulated` |
| Limits | price between 200 and 15,000,000 (backend rule) |
| Ids | fixed (derived from `ExternalRef` + hour): importing the same file twice does not duplicate rows |

**Why `ExternalRef` exists.** The backend creates each card's `Id` (a GUID) while importing `cards.csv`, so it differs in every database. `ExternalRef` is the stable key that lives in the CSV, and the generated SQL joins on it to find the card. That is why the same file works on any database, and why `ExternalRef` must be **unique** per card (the script refuses a CSV with duplicates).

## How the price is calculated

Each card has its own random generator (derived from `SEED` + `ExternalRef`): the same seed gives the same curve shape, and adding cards to the CSV does not change the others. The price combines five ingredients, multiplied together:

1. **Base price** from `2000 × 1.4^(overall − 80) × rarity`. Each overall point multiplies the price by 1.4. Examples (Gold Rare): 80 ≈ 2,000 · 85 ≈ 10,800 · 90 ≈ 57,900 · 95 ≈ 311,000 · 98 ≈ 854,000. Rarity multipliers: Gold Common 0.6 · Hero 1.6 · Icon 2.2 · anything else 1.0.
2. **Monthly trend**: each card drifts up or down by a random percentage (standard deviation of about 6% over 30 days), in a straight line.
3. **Friday rise** (only cards with overall ≥ 86): the price jumps 8% on Friday at 00:00 UTC and falls in a straight line back to normal on Monday at 00:00 UTC (72 hours later). Friday 00:00 UTC is Thursday 21:00 in Brasília.
4. **Smooth noise**: a wobble with "memory" (about 1 day) that is always pulled back to the center instead of drifting away forever. The price usually stays within about 2.5% of the center.
5. **Rounding**: the final price is clamped to 200–15,000,000 and rounded to **3 significant digits** (1,234 becomes 1,230; 961,234 becomes 961,000). This keeps curves smooth; the real market uses steps (50, 100, 250...), but the backend does not require them.

Because the ingredients multiply, "+8%" really is 8% of the price at any level.

## Global settings

At the top of `seed_prices.py`:

| Constant | What it does | Default |
|---|---|---|
| `DAYS` | history length in days | `30` |
| `SEED` | changes the "draw" for all cards | `42` |
| `BOOST_MIN_OVERALL` | minimum overall for the Friday rise (use `999` to turn it off for everyone) | `86` |
| `BOOST_PEAK` | size of the Friday rise | `0.08` (+8%) |
| `RARITY` | multiplier per rarity (lowercase); missing ones count as 1.0 | see the file |

Inside the `history` function there are numbers you can also change:

| Snippet | What it does |
|---|---|
| `2000 * 1.4 ** (overall - 80)` | price of an overall-80 card (`2000`) and how much each overall point adds (`1.4`) |
| `rng.gauss(0, 0.06)` | size of the random monthly trend (larger = cards differ more from each other) |
| `0.97` | noise "memory" (closer to 1 = slower, longer swings) |
| `0.006` | noise strength (larger = more nervous chart) |
| `72` | duration of the Friday rise, in hours |

After changing `DAYS`, `SEED` or any value, generate and import again. The same `SEED` keeps the noise and trend shape; only the Friday sawtooth moves, depending on the day you generate.

## Tuning a specific card

To give one card its own behavior (price level, trend, nervousness, or ending at an exact price), use the `OVERRIDES` dictionary at the top of the script. The key is the card's `ExternalRef`.

**Step by step**

1. **Find the `ExternalRef`** in `cards.csv` (last column). In PowerShell:

   ```powershell
   Select-String -Path cards.csv -Pattern "Mbapp" -Encoding utf8
   ```

   Or open the CSV in VS Code or Excel and search for the name.

2. **Edit `OVERRIDES`** at the top of `seed_prices.py`:

   ```python
   OVERRIDES = {
       "cards-030": {"base": 40000, "trend": 0.25, "noise": 2, "boost": False, "end": 54000},
       "cards-001": {"trend": 0.15, "noise": 0.5},
   }
   ```

3. **Generate and import again** (see [Quick start](#quick-start)).

Only the listed cards change; every other card stays exactly as it was.

**The options** (all optional; use only what you need):

| Option | What it does | Example |
|---|---|---|
| `base` | approximate price **at the start** of the window (30 days ago); replaces the overall/rarity formula | `"base": 40000` |
| `trend` | total change over the period, as a fraction: `0.25` ends ~25% above the start, `-0.3` ends 30% below. Replaces the random trend. Must be greater than `-1` | `"trend": 0.25` |
| `noise` | multiplier for the wobble: `0` = smooth line, `1` = normal, `2` or `3` = very nervous | `"noise": 2` |
| `boost` | `False` turns off the Friday rise for this card | `"boost": False` |
| `end` | the **current** price: over the last 48 hours the curve runs in a straight line to this value | `"end": 54000` |

**About `end`**: it pins the *last* point, which is what the API returns as the current price and what the alert service compares with the targets. Anything earlier only changes in the last 48 hours, so the long history keeps the shape that trend and noise gave it.

**Typo protection**: an `ExternalRef` that is not in the CSV, an unknown option (for example `"endd"`), or a `trend` less than or equal to `-1` stops the script with a clear message instead of being silently ignored.

## Recipes

| I want... | Use |
|---|---|
| A very stable card | `{"noise": 0.3, "trend": 0, "boost": False}` |
| A card that gains a lot over the month | `{"trend": 0.5}` |
| A card that crashes over the month | `{"trend": -0.4}` |
| A very nervous card | `{"noise": 3}` |
| A smooth line (good for screenshots) | `{"noise": 0, "trend": 0, "boost": False}` |
| An expensive card pinned around a value | `{"base": 120000, "trend": 0, "noise": 0.5}` |
| An 86+ card **without** the Friday sawtooth | `{"boost": False}` |
| End at an exact price (alert demo) | `{"end": 54000}` |

**Demoing a buy or sell alert**

1. Pick a card, for example `cards-030`, and set an `end` **below** the buy target you will use (or **above** the sell target): `"cards-030": {"end": 54000}`.
2. Generate and import the prices.
3. In the app, add the card to the watchlist with a buy target of `55000`.
4. The alert service runs every minute, so the alert should show up within about a minute, since the latest price (54,000) is already below the target.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `INSERT 0 0` in every block | The `Cards` table is empty (run the API once) or the CSV `ExternalRef` values are not the ones in the database (the CSV changed after the database was filled: recreate the database or re-import the cards) |
| `relation "PriceSnapshots" does not exist` | Migrations were not applied yet (`dotnet ef database update`) |
| `AssertionError: OVERRIDES: ExternalRef inexistente...` | The `OVERRIDES` key does not exist in the CSV given to the script |
| `docker exec ... the input device is not a TTY` | Do not use `-t`; the command already uses only `-i` |
| PowerShell rejects `<` | Use `Get-Content ... -Raw \| docker exec -i ...` |
| Charts look like yesterday's | The script uses the current hour; generate and import again to move the window |
| A card looks too flat | There is `"noise": 0` (or a very low value) in its `OVERRIDES` |

## Limitations

- Prices are **made up**: they do not reflect the real game market nor use any EA data.
- Values do not follow the game's price steps (50, 100, 250...), on purpose, to keep charts smooth.
- The Friday rise is a demo rule, not a market measurement.
- Table and column names (`"PriceSnapshots"`, `"Cards"`, lowercase `"Source"`) follow the current backend. If the schema changes, adjust the part of the script that builds the SQL, at the end.
- The generated file is plain SQL: read it before importing if you are unsure what it does.
