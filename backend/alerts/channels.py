"""Delivery channels for defect alerts: a phone call, a WhatsApp message and an email.

Credentials only come from the environment (.env), never from the dashboard. Recipients come from
the alert settings, falling back to ALERT_PHONE / ALERT_EMAIL_TO. A channel without credentials is
reported as not configured and nothing is sent.

- call: Sarvam outbound voice agent (same API as ARRC), or Twilio Voice reading the message aloud
- whatsapp: Twilio WhatsApp API
- email: any SMTP server (STARTTLS on 587, SSL on 465)
"""
import base64
import json
import os
import re
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from xml.sax.saxutils import escape

import backend.ai.llm  # noqa: F401  loads .env into os.environ

TIMEOUT_S = 15
SARVAM_KEYS = ("SARVAM_WORKSPACE_KEY", "SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "ALERT_CALL_APP_ID",
               "ALERT_CALL_CONNECTION_ID")
TWILIO_KEYS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
SMTP_KEYS = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")


class ChannelError(RuntimeError):
    pass


def _env(*keys) -> bool:
    return all(os.getenv(k) for k in keys)


def digits(number: str | None) -> str:
    return re.sub(r"\D", "", number or "")


def call_provider() -> str | None:
    if _env(*SARVAM_KEYS):
        return "sarvam"
    if _env(*TWILIO_KEYS, "TWILIO_CALL_FROM"):
        return "twilio"
    return None


PUSH_TOPIC = "rootlens-alerts"   # the Android app subscribes to this topic


def configured() -> dict:
    from backend import cloud
    return {"push": "fcm" if cloud.CLOUD or os.getenv("ROOTLENS_FCM") == "1" else None,
            "call": call_provider(),
            "whatsapp": "twilio" if _env(*TWILIO_KEYS, "TWILIO_WHATSAPP_FROM") else None,
            "email": "smtp" if _env(*SMTP_KEYS) else None}


def _post(url: str, data: bytes, headers: dict) -> str:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise ChannelError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise ChannelError(str(e.reason)) from e


def _twilio(path: str, form: dict) -> str:
    sid, token = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    return _post(f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}/{path}",
                 urllib.parse.urlencode(form).encode(),
                 {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})


LAST_ATTEMPT: dict = {}   # attempt id of the most recent call, read by the alert service after send_call


def send_call(to: str, message: str, variables: dict | None = None) -> str:
    number = digits(to)
    if not number:
        raise ChannelError("no phone number set")
    provider = call_provider()
    if provider == "sarvam":
        url = (f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{urllib.parse.quote(os.environ['SARVAM_ORG_ID'])}"
               f"/workspaces/{urllib.parse.quote(os.environ['SARVAM_WORKSPACE_ID'])}/outbounds")
        body = {"app_config": {
                    "app_id": os.environ["ALERT_CALL_APP_ID"],
                    "app_version": int(os.getenv("ALERT_CALL_APP_VERSION") or 1),
                    "connection_config": {"connection_id": os.environ["ALERT_CALL_CONNECTION_ID"],
                                          "agent_phone_number": os.getenv("ALERT_CALL_AGENT_NUMBER", "")},
                    # the agent greets with the opening_line variable, so the call opens with the alert
                    "agent_variables": {"opening_line": message, **(variables or {})},
                    "app_overrides": {"initial_bot_message": message,
                                      "initial_language_name": os.getenv("ALERT_CALL_LANGUAGE", "English")}},
                "user_config": {"user_phone_number": f"+{number}"}}
        hook = os.getenv("ALERT_CALL_WEBHOOK_URL")
        if hook:   # Sarvam posts the outcome (connected / no_answer / busy / failed, duration, transcript) here
            body["webhook_config"] = {"url": hook, "metadata": {"token": os.getenv("ALERT_WEBHOOK_TOKEN", "")}}
        reply = _post(url, json.dumps(body).encode(),
                      {"X-API-Key": os.environ["SARVAM_WORKSPACE_KEY"], "Content-Type": "application/json"})
        try:
            LAST_ATTEMPT["id"] = json.loads(reply).get("attempt_id")
        except ValueError:
            LAST_ATTEMPT["id"] = None
        return f"calling +{number} (Sarvam)"
    if provider == "twilio":
        twiml = f'<Response><Say voice="alice">{escape(message)}</Say><Pause length="1"/><Say voice="alice">{escape(message)}</Say></Response>'
        _twilio("Calls.json", {"To": f"+{number}", "From": os.environ["TWILIO_CALL_FROM"], "Twiml": twiml})
        return f"calling +{number} (Twilio)"
    raise ChannelError("call channel not configured")


def send_push(subject: str, text: str, link: str | None = None, kind: str = "alert") -> str:
    """Firebase Cloud Messaging to every phone running the app (topic rootlens-alerts), even when it is closed."""
    from firebase_admin import messaging

    from backend import cloud
    cloud._app()
    msg = messaging.Message(
        topic=PUSH_TOPIC,
        notification=messaging.Notification(title=subject[:120], body=text[:400]),
        data={"kind": kind, "link": link or "", "subject": subject[:200]},
        android=messaging.AndroidConfig(priority="high", notification=messaging.AndroidNotification(channel_id="rootlens_alerts")),
    )
    try:
        return f"pushed to the app ({messaging.send(msg)[-12:]})"
    except Exception as e:  # noqa: BLE001 - FCM errors come in many types
        raise ChannelError(f"push: {e}") from e


def send_whatsapp(to: str, message: str) -> str:
    number = digits(to)
    if not number:
        raise ChannelError("no WhatsApp number set")
    if not configured()["whatsapp"]:
        raise ChannelError("WhatsApp channel not configured")
    sender = os.environ["TWILIO_WHATSAPP_FROM"]
    _twilio("Messages.json", {"To": f"whatsapp:+{number}",
                              "From": sender if sender.startswith("whatsapp:") else f"whatsapp:{sender}",
                              "Body": message})
    return f"WhatsApp sent to +{number}"


def send_email(to: str, subject: str, message: str) -> str:
    to = (to or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        raise ChannelError("no valid email address set")
    if not configured()["email"]:
        raise ChannelError("email channel not configured")
    msg = EmailMessage()
    msg["Subject"], msg["To"] = subject, to
    msg["From"] = os.getenv("ALERT_EMAIL_FROM") or os.environ["SMTP_USER"]
    msg.set_content(message)
    host, port = os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT") or 587)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_S) as s:
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=TIMEOUT_S) as s:
                s.starttls()
                s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise ChannelError(f"SMTP: {e}") from e
    return f"email sent to {to}"
