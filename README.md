# FindYourMate

A full dating-flow web app — **Python (Flask + SQLite)** backend and **React (Vite)** frontend — built from the
`FindYourMate-Full-Dating-Flow` design.

## Quick start

**Option A — one command (uses the prebuilt UI in `frontend/dist`):**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

**Option B — live-reload development:**

```bash
# terminal 1
cd backend && source .venv/bin/activate && python app.py        # API on :5000
# terminal 2
cd frontend && npm install && npm run dev                        # UI on :5173 (proxies /api and /uploads to :5000)
```

`npm run build` regenerates `frontend/dist`, which Flask serves automatically.

Tests: `cd backend && python -m pip install -r requirements-dev.txt && python -m pytest -q`

> After pulling code changes, restart `python app.py` (Ctrl+C, then run it again) — Python doesn't reload code while
> it's running. On macOS, if port 5000 is taken by AirPlay Receiver, use `PORT=5001 python app.py` and
> `VITE_API_URL=http://127.0.0.1:5001 npm run dev`.

## Accounts & login

- **Email + password** — "Create account" on the login screen. Passwords are hashed (Werkzeug), sessions are signed
  HTTP-only cookies lasting 30 days, and repeated wrong passwords are throttled.
- **Forgot password?** on the login screen emails a one-time link (valid 30 minutes). Opening it lets you choose a
  new password; you're signed in and every other device is signed out. The reply never reveals whether an email
  has an account. **Settings → Change password** changes it with your current password (or emails a link if you
  forgot it). Each change sends a "your password was changed" email.

  **Email setup:** add an SMTP account to `backend/.env` (see `.env.example` — Gmail works with an
  [App password](https://myaccount.google.com/apppasswords)) and restart `python app.py`. Until then, reset emails
  are printed in the backend terminal so you can still test.
- Facebook login has been removed from the login screen. (The backend routes and the Facebook data-deletion
  callback are still there in case you turn it back on.)
- Every user's profile, photos, connections, chats and activity are stored in SQLite (`backend/findyourmate.db`).
  Settings → **Delete account** removes everything for that user.

## Features

### Me
- Setup checklist for new accounts (bio → ideal partner → main photo → "Verify it's me").
- 9-slot photo grid with real uploads. After "Verify it's me" the grid is locked to filled photos; **✏️ Edit** opens
  add-more mode (the verified main photo stays locked).
- **Verify it's me** — face recognition: a 3-second live selfie is captured with the camera (upload fallback) and
  6 frames from it are compared with your main photo on the server (see *Face recognition* below). It only passes if
  it's the same person; the match % is shown on the button and in Settings.
- Bio card with 🎓 education, ⚧️ gender and 💍 relationship-status title rows, bio text and facts (name, age,
  ethnicity, nationality, faith, career, location, height, hobbies, hometown, MBTI).
- Ideal partner shown read-only, with "Looking for" as a label. Everything is edited only through the ✏️ **Edit**
  dialogs; saving a dialog also confirms your profile (makes you eligible for Discover).
- Edit Bio: gender chips (Male, Female, Transgender, Non-binary, Other), relationship status, 🎤 voice dictation. Edit Ideal partner: single-choice Looking for, age range, education
  (Bachelor's / Master's / Doctor's), ethnicity, minimum height, not-want list (these are must-match), plus
  occupation, skin color, location and "Other requirement" (🎤 voice) which only affect the score.

### Discover
- Real profiles from the database, **AI-ranked** (see below) in two sections with no duplicates:
  **💞 Two-way matches** first, then **✓ Matches your requirements**.
- Each card shows rank badge (gold/silver/bronze), match %, top reasons, verification chips and photos; tap for the
  full profile sheet. Search box filters by name, bio, hobbies, career, location.
- **Pending invitations don't lock you**: until one is accepted you can keep liking / passing anyone. Cards show
  "♥ Liked you" (→ **♥ Accept**) or "Invited ✓" (→ **Withdraw**). Liking back someone who liked you accepts.
- Once you're in an accepted connection, a banner explains you're connected and Like is disabled.

### Connection
- **Liked you** list — sorted by match score (highest first); ties go to whoever liked you first. Accept /
  Not interested on each. Every card is checked against your must-match requirements: **✓ Good match** (with
  "Two-way match" / "Also shown in Discover" tags) or **Not a match** listing exactly what was missed, e.g.
  "Height 5'4 — you want at least 5'7". **Your invitations** list with Withdraw.
- Accepting starts a **72h chat** (live countdown) and locks **both** people: all their other invitations close
  and both leave everyone's Discover.
- **72-hour rule:** if neither person confirms within 72 hours, the conversation closes automatically — both return
  to the pool and the chat history is kept under Past conversations. Once **either** person confirms, the countdown
  is replaced by "∞ no time limit" and the other sees a prompt to confirm whenever they're ready.
- While chatting: **✓ Confirm Relationship** (DATING only when **both** confirm) and **✕ End Conversation**.
  Those buttons appear only after an invitation is accepted.
- Connected view shows just the partner's photo icon (tap → profile) above the chat.
- **Dating / Engaged**: the chat continues as before; Confirm / End Conversation are replaced by a
  **⚙︎ Manage** menu next to the partner's icon:
  - **💍 Engage** → sends an **engagement request**. Your partner sees it in Connection with **💍 Approve** / **✕ Decline**;
    only when they approve do both people become ENGAGED (after which the relationship can no longer be closed).
    The asker can cancel a pending request, and if both of you tap Engage it counts as agreement.
    The answer appears in the chat: if declined, the person who proposed sees *“The proposal of engagement was declined.”*;
    if approved, both see *“Congratulations, you successfully got engaged!”*
  - **💔 Close relationship** → the connection ends, both return to the pool and can't message each other.
- **Past conversations** — ended chats stay readable (text, photos, videos, voice) in a read-only view.

### Chat
- Emoji picker · 🎤 voice typing · **＋** menu: take a photo or video with the in-app camera (front/back flip),
  send a photo/video from your library, record a voice message · preview with caption before sending ·
  photos open full-screen.
- Attachments up to 25 MB, stored in `backend/uploads/chat/` and served only to the two people in the chat
  (`/api/media/<id>`), never from the public uploads folder.

### Settings
Verification status, connection rules, stats, log out, delete account.

### Sample profiles
Six seeded accounts (Maya, Sofia, Aisha, Emma, Kenji, Zara), labelled **Sample**, accept likes, reply to messages
and confirm automatically so the app works before many people sign up. Set `SEED_SAMPLE_USERS=0` to turn them off.

## AI compatibility ranking (`backend/ranking.py`)

1. **Pool** — people with a saved, verified profile whose status is **Single** (Dating, In Relationship and Engaged
   profiles are ignored) and who aren't locked in someone else's accepted connection. People who **liked you** are
   added even before "Verify it's me", so anyone who liked you and passes your requirements shows in Discover.
2. **Must-match requirements** (people who fail any are hidden; blank / "No preference" requirements are skipped):
   - gender = your "Looking for" · age within your range
   - height ≥ your minimum. Heights are entered, stored and compared in **centimetres** (e.g. `168`); older values
     like `5'6`, `5.5` ft or `66` (inches) are converted to cm when saved
   - education ≥ your level: Bachelor's < Master's < Doctor's (PhD, MD…)
   - ethnicity is one you listed
   - nothing from your "Not want" list appears in their introduction or profile ("non-smoker", "never smoke"
     and "no drugs" don't count as mentions)

   A candidate who left height, education or ethnicity blank is not hidden for it.
3. **Two groups** — if you also meet *their* must-match requirements they're a *two-way match* (shown first);
   otherwise *matches your requirements*.
4. **Score (0–1)** — weighted average of the factors that have data (missing ones are skipped):

   | Factor | Weight |
   | --- | --- |
   | Bio & hobby text similarity (TF-IDF cosine over all profiles) | 22% |
   | Shared hobbies | 14% |
   | "Other requirement" terms met (understands "no X" / "non-X") | 16% |
   | Location (same city / preferred area / same state) | 10% |
   | MBTI letter compatibility (MBTI is not a partner requirement) | 10% |
   | Age fit within your range | 10% |
   | Education / ethnicity / occupation preferences | 12% |
   | Verification badges (selfie face match, relationship status — education isn't verified or scored) | 6% |

   minus "Not want" penalties (e.g. smoking −0.15, long-distance −0.10).
5. **Match %** — two-way matches: average of your score for them and theirs for you × 100; otherwise your score × 100.
   Each group is sorted by match %; the top factors become the reasons on each card.

Tune the weights in `WEIGHTS` at the top of `ranking.py`.

## Face recognition (`backend/face.py`)

"Verify it's me" uses OpenCV's **YuNet** face detector and **SFace** face-recognition model (ONNX files from the
OpenCV model zoo, ~39 MB). They download into `backend/models/` automatically the first time the backend starts;
to fetch them ahead of time run `python face.py --download`.

1. Find the largest face in your main photo (it must be JPG / PNG / WEBP and show a clear face).
2. Find the face in each live selfie frame (at least 2 frames must contain a face).
3. Align both faces and compute a 128-number face embedding for each with SFace.
4. Compare with cosine similarity; the median across frames must be ≥ 0.40 (SFace's published same-person
   threshold is 0.363). Frames that are all identical are rejected as a still picture.

**Face-aware photos:** every uploaded profile photo is resized (long side ≤ 1600 px, phone rotation applied) and the
face is located. Discover cards, the profile view, your photo grid and the Connection avatars position each photo
so the face stays in view (round avatars zoom in on it). The **main photo must show a face** — uploads without one are
refused with a message; other photos may be anything. Photos uploaded earlier are scanned once in the background
when the backend starts.

Selfie frames are processed in memory and never stored. Changing the main photo resets the verification.
Check two images yourself: `python face.py main.jpg selfie1.jpg selfie2.jpg`.

## Connection state machine

```
like ─▶ INVITED (sender) / FAVOURED (receiver) ─accept─▶ CHATTING ─both confirm─▶ DATING ─engage request + partner approves─▶ ENGAGED
  pending: decline / withdraw ─▶ CLOSED        End Conversation / Close relationship ─▶ CLOSED (history kept)
  (pending invitations don't lock anyone; accepting locks both and closes their other invitations)
```

## Project layout

```
backend/
  app.py          Flask routes: auth (email + Facebook), sessions, JSON API, chat media, serves frontend/dist
  logic.py        Accounts, profile validation, connection state machine, sample-account behaviour
  ranking.py      AI compatibility scoring and two-tier Discover ranking
  store.py        SQLite persistence (users, connections, passes, messages, events) + automatic migrations
  seed_data.py    Options, new-user profile defaults, sample accounts
  tests/          pytest API tests
frontend/
  src/App.jsx                 Login gate, tabs, polling, toasts
  src/components/             AuthPage, MeTab, DiscoverTab, ConnectionTab, ChatComposer, CameraDialog,
                              SettingsTab, ProfileModal, BioDialog, IdealDialog, SelfieDialog,
                              ActivityPanel, CandidateHero
  src/lib/                    API client, helpers (gender icons, countdown, voice input)
  dist/                       Prebuilt UI served by Flask
```

## API

All endpoints except auth require a logged-in session; mutations return the caller's full snapshot.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/register` · `/login` · `/logout` | Email auth |
| GET | `/api/auth/facebook/start` → `/callback` | Facebook OAuth |
| GET | `/api/auth/config` · `/api/auth/me` | Is Facebook enabled · who am I |
| GET | `/api/state?q=` | Profile, ranked matches, invitations, active connection, messages, past chats, activity |
| PUT | `/api/profile` | Update profile (`"confirm": true` also confirms it) |
| POST | `/api/profile/verify-photo` | Selfie face-match verification |
| POST / DELETE | `/api/photos/<slot>` | Upload / remove photo 0–8 |
| POST | `/api/candidates/<id>/like` · `/pass` | Like / Not interested (decline or withdraw when pending) |
| POST | `/api/connection/accept` (`{candidateId}`) · `/confirm` · `/close` · `/engage` | Connection actions |
| POST | `/api/connection/engage/accept` · `/engage/decline` · `/engage/cancel` | Answer / withdraw an engagement request |
| POST | `/api/messages` | Send text (JSON) or a photo / video / voice file (multipart `file`, optional `text`) |
| GET | `/api/media/<message_id>` | Chat attachment (participants only) |
| GET | `/api/connections/<id>/messages` | Read-only history of an ended conversation |
| DELETE | `/api/events` · `/api/account` | Clear activity · delete account |

## Environment variables (all optional)

`SECRET_KEY` (auto-generated into `backend/.secret_key` if unset) · `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` ·
`APP_URL` · `PORT` · `FYM_DB` · `FYM_UPLOADS` · `SEED_SAMPLE_USERS`

## Known limits / next steps

- Chat updates by polling (about every 1.5 s while connected); WebSockets would make it instant.
- No password-reset email or email verification yet.
- The liveness check is basic (the frames must change, so a held-up still photo fails); it won't stop a replayed
  video of someone else.
- Camera, microphone and voice typing need a secure page (`localhost` or HTTPS). Voice typing works in Chrome, Edge
  and Safari.
- For production: serve over HTTPS, set `SECRET_KEY`, and enable `SESSION_COOKIE_SECURE`.
