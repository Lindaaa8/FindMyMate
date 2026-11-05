import { useEffect, useRef, useState } from 'react';

export function genderIcon(g = '') {
  const s = g.toLowerCase();
  if (s.includes('trans') || s.includes('non-binary') || s.includes('non binary') || s.includes('nonbinary')) return '⚧️';
  if (s.includes('female')) return '♀️';
  if (s.includes('male')) return '♂️';
  if (s.includes('prefer')) return '⚪';
  return '⚧️';
}

export function parseAgeRange(text) {
  if (!text) return null;
  const m = text.match(/(\d{1,2})\s*[-–—to]+\s*(\d{1,2})/i);
  if (m) {
    const a = parseInt(m[1], 10), b = parseInt(m[2], 10);
    if (a > 0 && b > 0) return { min: Math.min(a, b), max: Math.max(a, b) };
  }
  const one = text.match(/(\d{1,2})/);
  if (one) { const a = parseInt(one[1], 10); return { min: a - 2, max: a + 2 }; }
  return null;
}

export const rankStyle = (rank) => {
  if (rank === 1) return { bg: '#FFD700', text: '#5a4100', shadow: '0 2px 10px rgba(250,204,21,0.5)', label: 'Top Pick' };
  if (rank === 2) return { bg: '#C0C0C0', text: '#222', shadow: '0 2px 10px rgba(0,0,0,0.12)', label: 'Great Match' };
  if (rank === 3) return { bg: '#CD7F32', text: '#fff', shadow: '0 2px 10px rgba(217,119,6,0.25)', label: 'Strong Match' };
  return { bg: '#121114', text: '#fff', shadow: 'none', label: null };
};

export const fmtTime = (ms) => new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
export const fmtClock = (ms) => new Date(ms).toLocaleTimeString();
export const fmtDate = (ms) => new Date(ms).toLocaleDateString();

export function countdown(deadline, now) {
  if (!deadline) return null;
  const left = Math.max(0, deadline - now);
  const h = Math.floor(left / 3.6e6), m = Math.floor((left % 3.6e6) / 6e4), s = Math.floor((left % 6e4) / 1e3);
  return { text: [h, m, s].map((n) => String(n).padStart(2, '0')).join(':'), left };
}

/** Ticks every second; used by the 72h commitment countdown. */
export function useNow(serverNow) {
  const offset = useRef(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (serverNow) offset.current = serverNow - Date.now(); }, [serverNow]);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return now + offset.current;
}

/**
 * Browser speech-to-text (Web Speech API). Appends final transcripts via onText.
 * Returns { supported, listening, toggle }.
 */
export function useVoice(onText, onUnsupported) {
  const recRef = useRef(null);
  const cb = useRef(onText);
  cb.current = onText;
  const [listening, setListening] = useState(false);
  const Ctor = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => () => { try { recRef.current?.stop(); } catch { /* noop */ } }, []);

  const toggle = () => {
    if (listening) {
      try { recRef.current?.stop(); } catch { /* noop */ }
      setListening(false);
      return;
    }
    if (!Ctor) { onUnsupported?.(); return; }
    const rec = new Ctor();
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = 'en-US';
    rec.onresult = (e) => {
      let text = '';
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) text += e.results[i][0].transcript;
      if (text.trim()) cb.current(text.trim());
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    try { rec.start(); setListening(true); } catch { setListening(false); }
  };
  return { supported: !!Ctor, listening, toggle };
}

export const appendText = (base, add, sep = ' ') => (base ? base.replace(/\s+$/, '') + sep + add : add);

// ---- height (stored in centimetres; older values like 5'9, 5.75 ft or 66 in are converted) ----
export function heightToCm(text) {
  const t = String(text ?? '').trim().toLowerCase();
  if (!t) return null;
  let m = t.match(/(\d)\s*(?:'|’|ft|feet|foot)\s*(\d{1,2}(?:\.\d+)?)?/);
  if (m) return (Number(m[1]) * 12 + Number(m[2] || 0)) * 2.54;
  m = t.match(/\d+(?:\.\d+)?/);
  if (!m) return null;
  const n = Number(m[0]);
  if (n >= 100 && n <= 250) return n;            // centimetres
  if (n >= 3 && n < 9) return n * 12 * 2.54;     // decimal feet
  if (n >= 36 && n < 100) return n * 2.54;       // inches (older entries)
  return null;
}

/** "168" -> "168 cm"; unrecognised text is shown as typed. */
export function formatHeight(text) {
  const cm = heightToCm(text);
  return cm == null ? (text || '') : `${Math.round(cm)} cm`;
}

/**
 * Keep the face in view wherever a photo is cropped (object-fit: cover).
 * person.photoFocus[url] = { x, y } face centre in % of the image, s = face width / shorter side.
 * zoom: for small round avatars, enlarge so the face fills most of the circle.
 */
export function photoStyle(person, url, { zoom = false } = {}) {
  const f = person?.photoFocus?.[url];
  if (!f) return { objectPosition: '50% 30%' }; // no face found: centre, leaning to the top where faces usually are
  const style = { objectPosition: `${f.x}% ${f.y}%` };
  if (zoom && f.s > 0) {
    const z = Math.min(3, Math.max(1, 0.55 / f.s));
    if (z > 1.05) Object.assign(style, { transform: `scale(${z.toFixed(2)})`, transformOrigin: `${f.x}% ${f.y}%` });
  }
  return style;
}
