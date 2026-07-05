import re
import requests
from bs4 import BeautifulSoup
import json
import random
import os
import logging
from datetime import datetime

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
OUTPUT_FILE = "monthly_charts.json"
TEST_MODE = True  # VS Code me test karne ke liye ise True rakhein. Live karne se pehle False kar dein.

# Target website ke chart links (Isme aap aur bhi games add kar sakte hain)
GAMES_CONFIG = {
    "FARIDABAD": "https://sattaking-ghaziabad.com/faridabad-satta-king-result-chart.php",
    "GHAZIABAD": "https://sattaking-ghaziabad.com/ghaziabad-satta-king-result-chart.php",
    "GALI": "https://sattaking-ghaziabad.com/gali-satta-king-result-chart.php",
    "DESAWAR": "https://sattaking-ghaziabad.com/desawar-satta-king-result-chart.php"
}

MONTHS_LIST = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

# Logging Setup
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
        logging.info("Running in TEST MODE. Generating Mock HTML for Chart.")
        # Dummy HTML jisme Date column aur Jan-Dec ke columns hain
        return '''
        <table class="chart-table">
            <tr><th>Date</th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th><th>May</th><th>Jun</th><th>Jul</th><th>Aug</th><th>Sep</th><th>Oct</th><th>Nov</th><th>Dec</th></tr>
            <tr><td>1</td><td>45</td><td>12</td><td>99</td><td>34</td><td>56</td><td>11</td><td>89</td><td></td><td></td><td></td><td></td><td></td></tr>
            <tr><td>2</td><td>23</td><td>55</td><td>78</td><td>10</td><td>44</td><td>22</td><td>Wait</td><td></td><td></td><td></td><td></td><td></td></tr>
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

def initialize_json_structure(data, year, month):
    """Ensures that the JSON has the correct Year -> Month structure."""
    if year not in data:
        data[year] = {}
    if month not in data[year]:
        data[year][month] = {}
    return data

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

    # Fallback to the current month and year if page title does not contain a valid month/year.
    now = datetime.now()
    return str(now.year), now.strftime('%B')


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
        'DELHI BAZAR ': 'DELHI BAZAR'
    }
    return mapping.get(label, label.title() if label.isupper() else label)


def parse_and_merge(html, game_name, full_data):
    """Parses the HTML table and merges data into the main dictionary."""
    soup = BeautifulSoup(html, 'html.parser')
    
    table_class = 'chart-table'
    table = soup.find('table', class_=table_class)
    
    if not table:
        logging.warning(f"Table not found for {game_name}. Check HTML class!")
        return full_data

    current_year, current_month = extract_chart_month_year(soup)
    full_data = initialize_json_structure(full_data, current_year, current_month)

    header_row = table.find('tr', class_='date-name')
    if header_row:
        headers = [cell.text.strip() for cell in header_row.find_all(['th', 'td'])]
    else:
        first_row = table.find('tr')
        headers = [cell.text.strip() for cell in first_row.find_all(['th', 'td'])] if first_row else []

    data_headers = headers[1:] if len(headers) > 1 else []
    month_headers = set(m.capitalize() for m in MONTHS_LIST)
    is_month_layout = any(h.capitalize() in month_headers for h in data_headers)

    for row in table.find_all('tr'):
        cols = row.find_all(['td', 'th'])
        if len(cols) == 0:
            continue

        first_cell = cols[0].text.strip()
        if not first_cell.isdigit():
            continue

        date_str = first_cell.zfill(2)

        for i, col in enumerate(cols[1:], start=0):
            result_value = col.text.strip()
            if not result_value or 'wait' in result_value.lower():
                result_value = 'XX'

            if i >= len(data_headers):
                continue

            if is_month_layout:
                month_name = normalize_game_label(data_headers[i])
                if month_name not in full_data[current_year]:
                    full_data[current_year][month_name] = {}
                if date_str not in full_data[current_year][month_name]:
                    full_data[current_year][month_name][date_str] = {}
                full_data[current_year][month_name][date_str][game_name] = result_value
            else:
                game_label = normalize_game_label(data_headers[i])
                if date_str not in full_data[current_year][current_month]:
                    full_data[current_year][current_month][date_str] = {}
                full_data[current_year][current_month][date_str][game_label] = result_value

    return full_data

def save_to_json_safe(data, filename):
    """Saves data atomically to prevent corruption."""
    temp_file = filename + ".tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(temp_file, filename)
        logging.info(f"Successfully saved combined chart data to {filename}.")
    except Exception as e:
        logging.error(f"Error saving file: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    logging.info("Starting Advanced Monthly Chart Scraper...")
    
    # Load existing data if file exists so we don't overwrite past years
    full_data = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                full_data = json.load(f)
        except json.JSONDecodeError:
            logging.warning("Existing JSON was corrupt. Starting fresh.")
            full_data = {}

    # Scrape each game one by one
    for game_name, url in GAMES_CONFIG.items():
        logging.info(f"Processing chart for {game_name}...")
        html_content = get_html(url)
        
        if html_content:
            full_data = parse_and_merge(html_content, game_name, full_data)
        else:
            logging.error(f"Skipping {game_name} due to fetch error.")

    # Save the final combined data
    save_to_json_safe(full_data, OUTPUT_FILE)
    
    if TEST_MODE:
        logging.info("Test Mode Run Complete. Check 'monthly_charts.json' file in your folder.")

if __name__ == "__main__":
    main()