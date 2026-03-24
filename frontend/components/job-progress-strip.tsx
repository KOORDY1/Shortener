import { Job } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";

type Props = {
  jobs: Job[];
};

export function JobProgressStrip({ jobs }: Props) {
  return (
    <div className="panel">
      <h2 className="section-title">Jobs</h2>
      <div className="job-strip">
        {jobs.map((job) => (
          <div className="job-pill" key={job.id}>
            <div className="spaced">
              <strong>{job.type}</strong>
              <StatusBadge value={job.status} />
            </div>
            <p className="muted">{job.current_step ?? "queued"}</p>
            <div className="progress">
              <span style={{ width: `${job.progress_percent}%` }} />
            </div>
          </div>
        ))}
        {jobs.length === 0 ? <div className="muted">아직 생성된 job이 없습니다.</div> : null}
      </div>
    </div>
  );
}
