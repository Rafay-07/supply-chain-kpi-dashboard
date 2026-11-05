"""Check each KPI against numbers worked out by hand on a tiny dataset."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import kpi  # noqa: E402


@pytest.fixture
def conn(tmp_path):
    (tmp_path / "orders.csv").write_text(
        "order_id,order_date,region,channel,sku,cases_ordered,requested_date,delivered_date,cases_delivered,price_per_case\n"
        "1,2026-07-01,Ontario,Retail,A,100,2026-07-03,2026-07-03,100,10\n"   # on time, in full
        "2,2026-07-01,Ontario,Retail,A,100,2026-07-03,2026-07-04,100,10\n"   # late
        "3,2026-07-02,Quebec,On-Premise,A,100,2026-07-04,2026-07-04,80,10\n"  # short
        "4,2026-07-02,Quebec,Retail,A,100,2026-07-04,2026-07-03,100,10\n")   # early, in full
    (tmp_path / "inventory.csv").write_text(
        "snapshot_date,dc,sku,cases_on_hand\n2026-07-02,Mississauga DC,A,500\n2026-07-02,Montreal DC,A,20\n")
    (tmp_path / "line_runs.csv").write_text(
        "run_date,line,planned_minutes,run_minutes,cases_produced,cases_rejected,ideal_cases_per_hour\n"
        "2026-07-01,L1,100,80,100,10,100\n")
    return kpi.load(str(tmp_path))


def test_otif(conn):
    assert kpi.otif(conn) == pytest.approx(0.5)          # orders 1 and 4


def test_fill_rate(conn):
    assert kpi.fill_rate(conn) == pytest.approx(380 / 400)


def test_avg_cycle_days(conn):
    assert kpi.avg_cycle_days(conn) == pytest.approx((2 + 3 + 2 + 1) / 4)


def test_revenue_by_region(conn):
    assert kpi.revenue_by(conn, "region") == [("Ontario", 2000.0), ("Quebec", 1800.0)]


def test_revenue_rejects_bad_column(conn):
    with pytest.raises(ValueError):
        kpi.revenue_by(conn, "price; DROP TABLE orders")


def test_oee(conn):
    line, a, p, q, score = kpi.oee(conn)[0]
    assert a == pytest.approx(0.8)                       # 80 of 100 minutes
    assert p == pytest.approx(100 / (80 / 60 * 100))     # 100 cases vs 133.3 ideal
    assert q == pytest.approx(0.9)                       # 10 of 100 rejected
    assert score == pytest.approx(a * p * q)


def test_days_of_supply_flags_low_stock(conn):
    # Quebec demand: 200 cases over a 28-day window = 7.14/day, so 20 cases is 2.8 days
    flags = kpi.exceptions(conn)
    assert any("Montreal DC" in f for f in flags)
    assert not any("Mississauga DC" in f for f in flags)
