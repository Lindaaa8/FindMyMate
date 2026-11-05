"""Business rules: accounts, profiles, AI-ranked discovery and the two-sided connection state machine.

Connection rows are stored neutrally (user_a liked user_b):
    PENDING -> CHATTING -> DATING -> CLOSED
and shown to each person from their own side:
    PENDING is INVITED for user_a and FAVOURED for user_b.

Rules:
  * Pending invitations (INVITED / FAVOURED) don't lock anyone: you can send and receive several,
    and keep liking or passing on other people.
  * Accepting starts CHATTING (72h commitment timer) and locks BOTH people into this one connection:
    every other pending invitation involving either of them is cancelled, they leave Discover,
    and neither can like anyone new until the connection is closed.
  * DATING only when BOTH confirm; both statuses become "In Relationship".
  * Either person can close; both statuses reset to Single and both re-enter the pool.
  * Sample accounts (seeded) reply automatically so the app is usable with few sign-ups.
"""
import copy
import random
import re
import threading

from werkzeug.security import check_password_hash, generate_password_hash

import ranking
from seed_data import (AUTO_REPLIES, CHAT_COMMITMENT_MS, GENDER_PREF_OPTIONS, IDEAL_TEXT_FIELDS,
                       MARRIAGE_STATUS_OPTIONS, NEW_PROFILE, PROFILE_TEXT_FIELDS)
from store import Store, now_ms

