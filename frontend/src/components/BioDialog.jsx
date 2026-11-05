import { useState } from 'react';
import { api } from '../lib/api.js';
import { appendText, formatHeight, genderIcon, heightToCm, useVoice } from '../lib/util.js';

const FIELDS = [['Name', 'name'], ['Age', 'age'], ['Ethnicity', 'ethnicity'], ['Nationality', 'nationality'], ['Faith', 'faith'],
  ['Career', 'career'], ['Location', 'location'], ['Height', 'height'], ['Hobbies', 'hobbies'], ['Hometown', 'hometown'], ['MBTI', 'mbti']];

export default function BioDialog({ data, act, notify, onClose }) {
  const { profile, options, active } = data;
  const [draft, setDraft] = useState(() => ({
    bio: profile.bio, gender: profile.gender, education: profile.education, marriageStatus: profile.marriageStatus,
    ...Object.fromEntries(FIELDS.map(([, k]) => [k, profile[k]])),
  }));
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const voice = useVoice((t) => setDraft((d) => ({ ...d, bio: appendText(d.bio, t) })),
    () => notify('Voice input isn’t supported in this browser — try Chrome or Safari.', 'err'));
  const dating = active?.state === 'DATING';

  const save = async () => {
    const patch = { ...draft, confirm: true, _event: 'Updated bio via dialog' };
    if (dating) delete patch.marriageStatus;
    const ok = await act((q) => api.updateProfile(patch, q), { success: 'Bio saved' });
    if (ok) onClose();
  };

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet tall" role="dialog" aria-label="Edit bio">
        <div className="sheet-head">
          <div><h2>Edit Bio</h2><div className="t10 faint" style={{ marginTop: 4 }}>🎓 Education + ⚧️ Gender + 💍 Status + Bio — gender dropdown</div></div>
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body stack" style={{marginTop:5, paddingTop: 0, paddingBottom: 0, marginBottom:0}}>
          {/*<div className="pref-card">*/}
            <div className="field-label" style={{ marginBottom: 8 }}>My Gender</div>
            <div className="row wrap gap-6" style={{ marginTop: 8 }}>
              {options.bioGender.map((g) => (
                <button key={g} type="button" className={`chip-btn ${draft.gender === g ? 'on' : ''}`} onClick={() => set('gender', g)}>{genderIcon(g)} {g}</button>
              ))}
            </div>
          {/*</div>*/}
          <div style={{marginTop: 10, paddingTop: 5}}>
            <label className="field-label" htmlFor="edu" style={{marginTop: 0, paddingTop: 0}}>Education🎓</label>
            <input id="edu" className="field" value={draft.education} onChange={(e) => set('education', e.target.value)} placeholder="e.g. University of Waterloo - MEng" />
          </div>

          <div style={{paddingTop: 0, marginTop:10}}>
            <span className="field-label" style={{paddingBottom: 2}}>Relationship Status💍</span>
            <div className="row gap-6">
              {options.marriageStatus.map((s) => (
                <button key={s} className={`chip-btn ${draft.marriageStatus === s ? 'on' : ''}`} style={{ fontSize: 11, padding: '6px 12px' }}
                  disabled={dating} onClick={() => set('marriageStatus', s)}>{s}</button>
              ))}
            </div>
            {dating && <div className="t10 faint" style={{ marginTop: 6 }}>Managed automatically while you’re dating.</div>}
          </div>
            <div>
            <div className="row between" style={{ marginBottom: 8, marginTop: 0, paddingTop:0 }}>
              <label className="t12 m" htmlFor="bio-text">Self Introduction</label>
              <button className={`voice-btn ${voice.listening ? 'live' : ''}`} onClick={voice.toggle}>🎤 {voice.listening ? 'Listening… tap to stop' : 'Voice'}</button>
            </div>
            <textarea id="bio-text" className="field" rows={4} value={draft.bio} maxLength={2000}
              onChange={(e) => set('bio', e.target.value)} placeholder="What makes you curious, what you value, something special about you" />
          </div>
          <div className="form-grid" style={{marginTop: 3, paddingTop: 0}}>
            {FIELDS.map(([label, key]) => (
              <div key={key}>
                <label className="field-label caps" htmlFor={`f-${key}`}>{label}</label>
                <input id={`f-${key}`} className="field" value={draft[key]} inputMode={key === 'age' || key === 'height' ? 'numeric' : undefined}
                  placeholder={key === 'height' ? 'Height in cm, e.g. 168' : undefined}
                  onChange={(e) => set(key, key === 'age' ? e.target.value.replace(/\D/g, '').slice(0, 2) : e.target.value)} />
                {key === 'height' && <HeightHint value={draft.height} />}
              </div>
            ))}
          </div>
        </div>
        <div className="sheet-foot">
          <button className="btn btn-light" onClick={onClose}>Cancel</button>
          <button className="btn btn-dark" onClick={save}>Save</button>
        </div>
      </div>
    </div>
  );
}

export function HeightHint({ value }) {
  if (!String(value ?? '').trim()) return <div className="t9 faint" style={{ marginTop: 4 }}>Centimetres (cm)</div>;
  const cm = heightToCm(value);
  const ok = cm != null;
  const plainCm = /^\s*\d{3}(\.\d+)?\s*(cm)?\s*$/i.test(String(value));
  return (
    <div className="t9" style={{ marginTop: 4, color: ok ? 'var(--muted, #666)' : 'var(--red)' }}>
      {ok ? (plainCm ? `${formatHeight(value)}` : `= ${formatHeight(value)} (saved in cm)`) : 'Enter centimetres, e.g. 168'}
    </div>
  );
}
