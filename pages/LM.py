
import os
import time
import json
import shutil
import numpy as np
import pandas as pd
import streamlit as st

from collections import OrderedDict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from mplsoccer import VerticalPitch


# =========================
# Selenium (Chromium) setup
# =========================

def make_driver():
    chrome_options = ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # Nastavení cesty k binárce pro různá prostředí
    for bin_path in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
        if os.path.exists(bin_path):
            chrome_options.binary_location = bin_path
            break

    # chromedriver z PATH (Streamlit Cloud: balík chromium-driver)
    chromedriver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
    service = ChromeService(executable_path=chromedriver_path)

    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


# =========================
# Stažení a rozparsování dat (bez převodu souřadnic, WS 0–100)
# =========================

def get_events_df_from_url_with_qualifiers(match_url: str) -> pd.DataFrame:
    import time
    import json
    import pandas as pd
    import numpy as np
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from collections import OrderedDict
    import shutil
    import os

    def make_driver():
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless=new")  # Nový headless režim
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        
        # Anti-detekce nastavení
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Nastavení cesty k binárce pro různá prostředí
        for bin_path in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
            if os.path.exists(bin_path):
                chrome_options.binary_location = bin_path
                break

        # chromedriver z PATH
        chromedriver_path = shutil.which("chromedriver") or "/usr/bin/chromedriver"
        service = ChromeService(executable_path=chromedriver_path)

        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Skrytí webdriver vlastností
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver

    driver = make_driver()

    try:
        print(f"🌐 Načítám URL pomocí Chrome: {match_url}")
        
        # Pokus o načtení stránky s retry logikou
        max_retries = 3
        for attempt in range(max_retries):
            try:
                driver.get(match_url)
                print(f"✅ URL načtena, pokus {attempt + 1}")
                break
            except WebDriverException as e:
                print(f"⚠️ Pokus {attempt + 1}/{max_retries} neúspěšný: {e}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(3)
        
        # Delší čekání pro Chrome
        print("⏳ Čekám na plné načtení stránky...")
        time.sleep(10)
        
        # Zkusíme počkat na různé indikátory načtení
        wait = WebDriverWait(driver, 20)
        
        # 1. Počkáme na document.readyState
        wait.until(lambda driver: driver.execute_script("return document.readyState") == "complete")
        print("✅ Document ready state = complete")
        
        # 2. Počkáme na layout-wrapper
        try:
            wait.until(EC.presence_of_element_located((By.ID, "layout-wrapper")))
            print("✅ Layout-wrapper nalezen")
        except TimeoutException:
            print("⚠️ Layout-wrapper nenalezen v časovém limitu")
        
        # 3. Počkáme na první script tag s obsahem
        try:
            wait.until(lambda driver: len(driver.find_elements(By.TAG_NAME, "script")) > 0)
            print("✅ Script tagy nalezeny")
        except TimeoutException:
            print("⚠️ Script tagy nenalezeny")
        
        # Dodatečné čekání pro jistotu
        time.sleep(5)
        
        # Debugging: vypíšeme informace o stránce
        print(f"🔍 Aktuální URL: {driver.current_url}")
        print(f"🔍 Page title: {driver.title}")
        print(f"🔍 Page source length: {len(driver.page_source)}")
        
        # Zkusíme různé strategie pro nalezení dat
        target_script_content = None
        
        # Strategie 1: Původní XPath s čekáním
        try:
            print("🔍 Strategie 1: Hledám pomocí původního XPath...")
            script_element = wait.until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="layout-wrapper"]/script[1]'))
            )
            content = script_element.get_attribute('innerHTML')
            if content and 'matchId' in content:
                print("✅ Data nalezena pomocí původního XPath")
                target_script_content = content
        except TimeoutException:
            print("❌ Původní XPath selhal")
        
        # Strategie 2: Hledání ve všech script tazích
        if not target_script_content:
            print("🔍 Strategie 2: Prohledávám všechny script tagy...")
            try:
                all_scripts = driver.find_elements(By.TAG_NAME, "script")
                print(f"📊 Nalezeno {len(all_scripts)} script tagů")
                
                for i, script in enumerate(all_scripts):
                    try:
                        content = script.get_attribute('innerHTML')
                        if content and 'matchId' in content and len(content) > 1000:
                            print(f"✅ Script s matchId nalezen na pozici {i}")
                            target_script_content = content
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"❌ Chyba při hledání script tagů: {e}")
        
        # Strategie 3: Alternativní XPath selektory
        if not target_script_content:
            print("🔍 Strategie 3: Zkouším alternativní selektory...")
            selectors_to_try = [
                '//script[contains(text(), "matchId")][1]',
                '//*[@id="layout-wrapper"]//script[contains(text(), "matchId")]',
                '//div[@id="layout-wrapper"]/script[1]',
                '//body//script[contains(text(), "matchId")][1]'
            ]
            
            for selector in selectors_to_try:
                try:
                    script_element = driver.find_element(By.XPATH, selector)
                    content = script_element.get_attribute('innerHTML')
                    if content and 'matchId' in content:
                        print(f"✅ Script nalezen pomocí selektoru: {selector}")
                        target_script_content = content
                        break
                except NoSuchElementException:
                    continue
        
        # Strategie 4: JavaScript execution pro nalezení dat
        if not target_script_content:
            print("🔍 Strategie 4: Zkouším JavaScript execution...")
            try:
                # Pokusíme se spustit JavaScript pro nalezení dat
                js_code = """
                var scripts = document.getElementsByTagName('script');
                for (var i = 0; i < scripts.length; i++) {
                    var content = scripts[i].innerHTML;
                    if (content && content.includes('matchId')) {
                        return content;
                    }
                }
                return null;
                """
                content = driver.execute_script(js_code)
                if content:
                    print("✅ Data nalezena pomocí JavaScript execution")
                    target_script_content = content
            except Exception as e:
                print(f"❌ JavaScript execution selhal: {e}")
        
        # Strategie 5: Regex v page source
        if not target_script_content:
            print("🔍 Strategie 5: Hledám v celém page source...")
            try:
                page_source = driver.page_source
                import re
                
                # Hledáme JSON objekt s matchId
                patterns = [
                    r'matchId.*?events.*?\]\s*\}\s*(?:,|\})',
                    r'\{[^{}]*matchId[^{}]*events.*?\].*?\}',
                    r'matchId[^}]*events[^}]*\]'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, page_source, re.DOTALL)
                    if match:
                        print("✅ Data nalezena pomocí regex v page source")
                        target_script_content = match.group(0)
                        break
            except Exception as e:
                print(f"❌ Regex search selhal: {e}")
        
        if not target_script_content:
            # Poslední pokus - vypíšeme část page source pro debugging
            page_preview = driver.page_source[:2000] + "..." if len(driver.page_source) > 2000 else driver.page_source
            print(f"🔍 Page source preview:\n{page_preview}")
            raise Exception("❌ Script s matchId nebyl nalezen žádnou strategií")

        # Zpracování script obsahu (stejně jako předtím)
        print("🔄 Zpracovávám script obsah...")
        script = target_script_content.strip().replace('\n', '').replace('\t', '')
        
        # Robustnější parsing
        try:
            if "matchId" not in script:
                raise ValueError("Script neobsahuje matchId")
            
            # Hledáme začátek a konec JSON dat
            start_patterns = ["matchId", "matchCenter", "{"]
            start_idx = len(script)
            for pattern in start_patterns:
                try:
                    idx = script.index(pattern)
                    if idx < start_idx:
                        start_idx = idx
                except ValueError:
                    continue
            
            if start_idx == len(script):
                raise ValueError("Nenalezen začátek JSON dat")
            
            # Hledáme konec JSON objektu
            brace_count = 0
            in_json = False
            end_idx = len(script) - 1
            
            for i in range(start_idx, len(script)):
                if script[i] == '{':
                    brace_count += 1
                    in_json = True
                elif script[i] == '}':
                    brace_count -= 1
                    if in_json and brace_count == 0:
                        end_idx = i
                        break
            
            script = script[start_idx:end_idx + 1]
            print(f"📏 Extrahovaný script má {len(script)} znaků")
            
        except (ValueError, IndexError) as e:
            print(f"❌ Chyba při parsování scriptu: {e}")
            raise

        # Parsování dat (stejně jako původně, ale s lepším error handling)
        try:
            # Pokusíme se najít čistý JSON objekt
            if script.startswith('{'):
                # Script začíná JSON objektem
                data = json.loads(script)
            else:
                # Musíme parsovat komplexnější strukturu
                parts = list(filter(None, script.split(',            ')))
                if len(parts) < 2:
                    parts = list(filter(None, script.split(',')))
                
                if len(parts) < 2:
                    # Pokusíme se najít JSON přímo
                    json_start = script.find('{')
                    if json_start == -1:
                        raise ValueError("JSON objekt nenalezen")
                    data = json.loads(script[json_start:])
                else:
                    # Původní logika
                    json_start = -1
                    for i, part in enumerate(parts):
                        if '{' in part:
                            json_start = i
                            break
                    
                    if json_start == -1:
                        raise ValueError("JSON objekt nenalezen v částech")
                        
                    metadata = json.loads(parts[json_start][parts[json_start].index('{'):])
                    
                    # Doplnění dalších dat
                    keys = [p.split(':')[0].strip() for p in parts if ':' in p]
                    values = [p.split(':', 1)[1].strip() for p in parts if ':' in p]
                    for k, v in zip(keys, values):
                        if k not in metadata:
                            try:
                                metadata[k] = json.loads(v)
                            except Exception:
                                pass
                    data = metadata

        except (json.JSONDecodeError, ValueError, IndexError) as e:
            print(f"❌ Chyba při parsování JSON: {e}")
            print(f"🔍 Script preview: {script[:500]}...")
            raise

        data = dict(OrderedDict(sorted(data.items())))

        # Zbytek zpracování je stejný jako původně...
        try:
            region = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/span[1]').text
        except NoSuchElementException:
            region = ""

        try:
            league_season_text = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text
            if ' - ' in league_season_text:
                league = league_season_text.split(' - ')[0]
                season = league_season_text.split(' - ')[1]
            else:
                league = league_season_text
                season = ""
        except NoSuchElementException:
            league = ""
            season = ""

        home_team = data.get('home', {}).get('name', 'Unknown Home')
        away_team = data.get('away', {}).get('name', 'Unknown Away')
        score = data.get('score', 'N/A')
        date = data.get('startDate', '').split('T')[0] if data.get('startDate') else 'N/A'

        print(f"📥 Zápas: {home_team} vs {away_team} ({score})")
        print(f"📆 Datum: {date} | Liga: {league} ({season}) | Region: {region}")

        # Vytvoření DataFrame
        events = data.get('events', [])
        if not events:
            print("⚠️ Žádné události nenalezeny")
            return pd.DataFrame()

        # Přidání meta informací
        for e in events:
            e.update({
                'matchId': data.get('matchId'),
                'startDate': data.get('startDate'),
                'startTime': data.get('startTime'),
                'score': data.get('score'),
                'ftScore': data.get('ftScore'),
                'htScore': data.get('htScore'),
                'etScore': data.get('etScore'),
                'venueName': data.get('venueName'),
                'maxMinute': data.get('maxMinute')
            })

        events_df = pd.DataFrame(events)
        print(f"📊 Načteno {len(events_df)} událostí")

        # Zpracování sloupců
        if 'period' in events_df:
            events_df['period'] = pd.json_normalize(events_df['period'])['displayName']
        if 'type' in events_df:
            events_df['type'] = pd.json_normalize(events_df['type'])['displayName']
        if 'outcomeType' in events_df:
            events_df['outcomeType'] = pd.json_normalize(events_df['outcomeType'])['displayName']

        try:
            if 'cardType' in events_df:
                x = events_df['cardType'].fillna({i: {} for i in events_df.index})
                events_df['cardType'] = pd.json_normalize(x)['displayName'].fillna(False)
            else:
                events_df['cardType'] = False
        except Exception:
            events_df['cardType'] = False

        if 'playerId' in events_df:
            events_df['playerId'] = events_df['playerId'].fillna(-1).astype(int).astype(str)
            events_df['playerName'] = events_df['playerId'].map(data.get('playerIdNameDictionary', {}))

        # Team mapping
        home_team_id = data.get('home', {}).get('teamId')
        away_team_id = data.get('away', {}).get('teamId')
        
        if home_team_id and away_team_id:
            events_df['h_a'] = events_df['teamId'].map({home_team_id: 'h', away_team_id: 'a'})
            events_df['squadName'] = events_df['teamId'].map({
                home_team_id: home_team,
                away_team_id: away_team
            })

        # Rozbalení qualifiers
        def parse_qualifiers(qual_list):
            if not isinstance(qual_list, list):
                return {}
            return {q["type"]["displayName"]: q.get("value", True) for q in qual_list}

        if 'qualifiers' in events_df:
            qualifiers_df = pd.json_normalize(events_df['qualifiers'].apply(parse_qualifiers))
            events_df = pd.concat([events_df.drop(columns=['qualifiers']), qualifiers_df], axis=1)

        # Odvozené sloupce
        if 'outcomeType' in events_df:
            events_df['result'] = np.where(events_df['outcomeType'].str.lower() == 'successful',
                                         'SUCCESS',
                                         np.where(events_df['outcomeType'].isna(), np.nan, 'FAIL'))

        if 'x' in events_df:
            events_df['final_third_start'] = (events_df['x'] <= 66.7).astype(int)
        if 'endX' in events_df:
            events_df['final_third_end'] = (events_df['endX'] > 66.7).astype(int)

        if {'x', 'y'}.issubset(events_df.columns):
            events_df['penaltyBox'] = ((events_df['x'] >= 84.3) & 
                                     (np.abs(events_df['y'] - 50) <= 29.65)).astype(int)
        if {'endX', 'endY'}.issubset(events_df.columns):
            events_df['penaltyBox_end'] = ((events_df['endX'] >= 84.3) & 
                                         (np.abs(events_df['endY'] - 50) <= 29.65)).astype(int)

        print("✅ Data úspěšně zpracována pomocí Chrome")
        return events_df

    except Exception as e:
        print(f"❌ Celková chyba: {e}")
        try:
            print(f"🔍 Aktuální URL: {driver.current_url}")
            print(f"🔍 Page title: {driver.title}")
        except:
            pass
        raise
        
    finally:
        driver.quit()


