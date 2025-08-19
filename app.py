# app.py
import os
from flask import Flask, request, Response

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "verify_me")

@app.get("/")
def root():
    return "ok", 200

@app.get("/health")
def health():
    return "ok", 200

# Webhook de WhatsApp: verificación GET
@app.get("/whatsapp/webhook")
def wa_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        # Render responde el reto tal cual lo envía Meta
        return Response(challenge, status=200, mimetype="text/plain")
    return "forbidden", 403

# Webhook de WhatsApp: mensajes POST (aquí solo eco/log)
@app.post("/whatsapp/webhook")
def wa_incoming():
    data = request.get_json(silent=True) or {}
    # imprime en logs para depurar
    print("WA IN >>>", data)
    # Responder 200 SIEMPRE para que Meta no reintente
    return "ok", 200
