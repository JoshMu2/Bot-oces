"""
Monitor de eventos - eventossistema.com.mx
-------------------------------------------
Inicia sesion, lee la seccion "EVENTOS DISPONIBLES" y avisa por WhatsApp
(via CallMeBot) si el contenido cambio desde la ultima revision.

Requiere variables de entorno:
  EVENTOS_USER       -> tu usuario del sistema
  EVENTOS_PASS       -> tu contraseña
  CALLMEBOT_PHONE    -> tu numero de WhatsApp con codigo de pais, sin "+" (ej: 5215512345678)
  CALLMEBOT_APIKEY   -> apikey que te da CallMeBot (ver README)

Instalacion local para probar:
  pip install playwright requests
  playwright install chromium
  EVENTOS_USER=xxx EVENTOS_PASS=xxx CALLMEBOT_PHONE=xxx CALLMEBOT_APIKEY=xxx python monitor_eventos.py
"""

import os
import re
import json
import hashlib
import requests
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://eventossistema.com.mx/login.html"
EVENTOS_URL = "https://eventossistema.com.mx/confirmaciones/default.html"

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


def hacer_login(page):
    page.goto(LOGIN_URL)
    page.wait_for_load_state("networkidle")

    # Intento 1: por etiqueta de texto visible
    try:
        page.get_by_label(re.compile("Usuario", re.I)).fill(USUARIO)
        page.get_by_label(re.compile("Password", re.I)).fill(PASSWORD)
    except Exception:
        # Intento 2: por el atributo type, que es mas confiable que el orden
        # (evita inputs ocultos como tokens CSRF que rompen el conteo por indice)
        page.locator('input[type="password"]').first.fill(PASSWORD)
        campo_usuario = page.locator(
            'input[type="text"], input[type="email"], input:not([type])'
        ).first
        campo_usuario.fill(USUARIO)

    page.get_by_role("button", name=re.compile("Entrar", re.I)).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)

    print("URL despues del intento de login:", page.url)

    if "confirmaciones" not in page.url:
        page.goto(EVENTOS_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)


def obtener_texto_eventos(page):
    contenido = page.inner_text("body")

    if "EVENTOS DISPONIBLES" not in contenido:
        # No llegamos a la pagina correcta -> probablemente fallo el login
        return None

    match = re.search(r"EVENTOS DISPONIBLES(.*?)EVENTOS CONFIRMADOS", contenido, re.S)
    return match.group(1).strip() if match else contenido.strip()


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
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        hacer_login(page)

        # Captura de pantalla SIEMPRE, para poder diagnosticar si algo sale mal
        page.screenshot(path=SCREENSHOT_FILE, full_page=True)

        texto_actual = obtener_texto_eventos(page)
        browser.close()

    if texto_actual is None:
        print(
            "ADVERTENCIA: no se encontro la seccion EVENTOS DISPONIBLES. "
            "El login probablemente fallo. Revisa 'debug_screenshot.png' en los "
            "artifacts de este run para ver que pantalla quedo cargada. "
            "No se envio ningun WhatsApp."
        )
        return

    hash_actual = hashlib.sha256(texto_actual.encode("utf-8")).hexdigest()
    hash_anterior = cargar_hash_anterior()

    if hash_anterior and hash_actual != hash_anterior:
        mensaje = "🔔 Hay novedades en EVENTOS DISPONIBLES:\n\n" + texto_actual[:500]
        enviar_whatsapp(mensaje)
        print("Cambio detectado, WhatsApp enviado.")
    elif not hash_anterior:
        print("Primera ejecucion: guardando estado base, sin enviar aviso.")
    else:
        print("Sin cambios.")

    guardar_estado(hash_actual, texto_actual)


if __name__ == "__main__":
    main()
