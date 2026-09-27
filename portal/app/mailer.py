"""Outgoing e-mail over plain SMTP, so any provider works (Resend, Brevo, Gmail...).

Without SMTP_HOST the message is only written to the log, which is enough to test locally.
Sending happens on a background thread so a slow provider never holds up the page.
"""

import logging
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

log = logging.getLogger("portal.mail")

HOST = os.environ.get("SMTP_HOST", "").strip()
PORT = int(os.environ.get("SMTP_PORT", "587"))
USER = os.environ.get("SMTP_USER", "")
PASSWORD = os.environ.get("SMTP_PASSWORD", "")
FROM = os.environ.get("MAIL_FROM", "nao-responda@barbosamaria.online")
FROM_NAME = os.environ.get("MAIL_FROM_NAME", "VinOT")


def enabled():
    return bool(HOST)


def _send(to, subject, text, html_body):
    msg = EmailMessage()
    msg["From"] = formataddr((FROM_NAME, FROM))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=FROM.split("@")[-1])
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")
    ctx = ssl.create_default_context()
    try:
        if PORT == 465:
            with smtplib.SMTP_SSL(HOST, PORT, context=ctx, timeout=20) as s:
                s.login(USER, PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(HOST, PORT, timeout=20) as s:
                s.starttls(context=ctx)
                if USER:
                    s.login(USER, PASSWORD)
                s.send_message(msg)
        log.info("mail sent to %s: %s", to, subject)
    except Exception as exc:
        log.error("mail to %s failed: %s", to, exc)


def send(to, subject, text, html_body):
    if not enabled():
        log.warning("SMTP not configured; mail to %s not sent.\n%s", to, text)
        return
    threading.Thread(target=_send, args=(to, subject, text, html_body), daemon=True).start()
