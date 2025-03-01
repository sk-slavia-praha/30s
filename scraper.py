import requests
import datetime
import pandas as pd
import os

# 📅 Získání dnešního data
today = datetime.date.today().strftime("%Y-%m-%d")
one_year_ago = datetime.date.today() - datetime.timedelta(days=365)

# 📂 Cesta k CSV souboru
csv_file_path = "all_matches.csv"  

# 🏆 ID sledovaného týmu
team_id_to_find = 2697   #2216

# 📥 Načtení existujícího souboru, pokud existuje
if os.path.exists(csv_file_path):
    df_all_matches = pd.read_csv(csv_file_path)
    df_all_matches["date"] = pd.to_datetime(df_all_matches["date"]).dt.date  # Převod na datumový formát
else:
    df_all_matches = pd.DataFrame(columns=["match_id", "date", "home_team", "home_team_id", "away_team", "away_team_id"])

# 🔗 API URL pro dnešní den
url = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{today}"

# 📡 Stažení dat z API
try:
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        events = data.get("events", [])

        new_matches = []
        for event in events:
            match_id = event.get("id")
            match_date = datetime.datetime.utcfromtimestamp(event.get("startTimestamp")).date()
            home_team = event["homeTeam"]["name"] if "homeTeam" in event else "N/A"
            home_team_id = event["homeTeam"]["id"] if "homeTeam" in event else "N/A"
            away_team = event["awayTeam"]["name"] if "awayTeam" in event else "N/A"
            away_team_id = event["awayTeam"]["id"] if "awayTeam" in event else "N/A"

            # 🎯 Uložit pouze zápasy, kde hraje sledovaný tým
            if home_team_id == team_id_to_find or away_team_id == team_id_to_find:
                new_matches.append([match_id, match_date, home_team, home_team_id, away_team, away_team_id])

        # 📊 Přidání nových zápasů a odstranění duplikátů
        df_new_matches = pd.DataFrame(new_matches, columns=["match_id", "date", "home_team", "home_team_id", "away_team", "away_team_id"])
        df_all_matches = pd.concat([df_all_matches, df_new_matches]).drop_duplicates("match_id")
        df_all_matches = df_all_matches.sort_values(by='date',ascending=False)
        df_all_matches["Home_team - Away_team"] = df_all_matches["home_team"] + " - " + df_all_matches["away_team"]
        # 🔍 Filtr na posledních 365 dní
        df_all_matches = df_all_matches[df_all_matches["date"] >= one_year_ago]

        # 💾 Uložení aktualizovaných dat zpět do CSV
        df_all_matches.to_csv(csv_file_path, index=False, encoding="utf-8")
        print(f"✅ Data byla aktualizována a uložena do {csv_file_path}")

    else:
        print(f"❌ Chyba při stahování dat: {response.status_code}")

except Exception as e:
    print(f"❌ Chyba při připojení k API: {e}")