# =========================
# Vizualizace
# =========================

def plot_final_third_entries(ax, df_team, facecolor="#161B2E", textcolor="w"):
    pitch = VerticalPitch(pitch_type="custom", pitch_length=100, pitch_width=100,
                          pitch_color="w",
                          line_color=textcolor, linewidth=2, line_zorder=2, line_alpha=0.2, goal_alpha=0.2)
    pitch.draw(ax=ax)
    ax.set_facecolor(facecolor)

    mask = (
        df_team["type"].isin(["Pass", "Dribble"])) & \
        (df_team["result"] == "SUCCESS") & \
        (df_team["x"] <= 66.7) & (df_team["endX"] > 66.7)
    sub = df_team.loc[mask].copy()

    if sub.empty:
        ax.text(50, 50, "Žádné vstupy do finální třetiny", ha="center", va="center", color=textcolor)
        return

    pitch.lines(sub["x"], sub["y"],
                sub["endX"], sub["endY"],
                linestyle="--", ax=ax, lw=1.8, zorder=2)
    pitch.scatter(sub["endX"], sub["endY"], zorder=3,
                  s=40, edgecolors="#000000", marker="o", ax=ax)

    # Zóny 1–5 podle Y (0–20, 20–40, ..., 80–100)
    def zone_from_y(y):
        if 0 <= y <= 20:
            return "Zone 1"
        if 20 < y <= 40:
            return "Zone 2"
        if 40 < y <= 60:
            return "Zone 3"
        if 60 < y <= 80:
            return "Zone 4"
        if 80 < y <= 100:
            return "Zone 5"
        return np.nan

    sub = sub[sub["endX"] > 66.7].copy()
    sub["Fifth"] = sub["endY"].apply(zone_from_y)
    # gpa z PXT_PASS pokud existuje
    if "PXT_PASS" not in sub.columns:
        sub["PXT_PASS"] = np.nan

    fifth = sub.groupby("Fifth", dropna=True).agg(
        counts=("type", "count"),
        gpa=("PXT_PASS", "mean")
    ).reset_index()

    if fifth.empty:
        return

    fifth["percentage"] = fifth["counts"] / fifth["counts"].sum() * 100.0

    bar_widths = [12, 8, 12, 8, 12]
    x_pos = [80, 74, 68, 62, 56]

    vmin = np.nanmin(fifth["gpa"].values) if not np.all(np.isnan(fifth["gpa"].values)) else 0.0
    vmax = np.nanmax(fifth["gpa"].values) if not np.all(np.isnan(fifth["gpa"].values)) else 1.0
    cmap = LinearSegmentedColormap.from_list("", [facecolor, "#d00000"], N=5000)
    norm = Normalize(vmin=vmin, vmax=vmax)

    order = ["Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"]
    fifth = fifth.set_index("Fifth").reindex(order).fillna(0).reset_index()

    ax.bar(x_pos,
           -fifth["percentage"],
           width=bar_widths,
           bottom=66.7,
           align="center",
           color=cmap(norm(fifth["gpa"])),
           alpha=0.5,
           zorder=3,
           ec="gray",
           linewidth=2)

    counts = list(fifth["counts"])
    for x, height, val in zip(x_pos, -fifth["percentage"] + 66.7, counts):
        ax.text(x, height, str(int(val)), ha="center", va="bottom", fontsize=12, color=textcolor, alpha=1)

    ax.axhline(y=66.7, c=textcolor, ls="-", lw=3, alpha=0.3, zorder=5)


