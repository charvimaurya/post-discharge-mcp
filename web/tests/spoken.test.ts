// A reload shows a waiting reminder again but never speaks it twice. No browser needed.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { alreadySpoken, clearSpoken, forgetSpoken, markSpoken, shouldSpeakOpening } from '../lib/spoken.ts';

function fakeStore() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value); },
    removeItem: (key: string) => { data.delete(key); },
  };
}
const WALK = '2026-10-23#walk#2026-10-23#1';
const MEDICINES = '2026-10-23#medicine#morning';

test('a reminder is spoken once, and not again after a reload', () => {
  const store = fakeStore();
  assert.equal(alreadySpoken(store, WALK), false);
  markSpoken(store, WALK);
  // The reload: same tab storage, same checkin_id.
  assert.equal(alreadySpoken(store, WALK), true);
});

test('each reminder is remembered by its own checkin_id', () => {
  const store = fakeStore();
  markSpoken(store, WALK);
  assert.equal(alreadySpoken(store, MEDICINES), false);
  markSpoken(store, MEDICINES);
  markSpoken(store, WALK);
  assert.equal(alreadySpoken(store, WALK), true);
  assert.equal(alreadySpoken(store, MEDICINES), true);
});

test('after a reset the list is cleared, so the same reminder is spoken again', () => {
  const store = fakeStore();
  markSpoken(store, WALK);
  clearSpoken(store);
  assert.equal(alreadySpoken(store, WALK), false);
});

test('the opening greeting is spoken once; a new greeting is spoken', () => {
  const store = fakeStore();
  const walk = 'Good morning, Margaret. I hope you slept well. Next is your morning walk at half past seven.';
  assert.equal(shouldSpeakOpening(store, walk), true);
  assert.equal(shouldSpeakOpening(store, walk), false);
  assert.equal(shouldSpeakOpening(store, 'Good afternoon, Margaret.'), true);
});

test('blocked or broken storage never throws; it just speaks', () => {
  const broken = {
    getItem: () => { throw new Error('blocked'); },
    setItem: () => { throw new Error('blocked'); },
    removeItem: () => { throw new Error('blocked'); },
  };
  assert.equal(alreadySpoken(broken, WALK), false);
  markSpoken(broken, WALK);
  clearSpoken(broken);
  assert.equal(shouldSpeakOpening(broken, 'Good morning.'), true);
  assert.equal(alreadySpoken(undefined, WALK), false);
});

test('opening Today again forgets both, so the reminder and the greeting are spoken again', () => {
  const store = fakeStore();
  markSpoken(store, WALK);
  assert.equal(shouldSpeakOpening(store, 'Good morning, Margaret.'), true);
  assert.equal(shouldSpeakOpening(store, 'Good morning, Margaret.'), false);
  forgetSpoken(store);
  assert.equal(alreadySpoken(store, WALK), false);
  assert.equal(shouldSpeakOpening(store, 'Good morning, Margaret.'), true);
});
