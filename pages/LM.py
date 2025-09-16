import time
import json
import base64
import shutil
import numpy as np
import pandas as pd
import streamlit as st

from collections import OrderedDict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
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
    # allow perf logging
    chrome_prefs = {"download.default_directory": "/tmp"}
    chrome_options.experimental_options["prefs"] = chrome_prefs
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    # Prefer common Chromium paths
    for binary in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if shutil.which(binary):
            chrome_options.binary_location = binary
            break

    chromedriver_path = shutil.which("chromedriver") or shutil.which("chromium-driver") or "chromedriver"
    service = ChromeService(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def wait_ready(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


# =========================
# Robust data extraction
# =========================
def extract_json_from_scripts(driver):
    """Scan all <script> tags for a big JSON blob containing 'events' and 'matchId'."""
    scripts = driver.find_elements(By.TAG_NAME, "script")
    for s in scripts:
        try:
            txt = s.get_attribute("innerHTML") or ""
        except Exception:
            continue
        if ("events" not in txt) or ("matchId" not in txt):
            continue
        # Brace-matching to carve a JSON object
        n = len(txt)
        for i, ch in enumerate(txt):
            if ch != "{":
                continue
            depth = 0
            for j in range(i, n):
                if txt[j] == "{":
                    depth += 1
                elif txt[j] == "}":
                    depth -= 1
                    if depth == 0:
                        cand = txt[i:j+1]
                        if '"events"' in cand and '"matchId"' in cand:
                            try:
                                return json.loads(cand)
                            except Exception:
                                pass
                        break
    raise ValueError("JSON ve <script> nenalezen")


def extract_json_from_network(driver, collect_seconds=6):
    """Use Chrome DevTools Protocol via Selenium to capture XHR/fetch JSON bodies."""
    # Enable Network
    driver.execute_cdp_cmd("Network.enable", {})
    start = time.time()
    seen_request_ids = set()
    candidates = []

    while time.time() - start < collect_seconds:
        logs = driver.get_log("performance")
        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
            except Exception:
                continue
            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "Network.responseReceived":
                resp = params.get("response", {})
                url = resp.get("url", "")
                mime = resp.get("mimeType", "")
                req_id = params.get("requestId")
                if not req_id or req_id in seen_request_ids:
                    continue
                # Filter to JSON-ish responses from whoscored endpoints
                if ("whoscored" in url.lower()) and ("json" in mime or "javascript" in mime or "text/plain" in mime):
                    seen_request_ids.add(req_id)
                    candidates.append((req_id, url, mime))

        time.sleep(0.3)

    # Try to fetch bodies
    for req_id, url, mime in candidates:
        try:
            body_res = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
            body = body_res.get("body", "")
            if body_res.get("base64Encoded"):
                body = base64.b64decode(body).decode("utf-8", errors="ignore")
            # Some endpoints return JSON as text/plain
            # Try JSON parse directly; if fails, try to locate a JSON object with 'events'
            try:
                obj = json.loads(body)
                if isinstance(obj, dict) and "events" in obj and "matchId" in obj:
                    return obj
                # Sometimes nested under e.g. obj['matchCentreData']
                for k, v in obj.items() if isinstance(obj, dict) else []:
                    if isinstance(v, dict) and "events" in v and "matchId" in v:
                        return v
            except Exception:
                # Fallback: scan for the largest JSON object containing 'events'
                best = ""
                for idx in [i for i, ch in enumerate(body) if ch == "{"]:
                    depth = 0
                    for j in range(idx, len(body)):
                        c = body[j]
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                            if depth == 0:
                                cand = body[idx:j+1]
                                if '"events"' in cand and '"matchId"' in cand and len(cand) > len(best):
                                    best = cand
                                break
                if best:
                    try:
                        return json.loads(best)
                    except Exception:
                        pass
        except Exception:
            continue

    raise RuntimeError("Network log pro JSON s událostmi nenašel vhodné tělo odpovědi.")


def get_events_json(match_url: str):
    driver = make_driver()
    try:
        # Enable Network before navigation to capture early XHRs
        driver.execute_cdp_cmd("Network.enable", {})
        driver.get(match_url)
        wait_ready(driver, 25)
        time.sleep(2)

        # 1) Try inline scripts
        try:
            data = extract_json_from_scripts(driver)
        except Exception:
            # 2) Try network capture
            data = extract_json_from_network(driver, collect_seconds=8)

        # Supplementary info
        try:
            region = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/span[1]').text
        except NoSuchElementException:
            region = ""
        try:
            league_season = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text
            if " - " in league_season:
                league, season = league_season.split(" - ", 1)
            else:
                league, season = league_season, ""
        except NoSuchElementException:
            league, season = "", ""

    finally:
        driver.quit()

    return data, {"region": region, "league": league, "season": season}


# =========================
# Parse → DataFrame (no coordinate conversion, use WS 0..100)
# =========================
def to_events_df(data: dict, extra_meta: dict) -> (pd.DataFrame, dict):
    events = data.get("events", [])
    home = data.get("home", {}) or data.get("homeTeam", {})
    away = data.get("away", {}) or data.get("awayTeam", {})

    for e in events:
        e.update({
            "matchId": data.get("matchId"),
            "startDate": data.get("startDate"),
            "startTime": data.get("startTime"),
            "score": data.get("score"),
            "ftScore": data.get("ftScore"),
            "htScore": data.get("htScore"),
            "etScore": data.get("etScore"),
            "venueName": data.get("venueName"),
            "maxMinute": data.get("maxMinute"),
            "region": extra_meta.get("region", ""),
            "league": extra_meta.get("league", ""),
            "season": extra_meta.get("season", ""),
        })

    df = pd.DataFrame(events)
    meta = {
        "home": home,
        "away": away,
        "matchId": data.get("matchId"),
        "startDate": data.get("startDate"),
        "score": data.get("score"),
        "league": extra_meta.get("league", ""),
        "season": extra_meta.get("season", ""),
    }

    if df.empty:
        return df, meta

    # Flatten
    if "period" in df:
        df["period"] = pd.json_normalize(df["period"])["displayName"]
    if "type" in df:
        df["actionType"] = pd.json_normalize(df["type"])["displayName"]
    else:
        df["actionType"] = np.nan
    if "outcomeType" in df:
        df["outcomeType"] = pd.json_normalize(df["outcomeType"])["displayName"]
    else:
        df["outcomeType"] = np.nan

    df["result"] = np.where(df["outcomeType"].str.lower().eq("successful"), "SUCCESS",
                            np.where(df["outcomeType"].isna(), np.nan, "FAIL"))

    try:
        x = df["cardType"].fillna({i: {} for i in df.index})
        df["cardType"] = pd.json_normalize(x)["displayName"].fillna(False)
    except Exception:
        df["cardType"] = False

    # Names / teams
    df["playerId"] = df.get("playerId", pd.Series(index=df.index)).fillna(-1).astype(int).astype(str)
    id_name_map = data.get("playerIdNameDictionary", {})
    df["playerName"] = df["playerId"].map(id_name_map)

    home_tid = home.get("teamId")
    away_tid = away.get("teamId")
    df["h_a"] = df["teamId"].map({home_tid: "h", away_tid: "a"})
    team_id_to_name = {
        home_tid: home.get("name"),
        away_tid: away.get("name"),
    }
    df["squadName"] = df["teamId"].map(team_id_to_name)

    # Flags in 0..100 space
    df["final_third_start"] = (df["x"] <= 66.7).astype(int)
    df["final_third_end"] = (df["endX"] > 66.7).astype(int)
    df["penaltyBox"] = ((df["x"] >= 84.3) & (np.abs(df["y"] - 50) <= 29.65)).astype(int)
    df["penaltyBox_end"] = ((df["endX"] >= 84.3) & (np.abs(df["endY"] - 50) <= 29.65)).astype(int)

    return df, meta


# =========================
# Vizualizace (stejné jako dříve)
# =========================
def plot_final_third_entries(ax, df_team, facecolor="#161B2E", textcolor="w"):
    pitch = VerticalPitch(pitch_type="custom", pitch_length=100, pitch_width=100,
                          pitch_color="w",
                          line_color=textcolor, linewidth=2, line_zorder=2, line_alpha=0.2, goal_alpha=0.2)
    pitch.draw(ax=ax)
    ax.set_facecolor(facecolor)

    mask = (
        df_team["actionType"].isin(["Pass", "Dribble"])) & \
        (df_team["result"] == "SUCCESS") & \
        (df_team["x"] <= 66.7) & (df_team["endX"] > 66.7)
    sub = df_team.loc[mask].copy()

    pitch.lines(sub["x"], sub["y"],
                sub["endX"], sub["endY"],
                linestyle="--", ax=ax, lw=1.8, zorder=2)
    pitch.scatter(sub["endX"], sub["endY"], zorder=3,
                  s=40, edgecolors="#000000", marker="o", ax=ax)

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
    fifth = sub.groupby("Fifth", dropna=True).agg(
        counts=("actionType", "count"),
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
        df_team["actionType"].isin(["Pass", "Dribble"])) & \
        (df_team["result"] == "SUCCESS") & \
        (df_team["penaltyBox"] != 1) & (df_team["penaltyBox_end"] == 1)
    sub = df_team.loc[mask].copy()

    pitch.lines(sub["x"], sub["y"],
                sub["endX"], sub["endY"],
                linestyle="-", ax=ax, lw=2.5, zorder=2)
    pitch.scatter(sub["endX"], sub["endY"], zorder=3,
                  s=70, edgecolors="#000000", marker="o", ax=ax)

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
st.set_page_config(page_title="WhoScored → Entries Viz (Chromium + CDP)", layout="wide")
st.title("Vstupy do F3 a do vápna – WhoScored scraper → vizualizace (Chromium, bez převodu souřadnic)")

default_url = "https://1xbet.whoscored.com/matches/1874065/live/international-world-cup-qualification-uefa-2025-2026-montenegro-czechia"
match_url = st.text_input("Vlož URL zápasu z 1xbet.whoscored.com", value=default_url)

col_go, col_dbg = st.columns([1, 3])
with col_go:
    go = st.button("Načíst a vykreslit", type="primary")
with col_dbg:
    st.caption("Appka nejprve zkouší inline skripty, když selžou, chytá JSON přes Chrome DevTools (Network).")

if go and match_url:
    with st.spinner("Stahuji a zpracovávám data…"):
        try:
            raw_data, extra = get_events_json(match_url)
            events_df, meta = to_events_df(raw_data, extra)
        except Exception as e:
            st.error(f"Chyba při načítání: {e}")
            st.stop()

    if events_df.empty:
        st.warning("Pro tento zápas se nepodařilo načíst žádné události.")
        st.stop()

    home = meta.get("home", {}).get("name", "Home")
    away = meta.get("away", {}).get("name", "Away")
    home_tid = meta.get("home", {}).get("teamId")
    away_tid = meta.get("away", {}).get("teamId")

    st.subheader(f"{home} vs {away}")
    st.caption(f"Datum: {meta.get('startDate','')[:10]} | Skóre: {meta.get('score','')} | Liga: {meta.get('league','')} {meta.get('season','')}")

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

    csv_bytes = events_df.to_csv(index=False).encode("utf-8")
    st.download_button("Stáhnout events.csv", data=csv_bytes, file_name="events.csv", mime="text/csv")

    # Debug download raw JSON
    st.download_button("Stáhnout raw JSON", data=json.dumps(raw_data, ensure_ascii=False, indent=2),
                       file_name="whoscored_raw.json", mime="application/json")
else:
    st.info("Zadej URL a klikni na **Načíst a vykreslit**.")
