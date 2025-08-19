import os
import json
import requests
from flask import Flask, request

# === Config ===
WA_TOKEN = os.getenv("WA_TOKEN")                   # Token de acceso de WhatsApp Cloud API
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "verify_me")  # Para verificación del webhook

app = Flask(__name__)

@app.get("/webhook")
def verify():
    """Verificación inicial que pide Meta cuando configuras el webhook."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        return challenge, 200
    return "forbidden", 403


@app.post("/webhook")
def incoming():
    """Recibe mensajes y responde automáticamente con un eco simple."""
    if not WA_TOKEN:
        return "token-missing", 200

    payload = request.get_json(silent=True) or {}
    # print("IN >>>", json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        entry = (payload.get("entry") or [])[0]
        changes = (entry.get("changes") or [])[0]
        value   = changes.get("value", {})

        phone_id = (value.get("metadata") or {}).get("phone_number_id")
        messages = value.get("messages", [])
        if not phone_id or not messages:
            return "ok", 200

        for msg in messages:
            if msg.get("type") != "text":
                continue

            from_id = msg.get("from")  # ej: "5695xxxxxxx"
            user_text = (msg.get("text") or {}).get("body", "")

            reply_text = f"👋 Recibí tu mensaje: {user_text}"

            url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
            headers = {
                "Authorization": f"Bearer {WA_TOKEN}",
                "Content-Type": "application/json"
            }
            body = {
                "messaging_product": "whatsapp",
                "to": from_id,
                "text": {"body": reply_text}
            }
            r = requests.post(url, headers=headers, json=body, timeout=30)
            # print("OUT <<<", r.status_code, r.text)

        return "ok", 200

    except Exception as e:
        # print("ERR !!!", repr(e))
        return "ok", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
