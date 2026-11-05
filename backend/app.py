"""FindYourMate API server (Flask).

Run:  python app.py            -> http://localhost:5000
Serves the JSON API under /api and, when frontend/dist exists, the built React app.

Environment (all optional):
  SECRET_KEY            session signing key (auto-generated into backend/.secret_key if unset)
  FACEBOOK_APP_ID       enable "Continue with Facebook" (can also go in backend/.env — see .env.example)
  FACEBOOK_APP_SECRET
  APP_URL               public URL of the app when deployed (default http://localhost:5000). On localhost the
                        Facebook redirect automatically goes back to the address you opened (e.g. Vite :5173/:5174)
  FYM_DB / FYM_UPLOADS  database file / upload folder
  SEED_SAMPLE_USERS     "0" to skip the 6 sample accounts
"""
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, request, send_file, send_from_directory, session

import face
import mailer
from logic import DomainError, Service
from store import Store

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = (BASE_DIR.parent / "frontend" / "dist").resolve()
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
# Chat attachments: kind by MIME family, extension from the file name or a safe default.
CHAT_MEDIA_EXT = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"},
    "video": {".mp4", ".webm", ".mov", ".m4v"},
    "audio": {".webm", ".ogg", ".oga", ".m4a", ".mp3", ".wav", ".aac", ".mp4"},
}
DEFAULT_EXT = {"image": ".jpg", "video": ".mp4", "audio": ".webm"}
FB_GRAPH = "https://graph.facebook.com/v21.0"
FB_DIALOG = "https://www.facebook.com/v21.0/dialog/oauth"


def _load_dotenv(path: Path = BASE_DIR / ".env"):
    """Read KEY=value lines from backend/.env into the environment (real environment variables win)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _secret_key() -> str:
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = BASE_DIR / ".secret_key"
    if not path.exists():
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return path.read_text().strip()


def _http_get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 (fixed https Graph API URLs)
        return json.loads(r.read().decode())


def _check_facebook_app(app_id: str, secret: str) -> str | None:
    """Ask Facebook whether this App ID + secret pair is valid. Returns an error message, or None if OK."""
    url = f"{FB_GRAPH}/oauth/access_token?" + urllib.parse.urlencode(
        {"client_id": app_id, "client_secret": secret, "grant_type": "client_credentials"})
    try:
        with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 (fixed https Graph API URL)
            return None if json.loads(r.read().decode()).get("access_token") else "Facebook didn't accept these details."
    except urllib.error.HTTPError:
        return "Facebook says this App ID or App secret is wrong — copy both again from App settings → Basic."
    except Exception:  # noqa: BLE001
        return "Couldn't reach Facebook to check the details. Check your internet connection and try again."


def _save_env(path: Path, values: dict[str, str]):
    """Set KEY=value lines in backend/.env, keeping any other lines."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={values[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)  # the secret is readable only by you
    except OSError:
        pass


def _http_get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310
        return r.read()


