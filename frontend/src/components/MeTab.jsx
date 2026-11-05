import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';
import { formatHeight, genderIcon, parseAgeRange, photoStyle } from '../lib/util.js';

const FACTS = [['Name', 'name'], ['Age', 'age'], ['Ethnicity', 'ethnicity'], ['Nationality', 'nationality'], ['Faith', 'faith'],
  ['Career', 'career'], ['Location', 'location'], ['Height', 'height'], ['Hobbies', 'hobbies'], ['Hometown', 'hometown'], ['MBTI', 'mbti']];
export const IDEAL_FACTS = [['Education', 'education'], ['Ethnicity', 'ethnicity'], ['Occupation', 'occupation'],
  ['Skin color', 'skinColor'], ['Height', 'height'], ['Location', 'location'], ['Not want', 'notWant']];

export default function MeTab({ data, act, notify, onEditBio, onEditIdeal, onVerify }) {
  const { profile, userStatus, active } = data;
  const fileRef = useRef(null);
  const slotRef = useRef(0);


  // After "Verify it's me", photos become read-only; the Edit button opens add-more mode.
  // Once the profile has been saved (or verified) and has photos, the grid is read-only:
  // only uploaded photos show, no empty slots, until you tap ✏️ Edit.
  const hasPhotos = profile.photos.some(Boolean);
  // A profile counts as created once it's been saved (or verified, or has gender + age filled in).
  const profileCreated = profile.confirmed || profile.photoVerified || Boolean(profile.gender && profile.age);
  const locked = hasPhotos && profileCreated;
  const [editingPhotos, setEditingPhotos] = useState(false);
  useEffect(() => { if (!locked) setEditingPhotos(false); }, [locked]);

  const photoCount = profile.photos.filter(Boolean).length;
  const age = parseAgeRange(profile.ideal.age);

  const pickPhoto = (slot) => { slotRef.current = slot; fileRef.current?.click(); };
  const onFile = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('image/')) { notify('Please choose an image file', 'err'); return; }
    act((q) => api.uploadPhoto(slotRef.current, file, q));
  };

  return (
    <div className="stack">
      {userStatus === 'in_a_relationship' && (
        <div className="alert alert-dark">
          <span>🔒</span>
          <div>
            <div className="t12 b">Your profile is hidden - you are in a relationship</div>
            <div className="t11" style={{ opacity: 0.7, marginTop: 4 }}>
              You are dating {active?.candidate?.name}. Your profile is removed from the candidate pool and not available for ranking. End relationship to re-enter the pool.
            </div>
          </div>
        </div>
      )}

      {/* Setup checklist disappears once the profile has been created and has photos. */}
      {!(profileCreated && hasPhotos) && userStatus !== 'in_a_relationship' && (
        <div className="pref-card">
          <div className="t12 b">Welcome{profile.name ? `, ${profile.name}` : ''}! Finish setting up to appear in Discover</div>
          <ol className="t11 muted" style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: 1.8 }}>
            <li style={{ textDecoration: profile.confirmed ? 'line-through' : 'none' }}>
              Tap <button className="link" onClick={onEditBio}>✏️ Edit Bio</button> — add gender, age and a few lines, then Save
            </li>
            <li style={{ textDecoration: profile.ideal.genderPreference ? 'line-through' : 'none' }}>
              Tap <button className="link" onClick={onEditIdeal}>✏️ Edit Ideal partner</button> — who you’re looking for
            </li>
            <li style={{ textDecoration: profile.photos[0] ? 'line-through' : 'none' }}>Add a main photo</li>
            <li style={{ textDecoration: profile.photoVerified ? 'line-through' : 'none' }}>Tap “Verify it’s me”</li>
          </ol>
        </div>
      )}

      {/* Photos */}
      <section>
        <div className="row between" style={{ marginBottom: 8 }}>
          <div className="row gap-8">
            <span className="section-title">Photos</span>
            <span className="t11 faint">({photoCount}/9)</span>
          </div>
          {locked && (
            <button className="edit-btn" onClick={() => setEditingPhotos((v) => !v)} aria-pressed={editingPhotos}>
              {editingPhotos ? <>✓ Done</> : <><span>✏️</span> Edit</>}
            </button>
          )}
        </div>
        <div className="photo-grid">
          {profile.photos.map((p, i) => {
            const main = i === 0;
            if (!p) {
              // Once saved, empty slots only show while editing.
              if (locked && !editingPhotos) return null;
              return (
                <div key={i} className="photo-slot empty">
                  <button className="add" onClick={() => pickPhoto(i)} aria-label={main ? 'Add main photo' : `Add photo ${i + 1}`}>+</button>
                  {main && <span className="main-tag">Main</span>}
                </div>
              );
            }
            const placeholder = p.startsWith('placeholder:');
            // Before saving: everything editable. After saving: read-only until ✏️ Edit.
            // In Edit mode a verified main photo stays locked so verification isn't lost by accident.
            const editable = !locked || (editingPhotos && !(main && profile.photoVerified));
            return (
              <div key={i} className={`photo-slot filled ${main ? 'main' : ''}`}>
                <div className="fill" onClick={editable ? () => pickPhoto(i) : undefined}
                  style={{ cursor: editable ? 'pointer' : 'default' }} title={editable ? 'Replace photo' : undefined}>
                  {placeholder ? (main ? 'Main' : i + 1) : <img src={p} alt={main ? 'Main photo' : `Photo ${i + 1}`} style={photoStyle(profile, p)} />}
                </div>
                {main && <span className="main-tag">Main</span>}
                {main && profile.photoVerified && <span className="verified-tag">✓ Verified</span>}
                {editable && <button className="remove" aria-label="Remove photo" onClick={() => act((q) => api.deletePhoto(i, q))}>×</button>}
              </div>
            );
          })}
        </div>
        {locked && editingPhotos && (
          <div className="t10 faint" style={{ marginTop: 8 }}>
            Tap + to add photos, tap a photo to replace it, or × to remove it.{profile.photoVerified ? ' Your verified main photo is locked.' : ''} Tap ✓ Done when finished.
          </div>
        )}
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={onFile} />
      </section>

      {/* Verification */}
      <section>
        {!profile.photoVerified && (
          <div className="alert alert-red">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ flexShrink: 0, marginTop: 1, color: 'var(--red)' }}>
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <p style={{ margin: 0 }}>Your main photo must be verified before you appear in Discover. Record a short selfie video and we match it to this photo.</p>
          </div>
        )}
        <button
          className={`btn btn-block ${profile.photoVerified ? 'btn-verified' : 'btn-gray'}`}
          style={{ marginTop: 8 }}
          onClick={profile.photoVerified ? undefined : onVerify}
        >
          {profile.photoVerified ? `✓ Verified it’s me${profile.photoMatchScore ? ` · face match ${profile.photoMatchScore}%` : ''}` : 'Verify it’s me'}
        </button>
      </section>

      {/* Bio */}
      <section>
        <div className="row between" style={{ marginBottom: 8 }}>
          <span className="section-title">Bio</span>
          <button className="edit-btn" onClick={onEditBio}><span>✏️</span> Edit</button>
        </div>
        <div className="card">
          <div className="title-row">
            <span className="icon">🎓</span>
            <div className="grow">
              <div className="label-caps">Education title</div>
              <div className="value truncate">{profile.education || 'Add your degree'}</div>
            </div>
          </div>
          <div className="title-row">
            <span className="icon">{genderIcon(profile.gender)}</span>
            <div className="grow">
              <div className="label-caps">Gender title</div>
              <div className="row gap-8"><span className="value">{profile.gender || 'Not set'}</span>
                {profile.gender && <span className="pill pink">{genderIcon(profile.gender)} {profile.gender}</span>}</div>
            </div>
            <span className="pill">Always visible</span>
          </div>
          <div className="title-row">
            <span className="icon">💍</span>
            <div className="grow">
              <div className="label-caps">Relationship status title</div>
              <div className="value">{profile.marriageStatus}</div>
            </div>
            {profile.marriageVerified ? <span className="pill green">Verified ✓</span> : <span className="pill gray">Unverified</span>}
          </div>
          <div className="bio-text">{profile.bio || 'Tell us about yourself.'}</div>
          <div className="fact-grid">
            {FACTS.map(([label, key]) => (
              <div className="fact" key={key}>
                <div className="label-caps">{label}</div>
                <div className="v">{(key === 'height' ? formatHeight(profile[key]) : profile[key]) || '—'}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Ideal partner */}
      <section>
        <div className="row between" style={{ marginBottom: 8 }}>
          <span className="section-title">Ideal partner</span>
          <button className="edit-btn" onClick={onEditIdeal}><span>✏️</span> Edit</button>
        </div>
        <div className="stack-xs">
          <div className="pref-card row between">
            <span className="t12 m">💞 Looking for</span>
            <span className="pill dark" style={{ fontSize: 12, padding: '4px 12px' }}>
              {profile.ideal.genderPreference ? `${genderIcon(profile.ideal.genderPreference)} ${profile.ideal.genderPreference}` : 'Not set'}
            </span>
          </div>
          <div className="fact accent">
            <div className="row between"><span className="label-caps">Age range</span><span className="pill purple t9">Included in AI ranking filter</span></div>
            <div className="v">Age: {profile.ideal.age} <span className="t10 faint">({age ? `${age.min} to ${age.max}` : profile.ideal.age})</span></div>
          </div>
          <div className="fact-grid" style={{ padding: 0 }}>
            {IDEAL_FACTS.map(([label, key]) => (
              <div className="fact" key={key}><div className="label-caps">{label}</div><div className="v">{(key === 'height' && profile.ideal[key] ? `${formatHeight(profile.ideal[key])} or taller` : profile.ideal[key]) || 'No preference'}</div></div>
            ))}
          </div>
          <div className="card white card-pad">
            <div className="row between"><span className="t12 m">Other requirement</span><span className="pill purple t9">Included in ranking</span></div>
            <div className="soft-box t11" style={{ marginTop: 8, background: '#fafafe' }}>{profile.ideal.otherRequirement || 'None'}</div>
          </div>
        </div>
      </section>
    </div>
  );
}
