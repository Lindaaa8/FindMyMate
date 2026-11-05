"""Face recognition for "Verify it's me".

Compares frames captured from the live selfie video with the user's main profile photo, using OpenCV's
YuNet face detector and SFace face-recognition model (both small ONNX models from the OpenCV model zoo).

    verify(main_photo_bytes, [frame_bytes, ...]) -> FaceResult

The selfie passes when:
  * exactly one clear face is found in the main photo (the largest face is used if there are several),
  * a face is found in at least MIN_FRAMES of the live frames,
  * the median cosine similarity between the live face and the photo face is >= MATCH_THRESHOLD
    (SFace's published threshold is 0.363; we use a slightly stricter value), and
  * the live frames aren't all identical (a basic check that it's a live video, not a still picture).

The models are downloaded on first use into backend/models/ (about 39 MB), or ahead of time with
`python face.py --download`.
"""
from __future__ import annotations

import hashlib
import statistics
import sys
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent / "models"
ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
MODELS = {
    "detector": ("face_detection_yunet_2023mar.onnx", f"{ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
                 "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "recognizer": ("face_recognition_sface_2021dec.onnx",
                   f"{ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
                   "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}

MATCH_THRESHOLD = 0.40      # cosine similarity; SFace's same-person threshold is 0.363
MIN_FRAMES = 2              # live frames that must contain a face
MIN_FACE_PX = 60            # ignore tiny faces (too little detail to compare)
DETECT_SCORE = 0.8
MAX_PHOTO_PX = 1600         # uploaded profile photos are resized so the long side is at most this


class FaceError(Exception):
    """The check couldn't run or didn't pass; the message is shown to the user."""


@dataclass
class FaceResult:
    matched: bool
    similarity: float                       # median similarity of live frames vs. main photo (0-1)
    frames_with_face: int
    frames_total: int
    scores: list[float] = field(default_factory=list)

    @property
    def percent(self) -> int:
        return max(0, min(100, round(self.similarity * 100)))


def _cv():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise FaceError("Face recognition isn't installed on the server. Run: pip install -r requirements.txt") from e
    import cv2
    import numpy as np
    return cv2, np


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_models() -> dict[str, Path]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, (name, url, sha) in MODELS.items():
        path = MODELS_DIR / name
        if not path.exists() or _sha256(path) != sha:
            tmp = path.with_suffix(".part")
            try:
                urllib.request.urlretrieve(url, tmp)
            except Exception as e:
                raise FaceError(f"Couldn't download the face-recognition model {name}. Check the internet "
                                f"connection, or run `python face.py --download` in the backend folder.") from e
            if _sha256(tmp) != sha:
                tmp.unlink(missing_ok=True)
                raise FaceError(f"The downloaded face-recognition model {name} looks corrupted — try again.")
            tmp.replace(path)
        paths[key] = path
    return paths


class FaceMatcher:
    def __init__(self):
        self._lock = threading.Lock()
        self._detector = None
        self._recognizer = None

    def _load(self):
        if self._recognizer is None:
            cv2, _ = _cv()
            paths = ensure_models()
            self._detector = cv2.FaceDetectorYN.create(str(paths["detector"]), "", (320, 320), DETECT_SCORE, 0.3, 5000)
            self._recognizer = cv2.FaceRecognizerSF.create(str(paths["recognizer"]), "")

    def _decode(self, data: bytes, max_side: int = 1280):
        cv2, np = _cv()
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)  # applies EXIF rotation
        if img is None:
            return None
        # Very large photos slow detection down without helping; keep the long side <= max_side px.
        h, w = img.shape[:2]
        scale = max_side / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        return img

    def _face(self, img):
        """Largest detected face -> (embedding, aligned crop) or None."""
        h, w = img.shape[:2]
        self._detector.setInputSize((w, h))
        _, faces = self._detector.detect(img)
        if faces is None or len(faces) == 0:
            return None
        face = max(faces, key=lambda f: f[2] * f[3])
        if min(face[2], face[3]) < MIN_FACE_PX:
            return None
        crop = self._recognizer.alignCrop(img, face)
        return self._recognizer.feature(crop), crop

    def locate(self, data: bytes) -> dict | None:
        """Where the (largest) face is in a photo, for cropping it into view:
        {"x", "y"}: face centre as % of the image width/height,
        "s": face width as a fraction of the image's shorter side (used to zoom small avatars)."""
        with self._lock:
            self._load()
            img = self._decode(data)
            if img is None:
                return None
            h, w = img.shape[:2]
            self._detector.setInputSize((w, h))
            _, faces = self._detector.detect(img)
        if faces is None or len(faces) == 0:
            return None
        fx, fy, fw, fh = (float(v) for v in max(faces, key=lambda f: f[2] * f[3])[:4])
        if min(fw, fh) < 24:
            return None
        return {"x": round(100 * (fx + fw / 2) / w, 1), "y": round(100 * (fy + fh / 2) / h, 1),
                "s": round(fw / min(w, h), 3)}

    def prepare_photo(self, data: bytes, ext: str) -> tuple[bytes, str, dict | None]:
        """Resize an uploaded profile photo (long side <= MAX_PHOTO_PX, EXIF rotation applied) and find its face.
        Returns (bytes, extension, focus or None). GIF/HEIC are kept as they are (OpenCV can't re-encode them)."""
        if ext in (".gif", ".heic"):
            return data, ext, None
        cv2, _ = _cv()
        img = self._decode(data, max_side=MAX_PHOTO_PX)
        if img is None:
            return data, ext, None
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        out = buf.tobytes() if ok else data
        return out, (".jpg" if ok else ext), self.locate(out)

    def verify(self, photo: bytes, frames: list[bytes]) -> FaceResult:
        cv2, np = _cv()
        if not frames:
            raise FaceError("No selfie frames were received — record the selfie video again.")
        with self._lock:
            self._load()
            img = self._decode(photo)
            if img is None:
                raise FaceError("Your main photo can't be read for face matching — upload it as JPG or PNG.")
            ref = self._face(img)
            if ref is None:
                raise FaceError("We couldn't find a clear face in your main photo. Use a photo where your face is "
                                "clearly visible, then try again.")
            ref_feat, _ = ref
            scores, crops = [], []
            for data in frames[:12]:
                frame = self._decode(data)
                found = self._face(frame) if frame is not None else None
                if found is None:
                    continue
                feat, crop = found
                scores.append(float(self._recognizer.match(ref_feat, feat, cv2.FaceRecognizerSF_FR_COSINE)))
                crops.append(crop.astype(np.float32))

        if len(scores) < MIN_FRAMES:
            raise FaceError("We couldn't see your face clearly in the selfie video. Face the camera in good light, "
                            "keep your face inside the oval, and try again.")
        # Basic liveness: a live video changes a little between frames; a held-up still picture doesn't.
        diffs = [float(np.mean(np.abs(a - b))) for a, b in zip(crops, crops[1:])]
        if diffs and max(diffs) < 0.5:
            raise FaceError("The selfie looks like a still picture. Record a live video and slowly turn your head.")
        sim = statistics.median(scores)
        return FaceResult(matched=sim >= MATCH_THRESHOLD, similarity=sim, frames_with_face=len(scores),
                          frames_total=len(frames), scores=scores)


_default = None


def default_matcher() -> FaceMatcher:
    global _default
    if _default is None:
        _default = FaceMatcher()
    return _default


if __name__ == "__main__":
    if "--download" in sys.argv:
        for key, path in ensure_models().items():
            print(f"{key}: {path}")
    elif len(sys.argv) >= 3:
        files = [Path(p).read_bytes() for p in sys.argv[1:]]
        r = default_matcher().verify(files[0], files[1:])
        print(f"matched={r.matched} similarity={r.similarity:.3f} frames={r.frames_with_face}/{r.frames_total}")
    else:
        print("Usage: python face.py --download | python face.py MAIN_PHOTO FRAME [FRAME ...]")
