import { useState } from 'react';
import { api } from '../lib/api.js';
import { appendText, genderIcon, parseAgeRange, useVoice } from '../lib/util.js';
import { IDEAL_FACTS } from './MeTab.jsx';
import { HeightHint } from './BioDialog.jsx';

const EDUCATION_OPTIONS = ['No preference', "Bachelor's or above", "Master's or above", "Doctor's degree"];
// Map older free-text values (e.g. "Masters+") onto the options above.
function eduValue(v) {
  const t = (v || '').toLowerCase();
  if (!t || t.includes('no pref')) return 'No preference';
  if (/ph\.?d|doctor|md\b|dphil/.test(t)) return "Doctor's degree";
  if (/master|msc|meng|mba|\bma\b|\bms\b/.test(t)) return "Master's or above";
  if (/bachelor|bsc|\bba\b|\bbs\b|undergrad/.test(t)) return "Bachelor's or above";
  return 'No preference';
}
const PLACEHOLDERS = {
  ethnicity: 'e.g. East Asian, Caucasian — or No preference',
  height: 'Minimum height in cm, e.g. 170',
  notWant: 'e.g. smoking, drugs',
  location: 'e.g. West Coast',
  occupation: 'e.g. Tech, Creative',
};
// Requirements that filter Discover (and decide two-way matches); the rest only affect the match score.
const MUST_MATCH = {
  education: 'They need at least this degree.',
  ethnicity: 'Must be one of these (people who left it blank still show).',
  height: 'They must be this height or taller.',
  notWant: 'People whose profile mentions any of these are hidden (comma-separated).',
};

export default function IdealDialog({ data, act, notify, onClose }) {
  const { profile, options } = data;
  const [draft, setDraft] = useState(() => ({ ...profile.ideal, education: eduValue(profile.ideal.education) }));
  const range = parseAgeRange(profile.ideal.age) || { min: 24, max: 32 };
  const [minAge, setMinAge] = useState(String(range.min));
  const [maxAge, setMaxAge] = useState(String(range.max));
  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const voice = useVoice((t) => setDraft((d) => ({ ...d, otherRequirement: appendText(d.otherRequirement, t, ', ') })),
    () => notify('Voice input isn’t supported in this browser — try Chrome or Safari.', 'err'));

  const save = async () => {
    const lo = parseInt(minAge, 10), hi = parseInt(maxAge, 10);
    if (!lo || !hi || lo < 18 || hi > 99) { notify('Age range must be between 18 and 99', 'err'); return; }
    const age = `${Math.min(lo, hi)}-${Math.max(lo, hi)}`;
    const ok = await act((q) => api.updateProfile({
      ideal: { ...draft, age },
      confirm: true,
      _event: `Updated ideal partner via dialog: looking for ${draft.genderPreference}, age ${age}`,
    }, q), { success: 'Ideal partner saved — Discover re-ranked' });
    if (ok) onClose();
  };

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet tall" role="dialog" aria-label="Edit ideal partner">
        <div className="sheet-head">
          <div><h2>Edit Ideal Partner</h2><div className="t10 faint" style={{ marginTop: 4 }}>Single choice Female / Male — filters and ranks Discover</div></div>
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body stack">
          <div className="pref-card">
            <div className="row between" style={{ marginBottom: 10 }}>
              <span className="t12 m">💞 Looking for — Gender (single)</span>
              <span className="pill purple t9">Replaces previous</span>
            </div>
            <div className="stack-xs">
              {options.genderPreference.map((g) => (
                <label key={g} className={`radio-row ${draft.genderPreference === g ? 'on' : ''}`}>
                  <input type="radio" name="genderPref" checked={draft.genderPreference === g} onChange={() => set('genderPreference', g)} />
                  <span>{g}</span>
                  <span className="t10" style={{ marginLeft: 'auto', opacity: 0.6 }}>{genderIcon(g)} {draft.genderPreference === g ? 'selected' : ''}</span>
                </label>
              ))}
            </div>
            <div className="t10 faint" style={{ marginTop: 8 }}>Single selection: choosing one replaces the other.</div>
          </div>

          <div>
            <span className="field-label">Age Range</span>
            <div className="row gap-8">
              <span className="t10 faint">Min</span>
              <input className="field grow" type="number" min="18" max="99" value={minAge} onChange={(e) => setMinAge(e.target.value)} aria-label="Minimum age" />
              <span>—</span>
              <span className="t10 faint">Max</span>
              <input className="field grow" type="number" min="18" max="99" value={maxAge} onChange={(e) => setMaxAge(e.target.value)} aria-label="Maximum age" />
            </div>
          </div>

          <div className="form-grid">
            {IDEAL_FACTS.map(([label, key]) => (
              <div key={key} className={key === 'notWant' ? 'span2' : undefined}>
                <label className="field-label caps" htmlFor={`i-${key}`}>{label}{MUST_MATCH[key] ? ' · must match' : ''}</label>
                {key === 'education' ? (
                  <select id="i-education" className="field" value={eduValue(draft.education)} onChange={(e) => set('education', e.target.value)}>
                    {EDUCATION_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input id={`i-${key}`} className="field" value={draft[key] || ''} onChange={(e) => set(key, e.target.value)}
                    placeholder={PLACEHOLDERS[key]} inputMode={key === 'height' ? 'numeric' : undefined} />
                )}
                {key === 'height' && <HeightHint value={draft.height} />}
                {MUST_MATCH[key] && <div className="t9 faint" style={{ marginTop: 4, lineHeight: 1.4 }}>{MUST_MATCH[key]}</div>}
              </div>
            ))}
          </div>

          <div className="soft-box" style={{ background: 'var(--surface-2)' }}>
            <div className="row between" style={{ marginBottom: 10 }}>
              <label className="t12 m" htmlFor="other-req">Other requirement</label>
              <button className={`voice-btn ${voice.listening ? 'live' : 'dark'}`} onClick={voice.toggle}>🎤 {voice.listening ? 'Listening…' : 'Voice'}</button>
            </div>
            <textarea id="other-req" className="field" rows={3} value={draft.otherRequirement || ''} onChange={(e) => set('otherRequirement', e.target.value)}
              placeholder="e.g. non-smoker, loves dogs, no long-distance" />
            <div className="t10 faint" style={{ marginTop: 6 }}>Comma-separated. Candidates whose bio or hobbies mention these rank higher. Type directly or use voice.</div>
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
