import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
import face  # noqa: E402


class FakeFaceMatcher:
    """Frames containing b"other" don't match; anything else matches at 87%."""
    def verify(self, photo, frames):
        if any(b"noface" in f for f in frames):
            raise face.FaceError("We couldn't see your face clearly in the selfie video.")
        other = any(b"other" in f for f in frames)
        return face.FaceResult(matched=not other, similarity=0.12 if other else 0.87,
                               frames_with_face=len(frames), frames_total=len(frames))

    def locate(self, data):
        return None if b"noface" in data else {"x": 50.0, "y": 30.0, "s": 0.4}

    def prepare_photo(self, data, ext):
        return data, ext, self.locate(data)


def selfie(*contents):
    return {"frames": [(io.BytesIO(c), f"f{i}.jpg", "image/jpeg") for i, c in enumerate(contents or (b"me1", b"me2", b"me3"))]}

PROFILE_GRACE = {
    "name": "Grace", "gender": "Female", "age": "28", "location": "San Francisco, CA", "mbti": "INFJ",
    "bio": "I love hiking, cooking and quiet coffee mornings.", "hobbies": "Hiking, Indie films, Cooking",
    "education": "MEng Computer Science",
    "ideal": {"genderPreference": "Female", "age": "24-32", "otherRequirement": "non-smoker, loves dogs"},
}
PROFILE_LUNA = {
    "name": "Luna", "gender": "Female", "age": "27", "location": "San Francisco, CA", "mbti": "ENFP",
    "bio": "Weekend hiker and amateur cook who loves dogs.", "hobbies": "Hiking, Cooking, Dogs",
    "ideal": {"genderPreference": "Female", "age": "25-35"},
}


@pytest.fixture
def app(tmp_path):
    return create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"),
                      reply_delay_s=0, sample_delay_s=0, config={"FACE_MATCHER": FakeFaceMatcher()})


def register(app, name, email, profile=None, verify=True):
    c = app.test_client()
    r = c.post("/api/auth/register", json={"name": name, "email": email, "password": "password123"})
    assert r.status_code == 200, r.get_json()
    if profile:
        assert c.put("/api/profile", json={**profile, "confirm": True}).status_code == 200
    if verify:
        assert c.post("/api/profile/verify-photo", data=selfie(), content_type="multipart/form-data").status_code == 400
        data = {"photo": (io.BytesIO(b"\x89PNG"), "me.png", "image/png")}
        c.post("/api/photos/0", data=data, content_type="multipart/form-data")
        assert c.post("/api/profile/verify-photo", data=selfie(), content_type="multipart/form-data").status_code == 200
    return c


def state(c, q=""):
    return c.get(f"/api/state?q={q}").get_json()


# ------------------------------------------------------------------ auth ---

def test_requires_login(app):
    c = app.test_client()
    assert c.get("/api/state").status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_register_login_logout(app):
    c = app.test_client()
    assert c.post("/api/auth/register", json={"name": "A", "email": "bad", "password": "password123"}).status_code == 400
    assert c.post("/api/auth/register", json={"name": "A", "email": "a@x.com", "password": "short"}).status_code == 400
    s = c.post("/api/auth/register", json={"name": "Ann", "email": "A@X.com", "password": "password123"}).get_json()
    assert s["profile"]["name"] == "Ann" and s["me"]["email"] == "a@x.com"
    assert "password_hash" not in str(s)
    assert c.post("/api/auth/register", json={"name": "B", "email": "a@x.com", "password": "password123"}).status_code == 409
    c.post("/api/auth/logout")
    assert c.get("/api/state").status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@x.com", "password": "nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "a@x.com", "password": "password123"}).status_code == 200
    assert c.get("/api/auth/me").get_json()["name"] == "Ann"


def test_login_throttle(app):
    c = app.test_client()
    for _ in range(10):
        c.post("/api/auth/login", json={"email": "z@x.com", "password": "wrong-pass"})
    assert c.post("/api/auth/login", json={"email": "z@x.com", "password": "wrong-pass"}).status_code == 429


def test_profiles_saved_per_user(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    assert state(a)["profile"]["bio"] == PROFILE_GRACE["bio"]
    assert state(b)["profile"]["bio"] == PROFILE_LUNA["bio"]


def test_confirm_requires_basics(app):
    c = register(app, "Ann", "a@x.com", verify=False)
    r = c.put("/api/profile", json={"bio": "hi", "confirm": True})
    assert r.status_code == 200 and r.get_json()["profile"]["confirmed"] is False  # saved, not yet confirmed


def test_facebook_login(tmp_path):
    calls = []

    def fake_json(url):
        calls.append(url)
        if "access_token?" in url:
            return {"access_token": "tok"}
        return {"id": "fb123", "name": "Fiona FB", "email": "fiona@x.com",
                "picture": {"data": {"url": "https://example/pic.jpg"}}}

    app = create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"), config={
        "FACEBOOK_APP_ID": "id", "FACEBOOK_APP_SECRET": "secret", "APP_URL": "http://localhost:5000",
        "HTTP_GET_JSON": fake_json, "HTTP_GET_BYTES": lambda url: b"jpeg-bytes"})
    c = app.test_client()
    assert c.get("/api/auth/config").get_json()["facebook"] is True
    r = c.get("/api/auth/facebook/start")
    assert r.status_code == 302 and "facebook.com" in r.location
    st = r.location.split("state=")[1].split("&")[0]
    # wrong state is rejected
    bad = c.get("/api/auth/facebook/callback?code=x&state=nope")
    assert "auth_error" in bad.location
    c.get("/api/auth/facebook/start")
    with c.session_transaction() as s:
        st = s["fb_state"]
    r = c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert r.status_code == 302 and "auth_error" not in r.location
    s = state(c)
    assert s["profile"]["name"] == "Fiona FB" and s["me"]["facebook"] is True
    assert s["profile"]["photos"][0].startswith("/uploads/")


def test_facebook_disabled_by_default(app):
    c = app.test_client()
    assert c.get("/api/auth/config").get_json() == {"facebook": False, "canSetupFacebook": True}
    assert "auth_error" in c.get("/api/auth/facebook/start").location


# --------------------------------------------------------------- ranking ---

