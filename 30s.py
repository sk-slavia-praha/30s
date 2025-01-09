import streamlit as st
import requests
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image
from io import BytesIO
from collections import Counter
import numpy as np
from streamlit_autorefresh import st_autorefresh

# -- Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
import matplotlib.font_manager as font_manager
from matplotlib.colors import to_rgba
import matplotlib.patheffects as path_effects

# Nastavení pro běh Chromedriveru (bez GUI)
chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

# -----------------------------------------------------------------------------
# Stahování fontů (nahrazuje "!wget" příkaz)
# -----------------------------------------------------------------------------
@st.cache_data
def download_font(url, filename):
    """
    Pomocná funkce pro stažení fontu.
    Aby se nestahovalo při každém spuštění, je označeno @st.cache_data.
    """
    if not os.path.exists(filename):
        r = requests.get(url)
        with open(filename, 'wb') as f:
            f.write(r.content)

# Stáhneme Poppins fonty do lokálního adresáře
download_font(
    "https://github.com/google/fonts/blob/main/ofl/poppins/Poppins-Bold.ttf?raw=true",
    "Poppins-Bold.ttf"
)
download_font(
    "https://github.com/google/fonts/blob/main/ofl/poppins/Poppins-Regular.ttf?raw=true",
    "Poppins-Regular.ttf"
)
download_font(
    "https://github.com/google/fonts/blob/main/ofl/poppins/Poppins-Light.ttf?raw=true",
    "Poppins-Light.ttf"
)
download_font(
    "https://github.com/google/fonts/blob/main/ofl/poppins/Poppins-ExtraLight.ttf?raw=true",
    "Poppins-ExtraLight.ttf"
)

# Vytvoření FontProperties
fp_pop  = font_manager.FontProperties(fname='Poppins-Bold.ttf')
fp_pop2 = font_manager.FontProperties(fname='Poppins-Regular.ttf')
fp_pop3 = font_manager.FontProperties(fname='Poppins-Light.ttf')
fp_pop4 = font_manager.FontProperties(fname='Poppins-ExtraLight.ttf')


# -----------------------------------------------------------------------------
# Pomocné funkce
# -----------------------------------------------------------------------------

def load_logo(url):
    """
    Načte logo týmů z URL, vrátí PIL Image.
    """
    response = requests.get(url)
    if response.ok and response.headers['Content-Type'].startswith('image/'):
        return Image.open(BytesIO(response.content)).convert("RGBA")
    else:
        raise ValueError(f"URL {url} neobsahuje validní obrázek.")

def add_logo(ax, image, x, y, zoom=0.1):
    """
    Přidá logo (obrázek) do zadaného matplotlib Axes.
    """
    imagebox = OffsetImage(image, zoom=zoom)
    ab = AnnotationBbox(imagebox, (x, y), frameon=False, box_alignment=(0.5, 0.5))
    ax.add_artist(ab)

def get_rating_color(rating):
    """
    Pomocná funkce: podle ratingu vrátí barvu (string).
    """
    if rating <= 5:
        return 'red'
    elif rating <= 6:
        return 'orange'
    elif rating <= 7:
        return 'yellow'
    elif rating <= 8:
        return 'green'
    else:
        return 'darkgreen'

def clean_percentage(value):
    """
    Převede text typu '73%' na float 73.0. Pokud to není procento, zkusí float.
    """
    try:
        if isinstance(value, str) and "%" in value:
            return float(value.strip('%'))
        return float(value)
    except ValueError:
        return None

