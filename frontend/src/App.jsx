import React, { useRef } from 'react';
import { useVoiceSession } from './useVoiceSession.js';

export default function App() {
  const audioRef = useRef(null);
  const { status, error, muted, start, stop, toggleMute } = useVoiceSession(audioRef);
  const active = status !== 'idle';
  const labels = {
    idle: 'Ready when you are',
    connecting: 'Connecting…',
    listening: 'Listening',
    thinking: 'Thinking…',
    searching: 'Looking up your information…',
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
          {muted ? `Microphone muted · ${labels[status]}` : labels[status]}
        </p>
        <button className={`voice-button ${active ? 'stop' : ''}`} onClick={active ? stop : start}>
          {status === 'connecting' ? 'Cancel' : active ? 'End conversation' : 'Talk to JARVIS'}
        </button>
        {active && status !== 'connecting' && (
          <button
            className={`voice-button mute-button ${muted ? 'muted' : ''}`}
            onClick={toggleMute}
            aria-label="Mute microphone"
            aria-pressed={muted}
          >
            {muted ? 'Unmute microphone' : 'Mute microphone'}
          </button>
        )}
        <p className="voice-hint">AI voice · {muted ? 'Microphone muted' : active ? 'Microphone on' : 'Microphone off'} · Five-minute session limit</p>
        <p className="voice-hint">Ask about your emails or Crowdmark scores. Access is read-only.</p>
        {error && <p className="voice-error" role="alert">{error}</p>}
        <audio ref={audioRef} autoPlay controls={active} className="voice-audio" aria-label="JARVIS audio playback" />
      </section>
    </main>
  );
}
