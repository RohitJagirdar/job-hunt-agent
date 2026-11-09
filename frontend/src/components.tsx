import { useState } from "react";
import { ArrowUpRight, ChevronDown, Clipboard, Clock3, ExternalLink, FilePlus2, Globe2, LoaderCircle, Plus, Sparkles, Target, Upload, X } from "lucide-react";
import type { AgentRun, AgentSettings, AgentSource, Job, JobInput, Region, SourceType, Status } from "./types";
import { STATUSES, initials, formatPostedDate } from "./helpers";

export function StatCard({ label, value, note, icon, tone }: { label: string; value: string | number; note: string; icon: React.ReactNode; tone: string }) {
  return <div className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon ${tone}`}>{icon}</span></div><div className="stat-value">{value}</div><div className="stat-note">{note}</div></div>;
}

export function CompanyMark({ company }: { company: string }) {
  return <div className={`company-mark mark-${company.toLowerCase().replace(/[^a-z]/g, "").slice(0, 7)}`}>{initials(company)}</div>;
}

export function MatchScore({ score }: { score: number }) {
  return <span className={`match-score ${score >= 85 ? "high" : score >= 70 ? "medium" : "low"}`}><Sparkles size={12} /> {score}%</span>;
}

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`status-badge ${status.toLowerCase()}`}><span className={`status-dot ${status.toLowerCase()}`} />{status}</span>;
}

export function JobCard({ job, onOpen }: { job: Job; onOpen: () => void }) {
  return (
    <button className="job-card" onClick={onOpen}>
      <div className="job-card-top"><CompanyMark company={job.company} /><span className={`match-chip ${job.match_score >= 85 ? "good" : ""}`}><Sparkles size={11} />{job.match_score}%</span></div>
      <div className="job-card-title">{job.role_title}</div>
      <div className="job-card-company">{job.company}{job.source_type === "sample" && " · Sample"}</div>
      <div className="job-card-meta"><span><Globe2 size={12} />{job.location || job.region}</span><span>{job.region}</span></div>
      <div className="job-card-footer"><span>Posted {formatPostedDate(job.posted_at)}</span><ArrowUpRight size={14} /></div>
    </button>
  );
}

export function JobModal({ job, hasProfile, busy, onClose, onCopy, onSync, onStatus, onDelete }: {
  job: Job; hasProfile: boolean; busy: boolean; onClose: () => void; onCopy: () => void; onSync: () => void;
  onStatus: (status: Status) => void; onDelete: () => void;
}) {
  const outreachPitch = job.resume_outreach_pitch || job.outreach_pitch;
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <div className="modal-topline"><span>OPPORTUNITY DETAILS</span><button className="close-button" onClick={onClose} aria-label="Close details"><X size={18} /></button></div>
        <div className="detail-company"><CompanyMark company={job.company} /><div><span>{job.company}</span><small>{job.location || job.region}</small></div><a href={job.source_url || undefined} target="_blank" rel="noreferrer" aria-label="Open job source"><ExternalLink size={15} /></a></div>
        <h2 id="detail-title">{job.role_title}</h2>
        <div className="detail-tags"><StatusBadge status={job.status} /><MatchScore score={job.match_score} /><span className="region-tag"><Globe2 size={13} />{job.region}</span><span className="region-tag">Posted {formatPostedDate(job.posted_at)}</span></div>
        <div className="detail-divider" />
        <div className="insight-heading"><div className="insight-icon"><Sparkles size={15} /></div><div><strong>{hasProfile && job.match_summary ? "Your resume match" : "Your match insights"}</strong><span>{hasProfile && job.match_summary ? "AI estimate based on your resume and this role" : "Add a resume profile for personalized matching"}</span></div></div>
        {job.match_summary && <div className="recommendation-summary"><p>{job.match_summary}</p>{job.matched_skills.length > 0 && <div className="recommendation-list"><label>SKILLS IN COMMON</label><div className="skill-chips">{job.matched_skills.map((skill) => <span key={skill}>{skill}</span>)}</div></div>}{job.skill_gaps.length > 0 && <div className="recommendation-list"><label>AREAS TO CHECK</label><div className="skill-chips gap-chips">{job.skill_gaps.map((skill) => <span key={skill}>{skill}</span>)}</div></div>}</div>}
        <div className="detail-section"><label>HIRING MANAGER HINTS</label><p>{job.hiring_manager_hints || "No hiring manager hints yet. Add more role context or try the AI parser."}</p></div>
        <div className="pitch-box"><div className="pitch-heading"><span>{job.resume_outreach_pitch ? "RESUME-TAILORED OUTREACH" : "YOUR OUTREACH PITCH"}</span><button onClick={onCopy} disabled={!outreachPitch}><Clipboard size={13} /> Copy</button></div><p>{outreachPitch || "No outreach pitch yet. Use AI parsing to draft a tailored introduction."}</p></div>
        {job.description && <div className="detail-section description-section"><label>ROLE DESCRIPTION</label><p>{job.description}</p></div>}
        <div className="detail-actions">
          <label className="status-control">Move to <select value={job.status} onChange={(event) => onStatus(event.target.value as Status)} disabled={busy}>{STATUSES.map((status) => <option key={status}>{status}</option>)}</select><ChevronDown size={13} /></label>
          <button className="button-secondary sync-button" onClick={onSync} disabled={busy}><ArrowUpRight size={14} /> Sync to Notion</button>
          <button className="delete-button" onClick={onDelete} disabled={busy}>Delete</button>
        </div>
      </section>
    </div>
  );
}

export function ResumeModal({ file, setFile, consent, setConsent, busy, onClose, onSubmit }: {
  file: File | null;
  setFile: React.Dispatch<React.SetStateAction<File | null>>;
  consent: boolean;
  setConsent: React.Dispatch<React.SetStateAction<boolean>>;
  busy: boolean;
  onClose: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="resume-modal" role="dialog" aria-modal="true" aria-labelledby="resume-title">
        <div className="modal-topline"><span>PERSONALIZED JOB MATCHING</span><button className="close-button" onClick={onClose} aria-label="Close resume upload" disabled={busy}><X size={18} /></button></div>
        <div className="resume-modal-icon"><Target size={19} /></div>
        <h2 id="resume-title">Let’s find your <em>right fit.</em></h2>
        <p className="add-subtitle">We’ll compare your experience with each role and explain where you match—and what to check.</p>
        <form onSubmit={onSubmit}>
          <label className="form-label resume-file-label">RESUME FILE
            <span className="resume-file-picker"><Upload size={16} /><span>{file ? file.name : "Choose a PDF, DOCX, TXT, or Markdown file"}</span><input type="file" accept=".pdf,.docx,.txt,.md" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></span>
          </label>
          <div className="privacy-note"><strong>Your privacy, plainly:</strong> The original file is processed for this request only and is not retained by the app. After consent, contact-redacted text is sent to Anthropic's Claude (or Google Gemini as a fallback) to create your profile. When the job search agent runs, target-role names and skills from that profile are sent as search terms to Brave Search; your resume text is not sent to Brave. The structured profile stays in your local SQLite database and can be removed at any time.</div>
          <label className="consent-row"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>I agree to send the extracted, contact-redacted resume text to Anthropic Claude (or Google Gemini as a fallback) and to use profile role names and skills as Brave Search queries when I run the job search agent.</span></label>
          <div className="form-actions"><button type="button" className="button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button-primary" disabled={busy || !file || !consent}>{busy ? <><LoaderCircle className="spin" size={14} /> Analyzing resume…</> : <><Sparkles size={14} /> Analyze & match jobs</>}</button></div>
        </form>
      </section>
    </div>
  );
}

export function AgentConsole({
  settings,
  sources,
  runs,
  busy,
  profileReady,
  scheduleChoice,
  setScheduleChoice,
  customHours,
  setCustomHours,
  minimumScore,
  setMinimumScore,
  sourceName,
  setSourceName,
  sourceType,
  setSourceType,
  sourceUrl,
  setSourceUrl,
  sourceRegion,
  setSourceRegion,
  onSaveSchedule,
  onAddSource,
  onDeleteSource,
  onRun,
  onAddLinkedIn,
}: {
  settings: AgentSettings | null;
  sources: AgentSource[];
  runs: AgentRun[];
  busy: boolean;
  profileReady: boolean;
  scheduleChoice: string;
  setScheduleChoice: React.Dispatch<React.SetStateAction<string>>;
  customHours: string;
  setCustomHours: React.Dispatch<React.SetStateAction<string>>;
  minimumScore: number;
  setMinimumScore: React.Dispatch<React.SetStateAction<number>>;
  sourceName: string;
  setSourceName: React.Dispatch<React.SetStateAction<string>>;
  sourceType: SourceType;
  setSourceType: React.Dispatch<React.SetStateAction<SourceType>>;
  sourceUrl: string;
  setSourceUrl: React.Dispatch<React.SetStateAction<string>>;
  sourceRegion: Region;
  setSourceRegion: React.Dispatch<React.SetStateAction<Region>>;
  onSaveSchedule: () => void;
  onAddSource: (event: React.FormEvent<HTMLFormElement>) => void;
  onDeleteSource: (id: number) => void;
  onRun: () => void;
  onAddLinkedIn: () => void;
}) {
  const ready = Boolean(settings?.llm_configured && settings.notion_configured && settings.brave_configured && profileReady);
  const latestRun = runs[0];
  const sourcePlaceholder = {
    greenhouse: "https://boards.greenhouse.io/company",
    lever: "https://jobs.lever.co/company",
    rss: "https://company.example/jobs/feed.xml",
  }[sourceType];
  return (
    <section className="agent-console">
      <div className="agent-console-heading">
        <div>
          <div className="agent-console-eyebrow"><span className="agent-live-dot" /> YOUR JOB SEARCH AGENT</div>
          <h2>It looks while you focus.</h2>
          <p>Searches the open web across India, Japan, and Singapore, scores new roles against your resume, and files qualifying matches to Notion. Optional career boards add more coverage. It never applies or messages anyone.</p>
        </div>
        <button className="button-primary agent-run-button" onClick={onRun} disabled={busy || !ready}>
          {busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
          {busy ? "Agent working…" : "Run agent now"}
        </button>
      </div>

      <div className="agent-readiness">
        <ReadinessBadge label="Resume profile" ready={profileReady} />
        <ReadinessBadge label={settings?.llm_providers?.length ? `AI (${settings.llm_providers.join(" → ")})` : "AI"} ready={Boolean(settings?.llm_configured)} />
        <ReadinessBadge label="Notion" ready={Boolean(settings?.notion_configured)} />
        <ReadinessBadge label="Brave Search" ready={Boolean(settings?.brave_configured)} />
        <ReadinessBadge label={`${sources.length} optional source${sources.length === 1 ? "" : "s"}`} ready />
      </div>
      {!ready && <div className="agent-prerequisite">To run the agent, add a resume profile and configure ANTHROPIC_API_KEY (or GEMINI_API_KEY), BRAVE_SEARCH_API_KEY, and Notion integration credentials. Career sources below are optional.</div>}

      <div className="agent-settings-grid">
        <div className="agent-subpanel">
          <div className="agent-subheading"><Clock3 size={14} /><strong>Run schedule</strong></div>
          <div className="agent-control-row">
            <label className="agent-field">CHECK FREQUENCY
              <select value={scheduleChoice} onChange={(event) => setScheduleChoice(event.target.value)}>
                <option value="1440">Once daily</option>
                <option value="360">Every 6 hours</option>
                <option value="0">Manual only</option>
                <option value="custom">Custom interval…</option>
              </select>
            </label>
            {scheduleChoice === "custom" && <label className="agent-field custom-hours">HOURS
              <input type="number" min="1" max="8760" step="1" value={customHours} onChange={(event) => setCustomHours(event.target.value)} />
            </label>}
            <label className="agent-field threshold-field">SAVE MATCHES AT
              <span className="threshold-input"><input type="number" min="0" max="100" value={minimumScore} onChange={(event) => setMinimumScore(Number(event.target.value))} /><span>%</span></span>
            </label>
            <button className="button-secondary agent-save-button" onClick={onSaveSchedule} disabled={busy}>Save settings</button>
          </div>
          <p className="agent-setting-note">{settings?.interval_minutes === 0 ? "Scheduled checks are off. Use Run agent now whenever you like." : settings?.next_run_at ? `Next check ${new Date(settings.next_run_at).toLocaleString()}.` : "The schedule starts after settings are saved."}</p>
        </div>

        <div className="agent-subpanel agent-run-summary">
          <div className="agent-subheading"><Target size={14} /><strong>Latest run</strong><span className={`run-status ${settings?.last_status ?? "idle"}`}>{settings?.last_status ?? "idle"}</span></div>
          <p>{settings?.last_message ?? "Configure your sources to begin."}</p>
          {latestRun && <small>{new Date(latestRun.started_at).toLocaleString()} · {latestRun.found_count} new · {latestRun.qualified_count} qualified · {latestRun.synced_count} in Notion</small>}
          {latestRun?.errors.map((message, index) => <div className="agent-run-error" key={`${index}-${message}`}>{message}</div>)}
        </div>
      </div>

      <div className="agent-source-section">
        <div className="agent-sources-title"><div><div className="agent-subheading"><Globe2 size={14} /><strong>Optional career sources</strong></div><p>Add official Greenhouse/Lever boards or RSS/Atom feeds for extra coverage. Web search is handled by Brave; LinkedIn pages are never scraped.</p></div><button type="button" className="button-secondary linkedin-add" onClick={onAddLinkedIn}><FilePlus2 size={14} /> Add a LinkedIn role</button></div>
        {sources.length > 0 && <div className="source-list">{sources.map((source) => <div className="source-row" key={source.id}><span className={`source-kind ${source.source_type}`}>{source.source_type.toUpperCase()}</span><span className="source-name">{source.name}</span><span className="source-region">{source.region}</span><a href={source.url} target="_blank" rel="noreferrer" title={source.url}><ExternalLink size={12} /></a><button aria-label={`Remove ${source.name}`} onClick={() => onDeleteSource(source.id)} disabled={busy}><X size={14} /></button></div>)}</div>}
        <form className="source-form" onSubmit={onAddSource}>
          <label className="agent-field">SOURCE TYPE<select value={sourceType} onChange={(event) => setSourceType(event.target.value as SourceType)}><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option><option value="rss">RSS / Atom feed</option></select></label>
          <label className="agent-field">COMPANY / FEED NAME<input required maxLength={200} value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="e.g. Example company" /></label>
          <label className="agent-field source-url-field">BOARD OR FEED URL<input required type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder={sourcePlaceholder} /></label>
          <label className="agent-field">REGION<select value={sourceRegion} onChange={(event) => setSourceRegion(event.target.value as Region)}><option>India</option><option>Japan</option><option>Singapore</option></select></label>
          <button className="button-secondary source-add-button" type="submit" disabled={busy}><Plus size={14} /> Add source</button>
        </form>
      </div>
    </section>
  );
}

export function ReadinessBadge({ label, ready }: { label: string; ready: boolean }) {
  return <span className={`readiness-badge ${ready ? "ready" : ""}`}><span />{label}</span>;
}

export function LinkedInModal({ busy, onClose, onSubmit }: {
  busy: boolean;
  onClose: () => void;
  onSubmit: (
    event: React.FormEvent<HTMLFormElement>,
    listing: { role_title: string; company: string; region: Region; location: string; description: string; source_url: string; posted_at: string | null },
  ) => void;
}) {
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [region, setRegion] = useState<Region>("India");
  const [location, setLocation] = useState("");
  const [postedAt, setPostedAt] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section className="linkedin-modal" role="dialog" aria-modal="true" aria-labelledby="linkedin-title">
        <div className="modal-topline"><span>MANUAL LINKEDIN ROLE</span><button className="close-button" onClick={onClose} aria-label="Close LinkedIn import" disabled={busy}><X size={18} /></button></div>
        <h2 id="linkedin-title">Bring a role <em>to your agent.</em></h2>
        <p className="add-subtitle">LinkedIn blocks automated collection, so paste its job link and details here. Your agent will score it against your resume and save qualifying roles to Notion.</p>
        <form className="linkedin-form" onSubmit={(event) => onSubmit(event, { role_title: role, company, region, location, description, source_url: url, posted_at: postedAt || null })}>
          <label className="form-label">LINKEDIN JOB URL<input required type="url" className="form-input" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://www.linkedin.com/jobs/view/…" /></label>
          <div className="form-grid">
            <label className="form-label">ROLE TITLE<input required className="form-input" value={role} onChange={(event) => setRole(event.target.value)} /></label>
            <label className="form-label">COMPANY<input required className="form-input" value={company} onChange={(event) => setCompany(event.target.value)} /></label>
            <label className="form-label">REGION<select className="form-input" value={region} onChange={(event) => setRegion(event.target.value as Region)}><option>India</option><option>Japan</option><option>Singapore</option></select></label>
            <label className="form-label">LOCATION<input className="form-input" value={location} onChange={(event) => setLocation(event.target.value)} placeholder="City, country" /></label>
            <label className="form-label">POSTED DATE<input type="date" className="form-input" value={postedAt} onChange={(event) => setPostedAt(event.target.value)} /></label>
          </div>
          <label className="form-label">JOB DESCRIPTION<textarea required minLength={40} maxLength={20000} className="form-input linkedin-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Paste the job description text here…" /></label>
          <div className="form-actions"><button type="button" className="button-secondary" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" className="button-primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={14} /> : <Sparkles size={14} />} Score & save if it matches</button></div>
        </form>
      </section>
    </div>
  );
}

export function AddModal({ form, setForm, busy, onClose, onSubmit, onParse }: {
  form: JobInput; setForm: React.Dispatch<React.SetStateAction<JobInput>>; busy: boolean; onClose: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void; onParse: () => void;
}) {
  function field<K extends keyof JobInput>(key: K, value: JobInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  return (
    <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="add-modal" role="dialog" aria-modal="true" aria-labelledby="add-title">
        <div className="modal-topline"><span>NEW OPPORTUNITY</span><button className="close-button" onClick={onClose} aria-label="Close form"><X size={18} /></button></div>
        <h2 id="add-title">Make room for <em>what’s next.</em></h2>
        <p className="add-subtitle">Add the basics, or paste a description and let AI help with the details.</p>
        <form onSubmit={onSubmit}>
          <label className="form-label">JOB DESCRIPTION <span>OPTIONAL · USE AI TO FILL THE FORM</span></label>
          <textarea className="form-input description-input" value={form.description} onChange={(event) => field("description", event.target.value)} placeholder="Paste the job description here…" />
          <button type="button" className="parse-button" onClick={onParse} disabled={busy || form.description.length < 40}><Sparkles size={14} /> {busy ? "Working…" : "Parse with AI"}</button>
          <div className="form-grid">
            <label className="form-label">ROLE TITLE<input required className="form-input" value={form.role_title} onChange={(event) => field("role_title", event.target.value)} placeholder="e.g. Frontend Engineer" /></label>
            <label className="form-label">COMPANY<input required className="form-input" value={form.company} onChange={(event) => field("company", event.target.value)} placeholder="e.g. Atlassian" /></label>
            <label className="form-label">REGION<select className="form-input" value={form.region} onChange={(event) => field("region", event.target.value as Region)}><option>India</option><option>Japan</option><option>Singapore</option></select></label>
            <label className="form-label">LOCATION<input className="form-input" value={form.location} onChange={(event) => field("location", event.target.value)} placeholder="City, country" /></label>
            <label className="form-label">JOB LINK<input className="form-input" value={form.source_url} onChange={(event) => field("source_url", event.target.value)} placeholder="https://" /></label>
            <label className="form-label">POSTED DATE<input type="date" className="form-input" value={form.posted_at ?? ""} onChange={(event) => field("posted_at", event.target.value || null)} /></label>
            <label className="form-label">MATCH SCORE<input className="form-input" type="number" min="0" max="100" value={form.match_score} onChange={(event) => field("match_score", Number(event.target.value))} /></label>
          </div>
          <label className="form-label full-field">HIRING MANAGER HINTS<textarea className="form-input small-textarea" value={form.hiring_manager_hints} onChange={(event) => field("hiring_manager_hints", event.target.value)} placeholder="People or teams to look for…" /></label>
          <label className="form-label full-field">OUTREACH PITCH<textarea className="form-input small-textarea" value={form.outreach_pitch} onChange={(event) => field("outreach_pitch", event.target.value)} placeholder="A tailored introduction…" /></label>
          <div className="form-actions"><button type="button" className="button-secondary" onClick={onClose}>Cancel</button><button type="submit" className="button-primary" disabled={busy}><Plus size={15} /> Save opportunity</button></div>
        </form>
      </section>
    </div>
  );
}
