"""Small security helpers: client IP, rate limits, CSRF, passwords, security headers."""

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque

TRUST_PROXY = os.environ.get("PORTAL_TRUST_PROXY", "1") == "1"


def client_ip(request):
    # Behind Cloudflare Tunnel every request arrives from cloudflared; the real address is in
    # CF-Connecting-IP. The container is only bound to localhost, so the header can't be forged.
    if TRUST_PROXY:
        ip = request.headers.get("cf-connecting-ip", "").strip()
        if ip:
            return ip[:64]
    return request.client.host if request.client else "?"


class Limiter:
    """In-memory sliding window: allow `limit` hits per `window` seconds per key."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def _trim(self, key, now):
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        return q

    def blocked(self, key):
        with self.lock:
            return len(self._trim(key, time.time())) >= self.limit

    def hit(self, key):
        with self.lock:
            now = time.time()
            self._trim(key, now).append(now)
            if len(self.hits) > 50000:  # never grow without bound
                for k in [k for k, q in self.hits.items() if not q]:
                    del self.hits[k]


def csrf_token(session):
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def csrf_ok(session, token):
    return bool(token) and hmac.compare_digest(str(token), session.get("csrf", ""))


def sha1(text):
    # Canary's passwordType = "sha1": the game and the login server check this exact hash.
    return hashlib.sha1(text.encode()).hexdigest()


def password_ok(stored, password):
    return hmac.compare_digest((stored or "").lower(), sha1(password))


def fingerprint(stored_hash):
    """Ties a session to the current password hash, so changing the password logs out everywhere."""
    return hashlib.sha256(("portal:" + (stored_hash or "")).encode()).hexdigest()[:16]


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


COMMON = {"12345678", "123456789", "1234567890", "password", "senha123", "qwerty123", "abcd1234", "tibia123", "vinot123"}


def password_problem(pw, email=""):
    if len(pw) < 8:
        return "A senha precisa de pelo menos 8 caracteres."
    if len(pw) > 64:
        return "A senha pode ter no máximo 64 caracteres."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Use letras e números na senha."
    if pw.lower() in COMMON or (email and pw.lower() == email.lower()):
        return "Essa senha é fácil demais de adivinhar. Escolha outra."
    return None


def headers(response, turnstile=False):
    script = "'self'" + (" https://challenges.cloudflare.com" if turnstile else "")
    frame = "https://www.youtube-nocookie.com" + (" https://challenges.cloudflare.com" if turnstile else "")
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src {script}; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data: https://cdn.sanity.io; "
        f"frame-src {frame}; "
        "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response
