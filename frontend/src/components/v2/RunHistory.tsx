"use client";

import { FileSearch } from "lucide-react";

import type { AgenticParseJob } from "@/lib/api";

function title(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RunHistory({
  jobs,
  activeId,
  onSelect,
}: {
  jobs: AgenticParseJob[];
  activeId: string | null;
  onSelect: (jobId: string) => void;
}) {
  return (
    <nav className="run-history" aria-label="Extraction runs">
      <div className="run-history-heading">
        <span>Runs</span>
        <small>{jobs.length}</small>
      </div>
      <div className="run-history-list">
        {jobs.map((job) => (
          <button
            type="button"
            key={job.id}
            className={activeId === job.id ? "active" : ""}
            aria-current={activeId === job.id ? "true" : undefined}
            onClick={() => onSelect(job.id)}
          >
            <span>{job.original_filename}</span>
            <small>{job.completed_pages}/{job.page_count} pages · {title(job.status)}</small>
          </button>
        ))}
        {!jobs.length && (
          <div className="run-history-empty">
            <FileSearch size={22} />
            <span>No extraction runs yet</span>
          </div>
        )}
      </div>
    </nav>
  );
}
