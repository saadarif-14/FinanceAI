import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../api";

/* ── Markdown renderer ─────────────────────────────────────────────────── */
function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong class='text-white font-semibold'>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code style='background:rgba(139,92,246,0.2);padding:0.1rem 0.35rem;border-radius:5px;font-size:0.8em;color:#c4b5fd'>$1</code>")
    .replace(/^### (.+)$/gm, "<h3 style='font-weight:600;color:rgba(255,255,255,0.9);margin-top:0.75rem;margin-bottom:0.25rem'>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 style='font-weight:700;color:white;margin-top:1rem;margin-bottom:0.25rem;font-size:1rem'>$1</h2>")
    .replace(/^- (.+)$/gm, "<li style='margin-left:1rem;list-style:disc;color:rgba(255,255,255,0.75)'>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li style='margin-left:1rem;list-style:decimal;color:rgba(255,255,255,0.75)'>$2</li>")
    .replace(/\n/g, "<br/>");
}

/* ── Message bubble ────────────────────────────────────────────────────── */
function Message({ role, content, isLoading }) {
  const isUser = role === "user";

  if (isLoading) {
    return (
      <div className="flex gap-3 items-end">
        <div className="w-8 h-8 rounded-2xl flex items-center justify-center text-[10px] font-bold flex-shrink-0"
          style={{ background: "linear-gradient(135deg,#7c3aed,#4f46e5)", boxShadow: "0 0 16px rgba(124,58,237,0.4)" }}>
          AI
        </div>
        <div className="px-5 py-4 rounded-2xl rounded-bl-sm"
          style={{ background: "rgba(255,255,255,0.05)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.08)" }}>
          <div className="flex gap-1.5 items-center">
            {[0, 150, 300].map((d) => (
              <div key={d} className="w-1.5 h-1.5 rounded-full animate-bounce"
                style={{ background: "rgba(139,92,246,0.8)", animationDelay: `${d}ms` }} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 items-end ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className="w-8 h-8 rounded-2xl flex items-center justify-center text-[10px] font-bold flex-shrink-0 flex-shrink-0"
        style={isUser
          ? { background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.5)" }
          : { background: "linear-gradient(135deg,#7c3aed,#4f46e5)", boxShadow: "0 0 16px rgba(124,58,237,0.35)" }
        }
      >
        {isUser ? "U" : "AI"}
      </div>

      {/* Bubble */}
      <div
        className="max-w-[78%] sm:max-w-[68%] rounded-2xl px-5 py-3.5 text-sm leading-relaxed break-words"
        style={isUser
          ? { background: "linear-gradient(135deg,rgba(124,58,237,0.6),rgba(79,70,229,0.5))", border: "1px solid rgba(139,92,246,0.25)", borderBottomRightRadius: "4px", backdropFilter: "blur(20px)", color: "rgba(255,255,255,0.92)" }
          : { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", borderBottomLeftRadius: "4px", backdropFilter: "blur(20px)", color: "rgba(255,255,255,0.8)" }
        }
      >
        {isUser
          ? <span className="whitespace-pre-wrap">{content}</span>
          : <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
        }
      </div>
    </div>
  );
}

/* ── Suggestion chips ──────────────────────────────────────────────────── */
const SUGGESTIONS = [
  { text: "How much did I spend last month?",      icon: "📊" },
  { text: "What are my recurring subscriptions?",   icon: "🔄" },
  { text: "Am I spending more than usual on dining?", icon: "🍽️" },
  { text: "Summarize my finances in plain English", icon: "📝" },
  { text: "What's my biggest expense category?",   icon: "💸" },
  { text: "Are there any unusual charges?",         icon: "🚨" },
];

/* ── Date formatter ────────────────────────────────────────────────────── */
function fmtDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now - d) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return d.toLocaleDateString("en-US", { weekday: "short" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/* ── Conversation list ─────────────────────────────────────────────────── */
function ConvList({ conversations, activeId, onSelect, onNew, onDelete, loading }) {
  const [hoverId, setHoverId] = useState(null);

  return (
    <div className="w-full h-full flex flex-col" style={{ background: "rgba(7,7,26,0.6)", backdropFilter: "blur(24px)", borderRight: "1px solid rgba(255,255,255,0.05)" }}>
      {/* Header */}
      <div className="px-4 py-4 flex items-center justify-between flex-shrink-0" style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
        <span className="text-white font-bold text-sm tracking-tight">Chats</span>
        <button
          onClick={onNew}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-white text-xs font-semibold transition-all hover:scale-105"
          style={{ background: "linear-gradient(135deg,#7c3aed,#4f46e5)", boxShadow: "0 0 16px rgba(124,58,237,0.35)" }}
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New chat
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto py-2 space-y-0.5 px-2">
        {loading && <p className="text-white/20 text-xs text-center py-8">Loading…</p>}
        {!loading && conversations.length === 0 && (
          <div className="text-center py-12 px-4">
            <div className="w-12 h-12 rounded-2xl mx-auto mb-3 flex items-center justify-center"
              style={{ background: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.15)" }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-5 h-5 text-violet-500">
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
              </svg>
            </div>
            <p className="text-white/20 text-xs">No chats yet</p>
          </div>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            className="group relative flex items-center rounded-xl cursor-pointer transition-all"
            style={c.id === activeId
              ? { background: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.2)" }
              : { border: "1px solid transparent" }
            }
            onMouseEnter={() => setHoverId(c.id)}
            onMouseLeave={() => setHoverId(null)}
            onClick={() => onSelect(c.id)}
          >
            <div className="flex-1 px-3 py-2.5 min-w-0">
              <p className={`text-xs font-medium truncate ${c.id === activeId ? "text-violet-300" : "text-white/60 group-hover:text-white/80"}`}>
                {c.title}
              </p>
              <p className="text-[10px] mt-0.5" style={{ color: "rgba(255,255,255,0.2)" }}>{fmtDate(c.updated_at)}</p>
            </div>
            {hoverId === c.id && (
              <button
                className="flex-shrink-0 w-7 h-7 mr-1 flex items-center justify-center rounded-lg transition-colors"
                style={{ color: "rgba(255,255,255,0.2)" }}
                onMouseEnter={(e) => e.currentTarget.style.color = "#f87171"}
                onMouseLeave={(e) => e.currentTarget.style.color = "rgba(255,255,255,0.2)"}
                onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Input bar ─────────────────────────────────────────────────────────── */
function ChatInput({ onSend, loading, image, onImageSelect, onImageRemove }) {
  const [input, setInput] = useState("");
  const fileRef = useRef(null);
  const textareaRef = useRef(null);

  const send = () => {
    const msg = input.trim();
    if (!msg && !image) return;
    onSend(msg);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const handleInput = (e) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  };

  return (
    <div className="flex-shrink-0 px-4 py-4" style={{ borderTop: "1px solid rgba(255,255,255,0.05)", background: "rgba(7,7,26,0.5)", backdropFilter: "blur(20px)" }}>
      {image && (
        <div className="flex items-center gap-2 mb-2 px-1">
          <span className="text-xs text-violet-300/70 truncate flex-1">📎 {image.name}</span>
          <button onClick={onImageRemove} className="text-xs text-white/20 hover:text-rose-400 transition-colors">Remove</button>
        </div>
      )}
      <div className="flex gap-2 items-end">
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={onImageSelect} />
        <button
          onClick={() => fileRef.current?.click()}
          className="flex-shrink-0 w-10 h-10 rounded-xl transition-all hover:scale-105"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.3)" }}
          title="Upload receipt"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-5 h-5 mx-auto">
            <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
          </svg>
        </button>
        <textarea
          ref={textareaRef}
          rows={1}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your finances…"
          className="flex-1 text-sm resize-none overflow-hidden transition-all outline-none placeholder-white/20 text-white/90"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: "14px",
            padding: "10px 16px",
            minHeight: "40px",
            maxHeight: "120px",
            backdropFilter: "blur(20px)",
          }}
          onFocus={(e) => e.target.style.borderColor = "rgba(124,58,237,0.4)"}
          onBlur={(e) => e.target.style.borderColor = "rgba(255,255,255,0.08)"}
        />
        <button
          onClick={send}
          disabled={loading || (!input.trim() && !image)}
          className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all hover:scale-105 disabled:opacity-30 disabled:scale-100"
          style={{ background: "linear-gradient(135deg,#7c3aed,#4f46e5)", boxShadow: "0 0 20px rgba(124,58,237,0.4)" }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} className="w-4 h-4 text-white">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
          </svg>
        </button>
      </div>
    </div>
  );
}

/* ── Main ──────────────────────────────────────────────────────────────── */
export default function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [sending, setSending] = useState(false);
  const [image, setImage] = useState(null);
  const [mobileView, setMobileView] = useState("list");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const bottomRef = useRef(null);

  const loadConversations = useCallback(async () => {
    setLoadingConvs(true);
    try { const d = await api.listConversations(); setConversations(d); return d; }
    catch { return []; }
    finally { setLoadingConvs(false); }
  }, []);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  const openConversation = useCallback(async (id) => {
    setActiveId(id); setMobileView("chat"); setLoadingMsgs(true);
    try { const d = await api.getConversation(id); setMessages(d.messages || []); }
    catch { setMessages([]); }
    finally { setLoadingMsgs(false); }
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, sending]);

  const handleNew = () => { setActiveId(null); setMessages([]); setMobileView("chat"); };

  const handleDelete = async (id) => {
    await api.deleteConversation(id).catch(() => {});
    setConversations((p) => p.filter((c) => c.id !== id));
    if (activeId === id) { setActiveId(null); setMessages([]); setMobileView("list"); }
  };

  const handleSend = async (text) => {
    if (!text && !image) return;
    const imgData = image?.data || null;
    const imgType = image?.type || null;
    setImage(null);

    // Add user message + empty assistant placeholder immediately
    setMessages((p) => [
      ...p,
      { role: "user", content: image ? `[Receipt: ${image.name}] ${text}` : text },
      { role: "assistant", content: "", streaming: true },
    ]);
    setSending(true);

    try {
      await api.chatStream(
        text, activeId, imgData, imgType,
        // onChunk — append each token to the last message
        (chunk) => {
          setMessages((p) => {
            const next = [...p];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + chunk };
            return next;
          });
        },
        // onDone — finalise and refresh conversation list
        async (meta) => {
          setActiveId(meta.conversation_id);
          setMessages((p) => {
            const next = [...p];
            next[next.length - 1] = { ...next[next.length - 1], streaming: false };
            return next;
          });
          api.invalidate("conversations");
          setConversations(await api.listConversations());
          setSending(false);
        },
      );
    } catch (err) {
      setMessages((p) => {
        const next = [...p];
        next[next.length - 1] = { role: "assistant", content: `Sorry, I hit an error: ${err.message}`, streaming: false };
        return next;
      });
      setSending(false);
    }
  };

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage({ data: reader.result.split(",")[1], type: file.type, name: file.name });
    reader.readAsDataURL(file);
  };

  const activeTitle = activeId ? conversations.find((c) => c.id === activeId)?.title || "Chat" : "New Chat";

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden" style={{ background: "transparent" }}>

      {/* Left panel */}
      <div className={`flex-shrink-0 h-full flex-col transition-all duration-300 overflow-hidden
        ${mobileView === "list" ? "flex w-full" : "hidden"}
        md:flex ${sidebarOpen ? "md:w-60" : "md:w-0"}`}>
        <ConvList conversations={conversations} activeId={activeId} onSelect={openConversation}
          onNew={handleNew} onDelete={handleDelete} loading={loadingConvs} />
      </div>

      {/* Right panel */}
      <div className={`flex-col overflow-hidden flex-1
        ${mobileView === "chat" ? "flex w-full" : "hidden"} md:flex`}>

        {/* Header */}
        <div className="flex-shrink-0 flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.05)", background: "rgba(7,7,26,0.5)", backdropFilter: "blur(20px)" }}>
          {/* Desktop hamburger */}
          <button
            className="hidden md:flex w-9 h-9 items-center justify-center rounded-xl transition-all hover:bg-white/5 flex-shrink-0"
            style={{ color: "rgba(255,255,255,0.3)" }}
            onClick={() => setSidebarOpen((o) => !o)}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
            </svg>
          </button>
          {/* Mobile back */}
          <button
            className="md:hidden w-9 h-9 flex items-center justify-center rounded-xl transition-all hover:bg-white/5 flex-shrink-0"
            style={{ color: "rgba(255,255,255,0.4)" }}
            onClick={() => setMobileView("list")}
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-white/80 truncate">{activeTitle}</h1>
            <p className="text-[11px]" style={{ color: "rgba(255,255,255,0.2)" }}>Ask anything about your finances</p>
          </div>

        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-5">
          {loadingMsgs && (
            <div className="flex justify-center pt-12">
              <div className="w-6 h-6 border-2 border-violet-500/50 border-t-violet-400 rounded-full animate-spin" />
            </div>
          )}

          {!loadingMsgs && messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              {/* Glowing icon */}
              <div className="relative mb-6">
                <div className="absolute inset-0 rounded-3xl blur-2xl scale-150" style={{ background: "rgba(124,58,237,0.25)" }} />
                <div className="relative w-16 h-16 rounded-3xl flex items-center justify-center"
                  style={{ background: "linear-gradient(135deg,rgba(124,58,237,0.3),rgba(79,70,229,0.2))", border: "1px solid rgba(124,58,237,0.25)", backdropFilter: "blur(20px)" }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-8 h-8 text-violet-400">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                </div>
              </div>
              <h2 className="text-xl font-bold text-white mb-2">Ask me anything</h2>
              <p className="text-sm max-w-xs mb-8" style={{ color: "rgba(255,255,255,0.3)" }}>
                I can analyze spending, detect subscriptions, flag unusual charges, and more.
              </p>
              {/* Suggestion chips */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.text}
                    onClick={() => handleSend(s.text)}
                    className="flex items-center gap-3 text-left px-4 py-3 rounded-2xl transition-all hover:scale-[1.02]"
                    style={{
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.07)",
                      backdropFilter: "blur(20px)",
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.borderColor = "rgba(124,58,237,0.3)"}
                    onMouseLeave={(e) => e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)"}
                  >
                    <span className="text-base flex-shrink-0">{s.icon}</span>
                    <span className="text-xs font-medium" style={{ color: "rgba(255,255,255,0.55)" }}>{s.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {!loadingMsgs && messages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m, i) => (
              <Message
                key={i}
                role={m.role}
                content={m.content}
                isLoading={m.streaming && m.content === ""}
              />
            ))}

          {/* Fallback spinner only if somehow sending with no placeholder yet */}
          {sending && messages.length === 0 && <Message role="assistant" isLoading />}
          <div ref={bottomRef} />
        </div>

        <ChatInput onSend={handleSend} loading={sending} image={image}
          onImageSelect={handleImageSelect} onImageRemove={() => setImage(null)} />
      </div>
    </div>
  );
}
