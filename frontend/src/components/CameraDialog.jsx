import { useEffect, useRef, useState } from 'react';

const MAX_VIDEO_S = 60;

/** In-app camera: take a photo or record a short video, then hand the Blob to onCapture. */
export default function CameraDialog({ onCapture, onClose, notify }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recRef = useRef(null);
  const fallbackRef = useRef(null);
  const [mode, setMode] = useState('photo'); // photo | video
  const [facing, setFacing] = useState('user');
  const [phase, setPhase] = useState('starting'); // starting | ready | recording | nocamera
  const [secs, setSecs] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) { setPhase('nocamera'); return undefined; }
    setPhase('starting');
    navigator.mediaDevices.getUserMedia({ video: { facingMode: facing }, audio: mode === 'video' })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setPhase('ready');
      })
      .catch(() => !cancelled && setPhase('nocamera'));
    return () => {
      cancelled = true;
      if (recRef.current?.mr.state === 'recording') { recRef.current.mr.cancelled = true; recRef.current.mr.stop(); }
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [facing, mode]);

  const takePhoto = () => {
    const v = videoRef.current;
    if (!v?.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext('2d');
    if (facing === 'user') { ctx.translate(canvas.width, 0); ctx.scale(-1, 1); } // match the mirrored preview
    ctx.drawImage(v, 0, 0);
    canvas.toBlob((b) => b && onCapture(b, 'photo.jpg'), 'image/jpeg', 0.9);
  };

  const toggleVideo = () => {
    if (phase === 'recording') { recRef.current?.mr.stop(); return; }
    if (typeof window.MediaRecorder === 'undefined') { notify('Video recording isn’t supported in this browser', 'err'); return; }
    const chunks = [];
    const mr = new MediaRecorder(streamRef.current);
    mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    mr.onstop = () => {
      clearInterval(recRef.current?.timer);
      if (mr.cancelled) return;
      const type = (mr.mimeType || 'video/webm').split(';')[0];
      onCapture(new Blob(chunks, { type }), `video.${type.includes('mp4') ? 'mp4' : 'webm'}`);
    };
    mr.start();
    const started = Date.now();
    const timer = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      setSecs(s);
      if (s >= MAX_VIDEO_S) mr.stop();
    }, 250);
    recRef.current = { mr, timer };
    setSecs(0);
    setPhase('recording');
  };

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-label="Camera">
        <div className="sheet-head">
          <div><h2>Camera</h2><div className="t10 faint" style={{ marginTop: 4 }}>Take a photo or a video up to {MAX_VIDEO_S}s</div></div>
          <button className="close-x" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="sheet-body stack-sm">
          {phase === 'nocamera' ? (
            <div className="stack-sm">
              <div className="alert alert-red">We couldn’t open your camera. Allow camera access and try again, or use your device’s camera app.</div>
              <button className="btn btn-dark btn-block" onClick={() => fallbackRef.current?.click()}>Open device camera</button>
              <input ref={fallbackRef} type="file" accept="image/*,video/*" capture="environment" hidden
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) onCapture(f, f.name); }} />
            </div>
          ) : (
            <>
              <div className="camera" style={{ aspectRatio: '3/4' }}>
                <video ref={videoRef} autoPlay playsInline muted style={{ transform: facing === 'user' ? 'scaleX(-1)' : 'none' }} />
                {phase === 'recording' && <span className="rec">● REC {secs}s</span>}
                {phase === 'starting' && <span className="t12" style={{ position: 'absolute' }}>Opening camera…</span>}
              </div>
              <div className="row between">
                <div className="auth-tabs" style={{ margin: 0, width: 180 }}>
                  <button className={mode === 'photo' ? 'on' : ''} disabled={phase === 'recording'} onClick={() => setMode('photo')}>Photo</button>
                  <button className={mode === 'video' ? 'on' : ''} disabled={phase === 'recording'} onClick={() => setMode('video')}>Video</button>
                </div>
                <button className="btn btn-light btn-sm" disabled={phase === 'recording'} onClick={() => setFacing((f) => (f === 'user' ? 'environment' : 'user'))}>🔄 Flip</button>
              </div>
            </>
          )}
        </div>
        {phase !== 'nocamera' && (
          <div className="sheet-foot">
            <button className="btn btn-light" onClick={onClose}>Cancel</button>
            {mode === 'photo'
              ? <button className="btn btn-dark" disabled={phase !== 'ready'} onClick={takePhoto}>📸 Take photo</button>
              : <button className={`btn ${phase === 'recording' ? 'btn-red' : 'btn-dark'}`} disabled={phase === 'starting'} onClick={toggleVideo}>
                {phase === 'recording' ? `■ Stop (${secs}s)` : '● Record video'}
              </button>}
          </div>
        )}
      </div>
    </div>
  );
}
