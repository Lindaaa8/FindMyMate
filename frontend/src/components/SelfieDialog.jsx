import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api.js';

const CLIP_SECONDS = 3;
const FRAME_COUNT = 6;

/** Grab the current video frame as a JPEG blob (long side <= 720 px). */
function grab(video) {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return Promise.resolve(null);
  const scale = Math.min(1, 720 / Math.max(w, h));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
}

/** Pull FRAME_COUNT evenly spaced frames out of an uploaded selfie video file. */
async function framesFromFile(file) {
  const url = URL.createObjectURL(file);
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.src = url;
  try {
    await new Promise((resolve, reject) => { video.onloadeddata = resolve; video.onerror = reject; });
    const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : CLIP_SECONDS;
    const frames = [];
    for (let i = 0; i < FRAME_COUNT; i += 1) {
      video.currentTime = (duration * (i + 0.5)) / FRAME_COUNT;
      await new Promise((resolve) => { video.onseeked = resolve; });
      const blob = await grab(video);
      if (blob) frames.push(blob);
    }
    return frames;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * "Verify it's me": a short live selfie video. Frames from it are sent to the server, where face recognition
 * compares them with the main profile photo.
 */
export default function SelfieDialog({ data, act, notify, onClose }) {
  const hasMain = !!data.profile.photos[0];
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [phase, setPhase] = useState('starting'); // starting | ready | recording | uploading | nocamera | nophoto
  const [left, setLeft] = useState(CLIP_SECONDS);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!hasMain) { setPhase('nophoto'); return undefined; }
    if (!navigator.mediaDevices?.getUserMedia) { setPhase('nocamera'); return undefined; }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 } }, audio: false })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setPhase('ready');
      })
      .catch(() => !cancelled && setPhase('nocamera'));
    return () => { cancelled = true; streamRef.current?.getTracks().forEach((t) => t.stop()); };
  }, [hasMain]);

  const submit = async (frames) => {
    if (!frames.length) { setError('We couldn’t capture any frames — try again.'); setPhase(streamRef.current ? 'ready' : 'nocamera'); return; }
    setPhase('uploading');
    setError('');
    let message = '';
    const ok = await act(async (q) => {
      try { return await api.verifyPhoto(frames, q); } catch (e) { message = e.message; throw e; }
    }, { success: 'Face matched — verified it’s you ✓' });
    if (ok) onClose();
    else { setError(message); setPhase(streamRef.current ? 'ready' : 'nocamera'); }
  };

  const record = () => {
    const frames = [];
    const pending = [];
    setPhase('recording');
    setLeft(CLIP_SECONDS);
    const every = (CLIP_SECONDS * 1000) / FRAME_COUNT;
    let taken = 0;
    const shoot = setInterval(() => {
      pending.push(grab(videoRef.current).then((b) => b && frames.push(b)));
      taken += 1;
      if (taken >= FRAME_COUNT) {
        clearInterval(shoot);
        Promise.all(pending).then(() => submit(frames));
      }
    }, every);
    let n = CLIP_SECONDS;
    const tick = setInterval(() => { n -= 1; setLeft(Math.max(n, 0)); if (n <= 0) clearInterval(tick); }, 1000);
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    if (!f.type.startsWith('video/')) { notify('Please choose a selfie video', 'err'); return; }
    setPhase('uploading');
    try { submit(await framesFromFile(f)); } catch { setError('That video couldn’t be read — try another one.'); setPhase('nocamera'); }
  };

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-label="Verify it's me">
        <div className="sheet-head">
          <div><h2>Verify it’s me</h2><div className="t10 faint" style={{ marginTop: 4 }}>A {CLIP_SECONDS}-second live selfie, matched to your main photo with face recognition</div></div>
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body stack-sm">
          {phase === 'nophoto' ? (
            <div className="alert alert-red">Add a main photo first — verification matches your face to it.</div>
          ) : phase === 'nocamera' ? (
            <div className="stack-sm">
              <div className="alert alert-red">We couldn’t open your camera. Allow camera access and reopen this, or upload a short selfie video.</div>
              <button className="btn btn-dark btn-block" onClick={() => fileRef.current?.click()}>Upload selfie video</button>
              <input ref={fileRef} type="file" accept="video/*" capture="user" hidden onChange={onFile} />
            </div>
          ) : (
            <>
              <div className="camera">
                <video ref={videoRef} autoPlay playsInline muted />
                <div className="ring" />
                {phase === 'recording' && <span className="rec">● REC {left}s</span>}
                {phase === 'starting' && <span className="t12" style={{ position: 'absolute' }}>Opening camera…</span>}
                {phase === 'uploading' && <span className="rec" style={{ background: 'rgba(0,0,0,.6)' }}>Matching your face…</span>}
              </div>
              <div className="t11 muted center">Face the camera in good light, keep your face in the oval, and slowly turn your head a little.</div>
            </>
          )}
          {error && <div className="alert alert-red t11">{error}</div>}
          <div className="t10 faint center">Your selfie is compared with your main photo and then discarded — it isn’t stored.</div>
        </div>
        {!['nophoto', 'nocamera'].includes(phase) && (
          <div className="sheet-foot">
            <button className="btn btn-light" onClick={onClose}>Cancel</button>
            <button className="btn btn-dark" disabled={phase !== 'ready'} onClick={record}>
              {phase === 'recording' ? `Recording… ${left}s` : phase === 'uploading' ? 'Matching…' : error ? 'Try again' : 'Record selfie'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
