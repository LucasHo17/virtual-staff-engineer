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
        <p>Submit a change, inspect cited violations, and approve only validated patches.</p>
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
            {job.error_message && <div className="error">{job.failure_code}: {job.error_message}</div>}
          </>}
        </section>
      </section>

      {notice && <div className="notice">{notice}</div>}

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
