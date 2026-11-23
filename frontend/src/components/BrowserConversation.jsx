import { useEffect, useRef, useState } from "react";
import { useConversation } from "@elevenlabs/react";
import { api } from "../services/api";

export default function BrowserConversation({ screeningId, candidate = false, session, onFinished }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const attachedConversationRef = useRef("");
  const returnedConversationIdRef = useRef("");

  const conversation = useConversation({
    overrides: session.overrides,
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
      setBusy(false);
      setError(reason?.message || (typeof reason === "string" ? reason : "ElevenLabs could not connect. Check the agent, token, and microphone permissions."));
    },
  });

  // Current versions of the React SDK expose the conversation ID through
  // getId() after connection. Older versions returned it from startSession().
  // Attach only after the WebRTC connection is established so the backend
  // never receives an undefined conversation ID.
  useEffect(() => {
    if (conversation.status !== "connected" || attachedConversationRef.current) return;

    const conversationId = conversation.getId?.() || returnedConversationIdRef.current;
    if (!conversationId) {
      setError("ElevenLabs connected, but did not provide a conversation ID. Please try again.");
      setBusy(false);
      conversation.endSession().catch(() => {});
      return;
    }

    attachedConversationRef.current = conversationId;
    api.attachBrowserConversation(screeningId, conversationId, candidate)
      .then(() => setError(""))
      .catch(async (reason) => {
        attachedConversationRef.current = "";
        setError(reason?.message || "The screening connected, but the application could not save the session. Please try again.");
        try {
          await conversation.endSession();
        } catch {
          // Keep the original API error visible.
        }
      })
      .finally(() => setBusy(false));
  }, [conversation.status, screeningId, candidate]);

  async function start() {
    setBusy(true);
    setError("");
    setMessages([]);
    attachedConversationRef.current = "";
    returnedConversationIdRef.current = "";

    try {
      if (!session?.token) {
        throw new Error("The screening token is missing. Refresh the candidate portal and try again.");
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone access is unavailable. Open this page on localhost or HTTPS.");
      }

      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      permissionStream.getTracks().forEach((track) => track.stop());

      const result = conversation.startSession({
        connectionType: "webrtc",
        conversationToken: session.token,
        userId: screeningId,
        dynamicVariables: session.dynamic_variables,
        overrides: session.overrides,
      });

      // Backward compatibility with SDK versions that return the ID from
      // startSession(); newer React SDK versions return void and use getId().
      if (result && typeof result.then === "function") {
        result.then((id) => {
          if (typeof id === "string") returnedConversationIdRef.current = id;
        }).catch((reason) => {
          setBusy(false);
          setError(reason?.message || "ElevenLabs could not start the screening.");
        });
      } else if (typeof result === "string") {
        returnedConversationIdRef.current = result;
      }
    } catch (reason) {
      setBusy(false);
      setError(reason?.message || "Could not start the ElevenLabs screening. Check microphone permission and agent configuration.");
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
