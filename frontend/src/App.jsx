import { useCallback, useEffect, useRef, useState } from 'react';
import { api, setUnauthorizedHandler } from './lib/api.js';
import AuthPage, { ResetPasswordPage } from './components/AuthPage.jsx';
import MeTab from './components/MeTab.jsx';
import DiscoverTab from './components/DiscoverTab.jsx';
import ConnectionTab from './components/ConnectionTab.jsx';
import SettingsTab from './components/SettingsTab.jsx';
import ProfileModal from './components/ProfileModal.jsx';
import BioDialog from './components/BioDialog.jsx';
import IdealDialog from './components/IdealDialog.jsx';
import SelfieDialog from './components/SelfieDialog.jsx';
import ActivityPanel from './components/ActivityPanel.jsx';

const TABS = ['Me', 'Discover', 'Connection', 'Settings'];

export default function App() {
  const [data, setData] = useState(null);
  const [authed, setAuthed] = useState(null); // null = checking, false = show login, true = signed in
  const [authError, setAuthError] = useState(() => new URLSearchParams(window.location.search).get('auth_error') || '');
  const [authNotice] = useState(() => new URLSearchParams(window.location.search).get('auth_notice') || '');
  // Emailed password-reset link: /?reset=<token>
  const [resetToken, setResetToken] = useState(() => new URLSearchParams(window.location.search).get('reset') || '');
  const [authStart, setAuthStart] = useState('login');
  const [loadError, setLoadError] = useState(null);
  const [tab, setTab] = useState('Me');
  const [query, setQuery] = useState('');
  const [dialog, setDialog] = useState(null); // 'bio' | 'ideal' | 'selfie' | 'panel'
  const [profileCand, setProfileCand] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const queryRef = useRef(query);
  queryRef.current = query;
  const bodyRef = useRef(null);
  const mutationSeq = useRef(0);

  // Session expired / logged out anywhere -> back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => { setAuthed(false); setData(null); });
    if (/auth_(error|notice)|reset=/.test(window.location.search)) window.history.replaceState(null, '', window.location.pathname);
  }, []);

  const notify = useCallback((text, kind = 'info') => {
    setToast({ text, kind, id: Date.now() });
  }, []);

  // Result of "Link Facebook" (Settings) comes back as ?auth_notice / ?auth_error while signed in.
  useEffect(() => {
    if (!authed) return;
    if (authNotice) notify(authNotice);
    else if (authError) { notify(authError, 'err'); setAuthError(''); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed]);

  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 3800);
    return () => clearTimeout(t);
  }, [toast]);

  /** Run an API call that returns a fresh snapshot; surface errors as a toast. */
  const act = useCallback(async (call, { success } = {}) => {
    setBusy(true);
    mutationSeq.current += 1; // any poll started before this point is now stale
    try {
      const next = await call(queryRef.current);
      setData(next);
      if (success) notify(success);
      return next;
    } catch (e) {
      notify(e.message, 'err');
      // Errors like "blocked like" also write events; refresh so the log shows them.
      api.state(queryRef.current).then(setData).catch(() => {});
      return null;
    } finally {
      setBusy(false);
    }
  }, [notify]);

  const refresh = useCallback(() => {
    const seq = mutationSeq.current;
    return api.state(queryRef.current)
      .then((d) => { if (seq === mutationSeq.current) { setData(d); setAuthed(true); setLoadError(null); } })
      .catch((e) => { if (e.status !== 401) setLoadError(e.message); });
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!authed) return undefined;
    const t = setTimeout(refresh, 200);
    return () => clearTimeout(t);
  }, [query, refresh, authed]);

  // Poll faster while a chat or a pending mutual confirmation is in flight.
  const activeState = data?.active?.state;
  const fast = ['CHATTING', 'DATING', 'ENGAGED'].includes(activeState);
  useEffect(() => {
    if (!authed) return undefined;
    const t = setInterval(refresh, fast ? 1500 : 5000);
    return () => clearInterval(t);
  }, [fast, refresh, authed]);

  useEffect(() => {
    bodyRef.current?.scrollTo(0, 0);
    setMenuOpen(false);
    if (authed) refresh(); // fresh matches / connection status whenever you switch tabs
  }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const onAuthed = (snap) => { setData(snap); setAuthed(true); setAuthError(''); setResetToken(''); setTab('Me'); };
  const logout = async (skipServer) => {
    if (skipServer !== true) await api.logout().catch(() => {});
    setAuthed(false); setData(null); setDialog(null); setProfileCand(null); setQuery(""); setToast(null);
  };

  if (resetToken) {
    return (
      <div className="page"><div className="stage">
        <div className="phone-col"><div className="phone"><div className="notch" />
          <ResetPasswordPage token={resetToken} onAuthed={(snap) => { onAuthed(snap); notify('Password changed — you’re signed in ✓'); }}
            onCancel={(m) => { setResetToken(''); setAuthStart(m); if (authed !== true) setAuthed(false); }} />
        </div></div>
      </div></div>
    );
  }

  if (authed === false) {
    return (
      <div className="page"><div className="stage">
        <div className="phone-col"><div className="phone"><div className="notch" />
          <AuthPage key={authStart} onAuthed={onAuthed} initialError={authError} initialMode={authStart} />
        </div></div>
        <aside className="panel-col">
          <div className="panel-title">FindYourMate</div>
          <div className="panel-card t12 muted" style={{ lineHeight: 1.7 }}>
            <b>How it works</b><br />
            1. Sign up with your email and fill in your profile.<br />
            2. Discover ranks people with AI — two-way matches first, then people who fit your requirements.<br />
            3. One connection at a time: like → chat for 72h → both confirm to start dating.
          </div>
        </aside>
      </div></div>
    );
  }

  if (!data) {
    return (
      <div className="page"><div className="stage"><div className="phone-col"><div className="phone">
        <div className="empty-state" style={{ margin: 'auto' }}>
          <div className="t13 m">{loadError ? 'Can’t load FindYourMate' : 'Loading…'}</div>
          {loadError && <div className="t11 faint" style={{ marginTop: 6 }}>{loadError}</div>}
          {loadError && <button className="btn btn-dark btn-sm" style={{ marginTop: 14 }} onClick={refresh}>Retry</button>}
        </div>
      </div></div></div></div>
    );
  }

  const openProfile = (c) => setProfileCand(c);
  // Keep the open profile fresh as polling brings new data.
  const profileCandidate = profileCand
    ? (data.matches.find((c) => c.id === profileCand.id)
      || (data.active?.candidate?.id === profileCand.id ? { ...profileCand, ...data.active.candidate } : null)
      || { ...profileCand, ...(data.invitations || []).find((i) => i.candidateId === profileCand.id)?.candidate })
    : null;
  const goIdeal = () => { setTab('Me'); setDialog('ideal'); };

  const shared = { data, act, notify, busy, openProfile, setTab };

  return (
    <div className="page">
      <div className="stage">
        <div className="phone-col">
          <div className="phone">
            <div className="notch" />
            <header className="app-header">
              <div style={{ width: 24 }} />
              <h1>{tab}</h1>
              <button className="menu-btn" aria-label="Menu" onClick={() => setMenuOpen((v) => !v)}>⋯</button>
            </header>
            {menuOpen && (
              <div className="menu" onMouseLeave={() => setMenuOpen(false)}>
                <button onClick={() => { setDialog('bio'); setMenuOpen(false); setTab('Me'); }}>✏️ Edit bio</button>
                <button onClick={() => { goIdeal(); setMenuOpen(false); }}>💞 Edit ideal partner</button>
                <button className="mobile-only" onClick={() => { setDialog('panel'); setMenuOpen(false); }}>📋 Activity</button>
                <button onClick={() => { setMenuOpen(false); logout(); }}>↪ Log out</button>
              </div>
            )}

            <main className="app-body" ref={bodyRef}>
              {tab === 'Me' && <MeTab {...shared} onEditBio={() => setDialog('bio')} onEditIdeal={() => setDialog('ideal')} onVerify={() => setDialog('selfie')} />}
              {tab === 'Discover' && <DiscoverTab {...shared} query={query} setQuery={setQuery} onEditIdeal={goIdeal} />}
              {tab === 'Connection' && <ConnectionTab {...shared} />}
              {tab === 'Settings' && <SettingsTab {...shared} onLogout={logout} />}
            </main>

            <nav className="tabbar">
              {TABS.map((t) => (
                <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
                  {t}
                  {t === 'Connection' && (data.active || data.invitations?.some((i) => i.state === 'FAVOURED')) && <span className="dot" />}
                </button>
              ))}
            </nav>

            {profileCandidate && <ProfileModal {...shared} candidate={profileCandidate} onClose={() => setProfileCand(null)} />}
            {dialog === 'bio' && <BioDialog {...shared} onClose={() => setDialog(null)} />}
            {dialog === 'ideal' && <IdealDialog {...shared} onClose={() => setDialog(null)} />}
            {dialog === 'selfie' && <SelfieDialog {...shared} onClose={() => setDialog(null)} />}
            {dialog === 'panel' && (
              <div className="overlay" onClick={(e) => e.target === e.currentTarget && setDialog(null)}>
                <div className="sheet tall">
                  <div className="sheet-head centered"><h2>Activity</h2><button className="close-x" onClick={() => setDialog(null)}>✕</button></div>
                  <div className="sheet-body"><ActivityPanel {...shared} compact /></div>
                </div>
              </div>
            )}

            {toast && (
              <div className={`toast ${toast.kind === 'err' ? 'err' : ''}`} role="status" key={toast.id}>
                <span className="grow">{toast.text}</span>
                <button onClick={() => setToast(null)} aria-label="Dismiss">✕</button>
              </div>
            )}
          </div>
          <div className="phone-caption">
            Signed in as {data.profile.name || data.me.email}
          </div>
        </div>

        <aside className="panel-col">
          <ActivityPanel {...shared} />
        </aside>
      </div>
    </div>
  );
}
