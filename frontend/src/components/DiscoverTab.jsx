import { useState } from 'react';
import { api } from '../lib/api.js';
import { rankStyle } from '../lib/util.js';
import CandidateHero, { VerifyChips } from './CandidateHero.jsx';

function CandidateCard({ c, data, act, openProfile, setTab }) {
  const { active, profile } = data;
  const [photo, setPhoto] = useState(0);
  const blocked = !!active;
  const isCurrent = active?.candidateId === c.id;
  const closed = c.connectionState === 'CLOSED';
  const likedMe = c.connectionState === 'FAVOURED'; // they invited you; you haven't answered
  const invited = c.connectionState === 'INVITED'; // you invited them; waiting for them
  const rs = rankStyle(c.rank);
  const shown = c.photos?.length ? { ...c, photos: [c.photos[photo] || c.photos[0]] } : c;
  const tags = [c.gender, c.education?.split(',')[0], c.hobbies?.split(',')[0], c.hometown].filter(Boolean);

  const statusPill = isCurrent
    ? <span className={`state-pill state-${active.state}`}>{active.state}</span>
    : blocked ? <span className="pill red">Blocked</span>
      : likedMe ? <span className="state-pill state-FAVOURED">♥ Liked you</span>
        : invited ? <span className="state-pill state-INVITED">Invited</span>
          : closed ? <span className="pill gray">Passed</span> : null;

  const accept = (e) => {
    e.stopPropagation();
    act(async (q) => {
      const s = await api.accept(c.id, q);
      setTab('Connection');
      return s;
    });
  };

  const like = (e) => {
    e.stopPropagation();
    act(async (q) => {
      const s = await api.like(c.id, q);
      setTab('Connection');
      return s;
    });
  };

  return (
    <article className={`cand ${closed ? 'closed' : ''} ${isCurrent ? 'current' : ''}`}>
      <CandidateHero
        c={shown}
        onClick={() => openProfile(c)}
        glow={rs.shadow}
        topLeft={<>
          <span className="rank-badge" style={{ background: rs.bg, color: rs.text, boxShadow: rs.shadow }}>★ #{c.rank}</span>
          {rs.label && <span className="glass">{rs.label}</span>}
          {c.isSample && <span className="sample-tag" title="Sample profile that replies automatically">Sample</span>}
        </>}
        topRight={<>{statusPill}<span className="glass">Tap to view profile →</span></>}
        bottomRight={<VerifyChips c={c} />}
      />
      <div className="cand-body stack-sm">
        <div className="row gap-10">
          <div className="grow">
            <div className="row between gap-6">
              <span className="t10 b">{c.tier === 'mutual' ? 'Two-way AI match' : 'AI match • meets your requirements'}</span>
              <span className="t10 b" style={{ color: 'var(--green)', whiteSpace: 'nowrap' }}>{c.matchScore}% match</span>
            </div>
            <div className="score-bar"><div style={{ width: `${c.matchScore}%` }} /></div>
          </div>
        </div>
        {c.reasons?.length > 0 && (
          <ul className="reasons">{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        )}
        <div className="tags">{tags.map((t) => <span className="tag" key={t}>{t}</span>)}</div>
        <div className="btn-row">
          <button className="btn btn-light" disabled={blocked || closed}
            onClick={(e) => { e.stopPropagation(); act((q) => api.pass(c.id, q)); }}>
            {invited ? 'Withdraw' : 'Not interested'}
          </button>
          {isCurrent
            ? <button className="btn btn-dark" onClick={(e) => { e.stopPropagation(); setTab('Connection'); }}>{active.state} →</button>
            : likedMe
              ? <button className="btn btn-dark" disabled={blocked} onClick={accept}>♥ Accept</button>
              : invited
                ? <button className="btn btn-dark" disabled>Invited ✓</button>
                : <button className="btn btn-dark" disabled={blocked} onClick={like}>Like</button>}
        </div>
      </div>
    </article>
  );
}

export default function DiscoverTab({ data, act, query, setQuery, onEditIdeal, openProfile, setTab }) {
  const { active, profile, matches } = data;
  const mutual = matches.filter((m) => m.tier === 'mutual');
  const yours = matches.filter((m) => m.tier !== 'mutual');
  const pref = profile.ideal.genderPreference;
  const dating = active?.state === 'DATING';

  return (
    <div className="stack-sm" style={{ paddingBottom: 8 }}>
      {active && (
        <div className="alert alert-redbox">
          <span style={{ color: 'var(--red)', fontSize: 14 }}>⛔</span>
          <div>
            <div className="t12 b">{dating ? 'You are in a relationship. End it to discover new people.' : 'You are in a connection. End relationship to add new.'}</div>
            <div className="t11" style={{ opacity: 0.8, marginTop: 2 }}>
              Currently with {active.candidate.name} — {active.state}. Only one connection allowed.
              {' '}<button className="t11" style={{ textDecoration: 'underline' }} onClick={() => setTab('Connection')}>Open connection</button>
            </div>
          </div>
        </div>
      )}

      <div className="search-row">
        <input className="search" placeholder="Search bio…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search candidates" />
        <span className="count-chip">{matches.length} ranked</span>
      </div>
      {/*<div className="lookfor">*/}
      {/*  <span className="muted">Looking for:</span>*/}
      {/*  <span className="pill dark">{pref || 'Anyone'}</span>*/}
      {/*  <span className="t10 faint">(single)</span>*/}
      {/*  <button className="pill purple" style={{ marginLeft: 'auto', padding: '4px 8px' }} onClick={onEditIdeal}>Edit in Ideal partner</button>*/}
      {/*</div>*/}
      {!profile.confirmed && (
        <div className="alert alert-red">
          <span>ℹ️</span>
          <span>Review your profile and tap ✏️ Edit → Save to appear in Discover and like others.{' '}
            <button className="t11 b" style={{ textDecoration: 'underline', color: 'inherit' }} onClick={() => setTab('Me')}>Go to Me</button></span>
        </div>
      )}

      {mutual.length > 0 && (
        <div className="tier-head">
          <span className="t">💞 TWO-WAY MATCHES</span>
          <span className="t10 faint">you meet each other’s requirements</span>
        </div>
      )}
      {mutual.map((c) => <CandidateCard key={c.id} c={c} data={data} act={act} openProfile={openProfile} setTab={setTab} />)}

      {yours.length > 0 && (
        <div className="tier-head">
          <span className="t">✓ MATCHES YOUR REQUIREMENTS</span>
          <span className="t10 faint">they fit you, you may not fit them</span>
        </div>
      )}
      {yours.map((c) => <CandidateCard key={c.id} c={c} data={data} act={act} openProfile={openProfile} setTab={setTab} />)}

      {matches.length === 0 && (
        <div className="alert alert-redbox" style={{ flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: 16 }}>
          <div className="t12 b">{query ? `Nobody matches “${query}”` : 'No one matches your requirements yet'}</div>
          <div className="t11" style={{ opacity: 0.8 }}>
            {query ? 'Try a different search.' : <>Showing {pref || 'everyone'}{profile.ideal.age ? ` aged ${profile.ideal.age}` : ''} who has a verified, saved profile. Widen your requirements or check back as more people join.</>}
          </div>
          {!query && (
            <button className="btn btn-dark btn-sm" style={{ marginTop: 8 }} onClick={onEditIdeal}>✏️ Edit ideal partner</button>
          )}
        </div>
      )}
    </div>
  );
}
