"use client";

import { FormEvent, useEffect, useState } from "react";

const api = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

type Repo = {
  id: string;
  name: string;
  url: string;
  status: string;
  stats: {
    chunks?: number;
    languages?: Record<string, number>;
  };
};

type Citation = {
  path: string;
  start_line: number;
  end_line: number;
  symbol?: string | null;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

export default function Home() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demopassword123");
  const [isRegistering, setIsRegistering] = useState(false);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [url, setUrl] = useState("");
  const [active, setActive] = useState<Repo>();
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    try {
      const savedToken = localStorage.getItem("reposage_token");
      const savedEmail = localStorage.getItem("reposage_email");
      if (savedToken) setToken(savedToken);
      if (savedEmail) setEmail(savedEmail);
    } catch {}
  }, []);

  async function authenticate(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const endpoint = isRegistering ? "register" : "login";
      const r = await fetch(`${api}/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!r.ok) {
        setError(
          isRegistering
            ? "Could not create account. Please use a valid email and a password of at least 10 characters."
            : "Sign in failed. Check your email and password."
        );
        return;
      }
      const data = await r.json();
      setToken(data.access_token);
      try {
        localStorage.setItem("reposage_token", data.access_token);
        localStorage.setItem("reposage_email", email);
      } catch {}
      loadRepos(data.access_token);
    } catch {
      setError("Cannot reach backend server. Please verify the API is running.");
    } finally {
      setLoading(false);
    }
  }

  async function loadRepos(t = token) {
    if (!t) return;
    try {
      const r = await fetch(`${api}/repositories`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (r.status === 401) {
        handleSignOut();
        return;
      }
      if (r.ok) {
        const next: Repo[] = await r.json();
        setRepos(next);
        setActive((current) =>
          current ? next.find((repo) => repo.id === current.id) ?? current : next[0]
        );
      }
    } catch {}
  }

  useEffect(() => {
    if (!token) return;
    loadRepos();
    const timer = window.setInterval(() => loadRepos(), 4000);
    return () => window.clearInterval(timer);
  }, [token]);

  async function addRepo(e: FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setError("");
    try {
      const r = await fetch(`${api}/repositories`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ url: url.trim() }),
      });
      if (r.ok) {
        setUrl("");
        loadRepos();
      } else {
        const errText = await r.text();
        setError(errText || "Failed to register repository.");
      }
    } catch {
      setError("Network error while adding repository.");
    }
  }

  async function ask(e?: FormEvent, promptText?: string) {
    if (e) e.preventDefault();
    const query = promptText || question;
    if (!active || !query.trim()) return;

    const userMsg: ChatMessage = { role: "user", content: query.trim() };
    const assistantMsg: ChatMessage = { role: "assistant", content: "", citations: [] };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setQuestion("");
    setLoading(true);

    try {
      const r = await fetch(`${api}/repositories/${active.id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question: query.trim() }),
      });
      if (!r.ok) {
        if (r.status === 401) {
          handleSignOut();
          setError("Your session expired. Please sign in again.");
          return;
        }
        const errJson = await r.json().catch(() => null);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1].content = `Error (${r.status}): ${errJson?.detail || "Failed to get response from server."}`;
          return next;
        });
        return;
      }
      const reader = r.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const x = await reader.read();
        if (x.done) break;
        buffer += decoder.decode(x.value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const line = event.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const dataStr = line.slice(6);
          if (event.includes("event: citations")) {
            try {
              const parsed = JSON.parse(dataStr);
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1].citations = parsed;
                return next;
              });
            } catch {}
          } else if (event.includes("event: token")) {
            try {
              const tokenVal = JSON.parse(dataStr);
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1].content += tokenVal;
                return next;
              });
            } catch {}
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1].content = "Error receiving chat response from server.";
        return next;
      });
    } finally {
      setLoading(false);
    }
  }

  function handleSignOut() {
    setToken("");
    try {
      localStorage.removeItem("reposage_token");
    } catch {}
    setRepos([]);
    setActive(undefined);
    setMessages([]);
  }

  function formatContent(content: string) {
    if (!content) return <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>Thinking...</span>;
    const parts = content.split(/(```[\s\S]*?```)/g);
    return parts.map((part, index) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        const codeLines = part.slice(3, -3).trim().split("\n");
        const code = codeLines[0].includes(" ") || (codeLines[0].length < 15 && !codeLines[0].includes("=")) ? codeLines.slice(1).join("\n") : codeLines.join("\n");
        return (
          <pre key={index} style={{ background: "#15161a", color: "#e2e8f0", padding: "14px", borderRadius: "12px", overflowX: "auto", fontFamily: "var(--font-mono)", fontSize: "13px", margin: "10px 0", border: "1px solid #2d3139" }}>
            <code>{code || part.slice(3, -3)}</code>
          </pre>
        );
      }
      const lines = part.split("\n");
      return (
        <div key={index} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {lines.map((line, lIdx) => {
            if (line.startsWith("### ")) {
              return <h3 key={lIdx} style={{ fontSize: "16px", fontWeight: 700, margin: "8px 0 4px", color: "var(--text-primary)" }}>{line.replace("### ", "")}</h3>;
            }
            if (line.startsWith("#### ")) {
              return <h4 key={lIdx} style={{ fontSize: "14.5px", fontWeight: 600, margin: "6px 0 2px", color: "var(--text-primary)" }}>{line.replace("#### ", "")}</h4>;
            }
            if (line.startsWith("- ")) {
              return <li key={lIdx} style={{ marginLeft: "18px", fontSize: "14px", color: "var(--text-primary)" }}>{line.replace("- ", "")}</li>;
            }
            if (line.startsWith("| ") && line.endsWith(" |")) {
              return <div key={lIdx} style={{ fontFamily: "var(--font-mono)", fontSize: "12.5px", background: "#f8fafc", padding: "4px 8px", borderRadius: "6px", margin: "2px 0", border: "1px solid var(--border-subtle)" }}>{line}</div>;
            }
            const boldFormatted = line.split(/(\*\*.*?\*\*)/g).map((chunk, cIdx) => {
              if (chunk.startsWith("**") && chunk.endsWith("**")) {
                return <strong key={cIdx} style={{ fontWeight: 700, color: "var(--text-primary)" }}>{chunk.slice(2, -2)}</strong>;
              }
              return chunk;
            });
            return <p key={lIdx} style={{ margin: "2px 0", lineHeight: "1.6", color: "var(--text-primary)" }}>{boldFormatted}</p>;
          })}
        </div>
      );
    });
  }

  if (!token) {
    return (
      <main className="auth-container">
        <div className="auth-shell">
          <section className="auth-hero">
            <div className="auth-brand-badge">
              <span>REPO SAGE</span>
            </div>
            <h1>
              Know your codebase <br />
              <span>like its author.</span>
            </h1>
            <p>
              AI-powered repository intelligence with AST-aware symbol indexing,
              hybrid reciprocal-rank search, and verified citations.
            </p>
          </section>

          <form onSubmit={authenticate} className="auth-card">
            <div className="auth-card-header">
              <span className="eyebrow">WORKSPACE ACCESS</span>
              <h2>{isRegistering ? "Create your account" : "Welcome back"}</h2>
              <p>Sign in to index repositories and run semantic code queries.</p>
            </div>

            <div className="segmented-tab-bar">
              <button
                type="button"
                className={!isRegistering ? "active" : ""}
                onClick={() => {
                  setIsRegistering(false);
                  setError("");
                }}
              >
                Sign In
              </button>
              <button
                type="button"
                className={isRegistering ? "active" : ""}
                onClick={() => {
                  setIsRegistering(true);
                  setError("");
                }}
              >
                Create Account
              </button>
            </div>

            {error && <div className="error-banner">{error}</div>}

            <div className="form-group">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                placeholder="name@company.com"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password (10+ characters)</label>
              <input
                id="password"
                placeholder="Enter secure password"
                type="password"
                minLength={10}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="form-actions">
              <button className="btn-tactile-dark" type="submit" disabled={loading}>
                {loading ? "Processing..." : isRegistering ? "Create Account" : "Continue"}
              </button>

              <button
                type="button"
                className="btn-tactile-light"
                onClick={() => {
                  setEmail("demo@example.com");
                  setPassword("demopassword123");
                  setIsRegistering(false);
                }}
              >
                Fill Demo Credentials
              </button>
            </div>

            <div className="demo-helper">
              <span>Ready credentials: demo@example.com</span>
              <span className="pill-badge ready">Active</span>
            </div>
          </form>
        </div>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <div className="brand-name">RepoSage</div>
            <span className="brand-tag">v1.0</span>
          </div>

          <div className="sidebar-section-header">
            <span>YOUR REPOSITORIES</span>
            <span className="pill-badge">{repos.length}</span>
          </div>

          <div className="sidebar-repos-list">
            {repos.length === 0 ? (
              <p style={{ fontSize: "13px", color: "var(--text-muted)", padding: "8px" }}>
                No repositories registered yet. Add a public GitHub URL below.
              </p>
            ) : (
              repos.map((r) => {
                const isActive = active?.id === r.id;
                return (
                  <button
                    key={r.id}
                    className={`repo-card-btn ${isActive ? "active" : ""}`}
                    onClick={() => {
                      setActive(r);
                      setMessages([]);
                    }}
                  >
                    <div className="repo-card-info">
                      <b>{r.name}</b>
                      <span>{r.stats?.chunks ?? 0} code chunks</span>
                    </div>
                    <span className={`pill-badge ${r.status}`}>{r.status}</span>
                  </button>
                );
              })
            )}
          </div>

          <form onSubmit={addRepo} className="add-repo-card">
            <label htmlFor="repo-url">Ingest Public Repository</label>
            <input
              id="repo-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
            />
            <button className="btn-tactile-dark" type="submit">
              Start Indexing
            </button>
          </form>
        </div>

        <div className="sidebar-footer">
          <div className="user-profile-badge">
            <div className="user-avatar">{email.charAt(0).toUpperCase()}</div>
            <div className="user-details">
              <span>{email}</span>
            </div>
          </div>
          <button className="btn-tactile-light" type="button" onClick={handleSignOut} style={{ padding: "8px 14px", fontSize: "12px" }}>
            Sign Out
          </button>
        </div>
      </aside>

      <section className="workspace-content">
        {active ? (
          <>
            <header className="workspace-header-island">
              <div className="header-meta">
                <div className="header-status-strip">
                  <span className={`pill-badge ${active.status}`}>
                    {active.status === "ready" ? "Live & Ready" : `Status: ${active.status}`}
                  </span>
                  <span className="eyebrow">URL: {active.url}</span>
                </div>
                <h1>{active.name}</h1>
                <p>
                  {active.stats?.chunks ?? 0} indexed AST chunks ·{" "}
                  {Object.keys(active.stats?.languages ?? {}).join(", ") || "Analyzing languages…"}
                </p>
              </div>

              <div className="header-actions">
                <button
                  className="btn-tactile-light"
                  onClick={() => loadRepos()}
                  type="button"
                >
                  Refresh
                </button>
                {messages.length > 0 && (
                  <button
                    className="btn-tactile-light"
                    onClick={() => setMessages([])}
                    type="button"
                  >
                    Clear Chat
                  </button>
                )}
              </div>
            </header>

            <div className="chat-canvas">
              <div className="chat-history">
                {active.status !== "ready" ? (
                  <div className="empty-canvas-state">
                    <h2>Indexing in progress</h2>
                    <p>
                      The repository is currently being cloned and analyzed with AST symbol parsing.
                      Chat questions will automatically unlock when indexing completes.
                    </p>
                    <button className="btn-tactile-light" onClick={() => loadRepos()}>
                      Check Status
                    </button>
                  </div>
                ) : messages.length === 0 ? (
                  <div className="empty-canvas-state">
                    <h2>Ask about {active.name}</h2>
                    <p>
                      Query the codebase using reciprocal-rank fusion across full-text AST symbols
                      and semantic vector embeddings.
                    </p>

                    <div className="sample-prompts">
                      {[
                        "Where is authentication implemented?",
                        "Explain the high-level architecture",
                        "Show all API route declarations",
                        "How is database session managed?",
                      ].map((promptText) => (
                        <button
                          key={promptText}
                          type="button"
                          className="prompt-pill-btn"
                          onClick={() => ask(undefined, promptText)}
                        >
                          {promptText}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", width: "100%" }}>
                    {messages.map((m, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                          width: "100%",
                        }}
                      >
                        {m.role === "user" ? (
                          <div
                            style={{
                              background: "var(--tactile-dark-bg)",
                              color: "#ffffff",
                              padding: "12px 18px",
                              borderRadius: "18px 18px 4px 18px",
                              maxWidth: "75%",
                              fontSize: "14.5px",
                              boxShadow: "var(--tactile-dark-shadow)",
                              wordBreak: "break-word",
                            }}
                          >
                            {m.content}
                          </div>
                        ) : (
                          <div
                            style={{
                              background: "var(--surface-muted)",
                              border: "1px solid #e2e8f0",
                              color: "var(--text-primary)",
                              padding: "18px",
                              borderRadius: "18px 18px 18px 4px",
                              maxWidth: "85%",
                              width: "100%",
                              fontSize: "14.5px",
                              boxShadow: "0 4px 16px rgba(0,0,0,0.03)",
                              display: "flex",
                              flexDirection: "column",
                              gap: "12px",
                            }}
                          >
                            <div className="eyebrow">RepoSage Intelligence</div>
                            {m.citations && m.citations.length > 0 && (
                              <div style={{ display: "flex", flexDirection: "column", gap: "6px", paddingBottom: "10px", borderBottom: "1px solid #e2e8f0" }}>
                                <span className="eyebrow">CITED SOURCES ({m.citations.length}):</span>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                                  {m.citations.map((c, cIdx) => (
                                    <span key={cIdx} className="pill-badge" style={{ fontSize: "11px", background: "#ffffff" }}>
                                      <b>{c.path}</b>:{c.start_line}–{c.end_line} {c.symbol ? `(${c.symbol})` : ""}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div>{formatContent(m.content)}</div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <form onSubmit={ask} className="chat-form-bar">
                <input
                  disabled={active.status !== "ready" || loading}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={
                    active.status === "ready"
                      ? "Ask a technical question about this codebase…"
                      : "Waiting for repository indexing to complete…"
                  }
                />
                <button
                  className="btn-tactile-dark"
                  disabled={active.status !== "ready" || loading || !question.trim()}
                  type="submit"
                >
                  {loading ? "Streaming…" : "Send Question"}
                </button>
              </form>
            </div>
          </>
        ) : (
          <div className="empty-canvas-state" style={{ marginTop: "4rem" }}>
            <h2>Select or Ingest a Repository</h2>
            <p>
              Paste a public GitHub repository link in the sidebar to extract AST symbols and enable
              hybrid AI chat.
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
