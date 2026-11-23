import { useState } from "react";
import { useConversation } from "@elevenlabs/react";
import { api } from "../services/api";

export default function BrowserConversation({ screeningId, candidate = false, session, onFinished }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const conversation = useConversation({
    overrides: session?.overrides,
    onMessage: (message) => {
      const text = typeof message === "string"
        ? message
        : (message?.message ?? message?.text ?? message?.source?.text);
      if (typeof text === "string" && text.trim()) {
        setMessages((current) => [...current, {
          role: message?.source === "user" || message?.role === "user" ? "You" : "Assistant",
          text,
        }]);
      }
    },
    onError: (reason) => {
      setError(reason?.message || (typeof reason === "string" ? reason : "ElevenLabs connection failed. Check the agent configuration and try again."));
    },
  });

  async function start() {
    setBusy(true);
    setError("");
    setMessages([]);

    try {
      if (!session?.token || !session?.agent_id) {
        throw new Error("The ElevenLabs session details are incomplete. Refresh the portal and try again.");
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone access is unavailable. Open this page on localhost or HTTPS.");
      }

      // Ask for permission from the button click, before opening the agent.
      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach((track) => track.stop());

      // startSession resolves with the actual ElevenLabs conversation ID.
      // Wait for it before attaching the conversation to the candidate's record.
      const conversationId = await conversation.startSession({
        agentId: session.agent_id,
        conversationToken: session.token,
        connectionType: "webrtc",
        userId: screeningId,
        dynamicVariables: session.dynamic_variables,
        overrides: session.overrides,
      });

      if (typeof conversationId !== "string" || !conversationId.startsWith("conv_")) {
        throw new Error("ElevenLabs connected without returning a valid conversation ID. Please try again.");
      }

      try {
        await api.attachBrowserConversation(screeningId, conversationId, candidate);
      } catch (attachError) {
        await conversation.endSession();
        throw attachError;
      }
    } catch (reason) {
      setError(reason?.message || "Could not start the ElevenLabs screening. Check microphone permission and agent configuration.");
    } finally {
      setBusy(false);
    }
  }

  async function end() {
    setBusy(true);
    try {
      await conversation.endSession();
      onFinished?.();
    } catch (reason) {
      setError(reason?.message || "Could not end conversation.");
    } finally {
      setBusy(false);
    }
  }

  function sendText(event) {
    event.preventDefault();
    const value = draft.trim();
    if (!value || conversation.status !== "connected") return;
    conversation.sendUserMessage(value);
    setMessages((current) => [...current, { role: "You", text: value }]);
    setDraft("");
  }

  const connected = conversation.status === "connected";
  const connecting = conversation.status === "connecting" || busy;

  return <section className="panel" style={{ marginTop: 16 }}>
    <div className="panel-header">
      <div>
        <h2>ElevenLabs browser screening</h2>
        <p className="muted-copy">Voice over the internet with text chat available as an alternative.</p>
      </div>
      <span className="status-badge">{conversation.status}</span>
    </div>
    {!connected
      ? <button className="button button-primary" disabled={connecting} onClick={start}>
          {connecting ? "Connecting…" : "Start screening conversation"}
        </button>
      : <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="button button-secondary" onClick={() => conversation.setMuted(!conversation.isMuted)}>
            {conversation.isMuted ? "Unmute microphone" : "Mute microphone"}
          </button>
          <button className="button button-danger" disabled={busy} onClick={end}>End conversation</button>
        </div>}
    <p className="form-note">The assistant must ask for your verbal consent to AI screening, transcription, and AI-generated summary before asking job questions. You can decline or stop at any time.</p>
    {connected && <form onSubmit={sendText} style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <input aria-label="Type a message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Or type your answer…" />
      <button className="button button-primary" disabled={!draft.trim()}>Send</button>
    </form>}
    {messages.length > 0 && <div style={{ maxHeight: 260, overflowY: "auto", marginTop: 12 }}>
      {messages.map((item, index) => <p key={index}><strong>{item.role}:</strong> {item.text}</p>)}
    </div>}
    {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
  </section>;
}
