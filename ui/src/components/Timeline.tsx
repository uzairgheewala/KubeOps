import type { TimelineEvent } from "../types";

export function Timeline({ events, selectedSequence, onSelect }: {
  events: TimelineEvent[];
  selectedSequence: number | null;
  onSelect: (sequence: number) => void;
}) {
  if (events.length === 0) {
    return <div className="empty-state">Run a scenario to populate the event timeline.</div>;
  }
  return (
    <ol className="timeline">
      {events.map((event) => (
        <li key={event.sequence}>
          <button
            type="button"
            className={`timeline-event ${selectedSequence === event.sequence ? "is-selected" : ""}`}
            onClick={() => onSelect(event.sequence)}
          >
            <span className="timeline-time">t+{event.at_seconds}s</span>
            <span className="timeline-dot" />
            <span className="timeline-content">
              <strong>{event.title}</strong>
              <small>{event.event_type}</small>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
