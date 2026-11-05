import { useState } from 'react';
import { api } from '../lib/api.js';

export default function SettingsTab({ data, onLogout }) {
  const { profile, active, stats, userStatus, matches } = data;
  return (
    <div className="stack" style={{ paddingTop: 8 }}>
      <div>
        <div className="t13 m">Settings</div>
        <p className="t11 muted" style={{ lineHeight: 1.5, margin: '6px 0 0' }}>
          Privacy, notifications and verification. Your bio shows education, gender and relationship status as titles.
        </p>
      </div>

      <div className="card white card-pad">
        <div className="t12 b">Verification</div>
        <div className="stack-xs t11" style={{ marginTop: 10 }}>
          <Row label="Selfie Matched" ok={profile.photoVerified} detail={profile.photoMatchScore ? `face match ${profile.photoMatchScore}%` : null} />
          <Row label="Relationship Status" ok={profile.marriageVerified} detail={profile.marriageStatus} />
          <Row label="Profile Confirmed" ok={profile.confirmed} />
        </div>
      </div>

      <div className="card white card-pad">
        <div className="t12 b">Connection rules</div>
        <ul className="t11 muted" style={{ margin: '10px 0 0', paddingLeft: 16, lineHeight: 1.7 }}>
          <li>Only Single profiles are matched — anyone marked Dating, In Relationship or Engaged is ignored</li>
          <li>Discover only shows people who meet your must-match requirements: gender, age, minimum height, minimum education, ethnicity, and nothing from your “Not want” list</li>
          <li>Everyone who liked you is checked against your requirements; if they pass, they also appear in Discover (tagged ♥ Liked you)</li>
          <li>Two-way matches (you also meet their must-match requirements) are listed first</li>
          <li>Invitations you send or receive don’t lock you — keep liking until one is accepted</li>
          <li>Once an invitation is accepted, both people are in 1 connection and can’t like anyone new</li>
          <li>Accepting starts a 72h chat and closes both people’s other invitations</li>
          <li>If neither person confirms within 72h, the conversation closes automatically (history kept, both back in the pool). Once one person confirms, there’s no time limit</li>
          <li>Both confirm → DATING: status In Relationship, profile hidden, isAvailable = false</li>
          <li>End Conversation (or Manage → Close relationship while dating) → CLOSED → both re-enter the pool; chat history stays under Past conversations</li>
          <li>Manage → Engage sends an engagement request; only when your partner approves do you both become ENGAGED (they can also decline, and you can cancel). Once engaged, the relationship can no longer be closed</li>
          <li>“Verify it’s me” uses face recognition: frames from a live selfie video are compared with your main photo, and it only passes if it’s the same person</li>
          <li>Changing your main photo resets “Verify it’s me”</li>
          <li>You appear in Discover once your profile is saved and “Verify it’s me” is done</li>
        </ul>
      </div>

      <div className="card white card-pad">
        <div className="t12 b">Storage &amp; filters</div>
        <div className="t11 muted" style={{ marginTop: 8, lineHeight: 1.6 }}>
          {stats.people} people in your pool • {stats.connections} connections • {stats.messages} messages sent
            {' '}{matches.length} matches • active: {active ? active.candidate?.name : 'none'}
        </div>
      </div>

      <div className="card white card-pad">
        <div className="t12 b">Account</div>
        <div className="t11 muted" style={{ marginTop: 6, lineHeight: 1.6 }}>
          {data.me.email || 'No email on file'}
        </div>
        <PasswordCard me={data.me} />
        <div className="stack-xs" style={{ marginTop: 10 }}>
          <button className="btn btn-light btn-block" onClick={onLogout}>Log out</button>
          <button className="btn btn-red btn-block" onClick={async () => {
            if (!window.confirm('Delete your account? Your profile, photos, chats and connections will be permanently removed.')) return;
            try { await api.deleteAccount(); onLogout(true); } catch (e) { window.alert(e.message); }
          }}>Delete account</button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, ok, detail }) {
  return (
    <div className="row between gap-8">
      <span>{label}{detail ? <span className="faint"> · {detail}</span> : null}</span>
      {ok ? <span className="pill green">✓</span> : <span className="pill gray">Pending</span>}
    </div>
  );
}

/** Change password (needs the current one), or get an emailed link if you forgot it / never set one. */
function PasswordCard({ me }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [msg, setMsg] = useState(null); // { kind: 'ok' | 'err', text }
  const [busy, setBusy] = useState(false);
  const run = async (fn) => {
    setBusy(true); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ kind: 'err', text: e.message }); } finally { setBusy(false); }
  };
  const emailLink = () => run(async () => {
    const r = await api.forgotPassword(me.email);
    setMsg({ kind: 'ok', text: `Reset link sent to ${me.email}. ${r.devNote || ''}` });
  });
  const save = (e) => {
    e.preventDefault();
    if (next.length < 8) { setMsg({ kind: 'err', text: 'New password must be at least 8 characters' }); return; }
    if (next !== confirm) { setMsg({ kind: 'err', text: 'The two new passwords don’t match' }); return; }
    run(async () => {
      await api.changePassword(current, next);
      setCurrent(''); setNext(''); setConfirm(''); setOpen(false);
      setMsg({ kind: 'ok', text: 'Password changed ✓ Other devices were signed out.' });
    });
  };
  if (!me.email) return null;
  return (
    <div className="stack-xs" style={{ marginTop: 10 }}>
      {!me.hasPassword ? (
        <button className="btn btn-light btn-block" disabled={busy} onClick={emailLink}>Email me a link to set a password</button>
      ) : !open ? (
        <button className="btn btn-light btn-block" onClick={() => { setOpen(true); setMsg(null); }}>Change password</button>
      ) : (
        <form className="stack-xs" onSubmit={save}>
          <label className="field-label" htmlFor="pw-current">Current password</label>
          <input id="pw-current" className="field" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          <label className="field-label" htmlFor="pw-new">New password</label>
          <input id="pw-new" className="field" type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
          <label className="field-label" htmlFor="pw-confirm">Confirm new password</label>
          <input id="pw-confirm" className="field" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          <div className="btn-row">
            <button type="button" className="btn btn-light" onClick={() => { setOpen(false); setMsg(null); }}>Cancel</button>
            <button className="btn btn-dark" disabled={busy}>{busy ? 'Saving…' : 'Save password'}</button>
          </div>
          <button type="button" className="link t11" style={{ alignSelf: 'center' }} disabled={busy} onClick={emailLink}>Forgot your current password? Email me a reset link</button>
        </form>
      )}
      {msg && <div className={`alert ${msg.kind === 'ok' ? 'alert-green' : 'alert-red'} t11`} role="status">{msg.text}</div>}
    </div>
  );
}
