import { useCallback, useEffect, useRef, useState } from 'react';
import { answerVoiceToolCalls } from './voiceToolCalls.js';

export function useVoiceSession(audioRef) {
  const current = useRef(null);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);

  const release = useCallback((session) => {
    if (!session) return;
    clearTimeout(session.timeout);
    clearTimeout(session.duration);
    session.abort.abort();
    session.stream?.getTracks().forEach((track) => track.stop());
    if (session.peer) session.peer.onconnectionstatechange = null;
    if (session.channel) {
      session.channel.onmessage = null;
      session.channel.onopen = null;
      session.channel.onclose = null;
      session.channel.close();
    }
    session.peer?.close();
    if (current.current === session) {
      current.current = null;
      if (audioRef.current) audioRef.current.srcObject = null;
    }
  }, [audioRef]);

  const stop = useCallback(() => {
    release(current.current);
    setMuted(false);
    setStatus('idle');
  }, [release]);

  const toggleMute = useCallback(() => {
    const session = current.current;
    if (!session?.stream) return;
    session.muted = !session.muted;
    session.stream.getAudioTracks().forEach((track) => {
      track.enabled = !session.muted;
    });
    setMuted(session.muted);
  }, []);

  useEffect(() => () => release(current.current), [release]);

  const start = useCallback(async () => {
    if (current.current) return;
    setError('');
    setMuted(false);
    setStatus('connecting');
    const session = { abort: new AbortController(), toolCalls: new Set() };
    current.current = session;
    const active = () => current.current === session;
    const fail = (message) => {
      if (!active()) return;
      release(session);
      setMuted(false);
      setError(message);
      setStatus('idle');
    };

    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
        throw new Error('Voice requires a browser with microphone support on localhost or HTTPS.');
      }
      session.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      if (!active()) {
        session.stream.getTracks().forEach((track) => track.stop());
        return;
      }
      session.timeout = setTimeout(() => fail('Voice connection timed out. Try again.'), 30000);
      const tokenResponse = await fetch('/api/realtime/token', {
        method: 'POST',
        headers: { 'X-Jarvis-Voice': '1' },
        signal: session.abort.signal,
      });
      if (!tokenResponse.ok) {
        const body = await tokenResponse.json().catch(() => ({}));
        throw new Error(body.error || 'Cannot start voice. Make sure the Python voice server is running.');
      }
      const token = await tokenResponse.json();
      if (!active()) return;
      if (!token.value) throw new Error('No voice session token was returned.');

      const peer = new RTCPeerConnection();
      session.peer = peer;
      peer.ontrack = (event) => {
        if (active() && audioRef.current) {
          audioRef.current.srcObject = event.streams[0] || new MediaStream([event.track]);
        }
      };
      peer.onconnectionstatechange = () => {
        if (['failed', 'disconnected', 'closed'].includes(peer.connectionState)) {
          fail('Voice connection ended. Start a new conversation to reconnect.');
        }
      };
      session.stream.getTracks().forEach((track) => peer.addTrack(track, session.stream));
      session.channel = peer.createDataChannel('oai-events');
      session.channel.onopen = () => {
        if (!active()) return;
        clearTimeout(session.timeout);
        setStatus('listening');
        session.duration = setTimeout(() => {
          if (!active()) return;
          stop();
          setError('Five-minute session limit reached. Start a new conversation to continue.');
        }, 5 * 60 * 1000);
      };
      session.channel.onclose = () => fail('Voice connection ended. Start again to reconnect.');
      session.channel.onmessage = ({ data }) => {
        if (!active()) return;
        let event;
        try { event = JSON.parse(data); } catch { return; }
        if (event.type === 'response.done') {
          // Metadata only: never log spoken text, tool arguments, or email data.
          console.info('JARVIS response ended', {
            status: event.response?.status,
            reason: event.response?.status_details?.reason,
          });
        }
        if (event.type === 'error') {
          fail('The voice service reported an error. Please start a new conversation.');
        } else if (event.type === 'input_audio_buffer.speech_started') {
          setError('');
          setStatus('listening');
        } else if (event.type === 'input_audio_buffer.speech_stopped' || event.type === 'response.created') {
          setStatus('thinking');
        } else if (event.type === 'output_audio_buffer.started') {
          setStatus('speaking');
        } else if (['output_audio_buffer.stopped', 'output_audio_buffer.cleared'].includes(event.type)) {
          setStatus('listening');
        } else if (event.type === 'response.done' && event.response?.status === 'failed') {
          fail('JARVIS could not complete the response. Check your API billing and try again.');
        } else if (event.type === 'response.done' && event.response?.status === 'incomplete') {
          setError(event.response.status_details?.reason === 'max_output_tokens'
            ? 'JARVIS reached the response length limit. Ask it to continue.'
            : 'JARVIS could not finish that response. Try rephrasing your request.');
        } else if (event.type === 'response.done' && event.response?.status === 'completed') {
          const calls = (event.response.output || []).filter((item) => (
            item.type === 'function_call' && !session.toolCalls.has(item.call_id)
          ));
          if (!calls.length) return;
          calls.forEach((call) => session.toolCalls.add(call.call_id));
          setStatus('searching');
          answerVoiceToolCalls(calls, {
            channel: session.channel,
            signal: session.abort.signal,
            isActive: active,
          }).catch(() => fail('Could not return the lookup results. Please reconnect.'));
        }
      };

      const offer = await peer.createOffer();
      if (!active()) return;
      await peer.setLocalDescription(offer);
      const answer = await fetch('https://api.openai.com/v1/realtime/calls', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.value}`, 'Content-Type': 'application/sdp' },
        body: offer.sdp,
        signal: session.abort.signal,
      });
      if (!answer.ok) throw new Error(`Voice connection rejected (HTTP ${answer.status}).`);
      const sdp = await answer.text();
      if (!active()) return;
      await peer.setRemoteDescription({ type: 'answer', sdp });
    } catch (cause) {
      if (!active()) return;
      const message = cause.name === 'NotAllowedError'
        ? 'Microphone permission is required. Allow it in your browser, then try again.'
        : cause.name === 'NotFoundError'
          ? 'No microphone was found. Connect one and try again.'
          : cause.message || 'Could not connect to voice. Please try again.';
      fail(message);
    }
  }, [audioRef, release, stop]);

  return { status, error, muted, start, stop, toggleMute };
}
