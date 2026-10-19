import re
import requests
from bs4 import BeautifulSoup
import json
import random
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
OUTPUT_FILE = "monthly_charts.json"
ALL_CHARTS_FILE = "all_charts.json"  # NEW: accumulates every month's chart (for dropdown)
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() in ('1', 'true', 'yes', 'y')  # Live mode unless TEST_MODE env var set
GHAZIABAD_CHART_URL = "https://sattaking-ghaziabad.com/ghaziabad-satta-king-result-chart.php"
# Patna has its own chart page on the source (not on the Ghaziabad chart) —
# scraped separately and merged in as a "PATNA" column.
PATNA_CHART_URL = "https://sattaking-ghaziabad.com/patna-satta-king-result-chart.php"
IST_TZ = ZoneInfo('Asia/Kolkata')

MONTHS_LIST = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %I:%M:%S %p'
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# ==========================================
# CORE FUNCTIONS
# ==========================================

def get_html(url):
    """Fetches HTML content with error handling."""
    if TEST_MODE:
        logging.info("Running in TEST MODE. Generating mock chart HTML.")
        return '''
        <table class="chart-table">
            <tr><th>DATE</th><th>DSWR</th><th>GZBD</th><th>FRBD</th><th>GALI</th><th>SHRI GANESH</th></tr>
            <tr><td>01</td><td>XX</td><td>69</td><td>97</td><td>78</td><td>92</td></tr>
            <tr><td>02</td><td>24</td><td>11</td><td>69</td><td>33</td><td>27</td></tr>
        </table>
        '''

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None


def normalize_game_label(label):
    if not label:
        return label

    label = label.strip().upper()
    mapping = {
        'DSWR': 'DESAWAR',
        'FRBD': 'FARIDABAD',
        'GZBD': 'GHAZIABAD',
        'GALI': 'GALI',
        'DELHI BAZAR': 'DELHI BAZAR',
        'SHRI GANESH': 'SHRI GANESH',
        'PATNA': 'PATNA'
    }
    return mapping.get(label, label.title() if label.isupper() else label)


def extract_chart_month_year(soup):
    title_text = ''
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()

    match = re.search(r'([A-Za-z]+)\s+(\d{4})', title_text)
    if match:
        month_candidate, year_candidate = match.groups()
        month_candidate = month_candidate.capitalize()
        if month_candidate in MONTHS_LIST:
            return year_candidate, month_candidate

    updated_time = soup.find('time')
    if updated_time and updated_time.has_attr('datetime'):
        try:
            dt = datetime.fromisoformat(updated_time['datetime'])
            return str(dt.year), dt.strftime('%B')
        except ValueError:
            pass

    now = datetime.now()
    return str(now.year), now.strftime('%B')


def parse_chart_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='chart-table')

    if not table:
        logging.warning("Chart table not found in HTML.")
        return None, None, {}

    rows = table.find_all('tr')
    if len(rows) < 2:
        logging.warning("Chart table does not contain enough rows.")
        return None, None, {}

    header_cells = [cell.text.strip() for cell in rows[1].find_all(['th', 'td'])]
    data_headers = [normalize_game_label(text) for text in header_cells[1:]] if len(header_cells) > 1 else []

    current_year, current_month = extract_chart_month_year(soup)
    chart_data = {}

    for row in rows[2:]:
        cols = row.find_all(['td', 'th'])
        if len(cols) < 2:
            continue

        date_text = cols[0].text.strip()
        if not date_text.isdigit():
            continue

        date_key = date_text.zfill(2)
        chart_data.setdefault(date_key, {})

        for idx, col in enumerate(cols[1:], start=0):
            if idx >= len(data_headers):
                break

            result_value = col.text.strip()
            if not result_value or 'wait' in result_value.lower():
                result_value = 'XX'

            game_label = data_headers[idx]
            chart_data[date_key][game_label] = result_value

    return current_year, current_month, chart_data


