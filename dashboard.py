"""Build the KPI report: an Excel workbook and a single-page HTML dashboard."""
import html
import os

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Font, PatternFill

import kpi

BLUE = "#1f4e79"


def build_excel(conn, path):
    """Write the workbook: a summary sheet plus OEE, days of supply and revenue sheets."""
    # A new, empty workbook. Sheets are added below and the file is saved at the end.
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    # Summary sheet: a header row, then one row per headline KPI, rounded for display.
    ws.append(["KPI", "Value"])
    ws.append(["OTIF (on time, in full)", round(kpi.otif(conn), 4)])
    ws.append(["Fill rate", round(kpi.fill_rate(conn), 4)])
    ws.append(["Average order cycle (days)", round(kpi.avg_cycle_days(conn), 2)])
    # Show OTIF and fill rate as percentages.
    for row in ws.iter_rows(min_row=2, max_row=3, min_col=2):
        row[0].number_format = "0.0%"

    # OEE sheet: raw factors with live Excel formulas, so the workbook still works if someone edits the inputs.
    ws2 = wb.create_sheet("Line OEE")
    ws2.append(["Line", "Availability", "Performance", "Quality", "OEE"])
    # Start at row 2 because row 1 is the header. The OEE column is an Excel formula.
    for i, (line, a, p, q, _) in enumerate(kpi.oee(conn), start=2):
        ws2.append([line, round(a, 4), round(p, 4), round(q, 4), f"=B{i}*C{i}*D{i}"])
        for col in "BCDE":
            ws2[f"{col}{i}"].number_format = "0.0%"
    # Shade any OEE below the threshold red.
    ws2.conditional_formatting.add(
        f"E2:E{ws2.max_row}",
        CellIsRule(operator="lessThan", formula=[str(kpi.LOW_OEE)], fill=PatternFill("solid", fgColor="F4CCCC")))

    # Days of supply sheet, also with a live formula, and red shading for low stock.
    ws3 = wb.create_sheet("Days of Supply")
    ws3.append(["DC", "SKU", "Cases on hand", "Avg daily demand", "Days of supply"])
    for i, row in enumerate(kpi.days_of_supply(conn), start=2):
        # Copy the first four values, then add a formula: cases on hand / average daily demand.
        ws3.append(list(row[:4]) + [f"=ROUND(C{i}/D{i},1)"])
    ws3.conditional_formatting.add(
        f"E2:E{ws3.max_row}",
        CellIsRule(operator="lessThan", formula=[str(kpi.LOW_DAYS_OF_SUPPLY)],
                   fill=PatternFill("solid", fgColor="F4CCCC")))

    # Revenue sheet: by region with a total, then by channel.
    ws4 = wb.create_sheet("Revenue")
    ws4.append(["Region", "Revenue"])
    for row in kpi.revenue_by(conn, "region"):
        ws4.append(list(row))
    # Total row adds up the region revenue above it.
    ws4.append(["Total", f"=SUM(B2:B{ws4.max_row})"])
    ws4.append([])
    ws4.append(["Channel", "Revenue"])
    for row in kpi.revenue_by(conn, "channel"):
        ws4.append(list(row))

    # Bold header row and readable column widths on every sheet.
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.column_dimensions["A"].width = 30
        for col in "BCDE":
            sheet.column_dimensions[col].width = 18
    # Write the finished workbook to disk.
    wb.save(path)


