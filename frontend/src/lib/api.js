// Thin client for the Flask API. Every mutation returns the full app snapshot.
let onUnauthorized = null;
/** Called whenever the server says the session is gone (logged out / expired). */
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }
async function request(path, { method = 'GET', json, form } = {}) {
  const opts = { method, headers: {} };
  if (json !== undefined) {
    opts.headers['content-type'] = 'application/json';
    opts.body = JSON.stringify(json);
  } else if (form) {
    opts.body = form;
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Can't reach the server. Is the backend running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Request failed (${res.status})`);
    err.status = res.status;
    if (res.status === 401 && onUnauthorized) onUnauthorized();
    throw err;
  }
  return data;
}

const qs = (q) => (q ? `?q=${encodeURIComponent(q)}` : '');

export const api = {
  authConfig: () => request('/api/auth/config'),
  // Password reset: the emailed link comes back to the address the app is open on.
  forgotPassword: (email) => request('/api/auth/forgot', { method: 'POST', json: { email, origin: window.location.origin } }),
  checkReset: (token) => request(`/api/auth/reset/check?token=${encodeURIComponent(token)}`),
  resetPassword: (token, password) => request('/api/auth/reset', { method: 'POST', json: { token, password } }),
  changePassword: (current, password) => request('/api/auth/change-password', { method: 'POST', json: { current, password } }),
  register: (name, email, password) => request('/api/auth/register', { method: 'POST', json: { name, email, password } }),
  login: (email, password) => request('/api/auth/login', { method: 'POST', json: { email, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  deleteAccount: () => request('/api/account', { method: 'DELETE' }),
  state: (q) => request(`/api/state${qs(q)}`),
  updateProfile: (patch, q) => request(`/api/profile${qs(q)}`, { method: 'PUT', json: patch }),
  /** frames: JPEG blobs captured from the live selfie video (compared with the main photo on the server). */
  verifyPhoto: (frames, q) => {
    const form = new FormData();
    (frames || []).forEach((f, i) => form.append('frames', f, `frame${i}.jpg`));
    return request(`/api/profile/verify-photo${qs(q)}`, { method: 'POST', form });
  },
  uploadPhoto: (slot, file, q) => {
    const form = new FormData();
    form.append('photo', file);
    return request(`/api/photos/${slot}${qs(q)}`, { method: 'POST', form });
  },
  deletePhoto: (slot, q) => request(`/api/photos/${slot}${qs(q)}`, { method: 'DELETE' }),
  like: (id, q) => request(`/api/candidates/${id}/like${qs(q)}`, { method: 'POST' }),
  pass: (id, q) => request(`/api/candidates/${id}/pass${qs(q)}`, { method: 'POST' }),
  accept: (candidateId, q) => request(`/api/connection/accept${qs(q)}`, { method: 'POST', json: { candidateId } }),
  confirm: (q) => request(`/api/connection/confirm${qs(q)}`, { method: 'POST' }),
  close: (q) => request(`/api/connection/close${qs(q)}`, { method: 'POST' }),
  engage: (q) => request(`/api/connection/engage${qs(q)}`, { method: 'POST' }),
  acceptEngagement: (q) => request(`/api/connection/engage/accept${qs(q)}`, { method: 'POST' }),
  declineEngagement: (q) => request(`/api/connection/engage/decline${qs(q)}`, { method: 'POST' }),
  cancelEngagement: (q) => request(`/api/connection/engage/cancel${qs(q)}`, { method: 'POST' }),
  pastMessages: (connId) => request(`/api/connections/${connId}/messages`),
  send: (text, q) => request(`/api/messages${qs(q)}`, { method: 'POST', json: { text } }),
  sendMedia: (file, name, text, q) => {
    const form = new FormData();
    form.append('file', file, name);
    if (text) form.append('text', text);
    return request(`/api/messages${qs(q)}`, { method: 'POST', form });
  },
  clearEvents: (q) => request(`/api/events${qs(q)}`, { method: 'DELETE' }),
};
