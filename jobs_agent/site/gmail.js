// Optional Gmail auto-detection, ported from the old job-tracker server route.
// Runs entirely in the browser: the access token and email contents never leave
// this page except to talk to Google's own API. Requires the user's OWN OAuth
// client ID (see guides/gmail.md), so nobody else's app is involved.

const GIS_SRC = 'https://accounts.google.com/gsi/client';
const SCOPE = 'https://www.googleapis.com/auth/gmail.readonly';
const API = 'https://gmail.googleapis.com/gmail/v1/users/me';
const MAX_MESSAGES = 500;
const CONCURRENCY = 6;

// Phrases that indicate an application confirmation (English + German).
export const APPLICATION_KEYWORDS = [
  'thank you for applying', 'application received', 'we have received your application',
  'your application for', 'application confirmation', 'thank you for your interest',
  'we received your application', 'application submitted successfully',
  'your resume has been received', 'thank you for submitting', 'thanks for applying',
  'vielen dank für ihre bewerbung', 'herzlichen dank für ihre bewerbung', 'danke für deine bewerbung',
  'vielen dank für deine bewerbung', 'wir werden uns schnellstmöglich wieder mit ihnen kontakt aufnehmen',
  'wir werden uns so schnell wie möglich bei ihnen melden', 'ihre bewerbung für die position',
  'bewerbung eingegangen', 'eingangsbestätigung',
];
export const REJECTION_KEYWORDS = [
  'unfortunately', 'we regret to inform', 'not selected', 'decided to move forward with other candidates',
  'will not be moving forward', 'thank you for your interest, however', 'we have decided not to proceed',
  'position has been filled', 'leider mitteilen', 'leider müssen wir', 'andere kandidat',
  'nicht weiter berücksichtigen', 'absage',
];
export const INTERVIEW_KEYWORDS = [
  'interview', 'would like to schedule', 'next step in the process', 'phone screen', 'video call',
  'meet with our team', 'discuss your application further', 'vorstellungsgespräch', 'kennenlerngespräch',
];
// Job-alert senders and subjects that are not applications.
const EXCLUDED_SENDER_DOMAINS = ['linkedin.com', 'stepstone.de', 'indeed.com', 'xing.com'];
const EXCLUDED_SUBJECT_KEYWORDS = [
  'job alert', 'job recommendation', 'recommended jobs', 'jobs for you', 'new jobs for you',
  'hiring in your network', 'top jobs', 'jobagent', 'neue jobs', 'passende jobs', 'bewerbung abschließen',
  'complete your application', 'finish your application',
];
const PLATFORM_CONFIRMATIONS = [
  'application sent', 'you applied', 'your application has been submitted',
  'bewerbung gesendet', 'ihre bewerbung wurde gesendet',
];
// Applicant-tracking and mail providers: the sender domain says nothing about the employer.
const GENERIC_DOMAINS = new Set([
  'personio', 'softgarden', 'workday', 'myworkday', 'myworkdayjobs', 'greenhouse', 'lever', 'smartrecruiters',
  'join', 'recruitee', 'successfactors', 'icims', 'taleo', 'onlyfy', 'dvinci', 'umantis', 'rexx-systems',
  'concludis', 'bamboohr', 'workable', 'teamtailor', 'jobylon', 'gmail', 'googlemail', 'outlook', 'hotmail',
  'web', 'gmx', 't-online', 'yahoo', 'icloud', 'linkedin', 'indeed', 'stepstone', 'xing',
]);
const SENDER_NOISE = /\b(no-?reply|recruiting|recruitment|recruiter|careers?|karriere|jobs?|team|hr|talent(?: acquisition)?|bewerbermanagement|personalabteilung|people|hiring|via)\b/gi;

const lower = (s) => String(s || '').toLowerCase();
const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

export function companyFromSender(from) {
  const match = String(from || '').match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>/);
  const name = match ? match[1] : '';
  const address = match ? match[2] : String(from || '').trim();
  const domainParts = lower(address.split('@')[1] || '').split('.').filter(Boolean);
  const registrable = domainParts.length >= 2 ? domainParts[domainParts.length - 2] : domainParts[0] || '';
  const cleanedName = name.replace(SENDER_NOISE, ' ').replace(/[|,·:\-–]+/g, ' ').replace(/\s+/g, ' ').trim();
  if (cleanedName && cleanedName.length > 1) return cleanedName.slice(0, 120);
  if (registrable && !GENERIC_DOMAINS.has(registrable)) return capitalize(registrable);
  return 'Unknown Company';
}