def test_discover_tiers_mutual_first_then_requirements_only(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    register(app, "Luna", "l@x.com", PROFILE_LUNA)
    s = state(a)
    names = [m["name"] for m in s["matches"]]
    tiers = [m["tier"] for m in s["matches"]]
    assert "Luna" in names
    # no duplicates, mutual tier strictly before "yours"
    assert len(names) == len(set(names))
    assert tiers == sorted(tiers, key=lambda t: t != "mutual")
    assert all(m["gender"] == "Female" and 24 <= m["age"] <= 32 for m in s["matches"])
    # Aisha is looking for men, so she only meets Grace's requirements one way
    aisha = next(m for m in s["matches"] if m["name"] == "Aisha")
    assert aisha["tier"] == "yours"
    luna = next(m for m in s["matches"] if m["name"] == "Luna")
    assert luna["tier"] == "mutual" and luna["matchScore"] > 0 and luna["reasons"]
    mutual_scores = [m["matchScore"] for m in s["matches"] if m["tier"] == "mutual"]
    assert mutual_scores == sorted(mutual_scores, reverse=True)
    # private fields never leak
    assert "email" not in str(s["matches"]) and "l@x.com" not in str(s["matches"])


def test_unverified_or_unconfirmed_users_hidden(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    register(app, "Hidden", "h@x.com", {**PROFILE_LUNA, "name": "Hidden"}, verify=False)
    assert "Hidden" not in [m["name"] for m in state(a)["matches"]]


def test_search(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    assert [m["name"] for m in state(a, "vinyl")["matches"]] == ["Sofia"]


# ------------------------------------------------------------ connection ---

def test_two_real_users_full_flow(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    luna_id = state(b)["me"]["id"]
    grace_id = state(a)["me"]["id"]

    s = a.post(f"/api/candidates/{luna_id}/like").get_json()
    assert s["active"] is None and s["invitations"][0]["state"] == "INVITED"
    sb = state(b)
    assert sb["active"] is None
    assert sb["invitations"][0]["state"] == "FAVOURED" and sb["invitations"][0]["candidateId"] == grace_id
    assert any("Grace liked you" in e["text"] for e in sb["events"])

    # A pending invitation doesn't lock anyone: both still appear in Discover
    c = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    assert {"Grace", "Luna"} <= {m["name"] for m in state(c)["matches"]}

    s = b.post("/api/connection/accept").get_json()
    assert s["active"]["state"] == "CHATTING"
    # Accepted: both locked and out of everyone else's Discover
    assert not {"Grace", "Luna"} & {m["name"] for m in state(c)["matches"]}
    assert state(a)["active"]["state"] == "CHATTING"

    a.post("/api/messages", json={"text": "Hi Luna!"})
    b.post("/api/messages", json={"text": "Hi Grace!"})
    assert [(m["from"], m["text"]) for m in state(a)["messages"]] == [("me", "Hi Luna!"), ("them", "Hi Grace!")]
    assert [m["from"] for m in state(b)["messages"]] == ["them", "me"]

    s = a.post("/api/connection/confirm").get_json()
    assert s["active"]["state"] == "CHATTING" and s["active"]["meConfirmed"] and not s["active"]["themConfirmed"]
    assert state(b)["active"]["themConfirmed"] is True
    s = b.post("/api/connection/confirm").get_json()
    assert s["active"]["state"] == "DATING"
    for cl in (a, b):
        st = state(cl)
        assert st["userStatus"] == "in_a_relationship" and st["profile"]["marriageStatus"] == "In Relationship"

    b.post("/api/connection/close")
    for cl in (a, b):
        st = state(cl)
        assert st["active"] is None and st["profile"]["marriageStatus"] == "Single"
    assert {"Grace", "Luna"} <= {m["name"] for m in state(c)["matches"]}


def test_pending_invites_do_not_lock(app):
    grace = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    isaac = register(app, "Isaac", "i@x.com", {**PROFILE_LUNA, "name": "Isaac"})
    cara = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    grace_id, cara_id = state(grace)["me"]["id"], state(cara)["me"]["id"]
    isaac.post(f"/api/candidates/{grace_id}/like")
    s = state(grace)
    # Grace hasn't accepted: not in a connection, can still like / pass others
    assert s["active"] is None and s["isAvailable"] is True
    assert s["invitations"][0]["state"] == "FAVOURED"
    assert grace.post(f"/api/candidates/{cara_id}/like").status_code == 200
    maya = next(m for m in s["matches"] if m["name"] == "Sofia")
    assert grace.post(f"/api/candidates/{maya['id']}/pass").status_code == 200
    states = sorted(i["state"] for i in state(grace)["invitations"])
    assert states == ["FAVOURED", "INVITED"]
    # Liking back someone who already liked you accepts instead of duplicating
    s = cara.post(f"/api/candidates/{grace_id}/like").get_json()
    assert s["active"]["state"] == "CHATTING"
    # Accepting locks both and cancels their other invitations
    s = state(grace)
    assert s["active"]["candidateId"] == cara_id and s["invitations"] == []
    assert state(isaac)["invitations"] == []
    assert any("now chatting with someone else" in e["text"] for e in state(isaac)["events"])
    assert grace.post(f"/api/candidates/{state(isaac)['me']['id']}/like").status_code == 409
    r = isaac.post(f"/api/candidates/{grace_id}/like")
    assert r.status_code == 409 and "already in a connection" in r.get_json()["error"]


def test_accept_specific_invitation(app):
    grace = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    a = register(app, "Ann", "a@x.com", {**PROFILE_LUNA, "name": "Ann"})
    b = register(app, "Bea", "b@x.com", {**PROFILE_LUNA, "name": "Bea"})
    gid = state(grace)["me"]["id"]
    a.post(f"/api/candidates/{gid}/like")
    b.post(f"/api/candidates/{gid}/like")
    bea_id = state(b)["me"]["id"]
    s = grace.post("/api/connection/accept", json={"candidateId": bea_id}).get_json()
    assert s["active"]["candidateId"] == bea_id
    assert state(a)["invitations"] == []


def test_cannot_double_invite(app):
    grace = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    luna = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    lid = state(luna)["me"]["id"]
    assert grace.post(f"/api/candidates/{lid}/like").status_code == 200
    assert grace.post(f"/api/candidates/{lid}/like").status_code == 409


def test_decline_and_withdraw(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    luna, grace = state(b)["me"]["id"], state(a)["me"]["id"]
    a.post(f"/api/candidates/{luna}/like")
    b.post(f"/api/candidates/{grace}/pass")
    assert state(a)["invitations"] == []
    assert any("declined" in e["text"] for e in state(a)["events"])
    a.post(f"/api/candidates/{luna}/like")
    a.post(f"/api/candidates/{luna}/pass")
    assert state(b)["invitations"] == []


def test_sample_account_auto_responds(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    maya = next(m for m in state(a)["matches"] if m["name"] == "Maya")
    assert maya["isSample"] is True
    s = a.post(f"/api/candidates/{maya['id']}/like").get_json()
    assert s["active"]["state"] == "CHATTING"  # sample accepts (delay 0 in tests)
    s = a.post("/api/messages", json={"text": "hey"}).get_json()
    assert [m["from"] for m in s["messages"]] == ["me", "them"]
    s = a.post("/api/connection/confirm").get_json()
    assert s["active"]["state"] == "DATING"


def test_like_requires_saved_profile(app):
    c = register(app, "Ann", "a@x.com", verify=False)
    maya_id = 1
    assert c.post(f"/api/candidates/{maya_id}/like").status_code == 409


# --------------------------------------------------------------- profile ---

def test_gender_options_and_validation(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    for g in ["Transgender", "Non-binary", "Other"]:
        assert a.put("/api/profile", json={"gender": g}).get_json()["profile"]["gender"] == g
    assert a.put("/api/profile", json={"gender": "Robot"}).status_code == 400
    assert a.put("/api/profile", json={"ideal": {"age": "12-15"}}).status_code == 400
    assert a.put("/api/profile", json={"age": "12"}).status_code == 400


def test_education_verification_removed(app):
    import ranking
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    assert a.post("/api/profile/verify-education", json={"email": "grace@edu.uwaterloo.ca"}).status_code in (404, 405)
    s = a.put("/api/profile", json={"education": "PhD Physics, MIT"}).get_json()
    assert s["profile"]["education"] == "PhD Physics, MIT" and "educationVerified" not in s["profile"]
    # An old "educationVerified" flag in someone's data doesn't change their score.
    seeker = state(a)["profile"]
    base = {"id": 9, "name": "X", "gender": "Female", "age": 27, "bio": "hiking", "photoVerified": True,
            "marriageVerified": True, "ideal": {}}
    s1 = ranking.rank(seeker, [base])[0]["matchScore"]
    s2 = ranking.rank(seeker, [{**base, "educationVerified": True}])[0]["matchScore"]
    assert s1 == s2


def test_photo_upload_rules(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    s = state(a)
    assert s["profile"]["photoVerified"] is True
    data = {"photo": (io.BytesIO(b"\x89PNG"), "new.png", "image/png")}
    s = a.post("/api/photos/0", data=data, content_type="multipart/form-data").get_json()
    assert s["profile"]["photoVerified"] is False  # new main photo -> re-verify
    bad = {"photo": (io.BytesIO(b"x"), "x.exe", "application/octet-stream")}
    assert a.post("/api/photos/1", data=bad, content_type="multipart/form-data").status_code == 400


def test_delete_account(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    assert a.delete("/api/account").status_code == 200
    assert a.get("/api/state").status_code == 401
    assert state(b)["active"] is None and state(b)["invitations"] == []
    assert "Grace" not in [m["name"] for m in state(b)["matches"]]


# ---------------------------------------------------------------- chat media ---

def _chatting_pair(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    b.post("/api/connection/accept")
    return a, b


def test_send_photo_video_voice_and_emoji(app):
    a, b = _chatting_pair(app)
    a.post("/api/messages", json={"text": "Hi 😀🌸"})
    for fname, mime, kind in (("p.jpg", "image/jpeg", "image"), ("v.mp4", "video/mp4", "video"),
                              ("voice.webm", "audio/webm;codecs=opus", "audio")):
        data = {"file": (io.BytesIO(b"bytes-" + kind.encode()), fname, mime), "text": f"my {kind}"}
        r = a.post("/api/messages", data=data, content_type="multipart/form-data")
        assert r.status_code == 200, r.get_json()
    msgs = state(b)["messages"]
    assert msgs[0]["text"] == "Hi 😀🌸" and msgs[0]["kind"] == "text"
    assert [m["kind"] for m in msgs[1:]] == ["image", "video", "audio"]
    assert msgs[3]["mediaType"] == "audio/webm"
    # both people in the chat can open the media; nobody else can
    url = msgs[1]["mediaUrl"]
    assert b.get(url).data == b"bytes-image" and a.get(url).status_code == 200
    c = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    assert c.get(url).status_code == 404
    assert app.test_client().get(url).status_code == 401
    assert app.test_client().get("/uploads/chat/whatever.jpg").status_code == 404


def test_media_rejects_other_files(app):
    a, _ = _chatting_pair(app)
    data = {"file": (io.BytesIO(b"x"), "x.pdf", "application/pdf")}
    assert a.post("/api/messages", data=data, content_type="multipart/form-data").status_code == 400
    assert a.post("/api/messages", json={"text": "   "}).status_code == 400


def test_media_only_while_chatting(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    data = {"file": (io.BytesIO(b"x"), "p.jpg", "image/jpeg")}
    assert a.post("/api/messages", data=data, content_type="multipart/form-data").status_code == 409


def test_sample_replies_to_media(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    maya = next(m for m in state(a)["matches"] if m["name"] == "Maya")
    a.post(f"/api/candidates/{maya['id']}/like")
    data = {"file": (io.BytesIO(b"x"), "p.jpg", "image/jpeg")}
    s = a.post("/api/messages", data=data, content_type="multipart/form-data").get_json()
    assert s["messages"][-1]["from"] == "them" and "photo" in s["messages"][-1]["text"]


def test_delete_account_removes_chat_media(app, tmp_path):
    a, b = _chatting_pair(app)
    data = {"file": (io.BytesIO(b"x"), "p.jpg", "image/jpeg")}
    a.post("/api/messages", data=data, content_type="multipart/form-data")
    chat_dir = tmp_path / "up" / "chat"
    assert len(list(chat_dir.iterdir())) == 1
    a.delete("/api/account")
    assert list(chat_dir.iterdir()) == []


def test_close_only_after_chat_starts(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    # pending invitation: neither side can close or confirm; they decline / withdraw instead
    for cl in (a, b):
        assert cl.post("/api/connection/close").status_code == 409
        assert cl.post("/api/connection/confirm").status_code == 409
    b.post("/api/connection/accept")
    assert a.post("/api/connection/close").status_code == 200
    assert state(b)["active"] is None


def test_liked_you_sorted_by_score_then_earliest(app):
    import store as store_mod
    grace = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    gid = state(grace)["me"]["id"]
    # three people like Grace, in this order
    similar = {**PROFILE_LUNA, "bio": PROFILE_GRACE["bio"], "hobbies": PROFILE_GRACE["hobbies"]}
    first = register(app, "First", "f@x.com", {**similar, "name": "First"})
    best = register(app, "Best", "b@x.com", {**similar, "name": "Best", "mbti": "INFJ"})
    other = register(app, "Other", "o@x.com", {**PROFILE_LUNA, "name": "Other", "bio": "Motorbikes and late nights.",
                                                "hobbies": "Racing"})
    tie = register(app, "Tie", "t@x.com", {**similar, "name": "Tie"})
    clock = iter(range(1_000, 10_000, 100))
    orig = store_mod.now_ms
    store_mod.now_ms = lambda: next(clock)
    try:
        for c in (first, best, other, tie):
            c.post(f"/api/candidates/{gid}/like")
    finally:
        store_mod.now_ms = orig
    inv = [i for i in state(grace)["invitations"] if i["state"] == "FAVOURED"]
    scores = [i["candidate"]["matchScore"] for i in inv]
    assert scores == sorted(scores, reverse=True)
    names = [i["candidate"]["name"] for i in inv]
    by = {i["candidate"]["name"]: i for i in inv}
    assert by["First"]["candidate"]["matchScore"] == by["Tie"]["candidate"]["matchScore"]
    assert names.index("First") < names.index("Tie")  # same score: who liked first comes first
    assert names[-1] == "Other"


def _dating_pair(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    b.post("/api/connection/accept")
    a.post("/api/messages", json={"text": "hello"})
    a.post("/api/connection/confirm")
    b.post("/api/connection/confirm")
    return a, b


def test_chat_continues_while_dating_and_engaged(app):
    a, b = _dating_pair(app)
    assert state(a)["active"]["state"] == "DATING"
    assert a.post("/api/messages", json={"text": "still chatting 💜"}).status_code == 200
    assert a.post("/api/connection/confirm").status_code == 409  # nothing left to confirm
    b.post("/api/connection/engage")
    s = a.post("/api/connection/engage/accept").get_json()
    assert s["active"]["state"] == "ENGAGED" and s["userStatus"] == "engaged"
    sa = state(a)
    assert sa["active"]["state"] == "ENGAGED" and sa["profile"]["marriageStatus"] == "Engaged"
    assert any("engaged" in e["text"] for e in sa["events"])
    assert a.post("/api/messages", json={"text": "engaged chat"}).status_code == 200
    # once engaged, the relationship can't be closed by either person
    for cl in (a, b):
        r = cl.post("/api/connection/close")
        assert r.status_code == 409 and "engaged" in r.get_json()["error"]
    assert a.post("/api/connection/engage").status_code == 409  # already engaged


def test_engage_only_while_dating(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    b.post("/api/connection/accept")
    assert a.post("/api/connection/engage").status_code == 409


def test_close_relationship_keeps_history_read_only(app):
    a, b = _dating_pair(app)
    data = {"file": (io.BytesIO(b"img"), "p.jpg", "image/jpeg")}
    b.post("/api/messages", data=data, content_type="multipart/form-data")
    assert a.post("/api/connection/close").status_code == 200
    for cl in (a, b):
        s = state(cl)
        assert s["active"] is None and s["profile"]["marriageStatus"] == "Single"
        assert len(s["pastChats"]) == 1 and s["pastChats"][0]["messageCount"] == 2
        # can no longer chat
        assert cl.post("/api/messages", json={"text": "hi?"}).status_code == 409
    conn_id = state(a)["pastChats"][0]["id"]
    msgs = a.get(f"/api/connections/{conn_id}/messages").get_json()["messages"]
    assert [m["kind"] for m in msgs] == ["text", "image"]
    assert a.get(msgs[1]["mediaUrl"]).data == b"img"  # media still viewable
    outsider = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    assert outsider.get(f"/api/connections/{conn_id}/messages").status_code == 404


def test_delete_account_while_engaged(app):
    a, b = _dating_pair(app)
    a.post("/api/connection/engage")
    assert a.delete("/api/account").status_code == 200
    assert state(b)["active"] is None


# ------------------------------------------------------ must-match rules ---

def _names(c):
    return {m["name"] for m in state(c)["matches"]}


def test_must_match_height_minimum(app):
    g = register(app, "Grace", "g@x.com", {**PROFILE_GRACE, "ideal": {**PROFILE_GRACE["ideal"], "height": "5'7 - 6'2"}})
    register(app, "Tall", "t@x.com", {**PROFILE_LUNA, "name": "Tall", "height": "5'8"})
    register(app, "Short", "s@x.com", {**PROFILE_LUNA, "name": "Short", "height": "5'2"})
    register(app, "Metric", "m@x.com", {**PROFILE_LUNA, "name": "Metric", "height": "175 cm"})
    register(app, "Decimal", "d@x.com", {**PROFILE_LUNA, "name": "Decimal", "height": "6.16"})
    register(app, "NoHeight", "n@x.com", {**PROFILE_LUNA, "name": "NoHeight", "height": ""})
    names = _names(g)
    assert {"Tall", "Metric", "Decimal", "NoHeight"} <= names   # missing height is not excluded
    assert "Short" not in names


def test_must_match_education_levels(app):
    def seeker(level, email):
        return register(app, "Seeker", email, {**PROFILE_GRACE, "ideal": {**PROFILE_GRACE["ideal"], "education": level}})
    register(app, "Ba", "ba@x.com", {**PROFILE_LUNA, "name": "Ba", "education": "BA Literature"})
    register(app, "Ms", "ms@x.com", {**PROFILE_LUNA, "name": "Ms", "education": "Master's in Design"})
    register(app, "Phd", "phd@x.com", {**PROFILE_LUNA, "name": "Phd", "education": "PhD Physics"})
    register(app, "Hs", "hs@x.com", {**PROFILE_LUNA, "name": "Hs", "education": "High school"})
    register(app, "Blank", "bl@x.com", {**PROFILE_LUNA, "name": "Blank", "education": ""})
    people = {"Ba", "Ms", "Phd", "Hs", "Blank"}
    assert _names(seeker("Bachelor's", "s1@x.com")) & people == {"Ba", "Ms", "Phd", "Blank"}
    assert _names(seeker("Master's", "s2@x.com")) & people == {"Ms", "Phd", "Blank"}
    assert _names(seeker("Doctor's", "s3@x.com")) & people == {"Phd", "Blank"}
    assert _names(seeker("No preference", "s4@x.com")) & people == people


def test_must_match_ethnicity(app):
    g = register(app, "Grace", "g@x.com", {**PROFILE_GRACE, "ideal": {**PROFILE_GRACE["ideal"], "ethnicity": "East Asian, Caucasian"}})
    register(app, "Ea", "ea@x.com", {**PROFILE_LUNA, "name": "Ea", "ethnicity": "East Asian"})
    register(app, "Hi", "hi@x.com", {**PROFILE_LUNA, "name": "Hi", "ethnicity": "Hispanic"})
    register(app, "Un", "un@x.com", {**PROFILE_LUNA, "name": "Un", "ethnicity": ""})
    names = _names(g)
    assert {"Ea", "Un"} <= names and "Hi" not in names
    # samples follow the same rule: Sofia is Hispanic, Maya East Asian
    assert "Maya" in names and "Sofia" not in names


def test_must_match_not_want(app):
    g = register(app, "Grace", "g@x.com", {**PROFILE_GRACE, "ideal": {**PROFILE_GRACE["ideal"], "notWant": "Smoking, drugs"}})
    register(app, "Smoker", "a@x.com", {**PROFILE_LUNA, "name": "Smoker", "bio": "I smoke on weekends."})
    register(app, "Hobby", "b@x.com", {**PROFILE_LUNA, "name": "Hobby", "hobbies": "Hiking, Smoking cigars"})
    register(app, "NonSmoker", "c@x.com", {**PROFILE_LUNA, "name": "NonSmoker", "bio": "Proud non-smoker, never smoke."})
    register(app, "Clean", "d@x.com", {**PROFILE_LUNA, "name": "Clean", "bio": "Coffee and books. No drugs."})
    names = _names(g)
    assert {"NonSmoker", "Clean"} <= names
    assert not {"Smoker", "Hobby"} & names


def test_mutual_uses_all_must_match_rules(app):
    # Grace fits Luna's gender/age, but Luna requires a Master's and Grace lists a Bachelor's
    g = register(app, "Grace", "g@x.com", {**PROFILE_GRACE, "education": "BA History"})
    register(app, "Luna", "l@x.com", {**PROFILE_LUNA, "ideal": {**PROFILE_LUNA["ideal"], "education": "Master's"}})
    luna = next(m for m in state(g)["matches"] if m["name"] == "Luna")
    assert luna["tier"] == "yours"
    g.put("/api/profile", json={"education": "MSc Biology"})
    luna = next(m for m in state(g)["matches"] if m["name"] == "Luna")
    assert luna["tier"] == "mutual"


def test_mbti_not_part_of_ideal_partner(app):
    g = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    s = g.put("/api/profile", json={"ideal": {"mbti": "INTJ"}}).get_json()
    assert s["profile"]["ideal"].get("mbti", "") != "INTJ"   # ignored: no longer a questionnaire field


# ------------------------------------------------- 72h auto-close / grace ---

H = 3_600_000


def _chat_started_hours_ago(app, client, hours):
    from store import now_ms
    svc = app.extensions["fym_service"]
    conn_id = state(client)["active"]["id"]
    conn = svc.store.connection(conn_id)
    svc.store.update_connection(conn_id, chatting_started_at=now_ms() - int(hours * H),
                                a_confirmed=conn["a_confirmed"], b_confirmed=conn["b_confirmed"])


def _chatting(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    a.post(f"/api/candidates/{state(b)['me']['id']}/like")
    b.post("/api/connection/accept")
    a.post("/api/messages", json={"text": "hi"})
    return a, b


def test_auto_close_after_72h_when_nobody_confirmed(app):
    a, b = _chatting(app)
    _chat_started_hours_ago(app, a, 71.9)
    assert state(a)["active"]["state"] == "CHATTING"          # still inside the window
    _chat_started_hours_ago(app, a, 72.1)
    for cl in (a, b):
        s = state(cl)
        assert s["active"] is None and s["isAvailable"] is True
        assert s["pastChats"][0]["messageCount"] == 1         # history kept
        assert any("closed automatically" in e["text"] for e in s["events"])
    # both back in the pool: can like again
    c = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    assert a.post(f"/api/candidates/{state(c)['me']['id']}/like").status_code == 200


def test_no_time_limit_once_one_person_confirmed(app):
    a, b = _chatting(app)
    a.post("/api/connection/confirm")
    _chat_started_hours_ago(app, a, 24 * 30)                   # a month later: still open
    s = state(b)
    assert s["active"]["state"] == "CHATTING"
    assert s["active"]["noTimeLimit"] is True and s["active"]["chatDeadline"] is None
    assert s["active"]["themConfirmed"] is True
    assert b.post("/api/messages", json={"text": "sorry, was away"}).status_code == 200
    # the other person can still confirm any time -> dating
    assert b.post("/api/connection/confirm").get_json()["active"]["state"] == "DATING"


def test_waiting_partner_can_still_end_it(app):
    a, b = _chatting(app)
    a.post("/api/connection/confirm")
    _chat_started_hours_ago(app, a, 200)
    assert b.post("/api/connection/close").status_code == 200
    assert state(a)["active"] is None and len(state(a)["pastChats"]) == 1


def test_dating_is_not_auto_closed(app):
    a, b = _chatting(app)
    a.post("/api/connection/confirm")
    b.post("/api/connection/confirm")
    from store import now_ms
    svc = app.extensions["fym_service"]
    conn_id = state(a)["active"]["id"]
    svc.store.update_connection(conn_id, state="DATING", chatting_started_at=now_ms() - 500 * H, a_confirmed=1, b_confirmed=1)
    assert state(a)["active"]["state"] == "DATING"


# ------------------------------------------------------- single only ---

def test_only_single_profiles_are_matched(app):
    g = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    single = register(app, "Sam", "s@x.com", {**PROFILE_LUNA, "name": "Sam"})
    dating = register(app, "Dee", "d@x.com", {**PROFILE_LUNA, "name": "Dee", "marriageStatus": "Dating"})
    taken = register(app, "Rae", "r@x.com", {**PROFILE_LUNA, "name": "Rae", "marriageStatus": "In Relationship"})
    names = {m["name"] for m in state(g)["matches"]}
    assert "Sam" in names and not {"Dee", "Rae"} & names
    # liking someone who isn't single is refused
    r = g.post(f"/api/candidates/{state(dating)['me']['id']}/like")
    assert r.status_code == 409 and "isn't single" in r.get_json()["error"]
    # switching back to Single makes them matchable again
    dating.put("/api/profile", json={"marriageStatus": "Single"})
    assert "Dee" in {m["name"] for m in state(g)["matches"]}
    # setting yourself to In Relationship removes you from everyone else's Discover
    assert "Rae" not in {m["name"] for m in state(single)["matches"]}
    taken.put("/api/profile", json={"marriageStatus": "Single"})
    assert "Rae" in {m["name"] for m in state(single)["matches"]}


def test_couples_disappear_once_dating_or_engaged(app):
    a, b = _dating_pair(app)
    c = register(app, "Cara", "c@x.com", {**PROFILE_LUNA, "name": "Cara"})
    assert not {"Grace", "Luna"} & {m["name"] for m in state(c)["matches"]}
    a.post("/api/connection/engage")
    b.post("/api/connection/engage/accept")
    assert state(a)["profile"]["marriageStatus"] == "Engaged"
    assert not {"Grace", "Luna"} & {m["name"] for m in state(c)["matches"]}


def test_not_want_person_nouns_match_verbs():
    import ranking
    seeker = {"ideal": {"notWant": "smoker, heavy drinker"}}
    assert ranking.mentions_unwanted(seeker, {"bio": "I smoke after work"}) == "smoker"
    assert ranking.mentions_unwanted(seeker, {"hobbies": "Smoking cigars"}) == "smoker"
    assert ranking.mentions_unwanted(seeker, {"bio": "Proud non-smoker"}) is None
    assert ranking.mentions_unwanted(seeker, {"bio": "Heavy drinking on weekends"}) == "heavy drinker"
    assert ranking.mentions_unwanted(seeker, {"bio": "I never drink, heavy lifting fan"}) is None


# ------------------------------------------------ liked-you evaluation ---

def test_liked_you_evaluated_and_shown_in_discover_when_passing(app):
    grace = register(app, "Grace", "g@x.com", {**PROFILE_GRACE, "ideal": {**PROFILE_GRACE["ideal"], "height": "5'5"}})
    gid = state(grace)["me"]["id"]
    # liked Grace but hasn't verified their photo yet -> normally hidden from Discover
    good = register(app, "Good", "good@x.com", {**PROFILE_LUNA, "name": "Good", "height": "5'8"}, verify=False)
    bad = register(app, "Bad", "bad@x.com", {**PROFILE_LUNA, "name": "Bad", "age": "40", "height": "5'1"}, verify=False)
    good.post(f"/api/candidates/{gid}/like")
    bad.post(f"/api/candidates/{gid}/like")
    s = state(grace)
    inv = {i["candidate"]["name"]: i for i in s["invitations"]}
    assert inv["Good"]["meetsRequirements"] is True and inv["Good"]["missedRequirements"] == []
    assert inv["Good"]["inDiscover"] is True and inv["Good"]["twoWay"] is True
    assert inv["Bad"]["meetsRequirements"] is False and inv["Bad"]["inDiscover"] is False
    missed = " | ".join(inv["Bad"]["missedRequirements"])
    assert "Age 40 — you want 24–32" in missed and "Height 155 cm — you want at least 165 cm" in missed
    names = {m["name"]: m for m in s["matches"]}
    assert "Good" in names and names["Good"]["connectionState"] == "FAVOURED"
    assert "Bad" not in names
    # liking back from Discover accepts
    assert grace.post(f"/api/candidates/{names['Good']['id']}/like").get_json()["active"]["state"] == "CHATTING"


def test_unverified_people_still_hidden_unless_they_liked_you(app):
    grace = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    register(app, "Quiet", "q@x.com", {**PROFILE_LUNA, "name": "Quiet"}, verify=False)
    assert "Quiet" not in {m["name"] for m in state(grace)["matches"]}


def test_ideal_partner_can_be_saved_before_bio(app):
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "New", "email": "new@x.com", "password": "password123"})
    r = c.put("/api/profile", json={"ideal": {"genderPreference": "Male", "age": "25-35"}, "confirm": True})
    assert r.status_code == 200, r.get_json()
    p = r.get_json()["profile"]
    assert p["ideal"]["genderPreference"] == "Male" and p["ideal"]["age"] == "25-35"
    assert p["confirmed"] is False  # bio still missing gender/age
    p = c.put("/api/profile", json={"gender": "Female", "age": "27", "confirm": True}).get_json()["profile"]
    assert p["confirmed"] is True and p["ideal"]["genderPreference"] == "Male"


def test_height_entered_and_stored_in_cm(app):
    c = register(app, "Ann", "a@x.com", verify=False)
    p = c.put("/api/profile", json={"height": "168", "ideal": {"height": "175 cm"}}).get_json()["profile"]
    assert p["height"] == "168" and p["ideal"]["height"] == "175"
    p = c.put("/api/profile", json={"height": "5'9", "ideal": {"height": "5'7 - 6'2"}}).get_json()["profile"]
    assert p["height"] == "175" and p["ideal"]["height"] == "170"      # older formats converted to cm
    assert c.put("/api/profile", json={"height": "66"}).get_json()["profile"]["height"] == "168"  # old inch value
    assert c.put("/api/profile", json={"ideal": {"height": "No preference"}}).get_json()["profile"]["ideal"]["height"] == "No preference"
    r = c.put("/api/profile", json={"height": "tall"})
    assert r.status_code == 400 and "centimetres" in r.get_json()["error"]



# ------------------------------------------------------ face recognition ---

def _with_main_photo(app):
    c = register(app, "Ann", "a@x.com", PROFILE_LUNA, verify=False)
    c.post("/api/photos/0", data={"photo": (io.BytesIO(b"\x89PNG"), "me.png", "image/png")},
           content_type="multipart/form-data")
    return c


def test_selfie_matching_main_photo_verifies(app):
    c = _with_main_photo(app)
    r = c.post("/api/profile/verify-photo", data=selfie(), content_type="multipart/form-data")
    assert r.status_code == 200
    p = r.get_json()["profile"]
    assert p["photoVerified"] is True and p["photoMatchScore"] == 87


def test_selfie_of_someone_else_is_rejected(app):
    c = _with_main_photo(app)
    r = c.post("/api/profile/verify-photo", data=selfie(b"other1", b"other2"), content_type="multipart/form-data")
    assert r.status_code == 422 and "doesn't look like" in r.get_json()["error"]
    assert state(c)["profile"]["photoVerified"] is False


def test_selfie_needs_frames_and_a_visible_face(app):
    c = _with_main_photo(app)
    assert c.post("/api/profile/verify-photo").status_code == 400
    r = c.post("/api/profile/verify-photo", data=selfie(b"noface"), content_type="multipart/form-data")
    assert r.status_code == 422 and "face" in r.get_json()["error"]


def test_changing_main_photo_resets_face_match(app):
    c = _with_main_photo(app)
    c.post("/api/profile/verify-photo", data=selfie(), content_type="multipart/form-data")
    c.post("/api/photos/0", data={"photo": (io.BytesIO(b"\x89PNG"), "new.png", "image/png")},
           content_type="multipart/form-data")
    p = state(c)["profile"]
    assert p["photoVerified"] is False and p["photoMatchScore"] is None


def test_real_face_matcher_on_sample_images():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    skdata = pytest.importorskip("skimage.data")
    if not all((face.MODELS_DIR / name).exists() for name, _, _ in face.MODELS.values()):
        pytest.skip("face models not downloaded (python face.py --download)")
    astro = cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR)
    enc = lambda im: cv2.imencode(".jpg", im)[1].tobytes()  # noqa: E731
    h, w = astro.shape[:2]
    frames = []
    for ang, dx in [(-6, -10), (0, 0), (5, 8)]:
        m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        m[0, 2] += dx
        frames.append(enc(cv2.warpAffine(astro, m, (w, h))))
    matcher = face.FaceMatcher()
    assert matcher.verify(enc(astro), frames).matched
    # A main photo with no face can't be used.
    with pytest.raises(face.FaceError):
        matcher.verify(enc(np.full((400, 400, 3), 128, np.uint8)), frames)
    # The same still picture repeated isn't a live video.
    with pytest.raises(face.FaceError):
        matcher.verify(enc(astro), [enc(astro)] * 3)



# ------------------------------------------------------ engagement request ---

def test_engage_is_a_request_until_partner_approves(app):
    a, b = _dating_pair(app)
    s = a.post("/api/connection/engage").get_json()
    assert s["active"]["state"] == "DATING" and s["active"]["engageRequest"] == "sent"
    assert s["profile"]["marriageStatus"] == "In Relationship"           # nothing changes yet
    sb = state(b)
    assert sb["active"]["engageRequest"] == "received" and sb["profile"]["marriageStatus"] == "In Relationship"
    assert any("sent you an engagement request" in e["text"] for e in sb["events"])
    assert a.post("/api/connection/engage").status_code == 409            # already asked
    assert a.post("/api/connection/engage/accept").status_code == 409     # can't approve your own request
    s = b.post("/api/connection/engage/accept").get_json()
    assert s["active"]["state"] == "ENGAGED" and s["active"]["engageRequest"] is None
    for cl in (a, b):
        assert state(cl)["profile"]["marriageStatus"] == "Engaged"


def test_engagement_request_can_be_declined_or_cancelled(app):
    a, b = _dating_pair(app)
    a.post("/api/connection/engage")
    s = b.post("/api/connection/engage/decline").get_json()
    assert s["active"]["state"] == "DATING" and s["active"]["engageRequest"] is None
    assert any("declined" in e["text"] for e in state(a)["events"])
    a.post("/api/connection/engage")
    assert b.post("/api/connection/engage/cancel").status_code == 409     # only the asker can cancel
    assert a.post("/api/connection/engage/cancel").get_json()["active"]["engageRequest"] is None
    # both asking = agreement
    a.post("/api/connection/engage")
    assert b.post("/api/connection/engage").get_json()["active"]["state"] == "ENGAGED"


def test_relationship_can_still_be_closed_while_request_pending(app):
    a, b = _dating_pair(app)
    a.post("/api/connection/engage")
    assert b.post("/api/connection/close").status_code == 200
    assert state(a)["active"] is None


# ------------------------------------------------------- facebook extras ---

def _fb_app(tmp_path, fb_user):
    def fake_json(url):
        return {"access_token": "tok"} if "access_token?" in url else fb_user
    return create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"), config={
        "FACEBOOK_APP_ID": "id", "FACEBOOK_APP_SECRET": "secret", "APP_URL": "http://localhost:5000",
        "HTTP_GET_JSON": fake_json, "HTTP_GET_BYTES": lambda url: b"jpeg", "FACE_MATCHER": FakeFaceMatcher()})


def test_facebook_redirects_back_to_the_dev_server_origin(tmp_path):
    import urllib.parse as up
    c = _fb_app(tmp_path, {"id": "fb9", "name": "Dev"}).test_client()
    r = c.get("/api/auth/facebook/start?origin=" + up.quote("http://localhost:5174"))
    assert up.quote("http://localhost:5174/api/auth/facebook/callback", safe="") in r.location
    with c.session_transaction() as s:
        st = s["fb_state"]
    r = c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert r.location == "http://localhost:5174/"
    # a foreign origin can't be used as the redirect target
    r = c.get("/api/auth/facebook/start?origin=" + up.quote("https://evil.example"))
    assert up.quote("http://localhost:5000/api/auth/facebook/callback", safe="") in r.location


def test_link_facebook_to_existing_email_account(tmp_path):
    app = _fb_app(tmp_path, {"id": "fb77", "name": "Grace FB", "email": "other@facebook-mail.com"})
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Grace", "email": "g@x.com", "password": "password123"})
    uid = state(c)["me"]["id"]
    c.get("/api/auth/facebook/start?link=1")
    with c.session_transaction() as s:
        st = s["fb_state"]
    r = c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert "auth_notice" in r.location
    s = state(c)
    assert s["me"]["id"] == uid and s["me"]["facebook"] is True
    # logging in with that Facebook account later opens the same account
    c.post("/api/auth/logout")
    c.get("/api/auth/facebook/start")
    with c.session_transaction() as s2:
        st = s2["fb_state"]
    c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert state(c)["me"]["id"] == uid


def test_dotenv_file_is_read(tmp_path, monkeypatch):
    import app as app_module
    env = tmp_path / ".env"
    env.write_text('# comment\nFACEBOOK_APP_ID="123"\nexport FACEBOOK_APP_SECRET=abc\n')
    for key in ("FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"):
        monkeypatch.setenv(key, "")   # records the original value so it's restored after the test
        monkeypatch.delenv(key)
    app_module._load_dotenv(env)
    import os
    assert os.environ["FACEBOOK_APP_ID"] == "123" and os.environ["FACEBOOK_APP_SECRET"] == "abc"
    a = create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"), config={"FACE_MATCHER": FakeFaceMatcher()})
    assert a.test_client().get("/api/auth/config").get_json()["facebook"] is True


def test_engagement_answer_appears_in_chat(app):
    a, b = _dating_pair(app)
    a.post("/api/connection/engage")
    b.post("/api/connection/engage/decline")
    sys_a = [m["text"] for m in state(a)["messages"] if m["from"] == "system"]
    sys_b = [m["text"] for m in state(b)["messages"] if m["from"] == "system"]
    assert sys_a == ["The proposal of engagement was declined."]
    assert sys_b == []                                   # only the person who proposed sees it
    a.post("/api/connection/engage")
    b.post("/api/connection/engage/accept")
    for cl in (a, b):
        msgs = state(cl)["messages"]
        assert msgs[-1]["from"] == "system" and msgs[-1]["kind"] == "system"
        assert msgs[-1]["text"] == "Congratulations, you successfully got engaged!"



def test_facebook_can_be_set_up_from_the_login_screen(tmp_path):
    checked = []

    def check(app_id, secret):
        checked.append((app_id, secret))
        return None if secret == "a" * 32 else "Facebook says this App ID or App secret is wrong"

    env = tmp_path / ".env"
    env.write_text("# my settings\nSECRET_KEY=keep-me\n")
    app = create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"), config={
        "FB_CHECK_APP": check, "ENV_PATH": env, "FACEBOOK_APP_ID": "", "FACEBOOK_APP_SECRET": "",
        "FACE_MATCHER": FakeFaceMatcher()})
    c = app.test_client()
    assert c.get("/api/auth/config").get_json() == {"facebook": False, "canSetupFacebook": True}
    assert c.post("/api/auth/facebook/setup", json={"appId": "abc", "appSecret": "a" * 32}).status_code == 400
    r = c.post("/api/auth/facebook/setup", json={"appId": "1234567890", "appSecret": "b" * 32})
    assert r.status_code == 400 and "wrong" in r.get_json()["error"]
    assert c.post("/api/auth/facebook/setup", json={"appId": "1234567890", "appSecret": "a" * 32}).status_code == 200
    assert c.get("/api/auth/config").get_json() == {"facebook": True, "canSetupFacebook": False}
    saved = env.read_text()
    assert "SECRET_KEY=keep-me" in saved and "FACEBOOK_APP_ID=1234567890" in saved and f"FACEBOOK_APP_SECRET={'a' * 32}" in saved
    assert c.get("/api/auth/facebook/start").location.startswith("https://www.facebook.com/")  # live, no restart


def test_facebook_setup_refused_when_not_on_this_computer(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"), config={
        "FB_CHECK_APP": lambda *a: None, "ENV_PATH": tmp_path / ".env", "FACEBOOK_APP_ID": "", "FACEBOOK_APP_SECRET": "",
        "FACE_MATCHER": FakeFaceMatcher()})
    c = app.test_client()
    r = c.post("/api/auth/facebook/setup", json={"appId": "1234567890", "appSecret": "a" * 32},
               environ_base={"REMOTE_ADDR": "203.0.113.9"})
    assert r.status_code == 403
    assert c.get("/api/auth/config", base_url="https://findyourmate.example").get_json()["canSetupFacebook"] is False



# ------------------------------------------------------- photo face focus ---

def test_main_photo_must_show_a_face_and_focus_is_stored(app):
    c = register(app, "Ann", "a@x.com", PROFILE_LUNA, verify=False)
    r = c.post("/api/photos/0", data={"photo": (io.BytesIO(b"noface landscape"), "view.jpg", "image/jpeg")},
               content_type="multipart/form-data")
    assert r.status_code == 400 and "face" in r.get_json()["error"]
    s = c.post("/api/photos/0", data={"photo": (io.BytesIO(b"\x89PNG me"), "me.png", "image/png")},
               content_type="multipart/form-data").get_json()
    url = s["profile"]["photos"][0]
    assert s["profile"]["photoFocus"][url] == {"x": 50.0, "y": 30.0, "s": 0.4}
    # other photos may have no face (they just stay centred)
    s = c.post("/api/photos/1", data={"photo": (io.BytesIO(b"noface beach"), "b.jpg", "image/jpeg")},
               content_type="multipart/form-data").get_json()
    assert s["profile"]["photos"][1] and s["profile"]["photos"][1] not in s["profile"]["photoFocus"]
    # removing a photo drops its focus
    s = c.delete("/api/photos/0").get_json()
    assert url not in s["profile"]["photoFocus"]


def test_photo_focus_is_shared_with_other_people(app):
    a = register(app, "Grace", "g@x.com", PROFILE_GRACE)
    b = register(app, "Luna", "l@x.com", PROFILE_LUNA)
    luna = next(m for m in state(a)["matches"] if m["name"] == "Luna")
    assert luna["photoFocus"][luna["photos"][0]]["y"] == 30.0


def test_real_photo_preparation_resizes_and_finds_the_face():
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    skdata = pytest.importorskip("skimage.data")
    if not all((face.MODELS_DIR / name).exists() for name, _, _ in face.MODELS.values()):
        pytest.skip("face models not downloaded (python face.py --download)")
    astro = cv2.cvtColor(skdata.astronaut(), cv2.COLOR_RGB2BGR)
    big = cv2.resize(cv2.copyMakeBorder(astro, 0, 900, 600, 600, cv2.BORDER_CONSTANT, value=(30, 30, 30)), None, fx=2, fy=2)
    data, ext, focus = face.FaceMatcher().prepare_photo(cv2.imencode(".png", big)[1].tobytes(), ".png")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    assert ext == ".jpg" and max(img.shape[:2]) == face.MAX_PHOTO_PX
    assert focus and 40 < focus["x"] < 56 and focus["y"] < 15     # face is near the top, centred
    assert face.FaceMatcher().locate(cv2.imencode(".jpg", np.full((300, 300, 3), 120, np.uint8))[1].tobytes()) is None


# ------------------------------------------------ facebook data deletion ---

def _signed_request(secret, payload):
    import base64, hashlib, hmac, json as _json
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    body = enc(_json.dumps({"algorithm": "HMAC-SHA256", **payload}).encode())
    sig = enc(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{sig}.{body}"


def test_facebook_data_deletion_callback(tmp_path):
    app = _fb_app(tmp_path, {"id": "fb500", "name": "Only FB"})
    c = app.test_client()
    # a Facebook-only account
    c.get("/api/auth/facebook/start")
    with c.session_transaction() as s:
        st = s["fb_state"]
    c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert state(c)["me"]["facebook"] is True
    fb = app.test_client()
    # forged signature is rejected
    bad = fb.post("/api/auth/facebook/data-deletion", data={"signed_request": _signed_request("wrong", {"user_id": "fb500"})})
    assert bad.status_code == 400
    r = fb.post("/api/auth/facebook/data-deletion", data={"signed_request": _signed_request("secret", {"user_id": "fb500"})})
    out = r.get_json()
    assert r.status_code == 200 and out["confirmation_code"] and "deletion-status?code=" in out["url"]
    assert c.get("/api/state").status_code == 401                     # account is gone
    page = fb.get(out["url"].split("localhost:5000")[1]).get_data(as_text=True)
    assert out["confirmation_code"] in page and "permanently deleted" in page


def test_facebook_data_deletion_keeps_email_accounts_but_unlinks(tmp_path):
    app = _fb_app(tmp_path, {"id": "fb600", "name": "Grace", "email": "g@x.com"})
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Grace", "email": "g@x.com", "password": "password123"})
    c.get("/api/auth/facebook/start?link=1")
    with c.session_transaction() as s:
        st = s["fb_state"]
    c.get(f"/api/auth/facebook/callback?code=abc&state={st}")
    assert state(c)["me"]["facebook"] is True
    r = app.test_client().post("/api/auth/facebook/data-deletion",
                               data={"signed_request": _signed_request("secret", {"user_id": "fb600"})})
    assert r.status_code == 200
    s = state(c)
    assert s["me"]["facebook"] is False and s["profile"]["name"] == "Grace"


# ------------------------------------------------- forgot / reset password ---

def _mail_app(tmp_path):
    outbox = []

    def send(to, subject, text, html=None):
        outbox.append({"to": to, "subject": subject, "text": text})
        return True
    app = create_app(db_path=str(tmp_path / "t.db"), upload_dir=str(tmp_path / "up"),
                     config={"SEND_MAIL": send, "FACE_MATCHER": FakeFaceMatcher()})
    return app, outbox


def _link_token(mail):
    import re
    return re.search(r"\?reset=([\w-]+)", mail["text"]).group(1)


def test_forgot_password_emails_a_one_time_link(tmp_path):
    app, outbox = _mail_app(tmp_path)
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Grace", "email": "g@x.com", "password": "oldpassword1"})
    other_device = app.test_client()
    other_device.post("/api/auth/login", json={"email": "g@x.com", "password": "oldpassword1"})
    anon = app.test_client()
    # same reply for unknown emails (doesn't reveal who has an account), and no email is sent
    r1 = anon.post("/api/auth/forgot", json={"email": "nobody@x.com"}).get_json()
    r2 = anon.post("/api/auth/forgot", json={"email": "G@x.com", "origin": "http://localhost:5174"}).get_json()
    assert r1["message"] == r2["message"] and len(outbox) == 1
    assert outbox[0]["to"] == "g@x.com" and "http://localhost:5174/?reset=" in outbox[0]["text"]
    token = _link_token(outbox[0])
    assert anon.get(f"/api/auth/reset/check?token={token}").get_json() == {"valid": True, "email": "g•@x.com"}
    assert anon.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    s = anon.post("/api/auth/reset", json={"token": token, "password": "newpassword1"}).get_json()
    assert s["me"]["email"] == "g@x.com"                                   # signed in after reset
    assert outbox[-1]["subject"] == "Your FindYourMate password was changed"
    # the link only works once, other devices are signed out, and only the new password works
    assert anon.post("/api/auth/reset", json={"token": token, "password": "another123"}).status_code == 400
    assert other_device.get("/api/state").status_code == 401
    assert app.test_client().post("/api/auth/login", json={"email": "g@x.com", "password": "oldpassword1"}).status_code == 401
    assert app.test_client().post("/api/auth/login", json={"email": "g@x.com", "password": "newpassword1"}).status_code == 200


def test_reset_link_expires(tmp_path, monkeypatch):
    import store as store_module
    app, outbox = _mail_app(tmp_path)
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Grace", "email": "g@x.com", "password": "oldpassword1"})
    c.post("/api/auth/forgot", json={"email": "g@x.com"})
    token = _link_token(outbox[0])
    real_now = store_module.now_ms()
    monkeypatch.setattr(store_module, "now_ms", lambda: real_now + 31 * 60 * 1000)
    assert c.post("/api/auth/reset", json={"token": token, "password": "newpassword1"}).status_code == 400


def test_change_password_in_settings(tmp_path):
    app, outbox = _mail_app(tmp_path)
    c = app.test_client()
    c.post("/api/auth/register", json={"name": "Grace", "email": "g@x.com", "password": "oldpassword1"})
    other = app.test_client()
    other.post("/api/auth/login", json={"email": "g@x.com", "password": "oldpassword1"})
    r = c.post("/api/auth/change-password", json={"current": "wrongpass1", "password": "newpassword1"})
    assert r.status_code == 401
    assert c.post("/api/auth/change-password", json={"current": "oldpassword1", "password": "newpassword1"}).status_code == 200
    assert c.get("/api/state").status_code == 200                        # this device stays signed in
    assert other.get("/api/state").status_code == 401                    # others are signed out
    assert outbox[-1]["subject"] == "Your FindYourMate password was changed"
