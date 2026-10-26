import React, { useRef } from 'react';
import { useVoiceSession } from './useVoiceSession.js';

export default function App() {
  const audioRef = useRef(null);
  const { status, error, caption, start, stop } = useVoiceSession(audioRef);
  const active = status !== 'idle';
  const labels = {
    idle: 'Ready when you are',
    connecting: 'Connecting…',
    listening: 'Listening',
    thinking: 'Thinking…',
    speaking: 'Speaking',
  };

  return (
    <main className="homepage" aria-label="JARVIS home">
      <section className="voice-panel" aria-label="JARVIS voice assistant">
        <img
          className="jarvis-logo"
          src="/jarvis-logo.png"
          alt="JARVIS"
          width="360"
          height="360"
          draggable="false"
        />
        <p className="voice-status" role="status">
          <span className={`status-dot ${active ? 'active' : ''}`} aria-hidden="true" />
          {labels[status]}
        </p>
        <button className={`voice-button ${active ? 'stop' : ''}`} onClick={active ? stop : start}>
          {status === 'connecting' ? 'Cancel' : active ? 'End conversation' : 'Talk to JARVIS'}
        </button>
        <p className="voice-hint">AI voice · Microphone on during conversations · Five-minute session limit</p>
        {error && <p className="voice-error" role="alert">{error}</p>}
        {caption && <p className="voice-caption">{caption}</p>}
        <audio ref={audioRef} autoPlay controls={active} className="voice-audio" aria-label="JARVIS audio playback" />
      </section>
    </main>
  );
}
