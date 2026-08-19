import { useEffect, useState } from 'react';
import type { JobAnalysis, PreparationPackage, ReviewDecision, WorkflowState } from './types';

const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
const workflowSteps = ['queued', 'discovering', 'analyzing', 'ranking', 'preparing', 'waiting_for_review', 'completed'];

function App() {
  const [query, setQuery] = useState('Python Backend Developer');
  const [location, setLocation] = useState('Bangalore');
  const [jobs, setJobs] = useState<JobAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [workflowId, setWorkflowId] = useState('');
  const [status, setStatus] = useState('idle');
  const [strongMatches, setStrongMatches] = useState<JobAnalysis[]>([]);
  const [preparationPackages, setPreparationPackages] = useState<PreparationPackage[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);

  useEffect(() => {
    if (!workflowId || status === 'failed' || status === 'completed') {
      return;
    }

    const pollStatus = async () => {
      const response = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}`);
      if (!response.ok) {
        return;
      }

      const workflow = await response.json();
      const nextStatus = workflow.status || 'queued';
      setWorkflow(workflow);
      setJobs(workflow.ranked_jobs || workflow.analyzed_jobs || []);
      setStrongMatches(workflow.strong_matches || []);
      setPreparationPackages(workflow.preparation_packages || []);
      setStatus(nextStatus);

      if (nextStatus === 'waiting_for_review' || nextStatus === 'completed' || nextStatus === 'failed') {
        setLoading(false);
      }
    };

    const timer = window.setTimeout(pollStatus, 1200);
    return () => window.clearTimeout(timer);
  }, [workflowId, status]);

  const reviewPackage = async (jobId: string, decision: ReviewDecision) => {
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}/preparation-packages/${jobId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      });

      if (!response.ok) {
        throw new Error('Unable to save the review decision.');
      }

      const result = await response.json();
      setPreparationPackages((current) => current.map((item) => (
        item.job_id === jobId ? result.preparation_package : item
      )));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    }
  };

  const handleSearch = async () => {
    const normalizedQuery = query.trim();
    const normalizedLocation = location.trim();

    if (!normalizedQuery || !normalizedLocation) {
      setError('Query and location are required.');
      return;
    }

    setLoading(true);
    setError('');
    setStatus('queued');
    setWorkflow(null);
    setJobs([]);
    setStrongMatches([]);
    setPreparationPackages([]);

    try {
      const workflowResponse = await fetch(`${API_BASE_URL}/api/workflows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_title: normalizedQuery,
          location: normalizedLocation,
          skills: ['Python', 'FastAPI', 'PostgreSQL'],
          experience: '2 years',
          resume_text: 'Python engineer with FastAPI and PostgreSQL experience.',
        }),
      });

      if (!workflowResponse.ok) {
        throw new Error('Unable to start the workflow.');
      }

      const workflowData = await workflowResponse.json();
      setWorkflowId(workflowData.workflow_id || '');
      setStatus(workflowData.status || 'queued');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setJobs([]);
      setStrongMatches([]);
      setLoading(false);
    }
  };

  return (
    <div className="page-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">JP</div>
          <div>
            <p className="eyebrow">Autonomous Agent</p>
            <h1>JobPilot</h1>
          </div>
        </div>

        <nav className="nav">
          <span className="nav-item active">Dashboard</span>
          <span className="nav-item">Workflow</span>
          <span className="nav-item">Applications</span>
        </nav>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="eyebrow">AI job search assistant</p>
            <h2>Autonomous Job Hunt Agent</h2>
          </div>
          <button className="primary-button" type="button" onClick={handleSearch} disabled={loading}>
            {loading ? 'Starting...' : 'Start Job Hunt'}
          </button>
        </header>

        <section className="stats-grid">
          {[
            { label: 'Jobs discovered', value: workflow?.discovered_jobs?.length ?? 0 },
            { label: 'Strong matches', value: strongMatches.length },
            { label: 'Applications ready', value: preparationPackages.length },
          ].map((stat) => (
            <article key={stat.label} className="stat-card">
              <p>{stat.label}</p>
              <strong>{stat.value}</strong>
            </article>
          ))}
        </section>

        <section className="panel workflow-panel">
          <div className="workflow-header">
            <h3>Workflow status</h3>
          </div>
          <div className="workflow-meta">
            <span>Workflow ID: {workflowId || 'Not started'}</span>
            <span>Status: {status}</span>
            <span>Human review: {workflow?.requires_human_review ? 'Required' : 'Not required'}</span>
          </div>
          <div className="progress-steps">
            {['Queued', 'Discovering', 'Analyzing', 'Ranking', 'Preparing', 'Human Review'].map((step, index) => {
              const statusIndex = workflowSteps.indexOf(status);
              const currentStep = ['queued', 'discovering', 'analyzing', 'ranking', 'preparing', 'waiting_for_review'].indexOf(status);
              const active = status !== 'idle' && ((status === 'waiting_for_review' && index === 5) || (status === 'completed' && index >= 5) || (currentStep >= index && status !== 'idle'));
              return (
                <span key={step} className={active ? 'progress-step active' : 'progress-step'}>
                  {step}
                </span>
              );
            })}
          </div>
        </section>

        <section className="content-grid">
          <div className="panel upload-panel">
            <h3>Resume upload</h3>
            <div className="upload-box">
              <input type="file" aria-label="Upload resume" />
              <p>Upload your resume or CV PDF</p>
            </div>
          </div>

          <div className="panel form-panel">
            <h3>Job preferences</h3>
            <form className="preferences-form">
              <label>
                Job titles
                <input type="text" placeholder="Product Manager, Data Analyst" />
              </label>
              <label>
                Location
                <input type="text" placeholder="Remote / New York / Hybrid" />
              </label>
              <label>
                Salary target
                <input type="text" placeholder="$120k - $180k" />
              </label>
              <label>
                Work authorization
                <input type="text" placeholder="US work authorization" />
              </label>
            </form>
          </div>
        </section>

        <section className="panel status-panel">
          <div className="status-header">
            <h3>Agent status</h3>
            <span className={`status-badge ${status}`}>{status}</span>
          </div>
          <p className="status-copy">
            {status === 'idle' ? 'Ready to begin a job discovery and application-preparation workflow.' : `Workflow is ${status}.`}
          </p>
        </section>

        <section className="panel discovery-panel">
          <div className="discovery-header">
            <h3>Discover jobs</h3>
          </div>

          <div className="search-row">
            <label>
              Query
              <input
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Python Backend Developer"
              />
            </label>
            <label>
              Location
              <input
                type="text"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="Bangalore"
              />
            </label>
            <button className="primary-button" type="button" onClick={handleSearch} disabled={loading}>
              {loading ? 'Searching...' : 'Search Jobs'}
            </button>
          </div>

          {error ? <div className="search-error">{error}</div> : null}
        </section>

        <section className="panel jobs-panel">
          <div className="jobs-header">
            <h3>Analyzed jobs</h3>
          </div>

          <div className="jobs-table-wrap">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Job title</th>
                  <th>Company</th>
                  <th>Location</th>
                  <th>Match score</th>
                  <th>Matching skills</th>
                  <th>Missing skills</th>
                  <th>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={7}>No jobs found.</td>
                  </tr>
                ) : (
                  jobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.title}</td>
                      <td>{job.company}</td>
                      <td>{job.location}</td>
                      <td>{job.match_score}</td>
                      <td>{job.matching_skills.join(', ') || '—'}</td>
                      <td>{job.missing_skills.join(', ') || '—'}</td>
                      <td>
                        <span className={`recommendation-badge ${job.recommendation}`}>
                          {job.recommendation}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {strongMatches.length > 0 ? (
          <section className="panel strong-match-panel">
            <div className="jobs-header">
              <h3>Application preparation</h3>
            </div>
            {preparationPackages.length === 0 ? <p>No preparation packages yet.</p> : preparationPackages.map((packageItem) => {
              const match = jobs.find((job) => job.id === packageItem.job_id);
              const reviewStatus = packageItem.review_status || 'pending';
              return (
                <article key={packageItem.job_id} className="strong-match-card">
                  <h4>{match ? `${match.company} — ${match.title}` : packageItem.job_id}</h4>
                  <p><strong>Match score:</strong> {packageItem.match_score}</p>
                  <p><strong>Missing skills:</strong> {packageItem.missing_skills.join(', ') || 'None flagged'}</p>
                  <p><strong>Resume suggestions:</strong></p>
                  <ul>{packageItem.resume_bullet_suggestions.map((bullet, index) => <li key={`${packageItem.job_id}-bullet-${index}`}>{bullet}</li>)}</ul>
                  <p><strong>Cover letter draft:</strong> {packageItem.cover_letter_draft}</p>
                  <p className="human-review-note">
                    Review state: {reviewStatus === 'approved' ? 'Approved - NOT submitted' : reviewStatus === 'rejected' ? 'Rejected - NOT submitted' : 'Pending human review'}
                  </p>
                  {reviewStatus === 'pending' ? (
                    <div className="search-row">
                      <button className="primary-button" type="button" onClick={() => reviewPackage(packageItem.job_id, 'approve')}>
                        Approve
                      </button>
                      <button className="primary-button" type="button" onClick={() => reviewPackage(packageItem.job_id, 'reject')}>
                        Reject
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </section>
        ) : null}
      </main>
    </div>
  );
}

export default App;