def plot_box_entries_heatmap(ax, df_team, facecolor="#161B2E", textcolor="w"):
    pitch = VerticalPitch(pitch_type="custom", pitch_length=100, pitch_width=100,
                          pitch_color=facecolor,
                          pad_bottom=-30,
                          line_color=textcolor, linewidth=2, line_zorder=2, line_alpha=0.2, goal_alpha=0.2)
    pitch.draw(ax=ax)
    ax.set_facecolor(facecolor)

    mask = (
        df_team["type"].isin(["Pass", "Dribble"])) & \
        (df_team["result"] == "SUCCESS") & \
        (df_team["penaltyBox"] != 1) & (df_team["penaltyBox_end"] == 1)
    sub = df_team.loc[mask].copy()

    if sub.empty:
        ax.text(50, 50, "Žádné vstupy do vápna", ha="center", va="center", color=textcolor)
        return

    pitch.lines(sub["x"], sub["y"],
                sub["endX"], sub["endY"],
                linestyle="-", ax=ax, lw=2.5, zorder=2)
    pitch.scatter(sub["endX"], sub["endY"], zorder=3,
                  s=70, edgecolors="#000000", marker="o", ax=ax)

    # Heatmapa startů jen na soupeřově polovině (x >= 50)
    filt = sub[sub["x"] >= 50]
    if not filt.empty:
        bin_stat = pitch.bin_statistic_positional(
            filt["x"], filt["y"],
            statistic="count", positional="full", normalize=False
        )
        cmap = LinearSegmentedColormap.from_list("", [facecolor, "#d00000"], N=1000)
        pitch.heatmap_positional(bin_stat, ax=ax, cmap=cmap, edgecolors=None, zorder=1)
        pitch.label_heatmap(bin_stat, color=textcolor, fontsize=14, ax=ax, ha="center", va="center",
                            str_format="{:.0F}", exclude_zeros=True)


