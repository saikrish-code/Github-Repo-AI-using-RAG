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

export default function Home() {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demopassword123");
  const [isRegistering, setIsRegistering] = useState(false);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [url, setUrl] = useState("");
  const [active, setActive] = useState<Repo>();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
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
    } catch {
      // ignore network transient errors
    }
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

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!active || !question.trim()) return;
    setAnswer("");
    setCitations([]);
    setLoading(true);
    try {
      const r = await fetch(`${api}/repositories/${active.id}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ question }),
      });
      if (!r.ok) {
        if (r.status === 401) {
          handleSignOut();
          setError("Your session expired. Please sign in again.");
          return;
        }
        const errJson = await r.json().catch(() => null);
        setAnswer(`Error (${r.status}): ${errJson?.detail || "Failed to get response from server."}`);
        return;
      }
      const reader = r.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const x = await reader.read();
        if (x.done) break;
        buffer += decoder.decode(x.value);
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const line = event.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const dataStr = line.slice(6);
          if (event.includes("event: citations")) {
            try {
              setCitations(JSON.parse(dataStr));
            } catch {}
          } else if (event.includes("event: token")) {
            try {
              setAnswer((a) => a + JSON.parse(dataStr));
            } catch {}
          }
        }
      }
    } catch {
      setAnswer("Error receiving chat response from server.");
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
    setAnswer("");
    setCitations([]);
  }

  /* --------------------------------------------------------------------------
     1. AUTHENTICATION VIEW (Clean, icon-free tactile skeuomorphic design)
     -------------------------------------------------------------------------- */
  if (!token) {
    return (
      <main className="auth-container">
        <div className="auth-shell">
          {/* Hero Branding */}
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

          {/* Elevated Auth Card */}
          <form onSubmit={authenticate} className="auth-card">
            <div className="auth-card-header">
              <span className="eyebrow">WORKSPACE ACCESS</span>
              <h2>{isRegistering ? "Create your account" : "Welcome back"}</h2>
              <p>Sign in to index repositories and run semantic code queries.</p>
            </div>

            {/* Segmented Tab Bar */}
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

  /* --------------------------------------------------------------------------
     2. WORKSPACE DASHBOARD VIEW (Clean, icon-free layout with tactile buttons)
     -------------------------------------------------------------------------- */
  return (
    <main className="shell">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-top">
          {/* Brand header */}
          <div className="sidebar-brand">
            <div className="brand-name">RepoSage</div>
            <span className="brand-tag">v1.0</span>
          </div>

          {/* Repositories section */}
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
                    onClick={() => setActive(r)}
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

          {/* Ingest Repository Form */}
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

        {/* Sidebar Footer with user badge and Sign Out */}
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

      {/* Main Workspace Area */}
      <section className="workspace-content">
        {active ? (
          <>
            {/* Header Island */}
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
              </div>
            </header>

            {/* Chat & QA Canvas */}
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
                ) : answer ? (
                  <article className="analysis-bubble">
                    <div className="analysis-bubble-header">
                      <span className="eyebrow">CODE INTELLIGENCE RESPONSE</span>
                      <button
                        className="btn-tactile-light"
                        onClick={() => {
                          setAnswer("");
                          setCitations([]);
                        }}
                        style={{ padding: "6px 12px", fontSize: "12px" }}
                      >
                        Clear
                      </button>
                    </div>

                    {/* Citations badges strip */}
                    {citations.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px", paddingBottom: "10px", borderBottom: "1px solid #e5e9f2" }}>
                        <span className="eyebrow">CITED SOURCES ({citations.length}):</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                          {citations.map((c, i) => (
                            <span key={i} className="pill-badge" style={{ fontSize: "11.5px", background: "#ffffff" }}>
                              <b>{c.path}</b>:{c.start_line}–{c.end_line} {c.symbol ? `(${c.symbol})` : ""}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    <p style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-sans)", lineHeight: "1.7" }}>{answer}</p>
                  </article>
                ) : (
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
                          onClick={() => setQuestion(promptText)}
                        >
                          {promptText}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Chat Input Bar with proper spacing and alignment */}
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
