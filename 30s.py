
import time
import json
import numpy as np
import pandas as pd
import streamlit as st
import geckodriver_autoinstaller

from collections import OrderedDict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from mplsoccer import VerticalPitch


# =========================
# Selenium setup (Firefox)
# =========================
def make_driver():
    geckodriver_autoinstaller.install()
    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Firefox(options=options)
    return driver


# =========================
# Načtení a parsování zápasu z WhoScored 1xbet mirroru
# Bez převodu souřadnic: používáme WS 0..100 pro x i y
# =========================
def get_events_df_from_url_with_qualifiers(match_url: str) -> (pd.DataFrame, dict):
    driver = make_driver()
    try:
        driver.get(match_url)
    except WebDriverException:
        driver.get(match_url)
    time.sleep(5)

    script_el = driver.find_element(By.XPATH, '//*[@id="layout-wrapper"]/script[1]')
    script = script_el.get_attribute('innerHTML').strip().replace('\n', '').replace('\t', '')

    script = script[script.index("matchId"):script.rindex("}")]
    parts = list(filter(None, script.split(',            ')))
    metadata = json.loads(parts[1][parts[1].index('{'):])  # první JSON objekt
    keys = [p.split(':')[0].strip() for p in parts]
    values = [p.split(':', 1)[1].strip() for p in parts]
    for k, v in zip(keys, values):
        if k not in metadata:
            try:
                metadata[k] = json.loads(v)
            except Exception:
                pass

    data = dict(OrderedDict(sorted(metadata.items())))

    # Doplnění kontextu (nepovinné)
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

    driver.quit()

    events = data.get("events", [])
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
            "region": region,
            "league": league,
            "season": season,
        })

    df = pd.DataFrame(events)
    if df.empty:
        return df, data

    # Zploštění
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

    # Jména / týmy
    df["playerId"] = df.get("playerId", pd.Series(index=df.index)).fillna(-1).astype(int).astype(str)
    id_name_map = data.get("playerIdNameDictionary", {})
    df["playerName"] = df["playerId"].map(id_name_map)

    home_tid = data.get("home", {}).get("teamId")
    away_tid = data.get("away", {}).get("teamId")
    df["h_a"] = df["teamId"].map({home_tid: "h", away_tid: "a"})
    team_id_to_name = {
        home_tid: data.get("home", {}).get("name"),
        away_tid: data.get("away", {}).get("name"),
    }
    df["squadName"] = df["teamId"].map(team_id_to_name)

    # =========================
    # Pomocné flagy (bez převodu souřadnic, přímo v WS 0..100)
    # final third = x > 66.7 (tj. poslední třetina hřiště)
    # penalta (na útočné straně) přibližně x >= 84.3 a |y-50| <= 29.65
    # =========================
    df["final_third_start"] = (df["x"] <= 66.7).astype(int)
    df["final_third_end"] = (df["endX"] > 66.7).astype(int)

    df["penaltyBox"] = ((df["x"] >= 84.3) & (np.abs(df["y"] - 50) <= 29.65)).astype(int)
    df["penaltyBox_end"] = ((df["endX"] >= 84.3) & (np.abs(df["endY"] - 50) <= 29.65)).astype(int)

    return df, data


# =========================
# Vizualizace – Entries do poslední třetiny (x přejde přes 66.7)
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

    # Zóny ve finální třetině (5 horizontálních pásem po 20 jednotkách)
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

    # Sloupky jako overlay (umístíme je přibližně do středové oblasti hřiště)
    bar_widths = [12, 8, 12, 8, 12]
    x_pos = [80, 74, 68, 62, 56]  # z prava do leva poblíž hranice 66.7

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


# =========================
# Vizualizace – Vstupy do vápna + heatmapa startů (na soupeřově polovině)
# =========================
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
st.set_page_config(page_title="WhoScored → Entries Viz (bez převodu souřadnic)", layout="wide")
st.title("Vstupy do F3 a do vápna – WhoScored scraper → vizualizace (bez převodu souřadnic)")

default_url = "https://1xbet.whoscored.com/matches/1874065/live/international-world-cup-qualification-uefa-2025-2026-montenegro-czechia"
match_url = st.text_input("Vlož URL zápasu z 1xbet.whoscored.com", value=default_url)

col_go, col_info = st.columns([1, 3])
with col_go:
    go = st.button("Načíst a vykreslit", type="primary")
with col_info:
    st.caption("Běží bez převodu souřadnic (používá WS škálu 0–100). Ve Streamlit Cloud přidej do repa soubor packages.txt s 'firefox'.")

if go and match_url:
    with st.spinner("Stahuji a zpracovávám data…"):
        try:
            events_df, meta = get_events_df_from_url_with_qualifiers(match_url)
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

    # Výběr týmů do sloupců – vlevo preferuj teamId 349, jinak home
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
else:
    st.info("Zadej URL a klikni na **Načíst a vykreslit**.")