def bar_chart(title, rows, fmt, max_value=None):
    """Horizontal bar chart as inline SVG with a text table fallback for screen readers."""
    # Bars are scaled against max_value. Percent charts pass 1, so a full bar means 100%.
    max_value = max_value or max(v for _, v in rows)
    # Each row of the chart gets 28 pixels of height.
    height = 28 * len(rows) + 10
    bars = []
    # For each row: the label on the left, a bar scaled to the value, and the value after the bar.
    for i, (label, value) in enumerate(rows):
        y = 10 + i * 28
        # Bar width in pixels. A value equal to max_value fills 300 pixels.
        w = 300 * value / max_value
        bars.append(f'<text x="0" y="{y + 15}" font-size="13">{html.escape(str(label))}</text>'
                    f'<rect x="160" y="{y}" width="{w:.1f}" height="20" fill="{BLUE}"/>'
                    f'<text x="{165 + w:.1f}" y="{y + 15}" font-size="13">{fmt(value)}</text>')
    # The same numbers as a table, for people who cannot see the chart.
    table = "".join(f"<tr><td>{html.escape(str(l))}</td><td>{fmt(v)}</td></tr>" for l, v in rows)
    return (f'<section><h2>{title}</h2><svg role="img" aria-label="{title}" viewBox="0 0 560 {height}" '
            f'width="100%">{"".join(bars)}</svg>'
            f'<details><summary>Show data table</summary><table>{table}</table></details></section>')


def build_html(conn, path):
    """Write the one-page HTML dashboard: headline tiles, flags and four bar charts."""
    # Small formatters: 0.9 becomes 90.0%, and 1234 becomes $1,234.
    pct = lambda v: f"{v:.1%}"
    money = lambda v: f"${v:,.0f}"
    # The three headline numbers shown as tiles at the top of the page.
    tiles = [("OTIF", pct(kpi.otif(conn))), ("Fill rate", pct(kpi.fill_rate(conn))),
             ("Avg order cycle", f"{kpi.avg_cycle_days(conn):.1f} days")]
    tiles_html = "".join(f'<div class="tile"><p>{n}</p><p class="big">{v}</p></div>' for n, v in tiles)
    # html.escape stops text from the data being read as HTML.
    flags = "".join(f"<li>{html.escape(x)}</li>" for x in kpi.exceptions(conn)) or "<li>No exceptions</li>"
    weeks = kpi.weekly_otif(conn)
    # Page body: tiles, the "Needs attention" list, then four bar charts.
    body = (
        f'<div class="tiles">{tiles_html}</div>'
        f'<section><h2>Needs attention</h2><ul>{flags}</ul></section>'
        + bar_chart("OEE by packaging line", [(l, s) for l, *_, s in kpi.oee(conn)], pct, 1)
        + bar_chart("Weekly OTIF", weeks, pct, 1)
        + bar_chart("Revenue by region", kpi.revenue_by(conn, "region"), money)
        + bar_chart("Revenue by channel", kpi.revenue_by(conn, "channel"), money)
    )
    # The full page. The CSS is inline so the file works on its own. Doubled braces are literal braces in an f-string.
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supply Chain KPI Dashboard</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 1rem; color: #1a1a1a; }}
h1 {{ color: {BLUE}; }} .tiles {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
.tile {{ border: 1px solid #999; border-radius: 6px; padding: .5rem 1rem; min-width: 10rem; }}
.big {{ font-size: 1.8rem; font-weight: bold; color: {BLUE}; margin: 0; }}
section {{ margin-top: 1.5rem; }} table {{ border-collapse: collapse; }} td {{ padding: .2rem .8rem; }}
</style></head><body>
<h1>Supply Chain KPI Dashboard</h1>
<p>Synthetic data for 13 weeks of orders, inventory and packaging line runs.</p>
{body}
</body></html>"""
    with open(path, "w") as f:
        f.write(page)


def main():
    """Build the Excel report and the HTML dashboard, then print a short summary."""
    os.makedirs("output", exist_ok=True)
    # Load the CSV files into an in-memory SQLite database.
    conn = kpi.load("data")
    build_excel(conn, "output/kpi_report.xlsx")
    build_html(conn, "output/dashboard.html")
    # Print the headline numbers, then each flagged problem, in the terminal.
    print("OTIF", f"{kpi.otif(conn):.1%}", "| Fill rate", f"{kpi.fill_rate(conn):.1%}")
    for item in kpi.exceptions(conn):
        print("FLAG:", item)
    print("Wrote output/kpi_report.xlsx and output/dashboard.html")


# Run main() only when this file is run directly, not when it is imported.
if __name__ == "__main__":
    main()