def save_to_json_safe(data, filename):
    temp_file = filename + ".tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, filename)
        logging.info(f"Successfully saved data to {filename}.")
    except Exception as e:
        logging.error(f"Error saving file: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


def month_number(month_name):
    """January -> '01', July -> '07'. Returns '00' if unknown."""
    try:
        return str(MONTHS_LIST.index(month_name.capitalize()) + 1).zfill(2)
    except ValueError:
        return "00"


def update_all_charts(year, month, chart):
    """
    NEW: Maintains an accumulating archive so the website dropdown can show
    ANY month that has ever been scraped. Structure:
    {
      "last_updated": "...",
      "months": {
        "2026-07": { "year": "2026", "month": "July", "chart": {...} },
        "2026-08": { ... },
        ...
      }
    }
    Current month ka entry har run par latest data se update hota hai;
    purane months waise ke waise safe rehte hain.
    """
    key = f"{year}-{month_number(month)}"

    existing = {}
    if os.path.exists(ALL_CHARTS_FILE):
        try:
            with open(ALL_CHARTS_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception as e:
            logging.warning(f"Could not read {ALL_CHARTS_FILE}, starting fresh: {e}")
            existing = {}

    if not isinstance(existing, dict):
        existing = {}

    months = existing.get("months", {})
    if not isinstance(months, dict):
        months = {}

    months[key] = {
        "year": year,
        "month": month,
        "chart": chart
    }

    now_iso = datetime.now(IST_TZ).isoformat()
    out = {
        "last_updated": now_iso,
        "updated_at": now_iso,
        "months": months
    }

    save_to_json_safe(out, ALL_CHARTS_FILE)
    logging.info(f"Archive updated: {len(months)} month(s) total (added/updated {key}).")


# ==========================================
# MAIN EXECUTION
# ==========================================

def merge_game_column(chart, other_chart, game):
    """Copy one game's column from other_chart into chart (per date), without
    touching the other games already in chart."""
    for date_key, games in other_chart.items():
        if game in games:
            chart.setdefault(date_key, {})[game] = games[game]
    return chart


def fetch_patna_chart(month_num=None, year=None):
    url = PATNA_CHART_URL
    if month_num and year:
        url = f"{PATNA_CHART_URL}?month={month_num}&year={year}"
    html = get_html(url)
    if not html:
        return None, None, {}
    return parse_chart_page(html)


def backfill_patna(start_key):
    """One-off: python chart_scraper.py --backfill-patna 2025-01
    Fetches every month from start_key to the current month from the source's
    Patna chart page and merges the real PATNA column into all_charts.json.
    Months not yet in the archive get all columns from the Patna page."""
    import time
    existing = {}
    if os.path.exists(ALL_CHARTS_FILE):
        with open(ALL_CHARTS_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    months = existing.get("months", {}) if isinstance(existing, dict) else {}

    y, m = (int(x) for x in start_key.split('-'))
    now = datetime.now(IST_TZ)
    while (y, m) <= (now.year, now.month):
        key = f"{y}-{m:02d}"
        py, pm, pchart = fetch_patna_chart(f"{m:02d}", str(y))
        has_data = any(v != 'XX' for day in (pchart or {}).values() for v in day.values())
        if pchart and has_data and py == str(y) and month_number(pm) == f"{m:02d}":
            if key in months and isinstance(months[key].get("chart"), dict):
                merge_game_column(months[key]["chart"], pchart, "PATNA")
            else:
                months[key] = {"year": str(y), "month": pm, "chart": pchart}
            logging.info(f"Backfilled PATNA for {key} ({len(pchart)} days)")
        else:
            logging.warning(f"Skipped {key}: source has no declared results for this month")
        m += 1
        if m > 12:
            m, y = 1, y + 1
        time.sleep(2)

    now_iso = now.isoformat()
    save_to_json_safe({"last_updated": now_iso, "updated_at": now_iso,
                       "months": dict(sorted(months.items()))}, ALL_CHARTS_FILE)


def overlay_today_from_results(chart, year, month):
    """The source chart never fills the LAST day of a month for evening games
    (it stays 'XX' forever), even though the result is declared. scraper.py
    runs first in the workflow and writes today's declared numbers to
    results.json — use those to fill today's row wherever the chart still
    shows XX. DESAWAR is skipped: the source records its 05:10 AM result on
    the previous date's row, so "today" doesn't map to today's row for it."""
    try:
        with open("results.json", "r", encoding="utf-8") as f:
            res = json.load(f)
    except Exception as e:
        logging.warning(f"results.json not readable for overlay: {e}")
        return chart
    now = datetime.now(IST_TZ)
    if str(now.year) != str(year) or now.strftime('%B') != month:
        return chart
    day = f"{now.day:02d}"
    row = chart.get(day)
    if not isinstance(row, dict):
        return chart
    for g in res.get("games", []):
        name = str(g.get("game-name", "")).strip().upper()
        val = str(g.get("today-number", "")).strip()
        if name == "DESAWAR" or name not in row:
            continue
        if row[name] == "XX" and val.isdigit() and len(val) == 2:
            row[name] = val
            logging.info(f"Overlay: filled {name} {year}-{month} {day} = {val} from results.json")
    return chart


def fill_prev_month_last_day():
    """On the 1st of a month, results.json's yesterday-number is the previous
    month's LAST day — the one day the source chart never records. Fill those
    XX cells in the archive (non-DESAWAR games only, see overlay note)."""
    import calendar
    now = datetime.now(IST_TZ)
    if now.day != 1:
        return
    try:
        with open("results.json", "r", encoding="utf-8") as f:
            res = json.load(f)
        with open(ALL_CHARTS_FILE, "r", encoding="utf-8") as f:
            archive = json.load(f)
    except Exception as e:
        logging.warning(f"Prev-month fill skipped: {e}")
        return
    py, pm = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    key = f"{py}-{pm:02d}"
    last = f"{calendar.monthrange(py, pm)[1]:02d}"
    row = archive.get("months", {}).get(key, {}).get("chart", {}).get(last)
    if not isinstance(row, dict):
        return
    changed = False
    for g in res.get("games", []):
        name = str(g.get("game-name", "")).strip().upper()
        val = str(g.get("yesterday-number", "")).strip()
        if name == "DESAWAR" or name not in row:
            continue
        if row[name] == "XX" and val.isdigit() and len(val) == 2:
            row[name] = val
            changed = True
            logging.info(f"Filled {name} {key}-{last} = {val} from yesterday-number")
    if changed:
        save_to_json_safe(archive, ALL_CHARTS_FILE)


def main():
    logging.info("Starting simplified monthly chart scraper...")

    html_content = get_html(GHAZIABAD_CHART_URL)
    if not html_content:
        logging.error("Failed to fetch the Ghaziabad chart page. Exiting.")
        return

    year, month, chart = parse_chart_page(html_content)
    if not year or not month or not chart:
        logging.error("Chart parsing failed. Exiting without writing file.")
        return

    # Merge the real PATNA column from the Patna chart page (same month only)
    py, pm, pchart = fetch_patna_chart()
    if pchart and py == year and pm == month:
        merge_game_column(chart, pchart, "PATNA")
    else:
        logging.warning("Patna chart unavailable or month mismatch — PATNA column skipped this run.")

    overlay_today_from_results(chart, year, month)

    now_iso = datetime.now(IST_TZ).isoformat()
    chart_results = {
        "last_updated": now_iso,
        "updated_at": now_iso,
       # "source": GHAZIABAD_CHART_URL,
        "year": year,
        "month": month,
        "chart": chart
    }

    # 1) Current month file (unchanged — homepage & chart page use this)
    save_to_json_safe(chart_results, OUTPUT_FILE)

    # 2) NEW: accumulate into the archive so the dropdown has history
    update_all_charts(year, month, chart)

    # 3) Month-end gap: fill previous month's last day on the 1st
    fill_prev_month_last_day()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--backfill-patna":
        backfill_patna(sys.argv[2])
    else:
        main()
