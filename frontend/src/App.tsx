import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownUp,
  ArrowUpRight,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Command,
  FileText,
  Filter,
  Globe2,
  LayoutGrid,
  List,
  LoaderCircle,
  Plus,
  Search,
  Sparkles,
  Target,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  createJob,
  addAgentSource,
  deleteAgentSource,
  deleteJob,
  deleteProfile,
  getAgentRuns,
  getAgentSettings,
  getAgentSources,
  getJobs,
  getProfile,
  importLinkedInJob,
  parseDescription,
  refreshRecommendations,
  runAgent,
  saveAgentSettings,
  seedJobs,
  syncJob,
  updateJobStatus,
  uploadResume,
} from "./api";
import { StatCard, CompanyMark, MatchScore, StatusBadge, JobCard, JobModal, ResumeModal, AgentConsole, LinkedInModal, AddModal } from "./components";
import { STATUSES, formatPostedDate } from "./helpers";
import type {
  AgentRun,
  AgentSettings,
  AgentSource,
  Job,
  JobInput,
  Region,
  ResumeProfile,
  SourceType,
  Status,
} from "./types";

const REGIONS = ["All regions", "India", "Japan", "Singapore"] as const;
type RegionFilter = (typeof REGIONS)[number];
type StatusFilter = Status | "All statuses";

const initialForm: JobInput = {
  role_title: "",
  company: "",
  region: "India",
  location: "",
  status: "Wishlist",
  match_score: 0,
  hiring_manager_hints: "",
  outreach_pitch: "",
  description: "",
  source_url: "",
  posted_at: null,
};