const POSITION_PATTERNS = [
  /.*\bfor\s+(?:the\s+)?["„“']?(.+?)["“”']?\s+(?:position|role)\b/i, // last "for" before "position"
  /application\s+(?:for|as)\s+(?:the\s+)?["„“']?(.+?)["“”']?(?:\s+(?:at|@)\s|\s+[-–|]\s|$)/i,
  /bewerbung\s+(?:als|für|auf)\s+(?:die\s+(?:position|stelle)\s+)?(?:als\s+)?["„“']?(.+?)["“”']?(?:\s+(?:bei|at)\s|\s+[-–|]\s|$)/i,
  /(?:position|stelle|role)\s*(?:as|als|:)\s*["„“']?(.+?)["“”']?(?:\s+(?:at|bei)\s|\s+[-–|]\s|$)/i,
];

export function positionFromSubject(subject) {
  for (const pattern of POSITION_PATTERNS) {
    const match = String(subject || '').match(pattern);
    const value = match && match[1].replace(/\s+/g, ' ').trim();
    if (value && value.length > 1 && value.length < 150) return value;
  }
  return 'Unknown Position';
}

/** Decide whether one email is an application confirmation. Returns a tracker entry or null. */
export function detectApplication({ id, subject = '', from = '', date = '', body = '' }) {
  const subjectLower = lower(subject);
  const text = `${subjectLower} ${lower(body)}`;
  const fromLower = lower(from);
  if (EXCLUDED_SUBJECT_KEYWORDS.some((k) => subjectLower.includes(k))) return null;
  const isPlatform = EXCLUDED_SENDER_DOMAINS.some((d) => fromLower.includes(d));
  if (isPlatform && !PLATFORM_CONFIRMATIONS.some((k) => text.includes(k))) return null;
  if (!isPlatform && !APPLICATION_KEYWORDS.some((k) => text.includes(k))) return null;

  let status = 'applied';
  if (REJECTION_KEYWORDS.some((k) => text.includes(k))) status = 'rejected';
  else if (INTERVIEW_KEYWORDS.some((k) => text.includes(k))) status = 'interview';

  const when = Date.parse(date);
  return {
    emailId: id,
    company: companyFromSender(from),
    position: positionFromSubject(subject),
    applicationDate: new Date(Number.isNaN(when) ? Date.now() : when).toISOString(),
    status,
    notes: `Auto-detected from email: ${subject}`.slice(0, 500),
  };
}

/** Link a detected application to a listing in the feed when the company name matches exactly one job. */
export function matchJob(company, jobs) {
  const name = lower(company).replace(/\b(gmbh|ag|se|kg|ug|co|inc|ltd|mbh)\b|[^a-z0-9äöüß ]/g, ' ').replace(/\s+/g, ' ').trim();
  if (name.length < 3 || name === 'unknown company') return null;
  const hits = jobs.filter((j) => lower(j.company).includes(name));
  return hits.length === 1 ? hits[0] : null;
}

// ---------- browser-only helpers ----------
function decodeBase64Url(data) {
  try {
    const binary = atob(data.replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return new TextDecoder('utf-8').decode(bytes);
  } catch { return ''; }
}
function htmlToText(html) {
  return new DOMParser().parseFromString(html, 'text/html').body?.textContent || '';
}
export function collectText(payload) {
  if (!payload) return '';
  const plain = [];
  const html = [];
  (function walk(part) {
    if (!part) return;
    if (part.body?.data) {
      if (part.mimeType === 'text/html') html.push(decodeBase64Url(part.body.data));
      else if (!part.mimeType || part.mimeType.startsWith('text/')) plain.push(decodeBase64Url(part.body.data));
    }
    (part.parts || []).forEach(walk);
  })(payload);
  return plain.length ? plain.join('\n') : html.map(htmlToText).join('\n');
}

let gisPromise;
export function preload() {
  gisPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.oauth2) { resolve(); return; }
    const script = document.createElement('script');
    script.src = GIS_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => { gisPromise = undefined; reject(new Error('Could not load Google sign-in.')); };
    document.head.appendChild(script);
  });
  return gisPromise;
}

async function getToken(clientId) {
  await preload();
  return new Promise((resolve, reject) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: (response) => (response.error ? reject(new Error(response.error_description || response.error)) : resolve(response.access_token)),
      error_callback: (error) => reject(new Error(error?.message || error?.type || 'Sign-in was cancelled.')),
    });
    client.requestAccessToken();
  });
}

async function gmailGet(token, path) {
  const res = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).error?.message || detail; } catch { /* ignore */ }
    throw new Error(`Gmail API ${res.status}: ${detail}`);
  }
  return res.json();
}

function searchQuery(days) {
  const phrases = [...APPLICATION_KEYWORDS, ...PLATFORM_CONFIRMATIONS].map((k) => `"${k}"`).join(' ');
  return `newer_than:${days}d {${phrases}}`;
}

export async function scan({ clientId, days = 30, skipIds = new Set(), onProgress = () => {} }) {
  onProgress('Waiting for Google sign-in…');
  const token = await getToken(clientId);
  onProgress('Searching your inbox…');
  const ids = [];
  let pageToken = '';
  do {
    const params = new URLSearchParams({ q: searchQuery(days), maxResults: '100' });
    if (pageToken) params.set('pageToken', pageToken);
    const page = await gmailGet(token, `/messages?${params}`);
    (page.messages || []).forEach((m) => { if (!skipIds.has(m.id)) ids.push(m.id); });
    pageToken = page.nextPageToken || '';
  } while (pageToken && ids.length < MAX_MESSAGES);

  const found = [];
  let done = 0;
  const queue = ids.slice(0, MAX_MESSAGES);
  async function worker() {
    while (queue.length) {
      const id = queue.shift();
      try {
        const msg = await gmailGet(token, `/messages/${id}?format=full`);
        const headers = msg.payload?.headers || [];
        const header = (name) => headers.find((h) => lower(h.name) === name)?.value || '';
        const hit = detectApplication({
          id, subject: header('subject'), from: header('from'), date: header('date'), body: collectText(msg.payload),
        });
        if (hit) found.push(hit);
      } catch (error) {
        if (/Gmail API 401|Gmail API 403/.test(error.message)) throw error;
      }
      done += 1;
      onProgress(`Checked ${done} of ${ids.length} candidate emails…`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker));
  try { window.google.accounts.oauth2.revoke(token, () => {}); } catch { /* ignore */ }
  return found;
}
