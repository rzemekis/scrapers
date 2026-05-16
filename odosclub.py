import os
import time
import threading
import pandas as pd
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, InvalidElementStateException, StaleElementReferenceException

# Глобальные флаги
stop_flag = False
start_parsing = False


def monitor_input():
    global stop_flag, start_parsing
    while True:
        user_input = input().strip()
        if not start_parsing and user_input == "200 OK":
            print("[+] Команда принята! Начинаем сбор ссылок...")
            start_parsing = True
        elif user_input.lower() == "stop1":
            print("[!!!] Остановка... Сохраняем прогресс.")
            stop_flag = True
            break


def setup_driver():
    chrome_options = Options()

    # Сохраняем профиль (Windows)
    user_data_path = os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'OdosScraperProfile')
    if not os.path.exists(user_data_path):
        os.makedirs(user_data_path)

    chrome_options.add_argument(f"--user-data-dir={user_data_path}")
    chrome_options.add_argument("--profile-directory=Default")

    # Сетевые фиксы
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-quic")

    # Маскировка
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver


def parse_odosclub():
    global stop_flag, start_parsing
    catalog_url = "https://odosclub.ru/optics"

    driver = setup_driver()
    results = []

    threading.Thread(target=monitor_input, daemon=True).start()

    try:
        driver.get(catalog_url)
        print("\n" + "=" * 50)
        print("БРАУЗЕР ОТКРЫТ. ПОДГОТОВЬСЯ И ПИШИ 200 OK")
        print("=" * 50 + "\n")

        while not start_parsing:
            time.sleep(1)

        print("Начинаем сбор ссылок по страницам (пагинация)...")
        links = set()

        while not stop_flag:
            items = driver.find_elements(By.CSS_SELECTOR, ".js-product a[href*='tproduct']")
            for item in items:
                href = item.get_attribute('href')
                if href:
                    links.add(href)

            try:
                next_btn_selector = ".t-catalog__pagination__item_next"
                if not driver.find_elements(By.CSS_SELECTOR, next_btn_selector):
                    break

                next_btn = driver.find_element(By.CSS_SELECTOR, next_btn_selector)
                if "none" in next_btn.value_of_css_property("display"):
                    break

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(1.5)
                driver.execute_script("document.querySelector('.t-catalog__pagination__item_next').click();")
                time.sleep(random.uniform(3.0, 5.0))
                print(f"Переход на следующую страницу... (Собрано ссылок: {len(links)})")
            except Exception:
                break

        links = list(links)
        print(f"\nИтого найдено: {len(links)}. Начинаем обход...")

        for index, link in enumerate(links):
            if stop_flag: break
            print(f"[{index + 1}/{len(links)}] Переход: {link}")

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    driver.get(link)
                except TimeoutException:
                    driver.execute_script("window.stop();")

                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
                    name = driver.find_element(By.TAG_NAME, "h1").text.strip()

                    # СБОР ФОТО (только одна фотка, как ты просил)
                    photo_link = "Нет фото"
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".js-product-img, .t-slds__bgimg"))
                        )
                        images = driver.find_elements(By.CSS_SELECTOR, ".js-product-img, .t-slds__bgimg")
                        for img in images:
                            src = img.get_attribute('data-original') or img.get_attribute('src')
                            if src:
                                photo_link = src
                                break # <--- ОСТАНАВЛИВАЕМСЯ НА ПЕРВОЙ ФОТОГРАФИИ
                    except Exception:
                        pass

                    item_data = {
                        "Название": name,
                        "Ссылка на фото": photo_link,
                        "Ссылка на товар": link
                    }

                    # ХАРАКТЕРИСТИКИ
                    for _ in range(2):
                        try:
                            charcs = driver.find_elements(By.CSS_SELECTOR, ".js-catalog-prod-charcs")
                            for char in charcs:
                                text = char.text.strip()
                                if ":" in text:
                                    key, val = text.split(":", 1)
                                    key, val = key.strip(), val.strip()
                                    item_data[key] = val
                            break
                        except StaleElementReferenceException:
                            time.sleep(1)
                            continue

                    results.append(item_data)
                    print(f"  [+] Успешно: {name[:30]}...")
                    time.sleep(random.uniform(1.0, 2.0))
                    break
                except Exception as e:
                    print(f"  [!] Ошибка: {e}")
                    time.sleep(2)

        save_to_excel(results)
    finally:
        driver.quit()


def save_to_excel(results):
    if not results:
        print("Данных нет.")
        return

    df = pd.DataFrame(results)

    cols = df.columns.tolist()
    priority = ["Название", "Ссылка на фото", "Ссылка на товар"]
    new_order = [c for c in priority if c in cols] + [c for c in cols if c not in priority]
    df = df[new_order]

    filename = f"odosclub_data_{int(time.time())}.xlsx"
    df.to_excel(filename, index=False)
    print(f"\n[OK] Файл сохранен: {filename}")


if __name__ == "__main__":
    parse_odosclub()