# =========================
# Streamlit UI
# =========================

st.set_page_config(page_title="WhoScored → Entries Viz (Chromium, bez převodu)", layout="wide")
st.title("Vstupy do F3 a do vápna – WhoScored scraper → vizualizace (Chromium, bez převodu souřadnic)")

default_url = "https://1xbet.whoscored.com/matches/1874065/live/international-world-cup-qualification-uefa-2025-2026-montenegro-czechia"
match_url = st.text_input("Vlož URL zápasu z 1xbet.whoscored.com", value=default_url)

col_go, col_info = st.columns([1, 3])
with col_go:
    go = st.button("Načíst a vykreslit", type="primary")
with col_info:
    st.caption("Appka používá Chromium + chromedriver a **nepřevádí** souřadnice (pracuje s WS 0–100). Pokud běžíš ve Streamlit Cloud, přidej `packages.txt` s `chromium` a `chromium-driver`.")

if go and match_url:
    with st.spinner("Stahuji a zpracovávám data…"):
        try:
            events_df = get_events_df_from_url_with_qualifiers(match_url)
        except Exception as e:
            st.error(f"Chyba při načítání: {e}")
            st.stop()

    if events_df.empty:
        st.warning("Pro tento zápas se nepodařilo načíst žádné události.")
        st.stop()

    # Meta
    try:
        home_tid = int(events_df.loc[events_df['h_a'] == 'h', 'teamId'].iloc[0])
        away_tid = int(events_df.loc[events_df['h_a'] == 'a', 'teamId'].iloc[0])
        home = events_df.loc[events_df['teamId'] == home_tid, 'squadName'].iloc[0]
        away = events_df.loc[events_df['teamId'] == away_tid, 'squadName'].iloc[0]
    except Exception:
        # fallback
        home = 'Home'
        away = 'Away'
        home_tid = events_df['teamId'].unique()[0]
        away_tid = events_df['teamId'].unique()[1] if len(events_df['teamId'].unique()) > 1 else home_tid

    st.subheader(f"{home} vs {away}")

    # Vlevo preferuj teamId 349, jinak domácí
    preferred_left_tid = 349
    if preferred_left_tid in (home_tid, away_tid):
        left_tid = preferred_left_tid
        right_tid = away_tid if left_tid == home_tid else home_tid
    else:
        left_tid, right_tid = home_tid, away_tid

    team_map = {home_tid: home, away_tid: away}
    left_name = team_map.get(left_tid, "Tým A")
    right_name = team_map.get(right_tid, "Tým B")

    st.write(f"Vlevo: **{left_name}** (teamId {left_tid}), vpravo: **{right_name}** (teamId {right_tid})")

    left_df = events_df[events_df["teamId"] == left_tid].copy()
    right_df = events_df[events_df["teamId"] == right_tid].copy()

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"### {left_name}")
        fig1, ax1 = plt.subplots(figsize=(6, 4))
        plot_final_third_entries(ax1, left_df)
        st.pyplot(fig1, clear_figure=True)

        fig2, ax2 = plt.subplots(figsize=(6, 4))
        plot_box_entries_heatmap(ax2, left_df)
        st.pyplot(fig2, clear_figure=True)

    with c2:
        st.markdown(f"### {right_name}")
        fig3, ax3 = plt.subplots(figsize=(6, 4))
        plot_final_third_entries(ax3, right_df)
        st.pyplot(fig3, clear_figure=True)

        fig4, ax4 = plt.subplots(figsize=(6, 4))
        plot_box_entries_heatmap(ax4, right_df)
        st.pyplot(fig4, clear_figure=True)

    # Export CSV
    csv_bytes = events_df.to_csv(index=False).encode("utf-8")
    st.download_button("Stáhnout events.csv", data=csv_bytes, file_name="events.csv", mime="text/csv")
else:
    st.info("Zadej URL a klikni na **Načíst a vykreslit**.")


