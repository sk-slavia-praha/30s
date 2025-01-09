import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def main():
    st.title("Ukázka použití Selenium s ChromeDriverem")

    chrome_options = Options()
    # Headless mód (důležité pro prostředí bez GUI)
    chrome_options.add_argument("--headless")
    # (V některých případech je nutné přidat i další argumenty – záleží na verzi OS)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    # Pokud je chromedriver v PATH, stačí zavolat takto:
    driver = webdriver.Chrome(options=chrome_options)

    # Otevřít libovolnou stránku
    driver.get("https://www.google.com")
    
    # Vyčteme titulek stránky a vypíšeme ve Streamlitu
    st.write("Title:", driver.title)

    driver.quit()

if __name__ == "__main__":
    main()
