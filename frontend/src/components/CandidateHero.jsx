import { formatHeight, genderIcon, photoStyle } from '../lib/util.js';

/** Colored photo area used by Discover cards, the Connection card and the profile modal. */
export default function CandidateHero({ c, onClick, short, topLeft, topRight, showLocationEthnicity = true, bottomRight, glow }) {
  return (
    <div className={`cand-hero ${short ? 'short' : ''}`} style={{ background: c.color }} onClick={onClick}
      role={onClick ? 'button' : undefined} tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => { if (onClick && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onClick(); } }}>
      {c.photos?.[0]
        ? <img className="hero-photo" src={c.photos[0]} alt={`${c.name}'s main photo`} style={photoStyle(c, c.photos[0])} />
        : <div className="cand-initial" style={{ color: c.color, boxShadow: glow }}>{c.name[0]}</div>}
      {topLeft && <div className="hero-tl">{topLeft}</div>}
      {topRight && <div className="hero-tr">{topRight}</div>}
      <div className="hero-bl">
        <div className="hero-name">{c.name}{c.age ? `, ${c.age}` : ''}<span className="hero-meta">{[c.gender, formatHeight(c.height), c.mbti].filter(Boolean).join(' • ')}</span></div>
        <div className="hero-sub truncate" style={{ maxWidth: bottomRight ? '62%' : '100%' }}>
          {[c.location, showLocationEthnicity ? c.ethnicity : null, c.career].filter(Boolean).join(' • ')}
        </div>
      </div>
      {bottomRight}
    </div>
  );
}

export function VerifyChips({ c }) {
  return (
    <div className="verify-chips">
      <span className="pill">{genderIcon(c.gender)} {c.gender}</span>
      {c.photoVerified && <span className="pill">✓ It’s me</span>}
      {c.marriageVerified && c.relationshipStatus === 'Single' && <span className="pill green">✓ Single</span>}
    </div>
  );
}
