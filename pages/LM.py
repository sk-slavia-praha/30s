
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
    driver = make_driver()

    try:
        try:
            driver.get(match_url)
        except WebDriverException:
            driver.get(match_url)
        time.sleep(5)

        # Stejný přístup jako tvůj: první inline <script> pod #layout-wrapper
        script = driver.find_element(By.XPATH, '//*[@id="layout-wrapper"]/script[1]').get_attribute('innerHTML')
        script = script.strip().replace('\n', '').replace('\t', '')
        script = script[script.index("matchId"):script.rindex("}")]
        parts = list(filter(None, script.split(',            ')))
        metadata = json.loads(parts[1][parts[1].index('{'):])
        keys = [p.split(':')[0].strip() for p in parts]
        values = [p.split(':', 1)[1].strip() for p in parts]
        for k, v in zip(keys, values):
            if k not in metadata:
                try:
                    metadata[k] = json.loads(v)
                except Exception:
                    pass

        data = dict(OrderedDict(sorted(metadata.items())))

        # Info z breadcrumbs (nepovinné, ale užitečné)
        try:
            region = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/span[1]').text
        except Exception:
            region = ""
        try:
            ls = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text
            league = ls.split(' - ')[0] if ' - ' in ls else ls
            season = ls.split(' - ')[1] if ' - ' in ls else ""
        except Exception:
            league, season = "", ""

        home_team = data['home']['name']
        away_team = data['away']['name']
        score = data.get('score', '')
        date = (data.get('startDate') or '')[:10]

        print(f"📥 Stahuji zápas: {home_team} vs {away_team} ({score})")
        print(f"📆 Datum: {date} | Liga: {league} ({season}) | Region: {region}")

        # DataFrame
        events = data['events']
        for e in events:
            e.update({
                'matchId': data['matchId'],
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
        if events_df.empty:
            return events_df

        # Zploštění
        if 'period' in events_df:
            events_df['period'] = pd.json_normalize(events_df['period'])['displayName']
        if 'type' in events_df:
            events_df['type'] = pd.json_normalize(events_df['type'])['displayName']
        if 'outcomeType' in events_df:
            events_df['outcomeType'] = pd.json_normalize(events_df['outcomeType'])['displayName']

        try:
            x = events_df['cardType'].fillna({i: {} for i in events_df.index})
            events_df['cardType'] = pd.json_normalize(x)['displayName'].fillna(False)
        except Exception:
            events_df['cardType'] = False

        # Hráči / týmy
        if 'playerId' in events_df:
            events_df['playerId'] = events_df['playerId'].fillna(-1).astype(int).astype(str)
            events_df['playerName'] = events_df['playerId'].map(data.get('playerIdNameDictionary', {}))
        events_df['h_a'] = events_df['teamId'].map({data['home']['teamId']: 'h', data['away']['teamId']: 'a'})
        events_df['squadName'] = events_df['teamId'].map({
            data['home']['teamId']: data['home']['name'],
            data['away']['teamId']: data['away']['name'],
        })

        # Rozbalení qualifiers
        def parse_qualifiers(qual_list):
            if not isinstance(qual_list, list):
                return {}
            return {q["type"]["displayName"]: q.get("value", True) for q in qual_list}
        if 'qualifiers' in events_df:
            qualifiers_df = pd.json_normalize(events_df['qualifiers'].apply(parse_qualifiers))
            events_df = pd.concat([events_df.drop(columns=['qualifiers']), qualifiers_df], axis=1)

        # --- Odvozené sloupce pro filtry (bez převodu souřadnic, WS 0–100) ---
        # SUCCESS/FAIL
        if 'outcomeType' in events_df:
            events_df['result'] = np.where(events_df['outcomeType'].str.lower() == 'successful',
                                           'SUCCESS',
                                           np.where(events_df['outcomeType'].isna(), np.nan, 'FAIL'))
        else:
            events_df['result'] = np.nan

        # Final third (poslední třetina hřiště): x z <= 66.7 do > 66.7
        events_df['final_third_start'] = (events_df['x'] <= 66.7).astype(int) if 'x' in events_df else 0
        events_df['final_third_end'] = (events_df['endX'] > 66.7).astype(int) if 'endX' in events_df else 0

        # Penalta – na útočné straně: ~ endX >= 84.3 a |endY - 50| <= 29.65
        events_df['penaltyBox'] = ((events_df['x'] >= 84.3) & (np.abs(events_df['y'] - 50) <= 29.65)).astype(int) \
                                   if {'x','y'}.issubset(events_df.columns) else 0
        events_df['penaltyBox_end'] = ((events_df['endX'] >= 84.3) & (np.abs(events_df['endY'] - 50) <= 29.65)).astype(int) \
                                       if {'endX','endY'}.issubset(events_df.columns) else 0

        return events_df

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
```


