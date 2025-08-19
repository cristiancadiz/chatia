import os
import time
import json
from flask import Flask, request, jsonify
import requests

# ========= Config =========
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "verify_me")
WA_TOKEN     = os.getenv("WA_TOKEN")               # << obligatorio
WA_PHONE_ID  = os.getenv("WA_PHONE_ID", "")        # opcional (se puede leer del webhook)
DEBUG        = os.getenv("DEBUG", "0") == "1"

# anti-duplicados (idempotencia)
TTL_SEC = int(os.getenv("DEDUP_TTL_SEC", "300"))
PROCESADOS: dict[str, float] = {}

def is_dup(mid: str) -> bool:
    now = time.time()
    # limpia expirados
    for k, exp in list(PROCESADOS.items()):
        if exp < now:
            PROCESADOS.pop(k, None)
    if not mid:
        return False
    if mid in PROCESADOS and PROCESADOS[mid] > now:
        return True
    PROCESADOS[mid] = now + TTL_SEC
    return False

# memoria súper simple por remitente
SESSIONS: dict[str, dict] = {}
def sess(who: str) -> dict:
    s = SESSIONS.get(who)
    if not s:
        s = {"stage": "start", "name": ""}
        SESSIONS[who] = s
    return s

# ========= Flask =========
app = Flask(__name__)

@app.get("/")
def root():
    return "OK", 200

@app.get("/health")
def health():
    return jsonify({"ok": True})

# -- Verificación de webhook (GET)
@app.get("/whatsapp/webhook")
def wa_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if DEBUG:
        print("VERIFY >>>", mode, token, challenge)
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge or "", 200
    return "forbidden", 403

# -- Recepción de mensajes (POST)
@app.post("/whatsapp/webhook")
def wa_incoming():
    if not WA_TOKEN:
        # si no está configurado, no hacemos nada; evita errores de despliegue
        return "whatsapp not configured", 200

    payload = request.get_json(silent=True) or {}
    if DEBUG:
        print("WA IN >>>", json.dumps(payload, ensure_ascii=False))

    # WhatsApp Cloud estructura (WABA)
    try:
        entry = (payload.get("entry") or [])[0]
        changes = (entry.get("changes") or [])[0]
        value = changes.get("value", {})
        phone_id = (value.get("metadata") or {}).get("phone_number_id") or WA_PHONE_ID
        messages = value.get("messages", [])
        statuses = value.get("statuses", [])

        # Nada que procesar (p.ej. solo estatus de entrega)
        if not messages:
            if DEBUG and statuses:
                print("WA STATUS >>>", json.dumps(statuses, ensure_ascii=False))
            return "ok", 200

        for msg in messages:
            mid = msg.get("id") or msg.get("wamid")
            if is_dup(mid):
                if DEBUG:
                    print("WA DUP >>>", mid)
                continue

            from_id = msg.get("from")   # número del usuario
            mtype   = msg.get("type")
            text    = ""
            if mtype == "text":
                text = (msg.get("text") or {}).get("body", "").strip()
            elif mtype == "button":
                text = (msg.get("button") or {}).get("text", "").strip()
            else:
                text = "?"

            # === Lógica simple de chat ===
            state = sess(from_id)
            reply = handle_chat(state, text)

            # envía la respuesta
            send_text(phone_id, from_id, reply)

        return "ok", 200

    except Exception as e:
        if DEBUG:
            print("WA ERROR !!!", repr(e))
        return "ok", 200

# ========= Lógica del bot =========
def handle_chat(state: dict, text: str) -> str:
    t = text.lower()

    # reset rápido
    if t in {"menu", "reiniciar", "reset"}:
        state["stage"] = "start"; state["name"] = ""
        return "¡Listo! Empecemos de nuevo. ¿Cómo te llamas?"

    if state["stage"] == "start":
        state["stage"] = "ask_name"
        return "Hola 👋 Soy tu asistente. ¿Cómo te llamas?"

    if state["stage"] == "ask_name":
        # toma la primera palabra como nombre
        name = text.split()[0] if text else "amig@"
        state["name"] = name
        state["stage"] = "ask_need"
        return f"Encantado, {name}. ¿En qué te puedo ayudar?"

    if state["stage"] == "ask_need":
        # intentos muy básicos
        if any(x in t for x in ["hola", "buenas"]):
            return f"{state['name']}, dime: ¿en qué te ayudo?"
        if "precio" in t or "plan" in t or "planes" in t:
            return "Nuestros planes: Básico, Pro y Empresa. ¿Cuál te interesa?"
        if "ayuda" in t or "soporte" in t:
            return "Claro. Cuéntame brevemente el problema y te doy una mano."
        # fallback eco corto
        return f"Entendido. Me dijiste: “{text[:100]}”. ¿Quieres más detalles o hablar con un humano? (escribe 'humano')"

    # por si acaso
    state["stage"] = "start"
    return "Empecemos de nuevo. ¿Cómo te llamas?"

# ========= Envío por WhatsApp =========
def send_text(phone_id: str, to_id: str, body_text: str):
    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to_id,
        "type": "text",
        "text": {"body": body_text},
    }
    try:
        r = requests.post(url, headers=headers, json=data, timeout=30)
        if DEBUG:
            print("WA OUT <<<", r.status_code, r.text)
    except Exception as e:
        if DEBUG:
            print("WA OUT ERROR !!!", repr(e))

# ========= Run local (opcional) =========
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