def extract_metrics_from_json(json_data, metrics):
    """
    Projde JSON se statistikami a vytáhne jen požadované metriky.
    Funkce vrací přímo DataFrame se sloupci:
      - "Metoda" (původní název metriky, např. "Total shots")
      - "Domácí"
      - "Hosté"

    Pokud statistiky neexistují nebo jsou prázdné, vrátí prázdný DataFrame.
    """

    # Vytvoříme si prázdný DF pro případ, že data nenajdeme
    df_empty = pd.DataFrame(columns=["Domácí", "Hosté"])

    # Ověříme, zda JSON obsahuje pole 'statistics' a potřebnou strukturu
    if "statistics" not in json_data:
        return df_empty
    if not json_data["statistics"]:
        return df_empty
    if "groups" not in json_data["statistics"][0]:
        return df_empty

    data_rows = []
    # Projdeme groupy a items:
    for group in json_data["statistics"][0]["groups"]:
        for item in group["statisticsItems"]:
            # Zajímáme se jen o ty item['name'], které máme v 'metrics'
            if item["name"] in metrics:
                row = {
                    "Metoda": item["name"],
                    "Domácí": item["home"],
                    "Hosté": item["away"]
                }
                data_rows.append(row)

    # Pokud nic nenajdeme, vrátíme prázdný DF
    if not data_rows:
        return df_empty

    # V opačném případě vytvoříme z data_rows DataFrame
    df = pd.DataFrame(data_rows, columns=[ "Domácí", "Hosté"])
    return df

def extract_players(data, team_type):
    players = data[team_type]['players']
    extracted_data = []
    for player_data in players:
        player = player_data['player']
        statistics = player_data.get('statistics', {})
        extracted_data.append({
            'Hráč': player.get('shortName'),
            "Č.": player.get('jerseyNumber'),
            'Pozice': player_data.get('position'),
            'Známka': statistics.get('rating'),
            'Minuty': statistics.get('minutesPlayed'),
        })
    return extracted_data
