import { useState } from 'react';
import { api } from '../lib/api.js';
import { formatHeight, genderIcon, photoStyle } from '../lib/util.js';

const FIELDS = [['Gender', 'gender'], ['Age', 'age'], ['Ethnicity', 'ethnicity'], ['Nationality', 'nationality'],
  ['Faith', 'faith'], ['Career', 'career'], ['Location', 'location'], ['Height', 'height'],
  ['Hobbies', 'hobbies'], ['Hometown', 'hometown'], ['Skin', 'skin'], ['MBTI', 'mbti']];

export default function ProfileModal({ candidate: c, data, act, onClose, setTab, busy }) {
  const [idx, setIdx] = useState(0);
  const { active } = data;
  const isActive = active?.candidateId === c.id;
  const blocked = !!active && !isActive;
  const invite = (data.invitations || []).find((i) => i.candidateId === c.id);
  const state = isActive ? active.state : (invite?.state || c.connectionState || 'RECOMMENDED');
  const n = Math.max(1, c.photoCount || 0);
  const photo = c.photos?.[idx];

  const like = () => act(async (q) => { const s = await api.like(c.id, q); onClose(); setTab('Connection'); return s; });
  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet tall" role="dialog" aria-label={`${c.name}'s profile`}>
        <div className="sheet-head centered">
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
          <h2 style={{ fontSize: 14, fontWeight: 500 }}>Profile • {state === 'RECOMMENDED' ? 'Discover' : state.charAt(0) + state.slice(1).toLowerCase()}</h2>
          <div style={{ width: 28 }} />
        </div>
        <div className="sheet-body stack-sm">
          <div className="card white" style={{ padding: 0 }}>
            <div className="carousel" style={{ background: c.color, borderRadius: '16px 16px 0 0' }}>
              {photo
                ? <img src={photo} alt={`${c.name} photo ${idx + 1}`} style={photoStyle(c, photo)} />
                : <div className="initial" style={{ color: c.color }}>{idx === 0 ? (c.name || '?')[0] : idx + 1}</div>}
              <span className="photo-no">{idx + 1} / {n}</span>
              {n > 1 && <button className="nav l" onClick={() => setIdx((idx - 1 + n) % n)} aria-label="Previous photo">‹</button>}
              {n > 1 && <button className="nav r" onClick={() => setIdx((idx + 1) % n)} aria-label="Next photo">›</button>}
              <div style={{ position: 'absolute', left: 12, bottom: 12, color: '#fff', zIndex: 2 }}>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{c.name}{c.age ? `, ${c.age}` : ''} <span style={{ fontSize: 16 }}>{c.gender}</span></div>
                <div className="t11" style={{ opacity: 0.9 }}>{c.location} • {formatHeight(c.height)} • {c.mbti}</div>
              </div>
              <span className="pill dark" style={{ position: 'absolute', right: 12, bottom: 14, zIndex: 2, padding: '4px 10px' }}>{c.matchScore}% match</span>
            </div>
            <div style={{ padding: 8 }} className="stack-xs">
              {/*<div className="ptabs">*/}
              {/*  {Array.from({ length: Math.min(n, 5) }).map((_, i) => (*/}
              {/*    <button key={i} className={`ptab ${idx === i ? 'on' : ''}`} onClick={() => setIdx(i)}>{i === 0 ? 'Main' : i + 1}</button>*/}
              {/*  ))}*/}
              {/*</div>*/}
              <div className="tags">
                <span className="tag">{c.gender}</span>
                {c.photoVerified && <span className="tag purple">✓ It’s me verified</span>}
                {c.isSample && <span className="tag" title="Seeded profile that replies automatically">Sample profile</span>}
              </div>
              {c.reasons?.length > 0 && <ul className="reasons" style={{ padding: '4px 2px' }}>{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            </div>
          </div>

          <div className="row gap-8" style={{ paddingTop: 6 }}>
            <span className="t12 b">Bio Details</span>
            <span className="pill gray t9">Education + Gender + Single titles</span>
          </div>
          <div className="card">
            <div className="title-row"><span className="icon">🎓</span><span className="value grow">{c.education}</span></div>
            <div className="title-row"><span className="icon">{genderIcon(c.gender)}</span><span className="value grow">{c.gender}</span>
              <span className="pill pink">{genderIcon(c.gender)} {c.gender}</span></div>
            <div className="title-row"><span className="icon">💍</span>
              <span className="value grow">{c.relationshipStatus}{c.marriageVerified ? ' Verified' : ''}</span>
              <span className={`pill ${c.relationshipStatus === 'Single' ? 'dark' : 'purple'}`}>{c.relationshipStatus} {c.marriageVerified ? '✓' : ''}</span></div>
            <div className="bio-text" style={{ background: 'transparent', border: 0, margin: 0, fontSize: 12 }}>{c.bio}</div>
          </div>

          <div className="fact-grid" style={{ padding: 0 }}>
            {FIELDS.map(([label, key]) => (
              <div className="fact" key={key}><div className="label-caps">{label}</div><div className="v">{(key === 'height' ? formatHeight(c[key]) : c[key]) || '—'}</div></div>
            ))}
          </div>

          <div className="card white card-pad">
            <div className="t11 b">{c.name}’s ideal partner</div>
            <div className="t11 muted" style={{ marginTop: 4 }}>
              {[c.ideal?.genderPreference && `Looking for ${c.ideal.genderPreference}`, c.ideal?.age && `age ${c.ideal.age}`,
                c.ideal?.education, c.ideal?.occupation, c.ideal?.location].filter(Boolean).join(' • ') || 'No preferences shared'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
