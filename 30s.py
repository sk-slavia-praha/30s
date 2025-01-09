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
    Projde JSON se statistikami a vytáhne jen požadované metriky (metrics).
    Vrací dict, který následně převedeme do DataFrame.
    """
    extracted_data = {}
    for group in json_data['statistics'][0]['groups']:
        for item in group['statisticsItems']:
            if item['name'] in metrics:
                extracted_data[item['name']] = {
                    'home': item['home'],
                    'away': item['away']
                }
    return extracted_data

# -----------------------------------------------------------------------------
# Hlavní Streamlit aplikace
# -----------------------------------------------------------------------------
def main():
    st.title("Ukázka SofaScore zápasu se Seleniem a grafikou")

    # Ukázkové vstupy
    home_team = "Teplice"
    home_color = "blue"
    home_logo_url = "https://img.sofascore.com/api/v1/team/2208/image"

    away_team = "Slavia Praha"
    away_color = "red"
    away_logo_url = "https://img.sofascore.com/api/v1/team/2216/image"

    datum = "15.12.2024"
    match_id = 12580722

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
    # 3) Pro ukázku přidáme i sestavy (domácí_df a hosté_df)
    #    Tady jen uděláme "mock" data, aby se to zobrazilo.
    # -----------------------------------------------------------------------------
    # V reálném kódu byste sem vložili kód pro extrakci z /lineups
    # Zde jen dummy data s ratingy:
    home_data = {
        "Hráč": ["Novák", "Krejčí", "Moravec"],
        "Č.": [1, 10, 9],
        "Pozice": ["Br", "Zál", "Ú"],
        "Známka": [7.2, 6.1, 8.0],
        "Minuty": [90, 88, 90],
    }
    away_data = {
        "Hráč": ["Kolář", "Coufal", "Tecl"],
        "Č.": [1, 5, 11],
        "Pozice": ["Br", "Obr", "Ú"],
        "Známka": [6.9, 7.5, 5.9],
        "Minuty": [90, 90, 72],
    }

    home_df = pd.DataFrame(home_data)
    away_df = pd.DataFrame(away_data)

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

    # -----------------------------------------------------------------------------
    # 5) Zobrazení výsledného obrázku ve Streamlitu
    # -----------------------------------------------------------------------------
    st.pyplot(fig)

if __name__ == "__main__":
    main()
