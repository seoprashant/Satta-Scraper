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
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() in ('1', 'true', 'yes', 'y')  # Live mode unless TEST_MODE env var set
GHAZIABAD_CHART_URL = "https://sattaking-ghaziabad.com/ghaziabad-satta-king-result-chart.php"
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
        'SHRI GANESH': 'SHRI GANESH'
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
        logging.info(f"Successfully saved current month chart data to {filename}.")
    except Exception as e:
        logging.error(f"Error saving file: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)


# ==========================================
# MAIN EXECUTION
# ==========================================

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

    now_iso = datetime.now(IST_TZ).isoformat()
    chart_results = {
        "last_updated": now_iso,
        "updated_at": now_iso,
       # "source": GHAZIABAD_CHART_URL,
        "year": year,
        "month": month,
        "chart": chart
    }

    save_to_json_safe(chart_results, OUTPUT_FILE)


if __name__ == "__main__":
    main()