# -----------------------------------------------------------------------------
# Hlavní Streamlit aplikace
# -----------------------------------------------------------------------------
def main():
    # Nastavení auto-refresh každých 60 sekund
    count = st_autorefresh(interval=60000, limit=None, key="fizzbuzzcounter")

    st.write(f"Stránka se znovu načetla: {count}×")
    st.title("Ukázka SofaScore zápasu se Seleniem a grafikou")

    # Ukázkové vstupy
    home_team = "Chennaiyin"
    home_color = "blue"
    home_logo_url = "https://img.sofascore.com/api/v1/team/174590/image"

    away_team = "Odisha"
    away_color = "red"
    away_logo_url = "https://img.sofascore.com/api/v1/team/174592/image"

    datum = "09.01.2025"
    match_id = 13077964

    # Volitelně: umožnit uživateli zadat si i jiná data
    # match_id = st.number_input("Zadej match_id", value=12580722)
    # home_team = st.text_input("Domácí tým", "Teplice")
    # away_team = st.text_input("Hostující tým", "Slavia Praha")

    # -----------------------------------------------------------------------------
    # 1) Stažení JSONu pro momentum
    # -----------------------------------------------------------------------------
    url_momentum = f"https://www.sofascore.com/api/v1/event/{match_id}/graph"
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url_momentum)
        pre_element = driver.find_element(By.TAG_NAME, 'pre')
        json_text = pre_element.text
        data = json.loads(json_text)

        graph_points = data.get("graphPoints", [])
        momentum = pd.DataFrame(graph_points)
        # Odstraníme pauzy
        if not graph_points:
            st.warning("K dispozici nejsou žádná data pro graf momentum.")
        else:
            momentum = pd.DataFrame(graph_points)
        # Odstraníme pauzy
            momentum = momentum[~momentum['minute'].isin([45.5, 90.5])]
    finally:
        driver.quit()

    # -----------------------------------------------------------------------------
    # 2) Stažení JSONu pro statistiky
    # -----------------------------------------------------------------------------
    url_stats = f"https://www.sofascore.com/api/v1/event/{match_id}/statistics"
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.get(url_stats)
        pre_element = driver.find_element(By.TAG_NAME, 'pre')
        json_text = pre_element.text
        json_data = json.loads(json_text)
    finally:
        driver.quit()

    # Požadované metriky
    required_metrics = [
        "Total shots", "Shots on target", "Big chances", "Touches in penalty area",
        "Final third entries", "Ball possession", "Passes", "Accurate passes",
        "Ground duels", "Aerial duels", "Tackles", "Tackles won", 
        "Fouls", "Yellow cards"
    ]

    # Extrakce metrik
    extracted_metrics = extract_metrics_from_json(json_data, required_metrics)
    df = pd.DataFrame.from_dict(extracted_metrics, orient='index')
    df.columns = ['Domácí', 'Hosté']
    df = df.reindex(required_metrics)  # Seřadit podle `required_metrics`
    df.index.name = ''
    df.reset_index(inplace=True)

    # Vytahování procent z "Ground duels" a "Aerial duels"
    for col in ["Domácí", "Hosté"]:
        df.loc[df[""] == "Ground duels", col] = (
            df.loc[df[""] == "Ground duels", col]
              .astype(str)
              .str.extract(r'\((\d+%)\)')
              [0]
        )
        df.loc[df[""] == "Aerial duels", col] = (
            df.loc[df[""] == "Aerial duels", col]
              .astype(str)
              .str.extract(r'\((\d+%)\)')
              [0]
        )

    # Překlad sloupců
    translations = {
        "Total shots": "Střely",
        "Shots on target": "Střely na branku",
        "Big chances": "Velké šance",
        "Touches in penalty area": "Doteky ve vápně",
        "Final third entries": "Vstupy do F3",
        "Ball possession": "Držení míče [%]",
        "Passes": "Přihrávky",
        "Accurate passes": "Přesné přihrávky",
        "Ground duels": "Souboje na zemi [%]",
        "Aerial duels": "Hlavičkové souboje [%]",
        "Tackles": "Souboje",
        "Tackles won": "Vyhrané souboje",
        "Fouls": "Fauly",
        "Yellow cards": "Žluté karty",
    }
    df[""] = df[""].map(translations)
    df = df[["Domácí", "", "Hosté"]]

    # Uložíme si i "čistou" verzi pro podmíněné barvení
    df_cleaned = df.copy()
    df_cleaned["Domácí"] = df_cleaned["Domácí"].apply(clean_percentage)
    df_cleaned["Hosté"] = df_cleaned["Hosté"].apply(clean_percentage)

    # -----------------------------------------------------------------------------
    # 3) Stažení sestav (domácí a hosté) z /lineups
    # -----------------------------------------------------------------------------

    url_lineups = f"https://www.sofascore.com/api/v1/event/{match_id}/lineups"
    driver = webdriver.Chrome(options=chrome_options)
  

    url = f"https://www.sofascore.com/api/v1/event/{match_id}/lineups"
    try:
        # Načtení stránky s JSON
        driver.get(url)

        # SofaScore API vrací JSON přímo v <pre> tagu
        pre_element = driver.find_element(By.TAG_NAME, 'pre')
        json_text = pre_element.text

        data = json.loads(json_text)

            # Extrakce hráčů
        home_players = extract_players(data, 'home')
        away_players = extract_players(data, 'away')

        home_df = pd.DataFrame(home_players)
        away_df = pd.DataFrame(away_players)

            # Převod pozic z písmen na názvy
        position_names = {'G': 'Br', 'D': 'Obr', 'M': 'Zál', 'F': 'Ú'}

        # Zahodíme řádky s NaN u Známky (obvykle náhradníci bez ratingu)
        home_df = home_df.dropna(subset=['Známka'])
        away_df = away_df.dropna(subset=['Známka'])

            # Nahradíme kódy pozic
        home_df['Pozice'] = home_df['Pozice'].map(position_names)
        away_df['Pozice'] = away_df['Pozice'].map(position_names)

            # Seřazení podle pozice a známky
        position_order = {'Br': 1, 'Obr': 2, 'Zál': 3, 'Ú': 4}
        home_df['PositionOrder'] = home_df['Pozice'].map(position_order)
        away_df['PositionOrder'] = away_df['Pozice'].map(position_order)

        home_df = home_df.sort_values(
                by=['PositionOrder', 'Známka'],
                ascending=[True, False]
            ).drop(columns='PositionOrder')

        away_df = away_df.sort_values(
                by=['PositionOrder', 'Známka'],
                ascending=[True, False]
            ).drop(columns='PositionOrder')

            # Převod minut na int
        home_df['Minuty'] = home_df['Minuty'].astype(int)
        away_df['Minuty'] = away_df['Minuty'].astype(int)

    finally:
        driver.quit()
# -----------------------------------------------------------------------------
# 4) Vyčištění a úprava tabulek
# -----------------------------------------------------------------------------

# Odstranit hráče, kteří nemají rating (např. náhradníci, co nenastoupili)
    home_df = home_df.dropna(subset=['Známka'])
    away_df = away_df.dropna(subset=['Známka'])

