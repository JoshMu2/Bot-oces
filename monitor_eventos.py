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

# Script que se inyecta ANTES de cualquier JS del sitio
# Parchea eval y Function para eliminar debugger, y oculta que es un bot
STEALTH_SCRIPT = """
// Eliminar navigator.webdriver (principal señal de bot)
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Parchear eval para eliminar debugger
const _eval = window.eval;
window.eval = function(code) {
  if (typeof code === 'string') code = code.replace(/\\bdebugger\\b/g, '0');
  return _eval.call(this, code);
};

// Parchear Function constructor para eliminar debugger
const _Function = window.Function;
window.Function = function(...args) {
  if (args.length > 0 && typeof args[args.length - 1] === 'string') {
    args[args.length - 1] = args[args.length - 1].replace(/\\bdebugger\\b/g, '0');
  }
  return _Function(...args);
};
window.Function.prototype = _Function.prototype;
"""


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
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="es-MX",
        )

        # Inyectar parches ANTES de que cargue cualquier JS del sitio
        context.add_init_script(STEALTH_SCRIPT)

        page = context.new_page()
        page.goto(LOGIN_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # Llenar con page.fill (simula tipeo real) apuntando directo a los id conocidos
        page.fill("#usuario", USUARIO)
        page.fill("#password", PASSWORD)
        page.wait_for_timeout(500)

        print("Campos llenados, enviando formulario...")
        page.click("#login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(4000)

        print("URL después del login:", page.url)

        # Navegar a confirmaciones (el login va a inicio.html, no directo a confirmaciones)
        page.goto(CONFIRMACIONES_URL)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)

        print("URL final:", page.url)
        page.screenshot(path=SCREENSHOT_FILE, full_page=True)

        contenido = page.inner_text("body")
        print("Primeros 400 caracteres:", contenido[:400])
        browser.close()

    if "EVENTOS DISPONIBLES" not in contenido:
        print("ADVERTENCIA: login fallido. Revisá debug_screenshot.png en artifacts.")
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
