import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../lib/api.js';
import { countdown, fmtClock, fmtDate, fmtTime, photoStyle, useNow } from '../lib/util.js';
import CandidateHero from './CandidateHero.jsx';
import ChatComposer from './ChatComposer.jsx';

export default function ConnectionTab({ data, act, notify, openProfile, setTab, busy }) {
  const { active, messages, invitations = [], pastChats = [] } = data;
  const now = useNow(data.now);
  const [lightbox, setLightbox] = useState(null);
  const [manageOpen, setManageOpen] = useState(false);
  const [history, setHistory] = useState(null); // past conversation being viewed
  const scrollRef = useRef(null);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages.length]);

  if (!active && invitations.length > 0) {
    const received = invitations.filter((i) => i.state === 'FAVOURED');
    const sent = invitations.filter((i) => i.state === 'INVITED');
    return (
      <div className="stack-sm">
        <div className="soft-box t11 muted" style={{ lineHeight: 1.5 }}>
          You’re not in a connection yet, so you can keep liking people in Discover. Accepting an invitation starts a
          72h chat and closes your other invitations.
        </div>
        {received.length > 0 && <div className="tier-head"><span className="t">♥ LIKED YOU</span><span className="t10 faint">{received.length} waiting • best match first</span></div>}
        {received.map((i) => <InvitationCard key={i.id} inv={i} act={act} busy={busy} openProfile={openProfile} />)}
        {sent.length > 0 && <div className="tier-head"><span className="t">✉ YOUR INVITATIONS</span><span className="t10 faint">{sent.length} waiting for a reply</span></div>}
        {sent.map((i) => <InvitationCard key={i.id} inv={i} act={act} busy={busy} openProfile={openProfile} />)}
        <PastChats chats={pastChats} onOpen={setHistory} />
        {history && <HistorySheet chat={history} onClose={() => setHistory(null)} />}
      </div>
    );
  }

  if (!active) {
    return (
      <div className="empty-state">
        <div className="heart" style={{ background: 'var(--chip)' }}>💬</div>
        <div className="t13 m" style={{ marginTop: 14 }}>No active connection</div>
        <div className="t12 faint" style={{ marginTop: 4, maxWidth: 220, lineHeight: 1.5 }}>No active connection - go to Discover to find someone</div>
        <button className="btn btn-dark btn-sm" style={{ marginTop: 20, padding: '10px 20px', fontSize: 12 }} onClick={() => setTab('Discover')}>Go to Discover</button>
        <div style={{ width: '100%', marginTop: 28, textAlign: 'left' }}><PastChats chats={pastChats} onOpen={setHistory} /></div>
        {history && <HistorySheet chat={history} onClose={() => setHistory(null)} />}
      </div>
    );
  }

  const c = active.candidate;
  const st = active.state;
  const timer = st === 'CHATTING' ? countdown(active.chatDeadline, now) : null;
  const expired = timer && timer.left === 0;

  return (
    <div className="stack-sm">
      <div className="conn-head">
        <button className="avatar" style={{ background: c.color }} onClick={() => openProfile(c)} title={`View ${c.name}'s profile`} aria-label={`View ${c.name}'s profile`}>
          {c.photos?.[0] ? <span className="avatar-crop"><img src={c.photos[0]} alt="" style={photoStyle(c, c.photos[0], { zoom: true })} /></span> : c.name[0]}
          {c.photoVerified && <span className="ok">✓</span>}
        </button>
        <div className="grow">
          <div className="row gap-6"><span className="t13 b">{c.name}</span><span className={`state-pill state-${st}`}>{st}</span>
            {c.isSample && <span className="pill gray t9" title="Seeded profile that replies automatically">Sample</span>}</div>
          <div className="row gap-6 t10 faint" style={{ marginTop: 2 }}>
            <span>{[c.gender, c.age, c.location].filter(Boolean).join(' • ')}</span>
            {timer && <span className={`timer ${timer.left < 6 * 3.6e6 ? 'urgent' : ''}`} title="Confirm within 72h or this conversation closes automatically">{timer.text}</span>}
            {st === 'CHATTING' && active.noTimeLimit && <span className="timer" title="One of you confirmed — no time limit">∞ no time limit</span>}
          </div>
        </div>
        {(st === 'DATING' || st === 'ENGAGED') && (
          <div className="manage">
            <button className="btn btn-light btn-sm" aria-haspopup="menu" aria-expanded={manageOpen} onClick={() => setManageOpen((v) => !v)}>⚙︎ Manage</button>
            {manageOpen && (
              <div className="pop manage-menu" role="menu" onMouseLeave={() => setManageOpen(false)}>
                {st === 'DATING' ? (
                  <>
                    {active.engageRequest === 'sent' ? (
                      <>
                        <div className="menu-note">💍 Waiting for {c.name} to answer</div>
                        <button role="menuitem" onClick={() => { setManageOpen(false); act(api.cancelEngagement, { success: 'Engagement request cancelled' }); }}>↩︎ Cancel engagement request</button>
                      </>
                    ) : active.engageRequest === 'received' ? (
                      <button role="menuitem" onClick={() => setManageOpen(false)}>💍 {c.name} asked to get engaged — answer below</button>
                    ) : (
                      <button role="menuitem" onClick={() => {
                        setManageOpen(false);
                        if (window.confirm(`Ask ${c.name} to get engaged? You'll both become Engaged only if ${c.name} approves. Once engaged, the relationship can no longer be closed.`)) {
                          act(api.engage, { success: `💍 Engagement request sent to ${c.name}` });
                        }
                      }}>💍 Engage</button>
                    )}
                    <button role="menuitem" className="danger" onClick={() => {
                      setManageOpen(false);
                      if (window.confirm(`Close your relationship with ${c.name}? You'll both return to the candidate pool and can no longer chat. Your chat history is kept.`)) {
                        act(api.close, { success: 'Relationship closed — chat history saved under Past conversations' });
                      }
                    }}>💔 Close relationship</button>
                  </>
                ) : (
                  <>
                    <div className="menu-note">💍 You’re engaged to {c.name}</div>
                    <button role="menuitem" disabled title="Engaged relationships can’t be closed">💔 Close relationship</button>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {st === 'DATING' && active.engageRequest === 'received' && (
        <div className="pref-card engage-card" role="status">
          <div className="t12"><b>💍 {c.name} sent you an engagement request.</b> Approve to change both of your statuses to Engaged (the relationship can then no longer be closed), or decline to stay dating.</div>
          <div className="btn-row" style={{ marginTop: 10 }}>
            <button className="btn btn-light" disabled={busy}
              onClick={() => act(api.declineEngagement, { success: 'Engagement request declined — you’re still dating' })}>✕ Decline</button>
            <button className="btn btn-dark" disabled={busy}
              onClick={() => { if (window.confirm(`Get engaged to ${c.name}? This can't be undone.`)) act(api.acceptEngagement, { success: `💍 You and ${c.name} are engaged!` }); }}>💍 Approve</button>
          </div>
        </div>
      )}
      {st === 'DATING' && active.engageRequest === 'sent' && (
        <div className="pref-card t12" role="status">
          💍 Engagement request sent — waiting for <b>{c.name}</b> to approve. Your status stays <b>In Relationship</b> until then.
          <button className="link" style={{ marginLeft: 6 }} disabled={busy} onClick={() => act(api.cancelEngagement, { success: 'Engagement request cancelled' })}>Cancel request</button>
        </div>
      )}

      {/* Confirm / End Conversation only once the invitation is accepted and you can chat. */}
      {/* Before confirming: Confirm + End Conversation. Once dating, these move to the Manage menu. */}
      {st === 'CHATTING' && !active.meConfirmed && active.themConfirmed && (
        <div className="pref-card t12" role="status">
          💜 <b>{c.name} confirmed your relationship.</b> Tap ✓ Confirm Relationship when you’re ready — there’s no time limit.
        </div>
      )}
      {st === 'CHATTING' && (
        <div className="btn-row">
          <button className="btn btn-green" disabled={active.meConfirmed || busy}
            onClick={() => act(api.confirm)}>
            ✓ {active.meConfirmed ? 'Waiting for ' + c.name : active.themConfirmed ? 'Confirm — ' + c.name + ' did' : 'Confirm Relationship'}
          </button>
          <button className="btn btn-red" disabled={busy}
            onClick={() => {
              const msg = `End your conversation with ${c.name}? Both of you return to the candidate pool. Your chat history is kept.`;
              if (window.confirm(msg)) act(api.close, { success: 'Conversation ended — you’re back in the pool' });
            }}>
            ✕ End Conversation
          </button>
        </div>
      )}

      <div className="row between" style={{ paddingTop: 8 }}>
        <span className="t11 b muted" style={{ letterSpacing: '.04em' }}>CONVERSATION</span>
      </div>

      <div className="convo">
        {st === 'FAVOURED' && (
          <div className="stack-sm center">
            <div className="invite-card">
              <div className="t13 m">{c.name} liked you</div>
              <div className="t11 muted" style={{ marginTop: 4, lineHeight: 1.5 }}>{c.bio ? `“${c.bio.slice(0, 64)}…” ` : ''}wants to connect with you. Tap the photo above to view the full profile.</div>
              <span className="pill gray" style={{ marginTop: 8 }}>{c.gender}</span>
            </div>
            <span className="sys-chip">Invitation received • {fmtClock(active.updatedAt)}</span>
          </div>
        )}

        {st === 'INVITED' && (
          <div className="stack-sm center">
            <div className="invite-card">
              <div className="t13 m">Invitation sent to {c.name}</div>
              <div className="t11 muted" style={{ marginTop: 4, lineHeight: 1.5 }}>You’ll start a 72h chat as soon as {c.name} accepts. You can’t like anyone else while this is pending.</div>
            </div>
            <span className="sys-chip">Sent • {fmtClock(active.updatedAt)}</span>
          </div>
        )}

        {(st === 'CHATTING' || st === 'DATING' || st === 'ENGAGED') && (
          <div className="convo-scroll" ref={scrollRef}>
            <div className="t10 faint center" style={{ padding: '4px 0 8px' }}>
              {st === 'ENGAGED' ? <>💍 You and {c.name} are engaged</>
                : st === 'DATING' ? <>💜 You and {c.name} are dating</>
                  : <>You and {c.name} started chatting — 72h commitment timer started</>}
            </div>
            {messages.length === 0 && (
              <div className="center" style={{ padding: '16px 0' }}>
                <div className="t11 faint">No messages yet. Say hello!</div>
                {st === 'CHATTING' && <div className="t10 faint" style={{ marginTop: 4 }}>If neither of you confirms within 72 hours, this conversation closes automatically (your chat history is kept). Once one of you confirms, there's no time limit.</div>}
              </div>
            )}
            {messages.map((m) => <Bubble key={m.id} m={m} onPhoto={setLightbox} />)}
            {expired && <div className="sys-chip" style={{ alignSelf: 'center', color: 'var(--red)' }}>72 hours are up — closing this conversation…</div>}
          </div>
        )}

      </div>

      {st === 'FAVOURED' && (
        <div className="stack-xs" style={{ paddingTop: 4 }}>
          <button className="btn btn-dark btn-block" style={{ padding: 12 }} disabled={busy} onClick={() => act((q) => api.accept(c.id, q))}>Accept Invite</button>
          <button className="btn btn-light btn-block" disabled={busy} onClick={() => act((q) => api.pass(c.id, q))}>Not interested</button>
          <div className="t10 faint center">Accepting starts a 72h chat — confirm within 72 hours or it closes automatically • Tap avatar/photo to view profile</div>
        </div>
      )}

      {st === 'INVITED' && (
        <button className="btn btn-light btn-block" disabled={busy} onClick={() => act((q) => api.pass(c.id, q))}>Withdraw invitation</button>
      )}

      {(st === 'CHATTING' || st === 'DATING' || st === 'ENGAGED') && (
        <ChatDock>
          <ChatComposer act={act} notify={notify} />
          {st === 'CHATTING' && active.meConfirmed && <div className="t10 center" style={{ color: 'var(--purple)' }}>You confirmed — waiting for {c.name} to confirm. No time limit now.</div>}
        </ChatDock>
      )}

      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
    </div>
  );
}

/** Pins the message box to the bottom of the screen, right above the tab bar. */
function ChatDock({ children }) {
  const [host, setHost] = useState(null);
  useEffect(() => {
    const phone = document.querySelector('.phone');
    const body = document.querySelector('.app-body');
    body?.classList.add('has-dock');
    setHost(phone);
    return () => body?.classList.remove('has-dock');
  }, []);
  if (!host) return null;
  return createPortal(<div className="chat-dock stack-xs">{children}</div>, host);
}

function Lightbox({ src, onClose }) {
  return (
    <div className="overlay lightbox" onClick={onClose} role="dialog" aria-label="Photo">
      <img src={src} alt="Shared photo, full size" />
      <button className="close-x" aria-label="Close" style={{ position: 'absolute', top: 44, right: 16 }}>✕</button>
    </div>
  );
}

function Bubble({ m, onPhoto }) {
  if (m.kind === 'system') {
    const happy = m.text.startsWith('Congratulations');
    return (
      <div className={`sys-note ${happy ? 'happy' : 'sad'}`} role="status">
        <span>{happy ? '💍🎉' : '💔'}</span>
        <div>{m.text}<time>{fmtTime(m.at)}</time></div>
      </div>
    );
  }
  return (
    <div className={`bubble ${m.from === 'me' ? 'me' : 'them'} ${m.kind !== 'text' ? 'media' : ''}`}>
      {m.kind === 'image' && (
        <button className="media-btn" onClick={() => onPhoto(m.mediaUrl)} aria-label="Open photo">
          <img src={m.mediaUrl} alt="Shared photo" loading="lazy" />
        </button>
      )}
      {m.kind === 'video' && <video src={m.mediaUrl} controls playsInline preload="metadata" />}
      {m.kind === 'audio' && <audio src={m.mediaUrl} controls preload="metadata" />}
      {m.text && <div className={m.kind !== 'text' ? 'caption' : ''}>{m.text}</div>}
      <time>{m.kind === 'audio' ? '🎙️ ' : ''}{fmtTime(m.at)}</time>
    </div>
  );
}

/** Ended conversations; history stays readable but no new messages can be sent. */
function PastChats({ chats, onOpen }) {
  if (!chats.length) return null;
  return (
    <div className="stack-xs">
      <div className="tier-head"><span className="t">🕘 PAST CONVERSATIONS</span><span className="t10 faint">read only</span></div>
      {chats.map((ch) => (
        <button key={ch.id} className="past-chat" onClick={() => onOpen(ch)}>
          <span className="avatar" style={{ background: ch.candidate.color, width: 36, height: 36, fontSize: 13 }}>
            {ch.candidate.photos?.[0] ? <span className="avatar-crop"><img src={ch.candidate.photos[0]} alt="" style={photoStyle(ch.candidate, ch.candidate.photos[0], { zoom: true })} /></span> : (ch.candidate.name || '?')[0]}
          </span>
          <span className="grow" style={{ textAlign: 'left', minWidth: 0 }}>
            <span className="row between gap-6"><span className="t12 b truncate">{ch.candidate.name}</span><span className="t9 faint">Ended {fmtDate(ch.endedAt)}</span></span>
            <span className="t11 muted truncate" style={{ display: 'block' }}>{ch.lastMessage || 'No messages'}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

function HistorySheet({ chat, onClose }) {
  const [msgs, setMsgs] = useState(null);
  const [error, setError] = useState('');
  const [lightbox, setLightbox] = useState(null);
  useEffect(() => {
    api.pastMessages(chat.id).then((r) => setMsgs(r.messages)).catch((e) => setError(e.message));
  }, [chat.id]);
  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet tall" role="dialog" aria-label={`Past conversation with ${chat.candidate.name}`}>
        <div className="sheet-head centered">
          <div><h2>{chat.candidate.name}</h2><div className="t10 faint" style={{ marginTop: 2 }}>Conversation ended {fmtDate(chat.endedAt)} • read only</div></div>
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body">
          <div className="convo-scroll" style={{ maxHeight: 'none' }}>
            {error && <div className="alert alert-red">{error}</div>}
            {!msgs && !error && <div className="t11 faint center">Loading…</div>}
            {msgs && msgs.length === 0 && <div className="t11 faint center">No messages in this conversation.</div>}
            {msgs?.map((m) => <Bubble key={m.id} m={m} onPhoto={setLightbox} />)}
            {msgs && <div className="sys-chip" style={{ alignSelf: 'center' }}>This conversation has ended — you can no longer send messages</div>}
          </div>
        </div>
        {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
      </div>
    </div>
  );
}

function MatchVerdict({ inv }) {
  if (inv.meetsRequirements == null) return null;
  if (inv.meetsRequirements) {
    return (
      <div className="verdict verdict-ok t11">
        <div className="b">✓ Good match — meets all your requirements</div>
        <div className="row gap-8" style={{ flexWrap: 'wrap', marginTop: 4 }}>
          {inv.twoWay && <span className="pill green">💞 Two-way match</span>}
          {inv.inDiscover && <span className="pill gray">Also shown in Discover</span>}
        </div>
      </div>
    );
  }
  return (
    <div className="verdict verdict-miss t11">
      <div className="b">Not a match for your requirements</div>
      <ul style={{ margin: '4px 0 0', paddingLeft: 16, lineHeight: 1.55 }}>
        {(inv.missedRequirements || []).map((m) => <li key={m}>{m}</li>)}
      </ul>
    </div>
  );
}

function InvitationCard({ inv, act, busy, openProfile }) {
  const c = inv.candidate;
  const received = inv.state === 'FAVOURED';
  return (
    <article className="cand">
      <CandidateHero c={c} short showLocationEthnicity={false} onClick={() => openProfile(c)}
        topLeft={<span className={`state-pill state-${inv.state}`}>{inv.state}</span>}
        topRight={<span className="glass">Tap to view profile →</span>}
        bottomRight={c.matchScore != null ? <span className="match-pill" style={{ position: 'absolute', right: 12, bottom: 14, zIndex: 3 }}>✓ {c.matchScore}%</span> : null} />
      <div className="cand-body stack-xs">
        <div className="t12 m">{received ? `${c.name} liked you` : `Invitation sent to ${c.name}`}</div>
        {received && <MatchVerdict inv={inv} />}
        {c.bio && <p className="t11 muted clamp2" style={{ margin: 0, lineHeight: 1.55 }}>{c.bio}</p>}
        <div className="t10 faint">{received ? 'Received' : 'Sent'} • {fmtClock(inv.updatedAt)}</div>
        <div className="btn-row">
          {received ? (
            <>
              <button className="btn btn-light" disabled={busy} onClick={() => act((q) => api.pass(c.id, q))}>Not interested</button>
              <button className="btn btn-dark" disabled={busy} onClick={() => act((q) => api.accept(c.id, q))}>♥ Accept</button>
            </>
          ) : (
            <button className="btn btn-light" disabled={busy} onClick={() => act((q) => api.pass(c.id, q))}>Withdraw invitation</button>
          )}
        </div>
      </div>
    </article>
  );
}
