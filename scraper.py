import requests
from bs4 import BeautifulSoup
import json
import random
import os
import re
import logging
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

# --- CONFIGURATION ---
TARGET_URL = "https://sattaking-ghaziabad.com/"
OUTPUT_FILE = "results.json"
IST_TZ = ZoneInfo('Asia/Kolkata')
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() in ('1', 'true', 'yes', 'y')  # Set via env var for CI/local toggling

# Logging setup (GitHub Actions ke liye best hai)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %I:%M:%S %p'
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

def parse_time_safe(time_str):
    """Regex use karke kisi bhi format ka time nikalta hai (e.g., '6:15PM', '06:15 PM')"""
    match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)', str(time_str).upper())
    if match:
        h, m, am_pm = match.groups()
        h, m = int(h), int(m)
        if am_pm == 'PM' and h != 12:
            h += 12
        if am_pm == 'AM' and h == 12:
            h = 0
        return datetime.now(IST_TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    return None

def should_we_scrape():
    """Smart check: Decide karta hai scrape karna hai ya nahi."""
    if not os.path.exists(OUTPUT_FILE):
        logging.info("Initial run: File not found. Must scrape.")
        return True

    try:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        ist_now = datetime.now(IST_TZ)
        
        # Subah 7 se 9 baje hamesha refresh karo (Naye din ke 'Wait' status ke liye)
        if 7 <= ist_now.hour <= 9:
            logging.info("Morning Window: Forcing scrape to refresh board.")
            return True

        for game in data.get("games", []):
            today_num = str(game.get("today-number", "")).strip().lower()

            # Agar result aa chuka hai (numbers hain), toh is game ko skip karo
            if today_num and today_num not in ["wait", "xx", "coming", ""]:
                continue
                
            time_str = game.get("game-time", "")
            game_dt = parse_time_safe(time_str)

            if game_dt:
                time_diff_hours = (ist_now - game_dt).total_seconds() / 3600
                
                # Raat 12 baje ke time issues ko fix karne ke liye
                if time_diff_hours < -12:
                    time_diff_hours += 24 

                # Agar time ho chuka hai (0) aur pichle 5 ghante ke andar hai
                if 0 <= time_diff_hours <= 5:
                    logging.info(f"Time matched for '{game.get('game-name')}' (Diff: {time_diff_hours:.2f} hrs). Must scrape.")
                    return True
            else:
                logging.warning(f"Could not parse time '{time_str}' for {game.get('game-name')}. Forcing scrape to be safe.")
                return True

        logging.info("No games pending for current time. Sleeping.")
        return False

    except Exception as e:
        logging.error(f"Error reading JSON for logic: {e}. Defaulting to scrape.")
        return True

def get_html(url):
    """HTML fetch with error handling."""
    if TEST_MODE:
        logging.info("Running in TEST MODE with mock HTML.")
        return '''
        <div class="game-box">
            <h3 class="name">FARIDABAD</h3>
            <span class="time">06:15 PM</span>
            <a class="record" href="/faridabad-chart">Chart</a>
            <div class="yesterday">45</div>
            <div class="today">Wait</div>
        </div>
        '''
        
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Network Error: {e}")
        return None

def extract_results(html):
    """Safely extracts data from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    now_iso = datetime.now(IST_TZ).isoformat()
    results = {
        "last_updated": now_iso,
        "updated_at": now_iso,
        # "source": TARGET_URL,
        "games": []
    }
    
    # =================================================================
    # UPDATE THESE CLASSES BASED ON ACTUAL WEBSITE INSPECT ELEMENT
    # =================================================================
    # Test Mode ke dummy data ke liye classes set kiye hain.
    # Live site parser uses actual table rows and td classes.
    container_class = 'game-box' if TEST_MODE else 'game-result'
    
    game_containers = soup.find_all('tr', class_=container_class)
    
    for container in game_containers:
        try:
            # Helper function to safely extract text
            def safe_get_text(selector, class_name, default=""):
                elem = container.find(selector, class_=class_name)
                return elem.text.strip() if elem else default

            name_cls = 'name' if TEST_MODE else 'game-name'
            time_cls = 'time' if TEST_MODE else 'game-time'
            yest_cls = 'yesterday' if TEST_MODE else 'yesterday-number'
            today_cls = 'today' if TEST_MODE else 'today-number'

            game_name = safe_get_text('h3', name_cls, "Unknown")
            game_time = safe_get_text('h3', time_cls, "N/A").replace('at ', '').strip()
            yesterday_num = safe_get_text('td', yest_cls, "XX")
            today_num = safe_get_text('td', today_cls, "Wait")

            # Extract Link
            link_elem = container.find('a') if TEST_MODE else container.find('a', href=True)
            game_link = link_elem['href'].strip() if link_elem and link_elem.has_attr('href') else "No Link"
            
            if game_link and not game_link.startswith('http'):
                game_link = urljoin(TARGET_URL, game_link)

            results["games"].append({
                "game-name": game_name,
                "game-time": game_time,
                "game-link": game_link,
                "yesterday-number": yesterday_num,
                "today-number": today_num
            })
            
        except Exception as e:
            logging.error(f"Error parsing a container: {e}")
            continue
            
    return results

def save_to_json_safe(data, filename):
    """Atomic Save: Temp file -> Rename (Prevents data corruption)"""
    temp_file = filename + ".tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        # Replace main file with new temp file
        os.replace(temp_file, filename)
        logging.info(f"Successfully updated {len(data['games'])} games to {filename}.")
    except Exception as e:
        logging.error(f"File write error: {e}")
        if os.path.exists(temp_file):
            os.remove(temp_file)

def main():
    if not TEST_MODE and not should_we_scrape():
        return

    logging.info(f"Starting scraper...")
    html_content = get_html(TARGET_URL)
    
    if html_content:
        scraped_data = extract_results(html_content)
        
        if len(scraped_data["games"]) > 0:
            save_to_json_safe(scraped_data, OUTPUT_FILE)
            if TEST_MODE:
                print(json.dumps(scraped_data, indent=2))
        else:
            logging.warning("HTML fetched, but NO games found. Please check HTML classes.")
    else:
        logging.error("Failed to retrieve HTML content.")

if __name__ == "__main__":
    main()