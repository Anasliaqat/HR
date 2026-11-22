import { useState } from "react";
import { useConversation } from "@elevenlabs/react";
import { api } from "../services/api";

export default function BrowserConversation({ screeningId, candidate = false, session, onFinished }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const conversation = useConversation({
    overrides: session.overrides,
    onMessage: (message) => {
      const text = message?.message ?? message?.text ?? message?.source?.text;
      if (typeof text === "string" && text.trim()) {
        setMessages((current) => [...current, {
          role: message?.source === "user" || message?.role === "user" ? "You" : "Assistant",
          text,
        }]);
      }
    },
    onError: (reason) => setError(typeof reason === "string" ? reason : "Conversation connection error."),
  });

  async function start() {
    setBusy(true); setError("");
    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      const conversationId = await conversation.startSession({
        conversationToken: session.token,
        userId: screeningId,
        dynamicVariables: session.dynamic_variables,
        overrides: session.overrides,
      });
      await api.attachBrowserConversation(screeningId, conversationId, candidate);
    } catch (reason) {
      setError(reason?.message || "Could not start the ElevenLabs session. Check microphone permission and agent configuration.");
    } finally { setBusy(false); }
  }
  async function end() {
    setBusy(true);
    try { await conversation.endSession(); onFinished?.(); }
    catch (reason) { setError(reason?.message || "Could not end conversation."); }
    finally { setBusy(false); }
  }
  function sendText(event) {
    event.preventDefault();
    const value = draft.trim();
    if (!value || conversation.status !== "connected") return;
    conversation.sendUserMessage(value);
    setMessages((current) => [...current, { role: "You", text: value }]);
    setDraft("");
  }

  return <section className="panel" style={{ marginTop: 16 }}>
    <div className="panel-header"><div><h2>ElevenLabs browser screening</h2><p className="muted-copy">Voice over the internet with text chat available as an alternative.</p></div>
      <span className="status-badge">{conversation.status}</span></div>
    {conversation.status !== "connected" ? <button className="button button-primary" disabled={busy} onClick={start}>{busy ? "Connecting…" : "Start screening conversation"}</button> :
      <div style={{display:"flex",gap:8,flexWrap:"wrap"}}><button className="button button-secondary" onClick={()=>conversation.setMuted(!conversation.isMuted)}>{conversation.isMuted ? "Unmute microphone" : "Mute microphone"}</button><button className="button button-danger" disabled={busy} onClick={end}>End conversation</button></div>}
    <p className="form-note">The assistant must ask for your verbal consent to AI screening and transcription before asking job questions. You can decline or stop at any time.</p>
    {conversation.status === "connected" && <form onSubmit={sendText} style={{display:"flex",gap:8,marginTop:12}}><input aria-label="Type a message" value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Or type your answer…" /><button className="button button-primary" disabled={!draft.trim()}>Send</button></form>}
    {messages.length>0 && <div style={{maxHeight:260,overflowY:"auto",marginTop:12}}>{messages.map((item,index)=><p key={index}><strong>{item.role}:</strong> {item.text}</p>)}</div>}
    {error && <p role="alert" style={{color:"crimson"}}>{error}</p>}
  </section>;
}