def create_app(db_path: str | None = None, upload_dir: str | None = None, *, reply_delay_s: float = 1.2,
               sample_delay_s: float = 1.5, seed_samples: bool | None = None, config: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config.update(
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
        SECRET_KEY=_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        FACEBOOK_APP_ID=os.environ.get("FACEBOOK_APP_ID", ""),
        FACEBOOK_APP_SECRET=os.environ.get("FACEBOOK_APP_SECRET", ""),
        APP_URL=os.environ.get("APP_URL", "http://localhost:5000").rstrip("/"),
        HTTP_GET_JSON=_http_get_json,
        HTTP_GET_BYTES=_http_get_bytes,
        FB_CHECK_APP=_check_facebook_app,
        SEND_MAIL=mailer.send,
        ENV_PATH=BASE_DIR / ".env",
        FACE_MATCHER=None,  # defaults to face.default_matcher(); tests inject a fake
    )
    app.config.update(config or {})
    db_path = db_path or os.environ.get("FYM_DB", str(BASE_DIR / "findyourmate.db"))
    uploads = Path(upload_dir or os.environ.get("FYM_UPLOADS", BASE_DIR / "uploads"))
    uploads.mkdir(parents=True, exist_ok=True)
    chat_dir = uploads / "chat"
    chat_dir.mkdir(exist_ok=True)
    if seed_samples is None:
        seed_samples = os.environ.get("SEED_SAMPLE_USERS", "1") != "0"

    store = Store(db_path, seed_samples=seed_samples)
    svc = Service(store, reply_delay_s=reply_delay_s, sample_delay_s=sample_delay_s)
    app.extensions["fym_service"] = svc
    failed_logins: dict[str, deque] = defaultdict(deque)

    # ---- helpers -----------------------------------------------------------
    def body() -> dict:
        return request.get_json(silent=True) or {}

    def pw_version(user: dict) -> str:
        """Changes whenever the password changes, so older sessions are signed out after a reset."""
        return hashlib.sha256((user.get("password_hash") or "").encode()).hexdigest()[:16]

    def current_uid() -> int:
        uid = session.get("uid")
        if not uid:
            raise DomainError("Please log in", 401)
        user = store.user(uid)
        if not user or user["is_sample"] or ("pwv" in session and session["pwv"] != pw_version(user)):
            session.clear()
            raise DomainError("Please log in", 401)
        return uid

    def authed(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            return fn(current_uid(), *a, **kw)
        return wrapper

    def state(uid: int):
        return jsonify(svc.snapshot(uid, request.args.get("q", "")))

    def start_session(uid: int):
        session.clear()
        session.permanent = True
        session["uid"] = uid
        session["pwv"] = pw_version(store.user(uid))

    def matcher():
        return app.config["FACE_MATCHER"] or face.default_matcher()

    def prepare_photo(data: bytes, ext: str):
        """Resize the photo and find the face. focus: dict = face found, False = no face, None = couldn't check
        (face recognition not installed / models missing — the photo is accepted unchanged)."""
        try:
            out, out_ext, focus = matcher().prepare_photo(data, ext)
        except face.FaceError as e:
            app.logger.warning("photo face check skipped: %s", e)
            return data, ext, None
        if out_ext in (".gif", ".heic") and focus is None:
            return out, out_ext, None
        return out, out_ext, (focus if focus else False)

    def backfill_photo_focus():
        """Find faces in photos uploaded before this feature existed (runs once in the background)."""
        try:
            face.ensure_models()   # also makes the first "Verify it's me" quick
            m = matcher()
            for u in store.all_users():
                if u["is_sample"]:
                    continue
                p = u["profile"]
                fm = dict(p.get("photoFocus") or {})
                todo = [x for x in p["photos"] if x and x.startswith("/uploads/") and x not in fm]
                for url in todo:
                    path = uploads / Path(url).name
                    if path.is_file():
                        loc = m.locate(path.read_bytes())
                        if loc:
                            fm[url] = loc
                if todo and fm != (p.get("photoFocus") or {}):
                    fresh = store.user(u["id"])["profile"]       # re-read: the user may have changed photos
                    fresh["photoFocus"] = {k: v for k, v in fm.items() if k in fresh["photos"]}
                    store.save_profile(u["id"], fresh)
        except Exception as e:  # noqa: BLE001 - best effort
            app.logger.warning("photo focus backfill skipped: %s", e)

    if app.config["FACE_MATCHER"] is None and not app.config.get("TESTING"):
        threading.Thread(target=backfill_photo_focus, daemon=True).start()

    def fb_enabled() -> bool:
        return bool(app.config["FACEBOOK_APP_ID"] and app.config["FACEBOOK_APP_SECRET"])

    def fb_base(origin: str | None) -> str:
        """Where Facebook should send the user back: the address the app was opened on when that's this
        computer (any localhost port, so the Vite dev server works), otherwise APP_URL."""
        default = app.config["APP_URL"]
        if not origin:
            return default
        parsed = urllib.parse.urlsplit(origin)
        if parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1") and not parsed.path.strip("/"):
            return f"{parsed.scheme}://{parsed.netloc}"
        return default

    def throttle(key: str):
        q = failed_logins[key]
        now = time.time()
        while q and now - q[0] > 900:
            q.popleft()
        if len(q) >= 10:
            raise DomainError("Too many attempts. Try again in a few minutes.", 429)

    @app.before_request
    def enforce_chat_deadlines():
        # Auto-close chats where 72h passed without either person confirming.
        if request.path.startswith("/api/") and not request.path.startswith("/api/auth/facebook"):
            svc.expire_overdue()

    @app.errorhandler(DomainError)
    def domain_error(err: DomainError):
        return jsonify({"error": err.message}), err.status

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "File is too large (max 25 MB)"}), 413

    # ---- auth --------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    def local_request() -> bool:
        """Setup is only offered to someone using the app on this computer (not when deployed)."""
        host = (request.host or "").split(":")[0]
        return request.remote_addr in ("127.0.0.1", "::1") and host in ("localhost", "127.0.0.1")

    @app.get("/api/auth/config")
    def auth_config():
        return {"facebook": fb_enabled(), "canSetupFacebook": not fb_enabled() and local_request()}

    @app.post("/api/auth/facebook/setup")
    def facebook_setup():
        """Save your Facebook app's ID + secret from the login screen (localhost only) — no restart needed."""
        if not local_request():
            raise DomainError("Facebook login can only be set up from the computer running the app.", 403)
        data = body()
        app_id = str(data.get("appId") or "").strip()
        secret = str(data.get("appSecret") or "").strip()
        if not app_id.isdigit() or not 5 <= len(app_id) <= 25:
            raise DomainError("The App ID is a number, e.g. 1234567890123456 (App settings → Basic).", 400)
        if not secret or not secret.isalnum() or len(secret) < 16:
            raise DomainError("Paste the App secret from App settings → Basic (click Show to reveal it).", 400)
        problem = app.config["FB_CHECK_APP"](app_id, secret)
        if problem:
            raise DomainError(problem, 400)
        _save_env(Path(app.config["ENV_PATH"]), {"FACEBOOK_APP_ID": app_id, "FACEBOOK_APP_SECRET": secret})
        app.config.update(FACEBOOK_APP_ID=app_id, FACEBOOK_APP_SECRET=secret)
        return {"facebook": True}

    @app.get("/api/auth/me")
    def auth_me():
        uid = current_uid()
        u = store.user(uid)
        return {"id": uid, "name": u["profile"]["name"], "email": u["email"]}

    @app.post("/api/auth/register")
    def register():
        b = body()
        uid = svc.register(b.get("name", ""), b.get("email", ""), b.get("password", ""))
        start_session(uid)
        return state(uid)

    @app.post("/api/auth/login")
    def login():
        b = body()
        key = f"{(b.get('email') or '').lower()}|{request.remote_addr}"
        throttle(key)
        try:
            uid = svc.login(b.get("email", ""), b.get("password", ""))
        except DomainError:
            failed_logins[key].append(time.time())
            raise
        failed_logins.pop(key, None)
        start_session(uid)
        return state(uid)

    # ---- forgot / reset / change password -----------------------------------
    RESET_TTL_MS = 30 * 60 * 1000

    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def notify_password_changed(user: dict):
        if not user.get("email"):
            return
        try:
            app.config["SEND_MAIL"](user["email"], "Your FindYourMate password was changed",
                                    "Your FindYourMate password was just changed and other devices were signed out.\n\n"
                                    "If this wasn't you, use “Forgot password?” on the login screen right away.")
        except mailer.MailError as e:
            app.logger.warning("%s", e)

    @app.post("/api/auth/forgot")
    def forgot_password():
        """Email a one-time reset link. The reply is the same whether or not the email has an account."""
        b = body()
        email = (b.get("email") or "").strip().lower()
        if "@" not in email:
            raise DomainError("Please enter the email address you signed up with", 400)
        key = f"forgot|{email}|{request.remote_addr}"
        throttle(key)
        failed_logins[key].append(time.time())          # at most 10 emails per 15 minutes per address
        user = store.user_by_email(email)
        sent = None
        if user and not user["is_sample"]:
            token = secrets.token_urlsafe(32)
            store.add_password_reset(token_hash(token), user["id"], RESET_TTL_MS)
            link = f"{fb_base(b.get('origin'))}/?reset={token}"
            name = user["profile"].get("name") or "there"
            try:
                sent = app.config["SEND_MAIL"](
                    email, "Reset your FindYourMate password",
                    f"Hi {name},\n\nTap the link below to choose a new FindYourMate password. "
                    f"It works once and expires in 30 minutes.\n\n{link}\n\n"
                    "If you didn't ask for this, you can ignore this email — your password won't change.",
                    f"<p>Hi {html.escape(name)},</p><p>Tap the button below to choose a new FindYourMate password. "
                    f"It works once and expires in 30 minutes.</p>"
                    f"<p><a href='{html.escape(link)}' style='background:#111;color:#fff;padding:10px 18px;"
                    f"border-radius:999px;text-decoration:none;display:inline-block'>Reset password</a></p>"
                    f"<p style='color:#777;font-size:13px'>If you didn't ask for this, you can ignore this email — "
                    f"your password won't change.</p>")
            except mailer.MailError as e:
                app.logger.warning("%s", e)
                raise DomainError("We couldn't send the email right now. Please try again in a few minutes.", 503)
        out = {"ok": True, "message": "If an account uses that email, we've sent a link to reset the password. "
                                      "It expires in 30 minutes — check your spam folder too."}
        if not mailer.configured() and local_request() and app.config["SEND_MAIL"] is mailer.send:
            out["devNote"] = ("Email sending isn't set up yet (SMTP in backend/.env), so the reset link was printed "
                              "in the backend terminal instead.")
        return out

    @app.get("/api/auth/reset/check")
    def reset_check():
        r = store.password_reset(token_hash(request.args.get("token", "")))
        if not r:
            return {"valid": False}
        email = store.user(r["user_id"])["email"] or ""
        name, _, domain = email.partition("@")
        return {"valid": True, "email": f"{name[:2]}{'•' * max(1, len(name) - 2)}@{domain}"}

    @app.post("/api/auth/reset")
    def reset_password():
        b = body()
        r = store.password_reset(token_hash(b.get("token") or ""))
        if not r:
            raise DomainError("This reset link is invalid or has expired. Ask for a new one.", 400)
        svc.set_password(r["user_id"], b.get("password") or "")
        notify_password_changed(store.user(r["user_id"]))
        start_session(r["user_id"])                     # signs out every other device
        return state(r["user_id"])

    @app.post("/api/auth/change-password")
    @authed
    def change_password(uid):
        b = body()
        key = f"change|{uid}"
        throttle(key)
        try:
            svc.change_password(uid, b.get("current") or "", b.get("password") or "")
        except DomainError:
            failed_logins[key].append(time.time())
            raise
        notify_password_changed(store.user(uid))
        start_session(uid)                              # keep this device signed in, sign out the others
        return state(uid)

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return {"ok": True}

    @app.get("/api/auth/facebook/start")
    def facebook_start():
        base = fb_base(request.args.get("origin"))
        if not fb_enabled():
            return redirect(f"{base}/?auth_error=" + urllib.parse.quote(
                "Facebook login isn't set up on this server yet."))
        session["fb_state"] = secrets.token_urlsafe(24)
        session["fb_base"] = base
        # "Link Facebook" from Settings: attach the Facebook account to the logged-in user.
        session["fb_link"] = bool(request.args.get("link")) and bool(session.get("uid"))
        params = {
            "client_id": app.config["FACEBOOK_APP_ID"],
            "redirect_uri": f"{base}/api/auth/facebook/callback",
            "state": session["fb_state"],
            "scope": "public_profile,email",
            "response_type": "code",
        }
        return redirect(f"{FB_DIALOG}?{urllib.parse.urlencode(params)}")

    @app.get("/api/auth/facebook/callback")
    def facebook_callback():
        base = session.pop("fb_base", None) or app.config["APP_URL"]
        linking = session.pop("fb_link", False)
        home = base + "/"

        def fail(msg):
            return redirect(home + "?auth_error=" + urllib.parse.quote(msg))

        if request.args.get("error"):
            return fail("Facebook login was cancelled.")
        expected = session.pop("fb_state", None)
        if not expected or request.args.get("state") != expected:
            return fail("Facebook login expired. Please try again.")
        code = request.args.get("code")
        if not code:
            return fail("Facebook didn't return a login code.")
        try:
            token = app.config["HTTP_GET_JSON"](f"{FB_GRAPH}/oauth/access_token?" + urllib.parse.urlencode({
                "client_id": app.config["FACEBOOK_APP_ID"],
                "client_secret": app.config["FACEBOOK_APP_SECRET"],
                "redirect_uri": f"{base}/api/auth/facebook/callback",
                "code": code,
            }))["access_token"]
            fb = app.config["HTTP_GET_JSON"](f"{FB_GRAPH}/me?" + urllib.parse.urlencode({
                "fields": "id,name,email,picture.width(720).height(720)", "access_token": token}))
        except Exception:  # noqa: BLE001 - any network/Graph error -> friendly message
            return fail("Couldn't reach Facebook. Please try again.")
        if not fb.get("id"):
            return fail("Facebook didn't share your account details. Please try again.")
        if linking:
            uid = session.get("uid")
            owner = store.user_by_facebook(fb["id"])
            if owner and owner["id"] != uid:
                return fail("That Facebook account is already used by another FindYourMate account.")
            if not owner:
                store.link_facebook(uid, fb["id"])
                store.add_event(uid, "Facebook account linked — you can now log in with Facebook", "RECOMMENDED")
            return redirect(home + "?auth_notice=" + urllib.parse.quote("Facebook linked ✓ — you can log in with it now"))
        picture = picture_focus = None
        pic_url = (((fb.get("picture") or {}).get("data") or {}).get("url"))
        if pic_url and not store.user_by_facebook(fb["id"]):
            try:
                data, ext, picture_focus = prepare_photo(app.config["HTTP_GET_BYTES"](pic_url), ".jpg")
                name = f"{uuid.uuid4().hex}{ext}"
                (uploads / name).write_bytes(data)
                picture = f"/uploads/{name}"
            except Exception:  # noqa: BLE001 - profile picture is optional
                picture = None
        uid = svc.login_facebook(fb, picture, picture_focus or None if picture else None)
        start_session(uid)
        return redirect(home)

    def erase_account(uid: int):
        for url in svc.delete_account(uid):
            rel = url.removeprefix("/uploads/")
            target = (uploads / rel).resolve()
            if uploads.resolve() in target.parents:
                target.unlink(missing_ok=True)

    @app.delete("/api/account")
    @authed
    def delete_account(uid):
        erase_account(uid)
        session.clear()
        return {"ok": True}

    def parse_signed_request(signed: str) -> dict | None:
        """Facebook's signed_request: base64url(signature).base64url(json), HMAC-SHA256 with the app secret."""
        try:
            sig_b64, payload_b64 = signed.split(".", 1)
            pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
            sig = base64.urlsafe_b64decode(pad(sig_b64))
            data = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
        except Exception:  # noqa: BLE001
            return None
        expected = hmac.new(app.config["FACEBOOK_APP_SECRET"].encode(), payload_b64.encode(), hashlib.sha256).digest()
        if data.get("algorithm", "").upper() != "HMAC-SHA256" or not hmac.compare_digest(sig, expected):
            return None
        return data

    @app.post("/api/auth/facebook/data-deletion")
    def facebook_data_deletion():
        """Facebook "User Data Deletion" callback. Called by Facebook when someone removes this app in their
        Facebook settings and asks for their data to be deleted.
        Facebook-only accounts are deleted completely (profile, photos, chats, connections);
        accounts that also have an email + password are unlinked from Facebook and keep the rest."""
        if not fb_enabled():
            return jsonify(error="Facebook login isn't set up"), 400
        data = parse_signed_request(request.form.get("signed_request", ""))
        if not data or not data.get("user_id"):
            return jsonify(error="Invalid signed_request"), 400
        code = secrets.token_hex(8)
        user = store.user_by_facebook(str(data["user_id"]))
        if not user:
            result = "No FindYourMate data was linked to this Facebook account."
        elif user["password_hash"]:
            store.link_facebook(user["id"], None)
            store.add_event(user["id"], "Facebook was unlinked at your request — log in with your email now",
                            "RECOMMENDED")
            result = "The Facebook link was removed. The account also uses an email login, so its profile was kept."
        else:
            erase_account(user["id"])
            result = "The account, its photos, chats and connections were permanently deleted."
        store.add_deletion_request(code, result)
        status_url = f"{fb_base(None)}/api/auth/facebook/deletion-status?code={code}"
        return jsonify(url=status_url, confirmation_code=code)

    @app.get("/api/auth/facebook/deletion-status")
    def facebook_deletion_status():
        """Status page Facebook links people to after a deletion request."""
        req = store.deletion_request(request.args.get("code", ""))
        if not req:
            body_html = "<p>We couldn't find a deletion request with that confirmation code.</p>"
        else:
            body_html = (f"<p><b>Confirmation code:</b> {html.escape(req['code'])}</p>"
                         f"<p><b>Status:</b> Completed</p><p>{html.escape(req['result'])}</p>")
        return (f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                f"<title>FindYourMate data deletion</title>"
                f"<body style='font-family:system-ui;max-width:560px;margin:40px auto;padding:0 16px;line-height:1.5'>"
                f"<h1>FindYourMate data deletion</h1>{body_html}</body>"), 200, {"Content-Type": "text/html; charset=utf-8"}

    # ---- app state & profile ----------------------------------------------
    @app.get("/api/state")
    @authed
    def get_state(uid):
        return state(uid)

    @app.put("/api/profile")
    @authed
    def put_profile(uid):
        # Saving from an Edit dialog also confirms the profile (makes it visible in Discover).
        svc.update_profile(uid, body(), confirm=bool(body().get("confirm")))
        store.add_event(uid, body().get("_event") or "Updated profile", "RECOMMENDED")
        return state(uid)

    @app.post("/api/profile/verify-photo")
    @authed
    def verify_photo(uid):
        # Frames captured from the live selfie video are compared with the main photo (face.py).
        # They're processed in memory and never stored.
        main = store.user(uid)["profile"]["photos"][0]
        if not main:
            raise DomainError("Add a main photo before verifying", 400)
        if not main.startswith("/uploads/") or not (uploads / Path(main).name).is_file():
            raise DomainError("Your main photo can't be found — upload it again, then verify.", 400)
        frames = [f.read() for f in request.files.getlist("frames")][:12]
        if not frames:
            raise DomainError("No selfie frames were received — record the selfie video again.", 400)
        matcher = app.config["FACE_MATCHER"] or face.default_matcher()
        try:
            result = matcher.verify((uploads / Path(main).name).read_bytes(), frames)
        except face.FaceError as e:
            raise DomainError(str(e), 422) from e
        if not result.matched:
            store.add_event(uid, f"Selfie didn't match main photo ({result.percent}%)", "RECOMMENDED")
            raise DomainError(f"The selfie doesn't look like the person in your main photo (similarity "
                              f"{result.percent}%, needs {round(face.MATCH_THRESHOLD * 100)}%). Make sure your main "
                              f"photo shows your face clearly and try again in good light.", 422)
        svc.verify_photo(uid, result.percent)
        return state(uid)


    @app.post("/api/photos/<int:slot>")
    @authed
    def upload_photo(uid, slot: int):
        f = request.files.get("photo")
        if not f or not f.filename:
            raise DomainError("Choose an image to upload", 400)
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXT or not (f.mimetype or "").startswith("image/"):
            raise DomainError("Photos must be JPG, PNG, WEBP, GIF or HEIC", 400)
        if not 0 <= slot < 9:
            raise DomainError("Photo slot must be 0-8", 400)
        data, ext, focus = prepare_photo(f.read(), ext)
        if slot == 0 and focus is False:
            raise DomainError("We couldn't find a face in this photo. Your main photo is shown on Discover, Connection "
                              "and your profile, so choose one where your face is clearly visible.", 400)
        name = f"{uuid.uuid4().hex}{ext}"
        (uploads / name).write_bytes(data)
        old = store.user(uid)["profile"]["photos"][slot]
        svc.set_photo(uid, slot, f"/uploads/{name}", focus or None)
        if old and old.startswith("/uploads/"):
            (uploads / Path(old).name).unlink(missing_ok=True)
        store.add_event(uid, f"Added photo {slot + 1}", "RECOMMENDED")
        return state(uid)

    @app.delete("/api/photos/<int:slot>")
    @authed
    def delete_photo(uid, slot: int):
        old = store.user(uid)["profile"]["photos"][slot] if 0 <= slot < 9 else None
        svc.set_photo(uid, slot, None)
        if old and old.startswith("/uploads/"):
            (uploads / Path(old).name).unlink(missing_ok=True)
        return state(uid)

    @app.get("/uploads/<path:name>")
    def serve_upload(name: str):
        if name.startswith("chat/") or "/" in name:
            # Chat media is private: only served via /api/media/<id> to the two people in the chat.
            return jsonify({"error": "Not found"}), 404
        return send_from_directory(uploads, name)

    # ---- discover & connection ---------------------------------------------
    @app.post("/api/candidates/<cid>/like")
    @authed
    def like(uid, cid):
        svc.like(uid, cid)
        return state(uid)

    @app.post("/api/candidates/<cid>/pass")
    @authed
    def pass_candidate(uid, cid):
        svc.pass_candidate(uid, cid)
        return state(uid)

    @app.post("/api/connection/accept")
    @authed
    def accept(uid):
        svc.accept_invite(uid, body().get("candidateId"))
        return state(uid)

    @app.post("/api/connection/confirm")
    @authed
    def confirm(uid):
        svc.confirm_relationship(uid)
        return state(uid)

    @app.post("/api/connection/close")
    @authed
    def close(uid):
        svc.close_relationship(uid)
        return state(uid)

    @app.post("/api/connection/engage")
    @authed
    def engage(uid):
        svc.engage(uid)
        return state(uid)

    @app.post("/api/connection/engage/accept")
    @authed
    def engage_accept(uid):
        svc.accept_engagement(uid)
        return state(uid)

    @app.post("/api/connection/engage/decline")
    @authed
    def engage_decline(uid):
        svc.decline_engagement(uid)
        return state(uid)

    @app.post("/api/connection/engage/cancel")
    @authed
    def engage_cancel(uid):
        svc.cancel_engagement(uid)
        return state(uid)

    @app.get("/api/connections/<int:conn_id>/messages")
    @authed
    def past_messages(uid, conn_id: int):
        return jsonify({"messages": svc.past_messages(uid, conn_id)})

    @app.post("/api/messages")
    @authed
    def send_message(uid):
        """JSON {text} for text, or multipart with `text` (optional caption) and `file` (image/video/audio)."""
        f = request.files.get("file")
        if not f:
            svc.send_message(uid, body().get("text", ""))
            return state(uid)
        mime = (f.mimetype or "").split(";")[0].strip().lower()
        kind = mime.split("/")[0]
        if kind not in CHAT_MEDIA_EXT:
            raise DomainError("You can send photos, videos and voice messages", 400)
        ext = Path(f.filename or "").suffix.lower()
        if ext not in CHAT_MEDIA_EXT[kind]:
            ext = DEFAULT_EXT[kind]
        name = f"{uuid.uuid4().hex}{ext}"
        f.save(chat_dir / name)
        try:
            svc.send_message(uid, request.form.get("text", ""), {"file": name, "type": mime, "kind": kind})
        except DomainError:
            (chat_dir / name).unlink(missing_ok=True)
            raise
        return state(uid)

    @app.get("/api/media/<int:msg_id>")
    @authed
    def chat_media(uid, msg_id: int):
        m = svc.media_for(uid, msg_id)
        path = chat_dir / m["media_file"]
        if not path.exists():
            raise DomainError("Not found", 404)
        resp = send_file(path, mimetype=m["media_type"] or None, conditional=True)  # supports video seeking
        resp.headers["Cache-Control"] = "private, max-age=86400"
        return resp

    @app.delete("/api/events")
    @authed
    def clear_events(uid):
        store.clear_events(uid)
        return state(uid)

    # ---- built frontend ----------------------------------------------------
    @app.get("/")
    @app.get("/<path:path>")
    def spa(path: str = ""):
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        if not DIST_DIR.exists():
            return ("Frontend not built. Run `npm install && npm run build` in frontend/, "
                    "or `npm run dev` and open http://localhost:5173."), 200
        target = (DIST_DIR / path).resolve()
        if path and target.is_file() and DIST_DIR in target.parents:
            return send_from_directory(DIST_DIR, path)
        return send_from_directory(DIST_DIR, "index.html")

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    create_app().run(host="0.0.0.0", port=port, debug=False, threaded=True)
