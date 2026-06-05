import { useState, useEffect, useRef } from "react";
import { api } from "../api";

function renderMarkdown(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/^### (.+)$/gm, "<h3 class='font-semibold text-slate-200 mt-2'>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class='font-semibold text-slate-100 mt-2 text-base'>$1</h2>")
    .replace(/^- (.+)$/gm, "<li class='ml-4 list-disc'>$1</li>")
    .replace(/^(\d+)\. (.+)$/gm, "<li class='ml-4 list-decimal'>$2</li>")
    .replace(/\n/g, "<br/>");
}

function Message({ role, content, isLoading }) {
  const isUser = role === "user";

  if (isLoading) {
    return (
      <div className="flex gap-3 items-start">
        <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center text-xs flex-shrink-0 mt-0.5">AI</div>
        <div className="bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-3">
          <div className="flex gap-1.5 items-center">
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
            <div className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex gap-3 items-start ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs flex-shrink-0 mt-0.5 ${isUser ? "bg-slate-600" : "bg-indigo-600"}`}>
        {isUser ? "U" : "AI"}
      </div>
      <div className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${isUser ? "bg-indigo-600 text-white rounded-tr-sm" : "bg-slate-800 text-slate-200 rounded-tl-sm"}`}>
        {isUser ? (
          <span className="whitespace-pre-wrap">{content}</span>
        ) : (
          <div className="prose-chat" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
        )}
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "How much did I spend last month?",
  "What are my recurring subscriptions?",
  "Am I spending more than usual on dining?",
  "Summarize my finances in plain English",
  "What's my biggest expense category?",
  "Are there any unusual charges?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [image, setImage] = useState(null); // { data: base64, type, name }
  const bottomRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    api.getChatHistory()
      .then((data) => setMessages(data.messages || []))
      .catch(() => {})
      .finally(() => setInitializing(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result.split(",")[1];
      setImage({ data: base64, type: file.type, name: file.name });
    };
    reader.readAsDataURL(file);
  };

  const send = async (text) => {
    const msg = text || input.trim();
    if (!msg && !image) return;

    const userContent = image ? `[Receipt: ${image.name}] ${msg}` : msg;
    setMessages((prev) => [...prev, { role: "user", content: userContent }]);
    setInput("");
    setLoading(true);

    const imgData = image?.data || null;
    const imgType = image?.type || null;
    setImage(null);

    try {
      const res = await api.chat(msg, imgData, imgType);
      setMessages((prev) => [...prev, { role: "assistant", content: res.response }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Sorry, I encountered an error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleClear = async () => {
    if (!confirm("Clear conversation history?")) return;
    await api.clearChatHistory().catch(() => {});
    setMessages([]);
  };

  if (initializing) {
    return <div className="flex items-center justify-center h-full text-slate-400 text-sm">Loading chat…</div>;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-slate-100 font-semibold">AI Assistant</h1>
          <p className="text-slate-500 text-xs">Ask anything about your finances. Upload a receipt photo to record it.</p>
        </div>
        {messages.length > 0 && (
          <button onClick={handleClear} className="text-xs text-slate-500 hover:text-red-400 transition-colors">
            Clear history
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center mt-12">
            <div className="text-4xl mb-4">💬</div>
            <p className="text-slate-300 font-medium">Ask me anything about your finances</p>
            <p className="text-slate-500 text-sm mt-2">I can analyze spending, detect subscriptions, flag anomalies, and more.</p>
            <div className="mt-6 grid grid-cols-2 gap-2 max-w-lg mx-auto">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-xs bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 px-3 py-2.5 rounded-lg transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} />
        ))}

        {loading && <Message role="assistant" isLoading />}
        <div ref={bottomRef} />
      </div>

      {/* Image preview */}
      {image && (
        <div className="px-6 py-2 border-t border-slate-800 flex items-center gap-3 bg-slate-900/50">
          <span className="text-xs text-slate-400">📎 {image.name}</span>
          <button onClick={() => setImage(null)} className="text-xs text-slate-500 hover:text-red-400">✕ Remove</button>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-800 px-6 py-4">
        <div className="flex gap-3 items-end">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleImageSelect}
          />
          <button
            onClick={() => fileRef.current?.click()}
            className="flex-shrink-0 w-9 h-9 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 flex items-center justify-center transition-colors text-sm"
            title="Upload receipt photo"
          >
            📎
          </button>
          <textarea
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your finances… (Enter to send, Shift+Enter for newline)"
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm resize-none"
          />
          <button
            onClick={() => send()}
            disabled={loading || (!input.trim() && !image)}
            className="flex-shrink-0 w-9 h-9 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors"
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}
