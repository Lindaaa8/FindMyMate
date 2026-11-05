import { api } from '../lib/api.js';
import { fmtClock } from '../lib/util.js';

const STATES = ['RECOMMENDED', 'FAVOURED', 'INVITED', 'CHATTING', 'DATING', 'ENGAGED', 'CLOSED'];

/** Your connection status and activity log (shown beside the phone on wide screens, or from the ⋯ menu). */
export default function ActivityPanel({ data, act, compact }) {
  const { active, profile, matches, userStatus, isAvailable, stateCounts, events, me } = data;
  const mutual = matches.filter((m) => m.tier === 'mutual').length;

  return (
    <div className="stack-sm" style={{ gap: 20 }}>
      {!compact && (
        <div>
          <div className="panel-title">Hi {profile.name || 'there'} 👋</div>
          <div className="t11 muted" style={{ lineHeight: 1.5 }}>
            Signed in as {me.email || 'Facebook user'}{me.facebook ? ' · Facebook linked' : ''}. Your profile and activity are saved to your account.
          </div>
        </div>
      )}

      <div className="stack-xs">
        <div className="fsm">
          {STATES.map((s) => (
            <div key={s} className={`fsm-pill ${active?.state === s ? 'on' : ''}`}>
              {s}{stateCounts[s] > 0 && <span className="n">{stateCounts[s]}</span>}
            </div>
          ))}
        </div>
        <div className="t11 muted" style={{ lineHeight: 1.6 }}>
          Current: <b>{active ? `${active.candidate?.name} • ${active.state}` : 'none'}</b> • Looking for: <b>{profile.ideal.genderPreference || 'anyone'}</b> •
          {' '}{matches.length} matches ({mutual} two-way) • Status: <b>{userStatus}</b> • Available: <b>{String(isAvailable)}</b>
        </div>
      </div>

      <div className="panel-card">
        <div className="row between">
          <h3>Activity</h3>
          <button className="btn btn-light btn-xs" onClick={() => act(api.clearEvents)}>Clear</button>
        </div>
        <div className="log">
          {events.map((e) => (
            <div className="log-row" key={e.id}>
              <time>{fmtClock(e.at)}</time>
              <div className="grow">
                <div className="t11">{e.text}</div>
                <div className="t9 faint" style={{ marginTop: 2 }}>{e.state}{e.otherName ? ` • ${e.otherName}` : ''}</div>
              </div>
            </div>
          ))}
          {events.length === 0 && <div className="t11 faint center" style={{ padding: 24 }}>No activity yet</div>}
        </div>
      </div>
    </div>
  );
}
