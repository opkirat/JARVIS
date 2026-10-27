import assert from 'node:assert/strict';
import test from 'node:test';
import { answerVoiceToolCalls } from '../src/voiceToolCalls.js';

const calls = [
  { name: 'search_gmail', arguments: '{"query":"assignment"}', call_id: 'search-1' },
  { name: 'read_gmail_email', arguments: '{"id":"synthetic"}', call_id: 'read-1' },
];

function setup(fetcher) {
  const sent = [];
  const abort = new AbortController();
  return {
    sent, abort,
    options: {
      channel: { readyState: 'open', send: (event) => sent.push(JSON.parse(event)) },
      signal: abort.signal,
      isActive: () => !abort.signal.aborted,
      fetcher,
    },
  };
}

test('returns every tool result before requesting exactly one spoken continuation', async () => {
  const requests = [];
  const state = setup(async (url, options) => {
    requests.push([url, JSON.parse(options.body)]);
    return { ok: true, json: async () => ({ source: 'synthetic' }) };
  });
  await answerVoiceToolCalls(calls, state.options);
  assert.equal(requests.length, 2);
  assert.equal(requests[0][0], '/api/realtime/tool');
  assert.deepEqual(state.sent.map((event) => event.type), ['conversation.item.create', 'conversation.item.create', 'response.create']);
  assert.deepEqual(state.sent.slice(0, 2).map((event) => event.item.call_id), ['search-1', 'read-1']);
});

test('does not resume a conversation after the user disconnects during a lookup', async () => {
  let release;
  const state = setup(() => new Promise((resolve) => { release = resolve; }));
  const pending = answerVoiceToolCalls(calls.slice(0, 1), state.options);
  state.abort.abort();
  release({ ok: true, json: async () => ({ count: 0 }) });
  await pending;
  assert.deepEqual(state.sent, []);
});

test('returns lookup failures as errors instead of fabricated mail', async () => {
  const state = setup(async () => { throw new Error('offline'); });
  await answerVoiceToolCalls(calls.slice(0, 1), state.options);
  assert.ok(JSON.parse(state.sent[0].item.output).error);
  assert.equal(state.sent[1].type, 'response.create');
});

test('routes Crowdmark calls through the same voice tool endpoint', async () => {
  const requests = [];
  const state = setup(async (url, options) => {
    requests.push(JSON.parse(options.body));
    return { ok: true, json: async () => ({ assessments_table: 'synthetic results' }) };
  });
  await answerVoiceToolCalls([{ name: 'search_crowdmark', arguments: '{"query":"math"}', call_id: 'grades-1' }], state.options);
  assert.equal(requests[0].name, 'search_crowdmark');
  assert.equal(state.sent[0].item.call_id, 'grades-1');
  assert.equal(JSON.parse(state.sent[0].item.output).assessments_table, 'synthetic results');
});
