"""
Monitor de eventos - eventossistema.com.mx
"""

import os
import re
import json
import hashlib
import requests
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://eventossistema.com.mx/login.html"
CONFIRMACIONES_URL = "https://eventossistema.com.mx/confirmaciones/default.html"

USUARIO = os.environ["EVENTOS_USER"]
PASSWORD = os.environ["EVENTOS_PASS"]
CALLMEBOT_PHONE = os.environ["CALLMEBOT_PHONE"]
CALLMEBOT_APIKEY = os.environ["CALLMEBOT_APIKEY"]

STATE_FILE = "estado_eventos.json"
SCREENSHOT_FILE = "debug_screenshot.png"


def enviar_whatsapp(mensaje: str):
    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": CALLMEBOT_PHONE, "text": mensaje, "apikey": CALLMEBOT_APIKEY}
    r = requests.get(url, params=params, timeout=20)
    print("CallMeBot respuesta:", r.status_code, r.text[:200])


def cargar_hash_anterior() -> str:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("hash", "")
    return ""


def guardar_estado(nuevo_hash: str, texto: str):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"hash": nuevo_hash, "texto": texto}, f, ensure_ascii=False, indent=2)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.goto(LOGIN_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        # Hacer click en el campo, luego escribir letra por letra (dispara todos los eventos de jQuery)
        page.click("#usuario")
        page.keyboard.type(USUARIO, delay=100)

        page.click("#password")
        page.keyboard.type(PASSWORD, delay=100)

        page.wait_for_timeout(500)
        print("Campos llenados, haciendo submit...")
        page.click("#login")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)
        print("URL tras login:", page.url)

        # Verificar si hay JWT en localStorage
        token = page.evaluate("localStorage.getItem('key')")
        print("JWT obtenido:", "SÍ" if token else "NO")

        if not token:
            page.screenshot(path=SCREENSHOT_FILE, full_page=True)
            print("ADVERTENCIA: no se obtuvo token. Revisá debug_screenshot.png en artifacts.")
            browser.close()
            return

        # Ya tenemos token, ir a confirmaciones
        page.goto(CONFIRMACIONES_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)
        print("URL final:", page.url)

        page.screenshot(path=SCREENSHOT_FILE, full_page=True)
        contenido = page.inner_text("body")
        print("Primeros 400 caracteres:", contenido[:400])
        browser.close()

    if "EVENTOS DISPONIBLES" not in contenido:
        print("ADVERTENCIA: no se encontró EVENTOS DISPONIBLES. Revisá el screenshot.")
        return

    match = re.search(r"EVENTOS DISPONIBLES(.*?)EVENTOS CONFIRMADOS", contenido, re.S)
    texto_actual = match.group(1).strip() if match else contenido.strip()

    hash_actual = hashlib.sha256(texto_actual.encode("utf-8")).hexdigest()
    hash_anterior = cargar_hash_anterior()

    if hash_anterior and hash_actual != hash_anterior:
        mensaje = "🔔 Hay novedades en EVENTOS DISPONIBLES:\n\n" + texto_actual[:500]
        enviar_whatsapp(mensaje)
        print("Cambio detectado, WhatsApp enviado.")
    elif not hash_anterior:
        print("Primera ejecucion: guardando estado base.")
    else:
        print("Sin cambios.")

    guardar_estado(hash_actual, texto_actual)


if __name__ == "__main__":
    main()
