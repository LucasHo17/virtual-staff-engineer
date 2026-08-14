"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Job = {
  workflow_job_id: string;
  status: string;
  checkpoint: string;
  attempt_count: number;
  max_attempts: number;
  failure_code: string | null;
  error_message: string | null;
  queue_wait_ms: number | null;
  automated_processing_ms: number | null;
  human_wait_ms: number | null;
  end_to_end_ms: number | null;
  origin: "manual" | "github";
  github: GitHubContext | null;
};

type GitHubContext = {
  delivery_id: string;
  repository_owner: string;
  repository_name: string;
  pull_request_number: number;
  pull_request_title: string | null;
  pull_request_url: string | null;
  head_sha: string;
  source_path: string;
  created_pull_request_url: string | null;
};

type GitHubJob = {
  workflow_job_id: string;
  source_path: string;
  status: string;
  checkpoint: string;
  failure_code: string | null;
  created_pull_request_url: string | null;
  head_sha: string;
  received_at: string;
};

type GitHubPullRequest = {
  latest_delivery_id: string | null;
  repository_owner: string;
  repository_name: string;
  pull_request_number: number;
  pull_request_title: string | null;
  pull_request_url: string | null;
  head_sha: string;
  status: string;
  changed_file_count: number | null;
  analyzable_file_count: number | null;
  skipped_file_count: number | null;
  received_at: string;
  lifecycle_state: "open" | "closed" | "merged";
  github_updated_at: string;
  jobs: GitHubJob[];
};