PALETTE = ["#a78bfa", "#f472b6", "#facc15", "#60a5fa", "#34d399", "#fb7185", "#f59e0b", "#22d3ee", "#c084fc"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DomainError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def run_later(delay_s: float, fn):
    """Run fn after delay_s on a daemon thread (synchronously when delay is 0, e.g. in tests)."""
    if delay_s <= 0:
        fn()
        return
    t = threading.Timer(delay_s, fn)
    t.daemon = True
    t.start()


def public_profile(user: dict) -> dict:
    """What other people can see. Never includes email, password or Facebook id."""
    p = user["profile"]
    photos = [x for x in p["photos"] if x]
    return {
        "id": user["id"],
        "isSample": user["is_sample"],
        "name": p.get("name") or "Member",
        "age": ranking.age_of(p),
        "gender": p.get("gender", ""),
        "education": p.get("education", ""),
        "ethnicity": p.get("ethnicity", ""),
        "nationality": p.get("nationality", ""),
        "faith": p.get("faith", ""),
        "career": p.get("career", ""),
        "location": p.get("location", ""),
        "height": p.get("height", ""),
        "bio": p.get("bio", ""),
        "hobbies": p.get("hobbies", ""),
        "hometown": p.get("hometown", ""),
        "mbti": p.get("mbti", ""),
        "skin": p.get("skin", ""),
        "color": p.get("color") or PALETTE[user["id"] % len(PALETTE)],
        "photos": [x for x in photos if not x.startswith("placeholder:")],
        # Where the face is in each photo, so every page can keep it in view (see face.locate).
        "photoFocus": {u: f for u, f in (p.get("photoFocus") or {}).items() if u in photos},
        "photoCount": len(photos),
        "photoVerified": p.get("photoVerified", False),
        "marriageVerified": p.get("marriageVerified", False),
        "relationshipStatus": p.get("marriageStatus", "Single"),
        "ideal": {k: p["ideal"].get(k, "") for k in ("education", "occupation", "location", "genderPreference", "age")},
    }


def _cm_or_error(value, label: str) -> str:
    """Heights are stored as whole centimetres ("168"); older formats (5'6, 66 in) are converted."""
    cm = value if isinstance(value, (int, float)) else ranking.height_cm(value)
    if cm is None or not 100 <= cm <= 250:
        raise DomainError(f"{label} must be in centimetres, e.g. 168", 400)
    return str(round(cm))


class Service:
    def __init__(self, store: Store, reply_delay_s: float = 1.2, sample_delay_s: float = 1.5):
        self.store = store
        self.reply_delay_s = reply_delay_s
        self.sample_delay_s = sample_delay_s

    # ================================================================ auth ==
    def register(self, name: str, email: str, password: str) -> int:
        name = (name or "").strip()
        email = (email or "").strip().lower()
        if not name:
            raise DomainError("Please enter your name", 400)
        if not EMAIL_RE.match(email):
            raise DomainError("Please enter a valid email address", 400)
        if len(password or "") < 8:
            raise DomainError("Password must be at least 8 characters", 400)
        if self.store.user_by_email(email):
            raise DomainError("An account with this email already exists. Log in instead.", 409)
        profile = copy.deepcopy(NEW_PROFILE)
        profile["name"] = name[:60]
        uid = self.store.create_user(email=email, password_hash=generate_password_hash(password), profile=profile)
        self.store.add_event(uid, "Account created", "RECOMMENDED")
        return uid

    def login(self, email: str, password: str) -> int:
        user = self.store.user_by_email((email or "").strip().lower())
        if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password or ""):
            raise DomainError("Email or password is incorrect", 401)
        return user["id"]

    def set_password(self, uid: int, password: str):
        if len(password or "") < 8:
            raise DomainError("Password must be at least 8 characters", 400)
        self.store.set_password_hash(uid, generate_password_hash(password))
        self.store.clear_password_resets(uid)
        self.store.add_event(uid, "Password changed", "RECOMMENDED")

    def change_password(self, uid: int, current: str, new: str):
        user = self.me(uid)
        if not user["password_hash"]:
            raise DomainError("Your account has no password yet — use “Email me a reset link” to set one.", 400)
        if not check_password_hash(user["password_hash"], current or ""):
            raise DomainError("Your current password is incorrect", 401)
        if current == new:
            raise DomainError("Choose a new password that's different from the current one", 400)
        self.set_password(uid, new)

    def login_facebook(self, fb: dict, picture_path: str | None = None, picture_focus: dict | None = None) -> int:
        """fb = {'id', 'name', 'email'?}. Links to an existing account with the same email, else creates one."""
        user = self.store.user_by_facebook(fb["id"])
        if user:
            return user["id"]
        email = (fb.get("email") or "").strip().lower() or None
        if email:
            existing = self.store.user_by_email(email)
            if existing:
                self.store.link_facebook(existing["id"], fb["id"])
                return existing["id"]
        profile = copy.deepcopy(NEW_PROFILE)
        profile["name"] = (fb.get("name") or "")[:60]
        if picture_path:
            profile["photos"][0] = picture_path
            if picture_focus:
                profile["photoFocus"] = {picture_path: picture_focus}
        uid = self.store.create_user(email=email, facebook_id=fb["id"], profile=profile)
        self.store.add_event(uid, "Account created with Facebook", "RECOMMENDED")
        return uid

    def me(self, uid: int) -> dict:
        user = self.store.user(uid)
        if not user or user["is_sample"]:
            raise DomainError("Not logged in", 401)
        return user

    def delete_account(self, uid: int) -> list[str]:
        user = self.me(uid)
        if self.store.active_connection(uid):
            self.close_relationship(uid, force=True)
        for conn in self.store.pending_for(uid):
            self.pass_candidate(uid, self._other_id(conn, uid))
        chat_media = self.store.delete_user(uid)
        photos = [p for p in user["profile"]["photos"] if p and p.startswith("/uploads/")]
        return photos + [f"/uploads/chat/{m}" for m in chat_media]

    # ============================================================ snapshot ==
    def _view_state(self, conn: dict, uid: int) -> str:
        if conn["state"] == "PENDING":
            return "INVITED" if conn["user_a"] == uid else "FAVOURED"
        return conn["state"]

    def _other_id(self, conn: dict, uid: int) -> int:
        return conn["user_b"] if conn["user_a"] == uid else conn["user_a"]

    def _confirmed(self, conn: dict, uid: int) -> tuple[bool, bool]:
        mine = conn["a_confirmed"] if conn["user_a"] == uid else conn["b_confirmed"]
        theirs = conn["b_confirmed"] if conn["user_a"] == uid else conn["a_confirmed"]
        return bool(mine), bool(theirs)

    @staticmethod
    def is_single(profile: dict) -> bool:
        """Only Single profiles can be matched; Dating / In Relationship / Engaged are ignored."""
        return (profile.get("marriageStatus") or "Single").strip().lower() == "single"

    def discover_pool(self, uid: int) -> list[dict]:
        """Everyone who could appear in this user's Discover (before requirement filtering):
        saved + verified Single profiles that aren't locked into someone else's accepted connection."""
        busy = self.store.active_user_ids()
        active = self.store.active_connection(uid)
        partner = self._other_id(active, uid) if active else None
        # People who liked you can show up in your Discover even before they've verified their photo.
        liked_me = {c["user_a"] for c in self.store.pending_for(uid) if c["user_b"] == uid}
        pool = []
        for u in self.store.all_users():
            if u["id"] == uid:
                continue
            p = u["profile"]
            if not self.is_single(p):
                continue
            visible = p.get("confirmed") and (u["is_sample"] or p.get("photoVerified") or u["id"] in liked_me)
            if u["id"] == partner or (visible and u["id"] not in busy):
                pool.append(u)
        return pool

    def snapshot(self, uid: int, query: str = "") -> dict:
        me = self.me(uid)
        profile = me["profile"]
        active = self.store.active_connection(uid)
        passes = self.store.passes(uid)
        pool = self.discover_pool(uid)
        public = {u["id"]: public_profile(u) for u in pool}
        # The ranker sees each person's full partner preferences; only `public` goes to the browser.
        ranked = ranking.rank(profile, [{**public[u["id"]], "ideal": u["profile"]["ideal"]} for u in pool], query)
        partner_id = self._other_id(active, uid) if active else None
        pending = self.store.pending_for(uid)
        pending_state = {self._other_id(c, uid): self._view_state(c, uid) for c in pending}
        matches = []
        for m in ranked:
            pub = public[m["id"]]
            state = "RECOMMENDED"
            if m["id"] == partner_id:
                state = self._view_state(active, uid)
            elif m["id"] in pending_state:
                state = pending_state[m["id"]]
            elif m["id"] in passes:
                state = "CLOSED"
            matches.append({**pub, "tier": m["tier"], "matchScore": m["matchScore"], "reasons": m["reasons"],
                            "rank": m["rank"], "connectionState": state})

        active_view = None
        messages = []
        if active:
            other = self.store.user(partner_id)
            mine, theirs = self._confirmed(active, uid)
            deadline = active["chatting_started_at"] + CHAT_COMMITMENT_MS if active["chatting_started_at"] else None
            # Once either person confirms, the 72h limit no longer applies (no auto-close).
            no_limit = bool(mine or theirs)
            active_view = {
                "id": active["id"], "candidateId": partner_id, "state": self._view_state(active, uid),
                "updatedAt": active["updated_at"], "chattingStartedAt": active["chatting_started_at"],
                "chatDeadline": deadline if active["state"] == "CHATTING" and not no_limit else None,
                "noTimeLimit": no_limit if active["state"] == "CHATTING" else False,
                "meConfirmed": mine, "themConfirmed": theirs,
                # Engagement needs the partner's approval: "sent" (you asked), "received" (they asked) or None.
                "engageRequest": (None if not active.get("engage_requested_by") else
                                  "sent" if active["engage_requested_by"] == uid else "received"),
                "candidate": public_profile(other) if other else None,
            }
            ranked_partner = next((m for m in matches if m["id"] == partner_id), None)
            if active_view["candidate"] and ranked_partner:
                active_view["candidate"].update(matchScore=ranked_partner["matchScore"], reasons=ranked_partner["reasons"])
            messages = [{"id": m["id"], "from": "system" if m["kind"] == "system" else "me" if m["sender_id"] == uid else "them", "text": m["text"],
                         "at": m["at"], "kind": m["kind"] or "text",
                         "mediaUrl": f"/api/media/{m['id']}" if m["media_file"] else None,
                         "mediaType": m["media_type"]}
                        for m in self.store.messages(active["id"], uid)]

        invitations = []
        corpus = [{**public[u["id"]], "ideal": u["profile"]["ideal"]} for u in pool]
        for c in pending:
            other = self.store.user(self._other_id(c, uid))
            if not other:
                continue
            pub = public_profile(other)
            ranked_other = next((m for m in matches if m["id"] == other["id"]), None)
            if ranked_other:
                pub.update(matchScore=ranked_other["matchScore"], reasons=ranked_other["reasons"])
            else:  # not in your Discover (e.g. outside your requirements) - still score them
                score, reasons = ranking.pair_score(profile, {**pub, "ideal": other["profile"]["ideal"]}, corpus)
                pub.update(matchScore=score, reasons=reasons)
            other_full = {**pub, "ideal": other["profile"]["ideal"]}
            missed = ranking.requirement_report(profile, other_full)
            invitations.append({"id": c["id"], "candidateId": other["id"], "state": self._view_state(c, uid),
                                "likedAt": c["created_at"], "updatedAt": c["updated_at"], "candidate": pub,
                                # Evaluation: do they meet your must-match requirements (and you theirs)?
                                "meetsRequirements": not missed, "missedRequirements": missed,
                                "twoWay": not missed and ranking.meets_requirements(other["profile"], profile),
                                "inDiscover": ranked_other is not None})
        # People who liked you: highest match score first; same score -> whoever liked you first.
        # Then invitations you sent, newest first.
        received = sorted((i for i in invitations if i["state"] == "FAVOURED"),
                          key=lambda i: (-i["candidate"]["matchScore"], i["likedAt"], i["id"]))
        sent = sorted((i for i in invitations if i["state"] == "INVITED"), key=lambda i: -i["likedAt"])
        invitations = received + sent

        conns = self.store.connections_for(uid)
        counts = {s: 0 for s in ["RECOMMENDED", "FAVOURED", "INVITED", "CHATTING", "DATING", "ENGAGED", "CLOSED"]}
        for c in conns:
            counts[self._view_state(c, uid)] += 1
        events = self.store.events(uid)
        names = {u["id"]: u["profile"].get("name") for u in self.store.all_users()}
        for e in events:
            e["otherName"] = names.get(e["otherId"])
        return {
            "now": now_ms(),
            "me": {"id": uid, "email": me["email"], "facebook": bool(me["facebook_id"]),
                   "hasPassword": bool(me["password_hash"])},
            "profile": profile,
            "userStatus": ("engaged" if active and active["state"] == "ENGAGED" else
                           "in_a_relationship" if active and active["state"] == "DATING" else "single"),
            "pastChats": self._past_chats(uid),
            "isAvailable": active is None,
            "active": active_view,
            "invitations": invitations,
            "messages": messages,
            "matches": matches,
            "stateCounts": counts,
            "events": events,
            "stats": {"connections": len(conns), "messages": self.store.message_count(uid),
                      "events": len(events), "people": len(pool)},
            "options": {"bioGender": GENDER_PREF_OPTIONS, "genderPreference": GENDER_PREF_OPTIONS,
                        "marriageStatus": MARRIAGE_STATUS_OPTIONS},
        }

    # ============================================================= profile ==
    def update_profile(self, uid: int, patch: dict, *, confirm: bool = False) -> dict:
        profile = self.me(uid)["profile"]
        for key in PROFILE_TEXT_FIELDS:
            if key in patch:
                value = str(patch[key] or "").strip()
                if key == "age" and value and (not value.isdigit() or not 18 <= int(value) <= 99):
                    raise DomainError("Age must be a number from 18 to 99", 400)
                if key == "height" and value:
                    value = _cm_or_error(value, "Height")
                if key == "name" and not value:
                    raise DomainError("Name can't be empty", 400)
                profile[key] = value[:60] if key == "name" else value[:2000]
        if "gender" in patch:
            if patch["gender"] not in GENDER_PREF_OPTIONS:
                raise DomainError(f"Gender must be one of: {', '.join(GENDER_PREF_OPTIONS)}", 400)
            profile["gender"] = patch["gender"]
        if "marriageStatus" in patch:
            if patch["marriageStatus"] not in MARRIAGE_STATUS_OPTIONS:
                raise DomainError("Invalid relationship status", 400)
            active = self.store.active_connection(uid)
            if active and active["state"] in ("DATING", "ENGAGED"):
                raise DomainError("Status is managed by your relationship while dating", 409)
            if patch["marriageStatus"] != profile["marriageStatus"]:
                profile["marriageVerified"] = False
            profile["marriageStatus"] = patch["marriageStatus"]
        ideal_patch = patch.get("ideal") or {}
        for key in IDEAL_TEXT_FIELDS + ["otherRequirement"]:
            if key in ideal_patch:
                value = str(ideal_patch[key] or "").strip()[:500]
                if key == "height" and value and not ranking.is_no_pref(value):
                    value = _cm_or_error(ranking.min_height_cm(value) or value, "Minimum height")
                profile["ideal"][key] = value
        if "genderPreference" in ideal_patch:
            if ideal_patch["genderPreference"] not in GENDER_PREF_OPTIONS:
                raise DomainError(f"Looking for must be one of: {', '.join(GENDER_PREF_OPTIONS)}", 400)
            profile["ideal"]["genderPreference"] = ideal_patch["genderPreference"]
        if "age" in ideal_patch:
            rng = ranking.parse_age_range(str(ideal_patch["age"]))
            if not rng or rng[0] < 18:
                raise DomainError("Age range must be like 24-32 (minimum 18)", 400)
            profile["ideal"]["age"] = f"{rng[0]}-{rng[1]}"
        profile["saved"] = True
        # Any dialog can be saved in any order (e.g. Ideal partner before Bio). The profile only becomes
        # confirmed (eligible for Discover / liking) once the bio has name, gender and age.
        if confirm and all(profile.get(key) for key in ("name", "gender", "age")):
            profile["confirmed"] = True
        self.store.save_profile(uid, profile)
        return profile

    def set_photo(self, uid: int, slot: int, url: str | None, focus: dict | None = None):
        if not 0 <= slot < 9:
            raise DomainError("Photo slot must be 0-8", 400)
        profile = self.me(uid)["profile"]
        profile["photos"][slot] = url
        focus_map = {u: f for u, f in (profile.get("photoFocus") or {}).items() if u in profile["photos"]}
        if url and focus:
            focus_map[url] = focus
        profile["photoFocus"] = focus_map
        if slot == 0:
            if profile["photoVerified"]:
                self.store.add_event(uid, "Main photo changed — verification reset", "RECOMMENDED")
            profile["photoVerified"] = False
            profile["photoMatchScore"] = None
        self.store.save_profile(uid, profile)

    def verify_photo(self, uid: int, match_percent: int | None = None):
        profile = self.me(uid)["profile"]
        if not profile["photos"][0]:
            raise DomainError("Add a main photo before verifying", 400)
        profile["photoVerified"] = True
        profile["photoMatchScore"] = match_percent
        self.store.save_profile(uid, profile)
        self.store.add_event(uid, "Verified it's me" + (f" — face match {match_percent}%" if match_percent else ""),
                             "RECOMMENDED")

    # ======================================================= connections ==
    def _target(self, tid) -> dict:
        try:
            user = self.store.user(int(tid))
        except (TypeError, ValueError):
            user = None
        if not user:
            raise DomainError("This person isn't available anymore", 404)
        return user

    def _name(self, uid: int) -> str:
        u = self.store.user(uid)
        return (u and u["profile"].get("name")) or "Member"

    def _active_or_fail(self, uid: int, *states: str) -> dict:
        active = self.store.active_connection(uid)
        if not active or (states and self._view_state(active, uid) not in states):
            raise DomainError("That action isn't available for your current connection.")
        return active

    def like(self, uid: int, tid):
        me = self.me(uid)
        target = self._target(tid)
        if target["id"] == uid:
            raise DomainError("You can't like yourself", 400)
        if not me["profile"]["confirmed"]:
            raise DomainError("Add your gender and age in Bio (✏️ Edit on the Me tab) before liking people.")
        mine = self.store.active_connection(uid)
        if mine:
            other = self._name(self._other_id(mine, uid))
            self.store.add_event(uid, f"Blocked like for {target['profile']['name']} — already in connection with {other}",
                                 "RECOMMENDED", target["id"])
            raise DomainError(f"You are in a connection with {other}. End relationship to add new.")
        if not self.is_single(target["profile"]):
            raise DomainError(f"{target['profile']['name']} isn't single, so they can't be matched.")
        if self.store.active_connection(target["id"]):
            raise DomainError(f"{target['profile']['name']} is already in a connection.")
        existing = self.store.pending_between(uid, target["id"])
        if existing and existing["user_a"] == uid:
            raise DomainError(f"You already sent {target['profile']['name']} an invitation.")
        self.store.remove_pass(uid, target["id"])
        if existing:  # they already liked you -> liking back accepts
            self._start_chat(existing)
            return
        conn_id = self.store.create_connection(uid, target["id"])
        self.store.add_event(uid, f"You liked {target['profile']['name']} — invitation sent", "INVITED", target["id"])
        self.store.add_event(target["id"], f"{me['profile']['name']} liked you", "FAVOURED", uid)
        if target["is_sample"]:
            run_later(self.sample_delay_s, lambda: self._sample_accepts(conn_id))

    def pass_candidate(self, uid: int, tid):
        """Not interested: declines their invitation, withdraws yours, or just hides them."""
        target = self._target(tid)
        active = self.store.active_connection(uid)
        if active and self._other_id(active, uid) == target["id"]:
            raise DomainError("Use End Conversation to end an ongoing connection.")
        if active:
            raise DomainError("You are in a connection. End relationship to change other candidates.")
        pending = self.store.pending_between(uid, target["id"])
        if pending:
            self.store.update_connection(pending["id"], state="CLOSED")
            if pending["user_b"] == uid:
                self.store.add_event(uid, f"You declined {target['profile']['name']}'s invitation", "CLOSED", target["id"])
                self.store.add_event(target["id"], f"{self._name(uid)} declined your invitation", "CLOSED", uid)
            else:
                self.store.add_event(uid, f"You withdrew your invitation to {target['profile']['name']}", "CLOSED", target["id"])
                self.store.add_event(target["id"], f"{self._name(uid)} withdrew their invitation", "CLOSED", uid)
        else:
            self.store.add_event(uid, f"Not interested in {target['profile']['name']}", "CLOSED", target["id"])
        self.store.add_pass(uid, target["id"])

    def accept_invite(self, uid: int, tid=None):
        """Accept an invitation you received (from `tid`, or the newest one)."""
        if self.store.active_connection(uid):
            raise DomainError("You are already in a connection. End relationship to accept a new one.")
        received = [c for c in self.store.pending_for(uid) if c["user_b"] == uid]
        if tid is not None:
            received = [c for c in received if str(c["user_a"]) == str(tid)]
        if not received:
            raise DomainError("There is no invitation to accept.")
        conn = received[0]
        if self.store.active_connection(conn["user_a"]):
            raise DomainError(f"{self._name(conn['user_a'])} is already in a connection.")
        self._start_chat(conn)

    def _start_chat(self, conn: dict):
        """Accepted: start the chat and lock both people by cancelling all their other open invitations."""
        self.store.update_connection(conn["id"], state="CHATTING", chatting_started_at=now_ms())
        a, b = conn["user_a"], conn["user_b"]
        for person in (a, b):
            for other in self.store.pending_for(person):
                if other["id"] == conn["id"]:
                    continue
                self.store.update_connection(other["id"], state="CLOSED")
                someone = self._other_id(other, person)
                self.store.add_event(someone, f"{self._name(person)} is now chatting with someone else — "
                                              "your invitation was closed", "CLOSED", person)
                self.store.add_event(person, f"Invitation with {self._name(someone)} closed — you're now chatting "
                                             f"with {self._name(b if person == a else a)}", "CLOSED", someone)
        self.store.add_event(b, f"You accepted {self._name(a)}'s invitation — 72h commitment timer started", "CHATTING", a)
        self.store.add_event(a, f"{self._name(b)} accepted your invitation — 72h chat started", "CHATTING", b)

    def send_message(self, uid: int, text: str, media: dict | None = None):
        """Send text and/or one attachment. media = {"file", "type", "kind": image|video|audio}."""
        text = (text or "").strip()
        if not text and not media:
            raise DomainError("Message is empty", 400)
        conn = self._active_or_fail(uid, "CHATTING", "DATING", "ENGAGED")  # couples keep chatting after confirming
        if media:
            self.store.add_message(conn["id"], uid, text[:2000], media["kind"], media["file"], media["type"])
        else:
            self.store.add_message(conn["id"], uid, text[:2000])
        other = self.store.user(self._other_id(conn, uid))
        if other and other["is_sample"]:
            if media:
                reply = {"image": "Love this photo! 😍", "video": "Ha, great video! 🎬",
                         "audio": "Aw, it's so nice to hear your voice 🥰"}[media["kind"]]
            else:
                hobby = (self.me(uid)["profile"]["hobbies"] or "").split(",")[0].strip() or "your hobbies"
                reply = random.choice(AUTO_REPLIES).format(hobby=hobby)

            def deliver():
                current = self.store.connection(conn["id"])
                if current and current["state"] in ("CHATTING", "DATING", "ENGAGED"):
                    self.store.add_message(conn["id"], other["id"], reply)
            run_later(self.reply_delay_s, deliver)

    def media_for(self, uid: int, msg_id: int) -> dict:
        """Chat media is private to the two people in the conversation."""
        m = self.store.message(msg_id)
        if not m or not m["media_file"] or uid not in (m["user_a"], m["user_b"]):
            raise DomainError("Not found", 404)
        return m

    def confirm_relationship(self, uid: int):
        conn = self._active_or_fail(uid, "CHATTING")
        mine, theirs = self._confirmed(conn, uid)
        if mine:
            return
        field = "a_confirmed" if conn["user_a"] == uid else "b_confirmed"
        self.store.update_connection(conn["id"], **{field: 1})
        other_id = self._other_id(conn, uid)
        if theirs:
            self._start_dating(conn["id"])
            return
        self.store.add_event(uid, f"You confirmed relationship with {self._name(other_id)} — waiting for them",
                             "CHATTING", other_id)
        self.store.add_event(other_id, f"{self._name(uid)} confirmed your relationship — confirm to start dating",
                             "CHATTING", uid)
        other = self.store.user(other_id)
        if other and other["is_sample"]:
            def sample_confirms():
                current = self.store.connection(conn["id"])
                if current and current["state"] == "CHATTING":
                    f = "b_confirmed" if current["user_a"] == uid else "a_confirmed"
                    self.store.update_connection(conn["id"], **{f: 1})
                    self._start_dating(conn["id"])
            run_later(self.sample_delay_s, sample_confirms)

    def _start_dating(self, conn_id: int):
        conn = self.store.connection(conn_id)
        self.store.update_connection(conn_id, state="DATING")
        for uid, other in ((conn["user_a"], conn["user_b"]), (conn["user_b"], conn["user_a"])):
            u = self.store.user(uid)
            p = u["profile"]
            p["marriageStatus"] = "In Relationship"
            p["marriageVerified"] = True
            self.store.save_profile(uid, p)
            self.store.add_event(uid, f"✅ Relationship CONFIRMED with {self._name(other)} — both statuses → "
                                      "In Relationship, both profiles hidden from Discover", "DATING", other)

    def close_relationship(self, uid: int, *, force: bool = False):
        """End Conversation (while CHATTING) or Close relationship (while DATING).

        Both people return to the pool and can no longer message each other; the chat history is kept
        and shown read-only under Past conversations. Not allowed once ENGAGED (except account deletion).
        """
        conn = self._active_or_fail(uid, "CHATTING", "DATING", "ENGAGED")
        if conn["state"] == "ENGAGED" and not force:
            raise DomainError("You're engaged — the relationship can no longer be closed.")
        was_dating = conn["state"] in ("DATING", "ENGAGED")
        self.store.update_connection(conn["id"], state="CLOSED", engage_requested_by=None)
        for person, other in ((conn["user_a"], conn["user_b"]), (conn["user_b"], conn["user_a"])):
            u = self.store.user(person)
            if not u:
                continue
            p = u["profile"]
            p["marriageStatus"] = "Single"
            p["marriageVerified"] = True
            self.store.save_profile(person, p)
            if was_dating:
                text = (f"💔 You closed your relationship with {self._name(other)} — chat history kept, back in the pool"
                        if person == uid else
                        f"💔 {self._name(uid)} closed the relationship — chat history kept, back in the pool")
            elif person == uid:
                text = f"You ended your conversation with {self._name(other)}"
            else:
                text = f"{self._name(uid)} ended the conversation"
            self.store.add_event(person, text, "CLOSED", other)

    def expire_overdue(self):
        """Enforce the 72h window (called before each request).

        - 72h passed and neither person confirmed -> the conversation closes automatically
        - either person confirmed                 -> no time limit: it stays open until the other confirms
                                                     or someone ends the conversation
        Closing keeps the chat history (Past conversations) and returns both people to the pool.
        """
        now = now_ms()
        for conn in self.store.chats_started_before(now - CHAT_COMMITMENT_MS):
            if conn["a_confirmed"] or conn["b_confirmed"]:
                continue
            current = self.store.connection(conn["id"])
            if not current or current["state"] != "CHATTING" or current["a_confirmed"] or current["b_confirmed"]:
                continue
            self.store.update_connection(conn["id"], state="CLOSED")
            for person, other in ((conn["user_a"], conn["user_b"]), (conn["user_b"], conn["user_a"])):
                u = self.store.user(person)
                if not u:
                    continue
                p = u["profile"]
                p["marriageStatus"] = "Single"
                p["marriageVerified"] = True
                self.store.save_profile(person, p)
                self.store.add_event(person, f"⏰ Conversation with {self._name(other)} closed automatically — 72 hours "
                                             "passed without either of you confirming. Chat history kept; you're back "
                                             "in the pool.", "CLOSED", other)

    def engage(self, uid: int):
        """Ask the partner to get engaged (DATING only). Nothing changes until they approve.
        If the partner had already asked, this approves their request instead."""
        conn = self._active_or_fail(uid, "DATING")
        other_id = self._other_id(conn, uid)
        requester = conn.get("engage_requested_by")
        if requester == other_id:
            return self.accept_engagement(uid)
        if requester == uid:
            raise DomainError(f"You already asked {self._name(other_id)} — waiting for their answer.")
        self.store.update_connection(conn["id"], engage_requested_by=uid)
        self.store.add_event(uid, f"💍 Engagement request sent to {self._name(other_id)} — waiting for their answer",
                             "DATING", other_id)
        self.store.add_event(other_id, f"💍 {self._name(uid)} sent you an engagement request — open Connection to approve or decline",
                             "DATING", uid)
        other = self.store.user(other_id)
        if other and other["is_sample"]:
            def sample_says_yes():
                current = self.store.connection(conn["id"])
                if current and current["state"] == "DATING" and current.get("engage_requested_by") == uid:
                    self.accept_engagement(other_id)
            run_later(self.sample_delay_s, sample_says_yes)

    def _pending_engagement(self, uid: int) -> tuple[dict, int]:
        conn = self._active_or_fail(uid, "DATING")
        requester = conn.get("engage_requested_by")
        if not requester:
            raise DomainError("There's no engagement request to answer.")
        return conn, requester

    def accept_engagement(self, uid: int):
        """The partner approves: DATING -> ENGAGED for both; after this the relationship can't be closed."""
        conn, requester = self._pending_engagement(uid)
        if requester == uid:
            raise DomainError("Only your partner can approve your engagement request.")
        self.store.update_connection(conn["id"], state="ENGAGED", engage_requested_by=None)
        self.store.add_system_message(conn["id"], "Congratulations, you successfully got engaged!")
        for person, other in ((conn["user_a"], conn["user_b"]), (conn["user_b"], conn["user_a"])):
            p = self.store.user(person)["profile"]
            p["marriageStatus"] = "Engaged"
            p["marriageVerified"] = True
            self.store.save_profile(person, p)
            text = (f"💍 {self._name(other)} said yes — you're engaged!" if person == requester
                    else f"💍 You accepted {self._name(other)}'s request — you're engaged!")
            self.store.add_event(person, text, "ENGAGED", other)

    def decline_engagement(self, uid: int):
        """The partner says not yet: the request is cleared and you stay Dating."""
        conn, requester = self._pending_engagement(uid)
        if requester == uid:
            raise DomainError("Use Cancel request to withdraw your own request.")
        self.store.update_connection(conn["id"], engage_requested_by=None)
        # The person who proposed sees the answer in the chat.
        self.store.add_system_message(conn["id"], "The proposal of engagement was declined.", visible_to=requester)
        self.store.add_event(uid, f"You declined {self._name(requester)}'s engagement request — still dating",
                             "DATING", requester)
        self.store.add_event(requester, f"{self._name(uid)} declined your engagement request — still dating",
                             "DATING", uid)

    def cancel_engagement(self, uid: int):
        """The person who asked withdraws the request."""
        conn, requester = self._pending_engagement(uid)
        if requester != uid:
            raise DomainError("Only the person who asked can cancel the request.")
        other_id = self._other_id(conn, uid)
        self.store.update_connection(conn["id"], engage_requested_by=None)
        self.store.add_event(uid, f"You cancelled your engagement request to {self._name(other_id)}", "DATING", other_id)
        self.store.add_event(other_id, f"{self._name(uid)} withdrew the engagement request", "DATING", uid)

    def _past_chats(self, uid: int) -> list[dict]:
        out = []
        for c in self.store.past_chats(uid):
            other = self.store.user(self._other_id(c, uid))
            last = c["last_text"] or {"image": "📷 Photo", "video": "🎬 Video", "audio": "🎙️ Voice message"}.get(c["last_kind"] or "", "")
            out.append({"id": c["id"], "endedAt": c["updated_at"], "startedAt": c["chatting_started_at"],
                        "messageCount": c["message_count"], "lastMessage": last,
                        "candidate": public_profile(other) if other else {"id": None, "name": "Deleted account",
                                                                           "color": "#c4c2cc", "photos": []}})
        return out

    def past_messages(self, uid: int, conn_id: int) -> list[dict]:
        """Read-only history of an ended conversation (only for the two people in it)."""
        conn = self.store.connection(conn_id)
        if not conn or uid not in (conn["user_a"], conn["user_b"]):
            raise DomainError("Not found", 404)
        return [{"id": m["id"], "from": "system" if m["kind"] == "system" else "me" if m["sender_id"] == uid else "them", "text": m["text"], "at": m["at"],
                 "kind": m["kind"] or "text", "mediaUrl": f"/api/media/{m['id']}" if m["media_file"] else None,
                 "mediaType": m["media_type"]} for m in self.store.messages(conn_id, uid)]

    # ============================================== sample-account behaviour ==
    def _sample_accepts(self, conn_id: int):
        conn = self.store.connection(conn_id)
        if (conn and conn["state"] == "PENDING" and not self.store.active_connection(conn["user_a"])
                and not self.store.active_connection(conn["user_b"])):
            self._start_chat(conn)
