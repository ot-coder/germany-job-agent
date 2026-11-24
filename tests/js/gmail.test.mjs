// Run with: node --test tests/js/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { detectApplication, companyFromSender, positionFromSubject, matchJob } from '../../jobs_agent/site/gmail.js';

const mail = (over) => ({ id: 'm1', subject: '', from: '', date: 'Mon, 3 Nov 2026 10:00:00 +0100', body: '', ...over });

test('detects an English confirmation and extracts company + position', () => {
  const hit = detectApplication(mail({
    subject: 'Thank you for applying for the Working Student Data position',
    from: 'Acme Careers <no-reply@acme.de>', body: 'We received your application.',
  }));
  assert.equal(hit.company, 'Acme');
  assert.equal(hit.position, 'Working Student Data');
  assert.equal(hit.status, 'applied');
  assert.equal(hit.emailId, 'm1');
  assert.equal(hit.applicationDate, '2026-11-03T09:00:00.000Z');
});

test('detects German confirmations and rejections', () => {
  const ok = detectApplication(mail({ subject: 'Ihre Bewerbung als Werkstudent Backend bei Beta', from: 'jobs@beta-gruppe.de', body: 'Vielen Dank für Ihre Bewerbung!' }));
  assert.equal(ok.position, 'Werkstudent Backend');
  assert.equal(ok.company, 'Beta-gruppe');
  const no = detectApplication(mail({ subject: 'Ihre Bewerbung', from: 'HR <hr@gamma.de>', body: 'Vielen Dank für Ihre Bewerbung. Leider müssen wir Ihnen mitteilen …' }));
  assert.equal(no.status, 'rejected');
});

test('interview invitations are flagged', () => {
  const hit = detectApplication(mail({ subject: 'Your application', from: 'x@delta.io', body: 'Thank you for applying. We would like to schedule an interview.' }));
  assert.equal(hit.status, 'interview');
});

test('ignores job alerts and "finish your application" nags', () => {
  assert.equal(detectApplication(mail({ subject: 'Bewerbung abschließen', from: 'info@finest-jobs.com', body: 'Vielen Dank für Ihre Bewerbung' })), null);
  assert.equal(detectApplication(mail({ subject: '10 new jobs for you', from: 'jobs@linkedin.com', body: 'thank you for applying' })), null);
  assert.equal(detectApplication(mail({ subject: 'Werkstudent jobs in Leipzig', from: 'alerts@stepstone.de', body: 'working student roles' })), null);
  assert.equal(detectApplication(mail({ subject: 'Lunch?', from: 'friend@gmail.com', body: 'hi' })), null);
});

test('keeps LinkedIn "application sent" confirmations', () => {
  const hit = detectApplication(mail({ subject: 'Your application was sent to Epsilon', from: 'LinkedIn <jobs-noreply@linkedin.com>', body: 'Application sent' }));
  assert.ok(hit);
});

test('company falls back sensibly for ATS senders', () => {
  assert.equal(companyFromSender('noreply@personio.de'), 'Unknown Company');
  assert.equal(companyFromSender('"Zeta GmbH | Recruiting" <noreply@personio.de>'), 'Zeta GmbH');
  assert.equal(companyFromSender('careers@jobs.omega.com'), 'Omega');
});

test('position defaults when subject has no role', () => {
  assert.equal(positionFromSubject('Eingangsbestätigung'), 'Unknown Position');
});

test('matchJob links only unambiguous company matches', () => {
  const jobs = [{ id: '1', company: 'Acme GmbH' }, { id: '2', company: 'Beta AG' }, { id: '3', company: 'Beta Logistics' }];
  assert.equal(matchJob('Acme', jobs).id, '1');
  assert.equal(matchJob('Beta', jobs), null);
  assert.equal(matchJob('Unknown Company', jobs), null);
});