function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [region, setRegion] = useState<RegionFilter>("All regions");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("All statuses");
  const [view, setView] = useState<"board" | "table">("board");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Job | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [showResume, setShowResume] = useState(false);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeConsent, setResumeConsent] = useState(false);
  const [profile, setProfile] = useState<ResumeProfile | null>(null);
  const [agentSettings, setAgentSettings] = useState<AgentSettings | null>(null);
  const [agentSources, setAgentSources] = useState<AgentSource[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentBusy, setAgentBusy] = useState(false);
  const [showLinkedIn, setShowLinkedIn] = useState(false);
  const [scheduleChoice, setScheduleChoice] = useState("1440");
  const [customIntervalHours, setCustomIntervalHours] = useState("24");
  const [minimumScore, setMinimumScore] = useState(85);
  const [sourceName, setSourceName] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("greenhouse");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceRegion, setSourceRegion] = useState<Region>("India");
  const [form, setForm] = useState<JobInput>(initialForm);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      setJobs(await getJobs(region, statusFilter));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load jobs.");
    } finally {
      setLoading(false);
    }
  }, [region, statusFilter]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    void getProfile()
      .then(setProfile)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Could not load resume profile."));
  }, []);

  const loadAgentState = useCallback(async () => {
    const [settings, sources, runs] = await Promise.all([
      getAgentSettings(),
      getAgentSources(),
      getAgentRuns(),
    ]);
    setAgentSettings(settings);
    setAgentSources(sources);
    setAgentRuns(runs);
    setMinimumScore(settings.minimum_match_score);
    const presets = [0, 360, 1440];
    setScheduleChoice(presets.includes(settings.interval_minutes) ? String(settings.interval_minutes) : "custom");
    if (settings.interval_minutes > 0) {
      setCustomIntervalHours(String(Math.max(1, settings.interval_minutes / 60)));
    }
  }, []);

  useEffect(() => {
    void loadAgentState().catch((e: unknown) =>
      setError(e instanceof Error ? e.message : "Could not load agent settings."),
    );
  }, [loadAgentState]);

  useEffect(() => {
    const refreshRunStatus = async () => {
      try {
        const [settings, runs] = await Promise.all([getAgentSettings(), getAgentRuns()]);
        setAgentSettings(settings);
        setAgentRuns(runs);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not refresh agent status.");
      }
    };
    const timer = window.setInterval(() => void refreshRunStatus(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 3500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const filteredJobs = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return jobs;
    return jobs.filter((job) =>
      [job.role_title, job.company, job.region, job.location].some((value) =>
        value.toLowerCase().includes(query),
      ),
    );
  }, [jobs, search]);

  const counts = useMemo(
    () => ({
      total: jobs.length,
      interviewing: jobs.filter((job) => job.status === "Interviewing").length,
      wishlist: jobs.filter((job) => job.status === "Wishlist").length,
      average: jobs.length
        ? Math.round(jobs.reduce((sum, job) => sum + job.match_score, 0) / jobs.length)
        : 0,
    }),
    [jobs],
  );

  async function runAction(action: () => Promise<unknown>, message: string | ((result: unknown) => string)) {
    setBusy(true);
    setError("");
    try {
      const result = await action();
      setNotice(typeof message === "function" ? message(result) : message);
      await loadJobs();
      if (selected) {
        const refreshed = await getJobs(region, "All statuses");
        setSelected(refreshed.find((job) => job.id === selected.id) ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function addJob(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runAction(async () => {
      await createJob(form);
      setForm(initialForm);
      setShowAdd(false);
    }, "Job added to your tracker.");
  }

  async function handleSeed() {
    await runAction(
      () => seedJobs(),
      (result) => {
        if (!Array.isArray(result)) return "Sample jobs processed.";
        return result.length
          ? `${result.length} sample jobs added.`
          : "Sample jobs are already in your tracker.";
      },
    );
  }

  async function handleParse() {
    if (!form.description.trim()) return;
    setBusy(true);
    setError("");
    try {
      const parsed = await parseDescription(form.description);
      setForm((current) => ({ ...current, ...parsed }));
      setNotice("Description parsed. Review the details before saving.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI parsing failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResumeUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resumeFile || !resumeConsent) return;
    setBusy(true);
    setError("");
    try {
      const savedProfile = await uploadResume(resumeFile, resumeConsent);
      setProfile(savedProfile);
      setShowResume(false);
      setResumeFile(null);
      setResumeConsent(false);
      const result = await refreshRecommendations();
      setNotice(result.message);
      await loadJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resume analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshRecommendations() {
    setBusy(true);
    setError("");
    try {
      const result = await refreshRecommendations();
      setNotice(result.message);
      await loadJobs();
      if (selected) {
        const refreshed = await getJobs(region, "All statuses");
        setSelected(refreshed.find((job) => job.id === selected.id) ?? null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not refresh recommendations.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteProfile() {
    if (!window.confirm("Delete the saved resume profile and clear resume-based job scores and pitches?")) return;
    setBusy(true);
    setError("");
    try {
      await deleteProfile();
      setProfile(null);
      setNotice("Resume profile and personalized recommendations deleted.");
      await loadJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete resume profile.");
    } finally {
      setBusy(false);
    }
  }

  async function saveAgentSchedule() {
    const interval = scheduleChoice === "custom"
      ? Math.round(Number(customIntervalHours) * 60)
      : Number(scheduleChoice);
    if (!Number.isFinite(interval) || interval < 0 || interval > 525600) {
      setError("Choose a valid interval in hours (maximum one year).");
      return;
    }
    setAgentBusy(true);
    setError("");
    try {
      const settings = await saveAgentSettings(interval, minimumScore);
      setAgentSettings(settings);
      setNotice(interval === 0 ? "Agent set to manual runs only." : "Agent schedule saved.");
      await loadAgentState();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save agent settings.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleRunAgent() {
    setAgentBusy(true);
    setError("");
    try {
      const result = await runAgent();
      setNotice(result.message);
      await Promise.all([loadAgentState(), loadJobs()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The sourcing agent could not run.");
      await loadAgentState().catch(() => undefined);
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleAddSource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAgentBusy(true);
    setError("");
    try {
      await addAgentSource({
        name: sourceName,
        source_type: sourceType,
        url: sourceUrl,
        region: sourceRegion,
      });
      setSourceName("");
      setSourceUrl("");
      setNotice("Career source added. The agent will check it on schedule.");
      await loadAgentState();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add career source.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleDeleteSource(id: number) {
    setAgentBusy(true);
    setError("");
    try {
      await deleteAgentSource(id);
      setNotice("Career source removed.");
      await loadAgentState();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove career source.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function handleLinkedInImport(
    event: React.FormEvent<HTMLFormElement>,
    listing: { role_title: string; company: string; region: Region; location: string; description: string; source_url: string; posted_at: string | null },
  ) {
    event.preventDefault();
    setAgentBusy(true);
    setError("");
    try {
      const result = await importLinkedInJob(listing);
      setNotice(result.message);
      setShowLinkedIn(false);
      if (result.qualified) await Promise.all([loadAgentState(), loadJobs()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not evaluate LinkedIn role.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function copyPitch(pitch: string) {
    try {
      await navigator.clipboard.writeText(pitch);
      setNotice("Outreach pitch copied.");
    } catch {
      setError("Clipboard access is unavailable in this browser.");
    }
  }

  return (
    <div className="min-h-screen bg-[#f8f8f6] text-[#22241f]">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><BriefcaseBusiness size={18} strokeWidth={2.2} /></div>
          <span>work<span className="brand-dot">.</span>list</span>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <button className="workspace-picker">
          <span className="workspace-avatar">RJ</span>
          <span className="workspace-name">Rohit’s search</span>
          <ChevronDown size={14} />
        </button>
        <div className="nav-label">YOUR PIPELINE</div>
        <button className={`nav-item ${statusFilter === "All statuses" ? "active" : ""}`} onClick={() => setStatusFilter("All statuses")}>
          <LayoutGrid size={16} /><span>All opportunities</span><span className="nav-count">{jobs.length}</span>
        </button>
        {STATUSES.map((item) => (
          <button key={item} className={`nav-item ${statusFilter === item ? "active" : ""}`} onClick={() => setStatusFilter(item)}>
            <span className={`status-dot ${item.toLowerCase()}`} /><span>{item}</span>
            {item === "Interviewing" && counts.interviewing > 0 && <span className="nav-count">{counts.interviewing}</span>}
          </button>
        ))}
        <div className="sidebar-bottom">
          <div className="sidebar-tip">
            <div className="tip-icon"><Sparkles size={15} /></div>
            <strong>Make your next move</strong>
            <p>Turn a job description into a thoughtful first message.</p>
            <button onClick={() => setShowAdd(true)}>Try AI parsing <ArrowUpRight size={13} /></button>
          </div>
          <button className="nav-item muted"><CircleHelp size={16} /><span>Help & feedback</span></button>
          <div className="profile">
            <div className="profile-avatar">RJ</div>
            <div><strong>Rohit Jagirdar</strong><span>Personal workspace</span></div>
            <button aria-label="Profile options"><ChevronDown size={14} /></button>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> <strong>All opportunities</strong></div>
          <div className="topbar-actions">
            <div className="sync-state"><span /> Saved locally</div>
            <button className="icon-button" aria-label="Keyboard shortcuts"><Command size={16} /></button>
            <div className="top-avatar">RJ</div>
          </div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> YOUR CAREER, ORGANIZED</div>
              <h1>Job search, <em>in focus.</em></h1>
              <p className="page-subtitle">A little progress, every day. Keep your next opportunity close.</p>
            </div>
            <div className="heading-actions">
              <button className="button-secondary" onClick={() => setShowResume(true)} disabled={busy}>
                <FileText size={15} /> {profile ? "Resume profile" : "Add your resume"}
              </button>
              <button className="button-secondary" onClick={() => void handleSeed()} disabled={busy}>
                <Sparkles size={15} /> Load sample roles
              </button>
              <button className="button-primary" onClick={() => setShowAdd(true)}><Plus size={16} /> Add opportunity</button>
            </div>
          </div>

          <section className="stats-grid" aria-label="Job search summary">
            <StatCard label="IN YOUR PIPELINE" value={counts.total} note="opportunities saved" icon={<BriefcaseBusiness size={17} />} tone="olive" />
            <StatCard label="IN CONVERSATION" value={counts.interviewing} note="active interviews" icon={<Clock3 size={17} />} tone="coral" />
            <StatCard label="ON YOUR RADAR" value={counts.wishlist} note="roles to explore" icon={<Globe2 size={17} />} tone="blue" />
            <StatCard label="AVERAGE MATCH" value={`${counts.average}%`} note="across your roles" icon={<Sparkles size={17} />} tone="gold" />
          </section>

          <section className={`resume-panel ${profile ? "has-profile" : ""}`}>
            <div className="resume-panel-icon">{profile ? <Target size={18} /> : <FileText size={18} />}</div>
            <div className="resume-panel-copy">
              <div className="resume-panel-title">{profile ? "Your recommendations are about you." : "Make your matches about you."}</div>
              <p>{profile ? profile.profile_summary : "Add a resume profile to compare each role with your actual skills and experience—not a generic score."}</p>
              {profile && <div className="profile-facts"><span>{profile.years_experience === null ? "Experience not stated" : `${profile.years_experience} years’ experience`}</span><span>{profile.seniority}</span>{profile.target_roles.slice(0, 3).map((role) => <span key={role}>{role}</span>)}</div>}
              {profile && <div className="skill-chips">{profile.skills.slice(0, 8).map((skill) => <span key={skill}>{skill}</span>)}{profile.skills.length > 8 && <span>+{profile.skills.length - 8}</span>}</div>}
            </div>
            <div className="resume-panel-actions">
              {profile && <button className="button-secondary" onClick={() => void handleRefreshRecommendations()} disabled={busy}><Sparkles size={14} /> Refresh matches</button>}
              <button className={profile ? "text-button" : "button-primary"} onClick={() => setShowResume(true)} disabled={busy}>{profile ? "Replace resume" : <><Upload size={14} /> Upload resume</>}</button>
              {profile && <button className="text-button danger-text" onClick={() => void handleDeleteProfile()} disabled={busy} aria-label="Delete resume profile"><Trash2 size={14} /> Remove profile</button>}
            </div>
          </section>

          <AgentConsole
            settings={agentSettings}
            sources={agentSources}
            runs={agentRuns}
            busy={agentBusy}
            profileReady={Boolean(profile)}
            scheduleChoice={scheduleChoice}
            setScheduleChoice={setScheduleChoice}
            customHours={customIntervalHours}
            setCustomHours={setCustomIntervalHours}
            minimumScore={minimumScore}
            setMinimumScore={setMinimumScore}
            sourceName={sourceName}
            setSourceName={setSourceName}
            sourceType={sourceType}
            setSourceType={setSourceType}
            sourceUrl={sourceUrl}
            setSourceUrl={setSourceUrl}
            sourceRegion={sourceRegion}
            setSourceRegion={setSourceRegion}
            onSaveSchedule={() => void saveAgentSchedule()}
            onAddSource={(event) => void handleAddSource(event)}
            onDeleteSource={(id) => void handleDeleteSource(id)}
            onRun={() => void handleRunAgent()}
            onAddLinkedIn={() => setShowLinkedIn(true)}
          />

          <section className="opportunities">
            <div className="section-heading">
              <div><h2>Your opportunities</h2><p>Keep the momentum going.</p></div>
              <div className="view-switch" aria-label="Choose view">
                <button aria-label="Board view" className={view === "board" ? "selected" : ""} onClick={() => setView("board")}><LayoutGrid size={16} /></button>
                <button aria-label="Table view" className={view === "table" ? "selected" : ""} onClick={() => setView("table")}><List size={17} /></button>
              </div>
            </div>
            <div className="toolbar">
              <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search roles, companies..." /><kbd>⌘ K</kbd></label>
              <div className="toolbar-select"><Filter size={14} /><select value={region} onChange={(event) => setRegion(event.target.value as RegionFilter)} aria-label="Filter by region">{REGIONS.map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={13} /></div>
              <div className="toolbar-select"><ArrowDownUp size={14} /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)} aria-label="Filter by status"><option>All statuses</option>{STATUSES.map((item) => <option key={item}>{item}</option>)}</select><ChevronDown size={13} /></div>
              <span className="results-count">{filteredJobs.length} {filteredJobs.length === 1 ? "role" : "roles"}</span>
            </div>

            {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss error"><X size={14} /></button></div>}
            {loading ? (
              <div className="loading-state"><LoaderCircle className="spin" size={22} /> Loading your pipeline…</div>
            ) : filteredJobs.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon"><BriefcaseBusiness size={23} /></div>
                <h3>{search ? "No matching roles" : "A fresh start."}</h3>
                <p>{search ? "Try another search or adjust your filters." : "Add an opportunity or load sample roles to get your pipeline moving."}</p>
                {!search && <button className="button-primary" onClick={() => void handleSeed()}><Sparkles size={15} /> Load sample roles</button>}
              </div>
            ) : view === "board" ? (
              <div className="board">
                {STATUSES.filter((item) => statusFilter === "All statuses" || statusFilter === item).map((item) => {
                  const columnJobs = filteredJobs.filter((job) => job.status === item);
                  return (
                    <div className="board-column" key={item}>
                      <div className="column-heading"><div><span className={`status-dot ${item.toLowerCase()}`} /><h3>{item}</h3><span className="column-count">{columnJobs.length}</span></div><button aria-label={`More ${item} options`}><span>···</span></button></div>
                      <div className="column-cards">
                        {columnJobs.map((job) => <JobCard key={job.id} job={job} onOpen={() => setSelected(job)} />)}
                        {columnJobs.length === 0 && <div className="column-empty">Nothing here yet</div>}
                      </div>
                      <button className="add-to-column" onClick={() => { setForm((current) => ({ ...current, status: item })); setShowAdd(true); }}><Plus size={14} /> Add opportunity</button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>ROLE & COMPANY</th><th>REGION</th><th>MATCH</th><th>STATUS</th><th>POSTED</th><th>UPDATED</th><th /></tr></thead>
                  <tbody>{filteredJobs.map((job) => <tr key={job.id} onClick={() => setSelected(job)}>
                    <td><div className="table-role"><CompanyMark company={job.company} /><span><strong>{job.role_title}</strong><small>{job.company}</small></span></div></td>
                    <td><span className="region-cell">{job.region}</span></td>
                    <td><MatchScore score={job.match_score} /></td>
                    <td><StatusBadge status={job.status} /></td>
                    <td className="date-cell">{formatPostedDate(job.posted_at)}</td>
                    <td className="date-cell">{new Date(job.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
                    <td><ArrowUpRight size={15} className="table-arrow" /></td>
                  </tr>)}</tbody>
                </table>
              </div>
            )}
          </section>
          <footer className="page-footer"><span>Made for the in-between moments.</span><span><span className="footer-leaf">✳</span> A calmer kind of job search</span></footer>
        </div>
      </main>

      {selected && <JobModal job={selected} hasProfile={Boolean(profile)} busy={busy} onClose={() => setSelected(null)} onCopy={() => void copyPitch(selected.resume_outreach_pitch || selected.outreach_pitch)} onSync={() => void runAction(() => syncJob(selected.id), "Job synced to Notion.")} onStatus={(status) => void runAction(() => updateJobStatus(selected.id, status), `Moved to ${status}.`)} onDelete={() => void runAction(async () => { await deleteJob(selected.id); setSelected(null); }, "Opportunity deleted.")} />}
      {showAdd && <AddModal form={form} setForm={setForm} busy={busy} onClose={() => { setShowAdd(false); setForm(initialForm); }} onSubmit={(event) => void addJob(event)} onParse={() => void handleParse()} />}
      {showResume && <ResumeModal file={resumeFile} setFile={setResumeFile} consent={resumeConsent} setConsent={setResumeConsent} busy={busy} onClose={() => setShowResume(false)} onSubmit={(event) => void handleResumeUpload(event)} />}
      {showLinkedIn && <LinkedInModal busy={agentBusy} onClose={() => setShowLinkedIn(false)} onSubmit={(event, listing) => void handleLinkedInImport(event, listing)} />}
      {notice && <div className="toast"><Check size={16} /> {notice}</div>}
    </div>
  );
}

export default App;
