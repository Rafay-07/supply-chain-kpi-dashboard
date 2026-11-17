"""Generate a synthetic dataset for a beverage distributor.

All data is made up. It models orders, distribution centre inventory and
packaging line runs for 13 weeks so the KPI scripts have something to measure.
"""
import csv
import os
import random
from datetime import date, timedelta

# A fixed seed means the same data is produced on every run, so results can be compared.
random.seed(42)

START = date(2026, 7, 6)
DAYS = 91
REGIONS = ["Ontario", "Quebec", "West", "Atlantic"]
CHANNELS = ["Retail", "On-Premise", "E-commerce"]
DCS = {"Ontario": "Mississauga DC", "Quebec": "Montreal DC", "West": "Delta DC", "Atlantic": "Halifax DC"}
SKUS = {
    "LAG-24C": ("Lager 24 cans", 42.00),
    "LAG-12B": ("Lager 12 bottles", 24.50),
    "LGT-24C": ("Light lager 24 cans", 41.00),
    "IPA-6C": ("IPA 6 cans", 15.75),
    "SEL-12C": ("Hard seltzer 12 cans", 26.00),
    "NA-6C": ("Non-alcoholic 6 cans", 12.50),
}
LINES = {"Line 1 (cans)": 900, "Line 2 (cans)": 850, "Line 3 (bottles)": 600}  # ideal cases per hour


def write(path, header, rows):
    """Write a header row and data rows to a CSV file."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main(out="data"):
    os.makedirs(out, exist_ok=True)

    # Orders: 25 to 40 a day. Most arrive on time, and about 7% are delivered short.
    orders = []
    oid = 1000
    for d in range(DAYS):
        day = START + timedelta(days=d)
        for _ in range(random.randint(25, 40)):
            region = random.choices(REGIONS, weights=[45, 25, 20, 10])[0]
            sku = random.choice(list(SKUS))
            cases = random.randint(20, 400)
            requested = day + timedelta(days=random.choice([2, 3, 4]))
            delivered = requested + timedelta(days=random.choices([-1, 0, 1, 2], weights=[20, 62, 13, 5])[0])
            short = random.random() < 0.07
            delivered_cases = int(cases * random.uniform(0.7, 0.95)) if short else cases
            orders.append([oid, day, region, random.choice(CHANNELS), sku, cases,
                           requested, delivered, delivered_cases, SKUS[sku][1]])
            oid += 1
    write(f"{out}/orders.csv",
          ["order_id", "order_date", "region", "channel", "sku", "cases_ordered",
           "requested_date", "delivered_date", "cases_delivered", "price_per_case"], orders)

    # Inventory: one snapshot per DC and SKU on the last day, sized from recent demand.
    inventory = []
    last = START + timedelta(days=DAYS - 1)
    for region, dc in DCS.items():
        for sku in SKUS:
            recent = [o for o in orders if o[2] == region and o[4] == sku and (last - o[1]).days < 28]
            daily = sum(o[5] for o in recent) / 28
            inventory.append([last, dc, sku, int(daily * random.uniform(6, 30))])  # 6 to 30 days of stock
    write(f"{out}/inventory.csv", ["snapshot_date", "dc", "sku", "cases_on_hand"], inventory)

    # Packaging line runs: one per line per day. The bottle line is given more downtime.
    runs = []
    for d in range(DAYS):
        day = START + timedelta(days=d)
        for line, rate in LINES.items():
            planned = 960  # two 8-hour shifts
            downtime = random.randint(100, 420) if "bottles" in line else random.randint(30, 220)
            run = planned - downtime
            produced = int(run / 60 * rate * random.uniform(0.78, 0.97))
            rejects = int(produced * random.uniform(0.005, 0.03))
            runs.append([day, line, planned, run, produced, rejects, rate])
    write(f"{out}/line_runs.csv",
          ["run_date", "line", "planned_minutes", "run_minutes", "cases_produced", "cases_rejected",
           "ideal_cases_per_hour"], runs)

    print(f"Wrote {len(orders)} orders, {len(inventory)} inventory rows, {len(runs)} line runs to {out}/")


if __name__ == "__main__":
    main()
