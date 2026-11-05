import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '../lib/api.js';
import { appendText, useVoice } from '../lib/util.js';
import CameraDialog from './CameraDialog.jsx';

const MAX_BYTES = 25 * 1024 * 1024;
const EMOJI = {
  Smileys: ['😀', '😄', '😂', '🥹', '😊', '😍', '🥰', '😘', '😉', '😎', '🤗', '🤔', '😅', '😇', '🙃', '😌', '😴', '🥲', '😢', '😮'],
  Love: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🤍', '💖', '💕', '💞', '💘', '💌', '😻', '🌹', '💐', '🫶'],
  Fun: ['👍', '👏', '🙌', '🤞', '✌️', '👋', '🙏', '🔥', '✨', '🎉', '🎶', '☕', '🍷', '🍕', '🌮', '🏔️', '🌊', '🐶', '🐱', '📚'],
};

function fmtDur(s) {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Message box with emoji, dictation, photo/video attachments, in-app camera and voice messages. */
export default function ChatComposer({ act, notify }) {
  const [text, setText] = useState('');
  const [pending, setPending] = useState(null); // { file: Blob, name, kind, url }
  const [menu, setMenu] = useState(null); // 'emoji' | 'attach' | null
  const [camera, setCamera] = useState(false);
  const [rec, setRec] = useState(null); // { seconds } while recording a voice message
  const [sending, setSending] = useState(false);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const recorderRef = useRef(null);

  const voice = useVoice((t) => setText((v) => appendText(v, t)),
    () => notify('Voice typing isn’t supported in this browser — try Chrome or Safari, or send a voice message.', 'err'));

  useEffect(() => () => { if (pending?.url) URL.revokeObjectURL(pending.url); }, [pending]);
  useEffect(() => () => stopRecording(true), []); // eslint-disable-line react-hooks/exhaustive-deps

  const attach = (blob, name) => {
    const kind = (blob.type || '').split('/')[0];
    if (!['image', 'video', 'audio'].includes(kind)) { notify('You can send photos, videos and voice messages', 'err'); return; }
    if (blob.size > MAX_BYTES) { notify('That file is over 25 MB', 'err'); return; }
    setPending({ file: blob, name, kind, url: URL.createObjectURL(blob) });
    setMenu(null);
  };

  const insertEmoji = (e) => {
    const el = inputRef.current;
    const start = el?.selectionStart ?? text.length;
    const end = el?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + e + text.slice(end);
    setText(next);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(start + e.length, start + e.length); });
  };

  // ---- voice message ---------------------------------------------------------
  const startRecording = async () => {
    setMenu(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === 'undefined') {
      notify('Voice messages aren’t supported in this browser', 'err');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      const chunks = [];
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      mr.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        if (mr.cancelled || !chunks.length) return;
        const type = (mr.mimeType || 'audio/webm').split(';')[0];
        attach(new Blob(chunks, { type }), `voice.${type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'}`);
      };
      mr.start();
      const started = Date.now();
      const timer = setInterval(() => {
        const secs = Math.floor((Date.now() - started) / 1000);
        setRec({ seconds: secs });
        if (secs >= 120) stopRecording(); // 2-minute cap
      }, 250);
      recorderRef.current = { mr, timer };
      setRec({ seconds: 0 });
    } catch {
      notify('Allow microphone access to record a voice message', 'err');
    }
  };

  function stopRecording(cancel = false) {
    const r = recorderRef.current;
    if (!r) return;
    clearInterval(r.timer);
    r.mr.cancelled = cancel;
    if (r.mr.state !== 'inactive') r.mr.stop();
    recorderRef.current = null;
    setRec(null);
  }

  // ---- send ------------------------------------------------------------------
  const send = async () => {
    const t = text.trim();
    if (!t && !pending) return;
    setSending(true);
    const p = pending;
    const ok = await act((q) => (p ? api.sendMedia(p.file, p.name, t, q) : api.send(t, q)));
    setSending(false);
    if (ok) { setText(''); setPending(null); }
  };

  return (
    <div className="composer">
      {pending && (
        <div className="attach-preview">
          {pending.kind === 'image' && <img src={pending.url} alt="Photo to send" />}
          {pending.kind === 'video' && <video src={pending.url} controls playsInline />}
          {pending.kind === 'audio' && <audio src={pending.url} controls />}
          <button className="close-x" aria-label="Remove attachment" onClick={() => setPending(null)}>✕</button>
        </div>
      )}

      {rec ? (
        <div className="rec-bar">
          <span className="rec-dot" /> Recording voice message {fmtDur(rec.seconds)}
          <button className="btn btn-light btn-xs" style={{ marginLeft: 'auto' }} onClick={() => stopRecording(true)}>Cancel</button>
          <button className="btn btn-dark btn-xs" onClick={() => stopRecording()}>■ Stop</button>
        </div>
      ) : (
        <form className="compose" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <button type="button" className={`icon-btn ${menu === 'attach' ? 'on' : ''}`} aria-label="Attach photo, video or voice message"
            onClick={() => setMenu(menu === 'attach' ? null : 'attach')}>＋</button>
          <div className="compose-field">
            <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)}
              placeholder={pending ? 'Add a caption…' : voice.listening ? 'Listening…' : 'Message...'} aria-label="Message" maxLength={2000} />
            <button type="button" className={`icon-btn bare ${menu === 'emoji' ? 'on' : ''}`} aria-label="Emoji"
              onClick={() => setMenu(menu === 'emoji' ? null : 'emoji')}>😊</button>
            <button type="button" className={`icon-btn bare ${voice.listening ? 'live' : ''}`} aria-label={voice.listening ? 'Stop voice typing' : 'Voice typing'}
              onClick={voice.toggle}>🎤</button>
          </div>
          <button className="btn btn-dark" type="submit" disabled={sending || (!text.trim() && !pending)} style={{ padding: '10px 18px', fontSize: 12 }}>
            {sending ? '…' : 'Send'}
          </button>
        </form>
      )}

      {menu === 'attach' && (
        <div className="pop attach-menu" role="menu">
          <button role="menuitem" onClick={() => { setMenu(null); setCamera(true); }}>📷 Take photo or video</button>
          <button role="menuitem" onClick={() => fileRef.current?.click()}>🖼️ Photo or video from library</button>
          <button role="menuitem" onClick={startRecording}>🎙️ Record voice message</button>
        </div>
      )}
      {menu === 'emoji' && (
        <div className="pop emoji-pop" role="dialog" aria-label="Emoji">
          {Object.entries(EMOJI).map(([group, list]) => (
            <div key={group}>
              <div className="label-caps" style={{ margin: '4px 2px' }}>{group}</div>
              <div className="emoji-grid">
                {list.map((e) => <button key={e} type="button" onClick={() => insertEmoji(e)} aria-label={`Insert ${e}`}>{e}</button>)}
              </div>
            </div>
          ))}
        </div>
      )}

      <input ref={fileRef} type="file" accept="image/*,video/*" hidden
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) attach(f, f.name); }} />
      {camera && createPortal(
        <CameraDialog notify={notify} onClose={() => setCamera(false)} onCapture={(blob, name) => { setCamera(false); attach(blob, name); }} />,
        document.querySelector('.phone') || document.body,
      )}
    </div>
  );
}
