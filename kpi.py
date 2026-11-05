"""Load the CSV data into SQLite and calculate supply chain and operations KPIs with SQL."""
import csv
import sqlite3

TABLES = {
    "orders": "order_id INTEGER, order_date TEXT, region TEXT, channel TEXT, sku TEXT, cases_ordered INTEGER, "
              "requested_date TEXT, delivered_date TEXT, cases_delivered INTEGER, price_per_case REAL",
    "inventory": "snapshot_date TEXT, dc TEXT, sku TEXT, cases_on_hand INTEGER",
    "line_runs": "run_date TEXT, line TEXT, planned_minutes INTEGER, run_minutes INTEGER, cases_produced INTEGER, "
                 "cases_rejected INTEGER, ideal_cases_per_hour INTEGER",
}
DC_REGION = {"Mississauga DC": "Ontario", "Montreal DC": "Quebec", "Delta DC": "West", "Halifax DC": "Atlantic"}

# Flag thresholds
LOW_DAYS_OF_SUPPLY = 7
LOW_OEE = 0.65


def load(data_dir="data"):
    conn = sqlite3.connect(":memory:")
    for table, cols in TABLES.items():
        conn.execute(f"CREATE TABLE {table} ({cols})")
        with open(f"{data_dir}/{table}.csv") as f:
            rows = list(csv.reader(f))[1:]
        marks = ",".join("?" * len(rows[0]))
        conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
    conn.execute("CREATE TABLE dc_region (dc TEXT, region TEXT)")
    conn.executemany("INSERT INTO dc_region VALUES (?, ?)", DC_REGION.items())
    return conn


def otif(conn):
    """Share of orders delivered on or before the requested date AND in full."""
    return conn.execute("""
        SELECT AVG(CASE WHEN delivered_date <= requested_date AND cases_delivered = cases_ordered
                        THEN 1.0 ELSE 0.0 END)
        FROM orders""").fetchone()[0]


def fill_rate(conn):
    """Cases delivered divided by cases ordered."""
    return conn.execute("SELECT 1.0 * SUM(cases_delivered) / SUM(cases_ordered) FROM orders").fetchone()[0]


def avg_cycle_days(conn):
    """Average days from order to delivery."""
    return conn.execute(
        "SELECT AVG(julianday(delivered_date) - julianday(order_date)) FROM orders").fetchone()[0]


def revenue_by(conn, column):
    """Delivered revenue grouped by region or channel, largest first."""
    if column not in ("region", "channel", "sku"):
        raise ValueError("column must be region, channel or sku")
    return conn.execute(f"""
        SELECT {column}, ROUND(SUM(cases_delivered * price_per_case), 2) AS revenue
        FROM orders GROUP BY {column} ORDER BY revenue DESC""").fetchall()


def weekly_otif(conn):
    """OTIF per ISO week, to show the trend."""
    return conn.execute("""
        SELECT strftime('%Y-W%W', order_date) AS week,
               ROUND(AVG(CASE WHEN delivered_date <= requested_date AND cases_delivered = cases_ordered
                              THEN 1.0 ELSE 0.0 END), 4)
        FROM orders GROUP BY week ORDER BY week""").fetchall()


def days_of_supply(conn, window_days=28):
    """Cases on hand divided by average daily demand over the last window, per DC and SKU."""
    return conn.execute("""
        WITH last_day AS (SELECT MAX(order_date) AS d FROM orders),
        demand AS (
            SELECT o.region, o.sku, SUM(o.cases_ordered) * 1.0 / ? AS daily
            FROM orders o, last_day
            WHERE julianday(last_day.d) - julianday(o.order_date) < ?
            GROUP BY o.region, o.sku)
        SELECT i.dc, i.sku, i.cases_on_hand, ROUND(d.daily, 1),
               ROUND(i.cases_on_hand / d.daily, 1) AS dos
        FROM inventory i
        JOIN dc_region r ON r.dc = i.dc
        JOIN demand d ON d.region = r.region AND d.sku = i.sku
        ORDER BY dos""", (window_days, window_days)).fetchall()


def oee(conn):
    """Overall Equipment Effectiveness per packaging line = availability x performance x quality."""
    rows = conn.execute("""
        SELECT line,
               1.0 * SUM(run_minutes) / SUM(planned_minutes) AS availability,
               SUM(cases_produced) / SUM(run_minutes / 60.0 * ideal_cases_per_hour) AS performance,
               1.0 * SUM(cases_produced - cases_rejected) / SUM(cases_produced) AS quality
        FROM line_runs GROUP BY line ORDER BY line""").fetchall()
    return [(line, a, p, q, a * p * q) for line, a, p, q in rows]


def exceptions(conn):
    """Plain-language list of items that need attention."""
    out = []
    for dc, sku, on_hand, daily, dos in days_of_supply(conn):
        if dos < LOW_DAYS_OF_SUPPLY:
            out.append(f"{dc}: {sku} has {dos} days of supply ({on_hand} cases on hand)")
    for line, a, p, q, score in oee(conn):
        if score < LOW_OEE:
            low = min((a, "availability"), (p, "performance"), (q, "quality"))[1]
            out.append(f"{line}: OEE is {score:.0%}, lowest factor is {low}")
    return out
