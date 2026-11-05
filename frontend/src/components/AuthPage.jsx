import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';

function Brand() {
  return (
    <div className="auth-brand">
      <div className="auth-logo">💞</div>
      <h1>FindYourMate</h1>
      <p className="t12 muted">One meaningful connection at a time.</p>
    </div>
  );
}

/** Login / register / forgot-password screen. On success calls onAuthed(snapshot). */
export default function AuthPage({ onAuthed, initialError, initialMode = 'login' }) {
  const [mode, setMode] = useState(initialMode); // login | register | forgot
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(initialError || '');
  const [sent, setSent] = useState(null); // { message, devNote? } after "Send reset link"
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (mode === 'register' && password.length < 8) { setError('Password must be at least 8 characters'); return; }
    setBusy(true);
    try {
      if (mode === 'forgot') {
        setSent(await api.forgotPassword(email));
      } else {
        const snap = mode === 'login' ? await api.login(email, password) : await api.register(name, email, password);
        onAuthed(snap);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (m) => { setMode(m); setError(''); setSent(null); setPassword(''); };

  if (mode === 'forgot') {
    return (
      <div className="auth">
        <Brand />
        <div className="stack-sm">
          <div>
            <div className="t15 b">Forgot your password?</div>
            <p className="t12 muted" style={{ margin: '4px 0 0', lineHeight: 1.5 }}>
              Enter the email you signed up with and we’ll send you a link to choose a new password.
            </p>
          </div>
          {sent ? (
            <>
              <div className="alert alert-green" role="status">✉️ {sent.message}</div>
              {sent.devNote && <div className="alert t11" role="note">{sent.devNote}</div>}
              <button className="btn btn-light btn-block" type="button" onClick={() => setSent(null)}>Send again</button>
            </>
          ) : (
            <form className="stack-sm" onSubmit={submit}>
              <div>
                <label className="field-label" htmlFor="forgot-email">Email</label>
                <input id="forgot-email" className="field" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus />
              </div>
              {error && <div className="alert alert-red" role="alert">{error}</div>}
              <button className="btn btn-dark btn-block" type="submit" disabled={busy} style={{ padding: 13 }}>
                {busy ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
          )}
        </div>
        <div className="t11 muted center" style={{ marginTop: 16 }}>
          <button className="link" onClick={() => switchMode('login')}>← Back to log in</button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth">
      <Brand />

      <div className="auth-tabs" role="tablist">
        <button role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'on' : ''} onClick={() => switchMode('login')}>Log in</button>
        <button role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'on' : ''} onClick={() => switchMode('register')}>Create account</button>
      </div>

      <form className="stack-sm" onSubmit={submit}>
        {mode === 'register' && (
          <div>
            <label className="field-label" htmlFor="auth-name">Name</label>
            <input id="auth-name" className="field" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required maxLength={60} />
          </div>
        )}
        <div>
          <label className="field-label" htmlFor="auth-email">Email</label>
          <input id="auth-email" className="field" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
        </div>
        <div>
          <div className="row between">
            <label className="field-label" htmlFor="auth-pass">Password</label>
            {mode === 'login' && <button type="button" className="link t11" onClick={() => switchMode('forgot')}>Forgot password?</button>}
          </div>
          <input id="auth-pass" className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength={mode === 'register' ? 8 : undefined} />
          {mode === 'register' && <div className="t10 faint" style={{ marginTop: 4 }}>At least 8 characters.</div>}
        </div>
        {error && <div className="alert alert-red" role="alert">{error}</div>}
        <button className="btn btn-dark btn-block" type="submit" disabled={busy} style={{ padding: 13 }}>
          {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
        </button>
      </form>

      <div className="t11 muted center" style={{ marginTop: 16 }}>
        {mode === 'login'
          ? <>New here? <button className="link" onClick={() => switchMode('register')}>Create an account</button></>
          : <>Already have an account? <button className="link" onClick={() => switchMode('login')}>Log in</button></>}
      </div>
    </div>
  );
}

/** Opened from the emailed link (/?reset=<token>): choose a new password, then you're signed in. */
export function ResetPasswordPage({ token, onAuthed, onCancel }) {
  const [check, setCheck] = useState(null); // null = checking, { valid, email }
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.checkReset(token).then(setCheck).catch(() => setCheck({ valid: false })); }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) { setError('Password must be at least 8 characters'); return; }
    if (password !== confirm) { setError('The two passwords don’t match'); return; }
    setBusy(true);
    try { onAuthed(await api.resetPassword(token, password)); } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return (
    <div className="auth">
      <Brand />
      {check === null ? (
        <div className="t12 muted center">Checking your link…</div>
      ) : !check.valid ? (
        <div className="stack-sm">
          <div className="alert alert-red" role="alert">This reset link is invalid or has expired (links last 30 minutes and work once).</div>
          <button className="btn btn-dark btn-block" onClick={() => onCancel('forgot')}>Send a new link</button>
          <button className="btn btn-light btn-block" onClick={() => onCancel('login')}>Back to log in</button>
        </div>
      ) : (
        <form className="stack-sm" onSubmit={submit}>
          <div>
            <div className="t15 b">Choose a new password</div>
            <p className="t12 muted" style={{ margin: '4px 0 0' }}>For {check.email}. You’ll be signed out on other devices.</p>
          </div>
          <div>
            <label className="field-label" htmlFor="reset-pass">New password</label>
            <input id="reset-pass" className="field" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={8} autoFocus />
            <div className="t10 faint" style={{ marginTop: 4 }}>At least 8 characters.</div>
          </div>
          <div>
            <label className="field-label" htmlFor="reset-confirm">Confirm new password</label>
            <input id="reset-confirm" className="field" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />
          </div>
          {error && <div className="alert alert-red" role="alert">{error}</div>}
          <button className="btn btn-dark btn-block" type="submit" disabled={busy} style={{ padding: 13 }}>{busy ? 'Saving…' : 'Save new password'}</button>
          <button type="button" className="link t11" style={{ alignSelf: 'center' }} onClick={() => onCancel('login')}>Cancel</button>
        </form>
      )}
    </div>
  );
}