# Převedení minut na integer
    home_df['Minuty'] = home_df['Minuty'].astype(int)
    away_df['Minuty'] = away_df['Minuty'].astype(int)

# Seřazení hráčů (např. podle pozice a ratingu)
    position_order = {'Br': 1, 'Obr': 2, 'Zál': 3, 'Ú': 4}
    home_df['PositionOrder'] = home_df['Pozice'].map(position_order)
    away_df['PositionOrder'] = away_df['Pozice'].map(position_order)

    home_df = home_df.sort_values(by=['PositionOrder', 'Známka'],
                              ascending=[True, False]).drop(columns='PositionOrder')
    away_df = away_df.sort_values(by=['PositionOrder', 'Známka'],
                              ascending=[True, False]).drop(columns='PositionOrder')
    # -----------------------------------------------------------------------------
    # 4) Nakreslení obrázku s tabulkami a momentum grafem
    # -----------------------------------------------------------------------------
    # Načteme loga
    try:
        home_logo = load_logo(home_logo_url)
        away_logo = load_logo(away_logo_url)
    except ValueError as e:
        st.write(e)
        st.stop()

    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(3, 3, height_ratios=[1.5, 1, 2.5], width_ratios=[2, 1, 2])

    # A) Titulek (score je v datech "graphPoints"? Tady to uděláme napevno):
    #    Předpokládejme např. 2:1
    homeScore = 2
    awayScore = 1
    plt.text(
        0.52, 0.92,
        f"{home_team} x {away_team} {homeScore}-{awayScore}",
        fontproperties=fp_pop, fontsize=22, fontweight='bold', ha='center',
        transform=fig.transFigure
    )
    # Podtitul
    plt.text(
        0.52, 0.90,
        f"{datum}",
        fontproperties=fp_pop2, ha='center',
        transform=fig.transFigure
    )
    # Popisky týmů nad tabulkami
    plt.text(
        0.395, 0.61,
        f"{home_team}",
        fontproperties=fp_pop, fontsize=12, ha='left',
        transform=fig.transFigure
    )
    plt.text(
        0.63, 0.61,
        f"{away_team}",
        fontproperties=fp_pop, fontsize=12, ha='right',
        transform=fig.transFigure
    )

    # B) Horní graf = momentum
    ax_top = fig.add_subplot(gs[0, :])
    # Vybarvení sloupců podle kladné/záporné hodnoty
    colors = [home_color if value > 0 else away_color for value in momentum['value']]

    ax_top.axhline(y=0, color='gray', linestyle='-', linewidth=1, alpha=0.8, zorder=1)
    ax_top.bar(momentum['minute'], momentum['value'], color=colors, alpha=0.65, edgecolor='black')
    add_logo(ax_top, home_logo, x=-1, y=50, zoom=0.25)
    add_logo(ax_top, away_logo, x=-1, y=-50, zoom=0.25)

    ax_top.axvline(x=45.5, color='black', linestyle='--', linewidth=3)
    ax_top.set_xticks(range(0, 91, 10))
    ax_top.tick_params(axis='x', labelsize=12)
    ax_top.set_xlim(-1, 91)
    ax_top.set_ylim(-100, 100)
    ax_top.set_yticks([])
    ax_top.spines['top'].set_visible(False)
    ax_top.spines['right'].set_visible(False)
    ax_top.spines['left'].set_visible(False)

    # C) Levá tabulka = Domácí
    ax_left = fig.add_subplot(gs[1:, 0])
    ax_left.axis('tight')
    ax_left.axis('off')
    table_left = ax_left.table(
        cellText=home_df.values,
        colLabels=home_df.columns,
        loc='upper center'
    )
    table_left.auto_set_font_size(False)
    table_left.set_fontsize(12)
    table_left.scale(1.2, 1.6)

    # Podbarvování řádků podle ratingu (4. sloupec = index 3)
    rating_col_index = 3
    for (row, col), cell in table_left.get_celld().items():
        if row > 0:  # vynechat header (row=0)
            rating = float(home_df.iloc[row - 1, rating_col_index])
            base_color = get_rating_color(rating)
            rgba_color = to_rgba(base_color, alpha=0.5)
            cell.set_facecolor(rgba_color)
        else:
            # záhlaví tabulky
            cell.set_facecolor(to_rgba('lightgrey', alpha=1.0))

        # Šířka sloupců
        if col == 0:
            cell.set_width(0.45)
        elif col == 1:
            cell.set_width(0.1)
        elif col == 2:
            cell.set_width(0.15)
        else:
            cell.set_width(0.2)
        cell.set_text_props(ha='center', fontproperties=fp_pop2)

    # D) Prostřední tabulka = Statistiky
    ax_middle = fig.add_subplot(gs[1:, 1])
    ax_middle.axis('tight')
    ax_middle.axis('off')
    table_middle = ax_middle.table(
        cellText=df.values,
        colLabels=df.columns,
        loc='upper center'
    )
    table_middle.auto_set_font_size(False)
    table_middle.set_fontsize(12)
    table_middle.scale(1.2, 1.6)

    for (row, col), cell in table_middle.get_celld().items():
        if row == 0:
            # Header row: můžeme schovat nebo dát šedé pozadí
            cell.set_facecolor(to_rgba('lightgrey', alpha=1))
        else:
            # Podmíněné barvení: home > away => green pro home, red pro away atd.
            home_value = df_cleaned.iloc[row - 1, 0]  # Domácí
            away_value = df_cleaned.iloc[row - 1, 2]  # Hosté

            if col == 1:
                # Prostřední sloupec (metric)
                cell.set_facecolor(to_rgba('lightgrey', alpha=1))
            elif col == 0:  # Domácí
                if home_value is not None and away_value is not None:
                    if home_value > away_value:
                        cell.set_facecolor(to_rgba('green', alpha=0.5))
                    elif home_value < away_value:
                        cell.set_facecolor(to_rgba('red', alpha=0.5))
                    else:
                        cell.set_facecolor(to_rgba('yellow', alpha=0.5))
            elif col == 2:  # Hosté
                if home_value is not None and away_value is not None:
                    if away_value > home_value:
                        cell.set_facecolor(to_rgba('green', alpha=0.5))
                    elif away_value < home_value:
                        cell.set_facecolor(to_rgba('red', alpha=0.5))
                    else:
                        cell.set_facecolor(to_rgba('yellow', alpha=0.5))

        # Nastavení šířek
        if col == 1:
            cell.set_width(1.25)
        else:
            cell.set_width(0.4)
        cell.set_text_props(ha='center', fontproperties=fp_pop2)

    # E) Pravá tabulka = Hosté
    ax_right = fig.add_subplot(gs[1:, 2])
    ax_right.axis('tight')
    ax_right.axis('off')
    table_right = ax_right.table(
        cellText=away_df.values,
        colLabels=away_df.columns,
        loc='upper center'
    )
    table_right.auto_set_font_size(False)
    table_right.set_fontsize(12)
    table_right.scale(1.2, 1.6)

    for (row, col), cell in table_right.get_celld().items():
        if row > 0:  # vynechat header
            rating = float(away_df.iloc[row - 1, rating_col_index])
            base_color = get_rating_color(rating)
            rgba_color = to_rgba(base_color, alpha=0.5)
            cell.set_facecolor(rgba_color)
        else:
            cell.set_facecolor(to_rgba('lightgrey', alpha=1.0))

        if col == 0:
            cell.set_width(0.45)
        elif col == 1:
            cell.set_width(0.1)
        elif col == 2:
            cell.set_width(0.15)
        else:
            cell.set_width(0.2)
        cell.set_text_props(ha='center', fontproperties=fp_pop2)

    plt.subplots_adjust(wspace=0.5, hspace=0.25)
    for ax in fig.get_axes():
        if ax is ax_top:
            # Nechceme Y osu (ticks ani spine), ale X osu ponecháme
            ax.set_yticks([])
            ax.spines['left'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['top'].set_visible(False)
            # spodní (bottom) spine + xticks necháme
        else:
            # Všechny ostatní ax (tabulky) zbavíme i X i Y os
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
    # -----------------------------------------------------------------------------
    # 5) Zobrazení výsledného obrázku ve Streamlitu
    # -----------------------------------------------------------------------------
    st.pyplot(fig)

if __name__ == "__main__":
    main()