type GitHubPullRequestPage = {
  items: GitHubPullRequest[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type Review = {
  source_path: string;
  explanation: string;
  unified_diff: string;
  rules: { rule_key: string; rule_snapshot: string }[];
  checks: { name: string; status: string; details: string }[];
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const terminal = new Set(["completed", "failed", "rejected", "cancelled"]);

export default function Dashboard() {
  const [apiKey, setApiKey] = useState("");
  const [inputType, setInputType] = useState("code_diff");
  const [sourcePath, setSourcePath] = useState("app.py");
  const [content, setContent] = useState("");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [notice, setNotice] = useState("");
  const [pullRequests, setPullRequests] = useState<GitHubPullRequest[]>([]);
  const [githubLoading, setGitHubLoading] = useState(false);
  const [githubView, setGitHubView] = useState<"active" | "archive" | "all">("active");
  const [githubState, setGitHubState] = useState("all");
  const [githubPage, setGitHubPage] = useState(1);
  const [githubTotalPages, setGitHubTotalPages] = useState(0);
  const [githubTotal, setGitHubTotal] = useState(0);
  const streamAbort = useRef<AbortController | null>(null);

  async function request(path: string, init?: RequestInit) {
    const response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
        ...(init?.headers ?? {}),
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed (${response.status})`);
    }
    return response;
  }

  async function refresh(id = jobId) {
    if (!id) return;
    const response = await request(`/jobs/${id}`);
    const nextJob = (await response.json()) as Job;
    setJob(nextJob);
    if (nextJob.status === "awaiting_approval") {
      const reviewResponse = await request(`/jobs/${id}/review`);
      setReview(await reviewResponse.json());
    } else if (nextJob.status !== "approved") {
      setReview(null);
    }
  }

  async function watch(id: string) {
    streamAbort.current?.abort();
    const controller = new AbortController();
    streamAbort.current = controller;
    try {
      const response = await request(`/jobs/${id}/events`, {
        signal: controller.signal,
        headers: { Accept: "text/event-stream" },
      });
      const reader = response.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      while (true) {
        const { done } = await reader.read();
        await refresh(id);
        if (done) break;
      }
    } catch (error) {
      if (!controller.signal.aborted) setNotice(message(error));
    }
  }

  async function loadGitHubPullRequests(
    targetPage = githubPage,
    targetView = githubView,
    targetState = githubState,
  ) {
    if (!apiKey) {
      setNotice("Enter your API key before loading GitHub activity.");
      return;
    }
    setGitHubLoading(true);
    setNotice("");
    try {
      const params = new URLSearchParams({
        view: targetView, state: targetState,
        page: String(targetPage), page_size: "10",
      });
      const response = await request(`/github/pull-requests?${params}`);
      const result = (await response.json()) as GitHubPullRequestPage;
      setPullRequests(result.items);
      setGitHubPage(result.page);
      setGitHubTotalPages(result.total_pages);
      setGitHubTotal(result.total);
    } catch (error) {
      setNotice(message(error));
    } finally {
      setGitHubLoading(false);
    }
  }

  async function selectGitHubJob(id: string) {
    setJobId(id);
    setReview(null);
    setNotice("");
    try {
      await refresh(id);
      void watch(id);
    } catch (error) {
      setNotice(message(error));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setNotice("");
    try {
      const response = await request("/analysis-runs", {
        method: "POST",
        body: JSON.stringify({
          input_type: inputType,
          content,
          source_path: sourcePath || null,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      const result = await response.json();
      setJobId(result.workflow_job_id);
      setNotice("Analysis submitted. Workers will process it asynchronously.");
      await refresh(result.workflow_job_id);
      void watch(result.workflow_job_id);
    } catch (error) {
      setNotice(message(error));
    }
  }

  async function decide(decision: "approved" | "rejected") {
    try {
      await request(`/jobs/${jobId}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setNotice(`Patch ${decision}.`);
      await refresh(jobId);
      await loadGitHubPullRequests(githubPage);
      void watch(jobId);
    } catch (error) {
      setNotice(message(error));
    }
  }

  useEffect(() => () => streamAbort.current?.abort(), []);

  return (
    <main>
      <header>
        <div className="eyebrow">Evidence-backed code governance</div>
        <h1>Virtual Staff Engineer</h1>
        <p>Review manual changes or GitHub pull requests, inspect cited violations, and approve only validated patches.</p>
      </header>

      <section className="grid">
        <form className="panel submit" onSubmit={submit}>
          <div className="panel-title"><span>01</span><h2>Submit review</h2></div>
          <label>API key<input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required /></label>
          <div className="row">
            <label>Input type<select value={inputType} onChange={(e) => setInputType(e.target.value)}><option value="code_diff">Code diff</option><option value="design_document">Design document</option></select></label>
            <label>Source path<input value={sourcePath} onChange={(e) => setSourcePath(e.target.value)} /></label>
          </div>
          <label>Change<textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder={"+ logger.info(request.token)"} required /></label>
          <button type="submit">Analyze change <span>→</span></button>
        </form>

        <section className="panel status">
          <div className="panel-title"><span>02</span><h2>Workflow status</h2></div>
          {!job ? <div className="empty">Submit a review to start a durable workflow.</div> : <>
            <div className="status-line"><span className={`dot ${terminal.has(job.status) ? "done" : "active"}`} /><strong>{job.status.replaceAll("_", " ")}</strong><small>{job.checkpoint.replaceAll("_", " ")}</small></div>
            <div className="metrics">
              <Metric label="Queue" value={job.queue_wait_ms} />
              <Metric label="Automated" value={job.automated_processing_ms} />
              <Metric label="Human wait" value={job.human_wait_ms} />
              <Metric label="End to end" value={job.end_to_end_ms} />
            </div>
            <div className="job-id">Job {job.workflow_job_id}</div>
            {job.github && <div className="github-origin">
              <div className="label">GitHub source</div>
              <a href={job.github.pull_request_url ?? undefined} target="_blank" rel="noreferrer">
                {job.github.repository_owner}/{job.github.repository_name} #{job.github.pull_request_number}
              </a>
              <span>{job.github.source_path} · {job.github.head_sha.slice(0, 8)}</span>
              {job.github.created_pull_request_url && <a className="result-link" href={job.github.created_pull_request_url} target="_blank" rel="noreferrer">Open created remediation PR →</a>}
            </div>}
            {job.error_message && <div className="error">{job.failure_code}: {job.error_message}</div>}
          </>}
        </section>
      </section>

      {notice && <div className="notice">{notice}</div>}

      <section className="github-feed panel">
        <div className="feed-heading">
          <div className="panel-title"><span>GH</span><div><div className="label">Webhook activity</div><h2>GitHub pull requests</h2></div></div>
          <button className="secondary compact" type="button" onClick={() => loadGitHubPullRequests(githubPage)} disabled={githubLoading}>{githubLoading ? "Loading…" : "Refresh"}</button>
        </div>
        <div className="feed-controls">
          <div className="view-tabs" aria-label="Pull request history view">
            {(["active", "archive", "all"] as const).map((view) => <button type="button" className={githubView === view ? "selected" : ""} key={view} onClick={() => { setGitHubView(view); setGitHubState("all"); setGitHubPage(1); void loadGitHubPullRequests(1, view, "all"); }}>{view === "active" ? "Open" : view === "archive" ? "Archive" : "All history"}</button>)}
          </div>
          <label>Lifecycle<select value={githubState} onChange={(event) => { const nextState = event.target.value; setGitHubState(nextState); setGitHubPage(1); void loadGitHubPullRequests(1, githubView, nextState); }}><option value="all">All states</option>{githubView !== "archive" && <option value="open">Open</option>}{githubView !== "active" && <option value="merged">Merged</option>}{githubView !== "active" && <option value="closed">Closed</option>}</select></label>
        </div>
        {pullRequests.length === 0 ? <div className="feed-empty">Enter the same API key above and refresh to see pull requests received by the GitHub App.</div> :
          <div className="pr-list">{pullRequests.map((pullRequest) => <article className="pr-card" key={`${pullRequest.repository_owner}/${pullRequest.repository_name}#${pullRequest.pull_request_number}`}>
            <div className="pr-summary">
              <div>
                <div className="repo-name">{pullRequest.repository_owner}/{pullRequest.repository_name}</div>
                <h3>{pullRequest.pull_request_title ?? `Pull request #${pullRequest.pull_request_number}`}</h3>
                <div className="pr-meta">#{pullRequest.pull_request_number} · head {pullRequest.head_sha.slice(0, 8)} · {new Date(pullRequest.received_at).toLocaleString()}</div>
              </div>
              <div className="pr-links">
                <span className={`badge ${pullRequest.lifecycle_state}`}>{pullRequest.lifecycle_state}</span>
                {pullRequest.pull_request_url && <a href={pullRequest.pull_request_url} target="_blank" rel="noreferrer">Open source PR ↗</a>}
              </div>
            </div>
            <div className="file-counts"><span>{pullRequest.changed_file_count ?? "—"} changed</span><span>{pullRequest.analyzable_file_count ?? "—"} analyzed</span><span>{pullRequest.skipped_file_count ?? "—"} skipped</span></div>
            {pullRequest.jobs.length === 0 ? <div className="job-empty">Ingestion has not created file jobs yet. Refresh shortly.</div> :
              <div className="github-jobs">{pullRequest.jobs.map((item) => <button type="button" className={`github-job ${jobId === item.workflow_job_id ? "selected" : ""}`} key={item.workflow_job_id} onClick={() => selectGitHubJob(item.workflow_job_id)}>
                <span><strong>{item.source_path}</strong><small>{item.head_sha.slice(0, 8)} · {item.checkpoint.replaceAll("_", " ")}</small></span>
                <span className="job-state">{item.status.replaceAll("_", " ")} →</span>
              </button>)}</div>}
          </article>)}</div>}
        <div className="pagination"><span>{githubTotal} pull request{githubTotal === 1 ? "" : "s"}</span><div><button type="button" className="secondary compact" disabled={githubPage <= 1 || githubLoading} onClick={() => loadGitHubPullRequests(githubPage - 1)}>← Previous</button><span>Page {githubPage} of {Math.max(githubTotalPages, 1)}</span><button type="button" className="secondary compact" disabled={githubPage >= githubTotalPages || githubLoading} onClick={() => loadGitHubPullRequests(githubPage + 1)}>Next →</button></div></div>
      </section>

      {review && <section className="review panel">
        <div className="panel-title"><span>03</span><h2>Review validated patch</h2></div>
        <div className="review-grid">
          <div><div className="label">Finding</div><h3>{review.source_path}</h3><p>{review.explanation}</p>{review.rules.map((rule) => <article key={rule.rule_key}><b>{rule.rule_key}</b><p>{rule.rule_snapshot}</p></article>)}</div>
          <div><div className="label">Validation</div>{review.checks.map((check) => <div className="check" key={check.name}><span>✓</span><div><b>{check.name}</b><p>{check.details}</p></div></div>)}</div>
        </div>
        <pre>{review.unified_diff}</pre>
        <div className="actions"><button className="secondary" onClick={() => decide("rejected")}>Reject</button><button onClick={() => decide("approved")}>Approve patch <span>→</span></button></div>
      </section>}
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return <div><small>{label}</small><strong>{value === null ? "—" : `${Math.round(value)} ms`}</strong></div>;
}

function message(error: unknown) {
  return error instanceof Error ? error.message : "Unexpected request failure.";
}
