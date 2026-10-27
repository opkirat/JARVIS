// Complete all calls from one model response before asking it to speak again.
export async function answerVoiceToolCalls(calls, { channel, signal, isActive, fetcher = fetch }) {
  const outputs = await Promise.all(calls.map(async (call) => {
    let output;
    try {
      if (!['search_gmail', 'read_gmail_email', 'search_crowdmark'].includes(call.name)) {
        throw new Error('Unsupported lookup tool.');
      }
      const args = JSON.parse(call.arguments);
      const response = await fetcher('/api/realtime/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Jarvis-Voice': '1' },
        body: JSON.stringify({ name: call.name, arguments: args }),
        signal,
      });
      output = await response.json();
      if (!response.ok && !output.error) output = { error: 'Data lookup failed.' };
    } catch {
      output = { error: 'Could not look up the local data. Do not invent results.' };
    }
    return { type: 'function_call_output', call_id: call.call_id, output: JSON.stringify(output) };
  }));
  if (!isActive() || signal.aborted || channel.readyState !== 'open') return;
  for (const item of outputs) {
    channel.send(JSON.stringify({ type: 'conversation.item.create', item }));
  }
  channel.send(JSON.stringify({ type: 'response.create' }));
}
