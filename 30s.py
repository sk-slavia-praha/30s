import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
import json
import pandas as pd

home_team = "Teplice"
home_color = "blue"
home_logo_url = "https://img.sofascore.com/api/v1/team/2208/image"

away_team = "Slavia Praha"
away_color = "red"
away_logo_url = "https://img.sofascore.com/api/v1/team/2216/image"

datum = "15.12.2024"
match_id = 12580722


# Funkce na extrakci hráčů z JSON
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

def main():
    st.title("Ukázka použití Selenium s ChromeDriverem a SofaScore")

    # Vstup od uživatele - ID zápasu
    match_id = st.text_input("Zadejte ID zápasu", value="123456")

    if st.button("Načíst sestavy"):
        # Nastavení Chromu
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')      # Pro provoz bez GUI
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        # Inicializace webdriveru
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

            # Výstup ve Streamlitu
            st.subheader("Domácí tým")
            st.dataframe(home_df)

            st.subheader("Hostující tým")
            st.dataframe(away_df)

        except Exception as e:
            st.error(f"Nastala chyba: {e}")
        finally:
            driver.quit()

if __name__ == "__main__":
    main()
