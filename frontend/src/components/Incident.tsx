import { useEffect, useRef, useState } from "react";
import { evidenceUrl } from "../api/events";
import type { RoadBlockageDetails, ScenarioId, StoppedVehicleDetails, TrafficEvent } from "../types";

export function IncidentCard({ event, scenarioId, canReview, reviewing, onView, onDecision, live = false }: {
  event: TrafficEvent;
  scenarioId?: ScenarioId;
  canReview: boolean;
  reviewing: boolean;
  onView: () => void;
  onDecision: (decision: "verify" | "dismiss") => void;
  live?: boolean;
}) {
  const proposed = event.status === "PROPOSED";
  return (
    <article className={`incident-card severity-border-${event.severity.toLowerCase()}`}>
      <div className="incident-top"><span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span><time>{live ? new Date(event.timestamp * 1000).toLocaleTimeString() : `${event.timestamp.toFixed(1)}s`}</time></div>
      <strong>{event.event_type.replace(/_/g, " ")}</strong>
      <small>{event.camera_name}</small>
      <p>{event.explanation}</p>
      <div className="incident-state"><span>{event.status}</span><b>{Math.round(event.confidence * 100)}%</b></div>
      <div className="incident-actions">
        <button type="button" className="ghost" onClick={onView}>View</button>
        <button type="button" disabled={!proposed || !canReview || reviewing} onClick={() => onDecision("verify")}>Verify</button>
        <button type="button" className="danger-ghost" disabled={!proposed || !canReview || reviewing} onClick={() => onDecision("dismiss")}>Dismiss</button>
      </div>
    </article>
  );
}

export function IncidentDetail({ event, scenarioId, canReview, reviewing, onClose, onDecision, evidenceSrc, live = false }: {
  event: TrafficEvent;
  scenarioId?: ScenarioId;
  canReview: boolean;
  reviewing: boolean;
  onClose: () => void;
  onDecision: (decision: "verify" | "dismiss") => void;
  evidenceSrc?: string;
  live?: boolean;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const imageSrc = evidenceSrc ?? evidenceUrl(event.evidence_image, scenarioId);
  const [failedImage, setFailedImage] = useState<string | null>(null);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current!;
    const controls = () => Array.from(dialog.querySelectorAll<HTMLElement>("button:not(:disabled), [href], input:not(:disabled), [tabindex='0']"));
    controls()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault(); first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); previousFocus?.focus(); };
  }, []);
  const proposed = event.status === "PROPOSED";
  const roadDetails = event.event_type === "ROAD_BLOCKAGE" && event.details && "zone_name" in event.details
    ? event.details as RoadBlockageDetails
    : null;
  const stoppedDetails = event.event_type === "STOPPED_VEHICLE" && event.details
    && typeof event.details.stationary_duration_seconds === "number"
    && "movement_value" in event.details
    && "pixel_speed_debug" in event.details
    && typeof event.details.movement_value === "number"
    && typeof event.details.pixel_speed_debug === "number"
    ? event.details as StoppedVehicleDetails
    : null;
  return (
    <div className="detail-backdrop" role="presentation" onMouseDown={onClose}>
      <aside ref={dialogRef} className="incident-detail" role="dialog" aria-modal="true" aria-label="Incident detail" onMouseDown={(event) => event.stopPropagation()}>
        <div className="detail-header"><span>INCIDENT DETAIL</span><button type="button" className="icon-button" onClick={onClose} aria-label="Close incident detail">×</button></div>
        {failedImage === imageSrc ? <div role="status" className="unavailable-detail">Evidence image is unavailable.</div> : <img src={imageSrc} onError={() => setFailedImage(imageSrc)} alt={`Evidence for ${event.event_type}`} />}
        <div className="proposal-label"><i />{proposed ? "AI PROPOSED EVENT" : `MUNICIPAL DECISION: ${event.status}`}<small>{proposed ? "Requires municipal verification" : "Review decision saved"}</small></div>
        <div className="detail-title"><div><h2>{event.event_type.replace(/_/g, " ")}</h2><p>{event.explanation}</p></div><span className={`severity ${event.severity.toLowerCase()}`}>{event.severity}</span></div>
        <dl className="detail-grid">
          <div><dt>Source</dt><dd>{live ? "LIVE" : "RECORDED DEMO"} · {event.camera_name}</dd></div>
          <div><dt>{live ? "Observed at" : "Video timestamp"}</dt><dd>{live ? new Date(event.timestamp * 1000).toLocaleTimeString() : `${event.timestamp.toFixed(1)}s`}</dd></div>
          <div><dt>Confidence</dt><dd>{Math.round(event.confidence * 100)}%</dd></div>
          <div><dt>Review state</dt><dd>{event.status}</dd></div>
        </dl>
        {roadDetails ? <dl className="detail-grid measured-details">
          <div><dt>Track ID</dt><dd>{roadDetails.track_id}</dd></div>
          <div><dt>Tracked class</dt><dd>{roadDetails.vehicle_class}</dd></div>
          <div><dt>Blockage zone</dt><dd>{roadDetails.zone_name}</dd></div>
          <div><dt>Stationary duration</dt><dd>{roadDetails.stationary_duration_seconds.toFixed(1)}s</dd></div>
          <div><dt>Vehicle-zone overlap</dt><dd>{Math.round(roadDetails.vehicle_zone_overlap * 100)}%</dd></div>
          <div><dt>Image-space obstruction</dt><dd>{Math.round(roadDetails.normalized_obstruction_ratio * 100)}%</dd></div>
          <div><dt>Upstream vehicles</dt><dd>{roadDetails.upstream_vehicle_count}</dd></div>
          <div><dt>Slow upstream vehicles</dt><dd>{roadDetails.slow_upstream_vehicle_count}</dd></div>
          <div><dt>Traffic impact duration</dt><dd>{roadDetails.traffic_impact_duration_seconds.toFixed(1)}s</dd></div>
          <div className="detail-wide"><dt>Confidence reasoning</dt><dd>{roadDetails.confidence_reasoning}</dd></div>
        </dl> : stoppedDetails ? <dl className="detail-grid measured-details">
          <div><dt>Track ID</dt><dd>{stoppedDetails.track_id}</dd></div>
          <div><dt>Tracked class</dt><dd>{stoppedDetails.vehicle_class}</dd></div>
          <div><dt>Stationary duration</dt><dd>{stoppedDetails.stationary_duration_seconds.toFixed(1)}s</dd></div>
          <div><dt>Normalized movement</dt><dd>{stoppedDetails.movement_value.toFixed(4)} ROI/s</dd></div>
          <div><dt>ROI state</dt><dd>{stoppedDetails.roi_status}</dd></div>
          <div><dt>Pixel speed (debug)</dt><dd>{stoppedDetails.pixel_speed_debug.toFixed(1)} px/s</dd></div>
        </dl> : <div className="unavailable-detail">Additional track measurements are not available for this event.</div>}
        <div className="detail-actions"><button disabled={!proposed || !canReview || reviewing} onClick={() => onDecision("verify")}>Verify event</button><button className="danger-ghost" disabled={!proposed || !canReview || reviewing} onClick={() => onDecision("dismiss")}>Dismiss</button></div>
        {!canReview && proposed && <small className="permission-note">Employee or Admin access is required.</small>}
      </aside>
    </div>
  );
}
