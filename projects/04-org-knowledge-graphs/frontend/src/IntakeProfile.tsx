import { Check, ShieldCheck } from "./icons";
import type { IntakeProfile } from "./intakeTypes";
import { fieldCoverage, formatBytes } from "./intakeModel";
const number = (value: number) => value.toLocaleString();
export function ProfileSummary({
  profile,
  bytes,
}: {
  profile: IntakeProfile;
  bytes: number | null;
}) {
  const counts = profile.counts;
  const metrics = [
    {
      label: "Individuals",
      value: number(counts.people),
      note: "Distinct person records",
    },
    {
      label: "Messages",
      value: number(counts.messages),
      note: "Communication records",
    },
    {
      label: "Data points",
      value: number(counts.data_points),
      note: "Accepted records across types",
    },
    {
      label: "Source size",
      value: formatBytes(bytes),
      note: "Measured source bytes",
    },
  ];
  return (
    <section className="intake-profile" aria-label="Dataset profile">
      <div className="intake-section-heading">
        <span>
          <span className="intake-eyebrow">Measured, before building</span>
          <h3>What’s in this dataset?</h3>
        </span>
        <span className="intake-small-badge">
          <Check size={12} /> Inspection complete
        </span>
      </div>
      <div className="intake-metrics">
        {metrics.map((metric) => (
          <div key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <small>{metric.note}</small>
          </div>
        ))}
      </div>
      <div className="intake-record-breakdown">
        <span>
          <strong>{number(counts.units)}</strong> organizational units
        </span>
        <span>
          <strong>{number(counts.shared_mailboxes)}</strong> shared mailboxes
        </span>
        <span>
          <strong>{number(counts.assertions)}</strong> supplied assertions
        </span>
        <span>
          <strong>{number(counts.evidence)}</strong> evidence records
        </span>
        <span>
          <strong>{number(counts.communication_links)}</strong> communication
          links
        </span>
        <span>
          <strong>{number(counts.labels)}</strong> isolated evaluation labels
        </span>
      </div>
      <div className="intake-profile-columns">
        <div>
          <h4>Available information</h4>
          <div className="intake-fields">
            {profile.fields.map((field) => (
              <div className="intake-field" key={field.id}>
                <span>{field.label}</span>
                <strong>
                  {number(field.present)}
                  <small> / {number(field.total)}</small>
                </strong>
                <div
                  className="intake-field-meter"
                  role="meter"
                  aria-label={`${field.label} coverage`}
                  aria-valuemin={0}
                  aria-valuemax={field.total || 1}
                  aria-valuenow={field.present}
                >
                  <i
                    style={{
                      width: `${fieldCoverage(field.present, field.total)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="intake-quality">
          <h4>Source quality</h4>
          <dl>
            <div>
              <dt>Records read</dt>
              <dd>{number(profile.quality.read)}</dd>
            </div>
            <div>
              <dt>Accepted</dt>
              <dd>{number(profile.quality.accepted)}</dd>
            </div>
            <div>
              <dt>Duplicates</dt>
              <dd>{number(profile.quality.duplicate)}</dd>
            </div>
            <div>
              <dt>Quarantined</dt>
              <dd>{number(profile.quality.quarantined)}</dd>
            </div>
            <div>
              <dt>Unsupported</dt>
              <dd>{number(profile.quality.unsupported)}</dd>
            </div>
          </dl>
          {profile.timestamp_start && (
            <p>
              Communications: {profile.timestamp_start.slice(0, 10)}
              {profile.timestamp_end &&
                ` — ${profile.timestamp_end.slice(0, 10)}`}
            </p>
          )}
          {profile.quality.issue_count > 0 && (
            <details>
              <summary>
                {number(profile.quality.issue_count)} source issues
              </summary>
              <ul>
                {profile.quality.issues.slice(0, 15).map((issue, index) => (
                  <li key={index}>{issue.reason}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
      {profile.notes.length > 0 && (
        <div className="intake-profile-notes">
          <ShieldCheck size={16} />
          <ul>
            {profile.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

