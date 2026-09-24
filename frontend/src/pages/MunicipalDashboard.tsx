import { useEffect, useMemo, useRef, useState } from "react";

import { fetchScenarios } from "../api/analysis";

import {
  fetchLiveCameras,
  fetchLiveEvents,
  fetchLiveMetrics,
  liveEvidenceUrl,
  reviewLiveEvent,
} from "../api/live";

import { IncidentCard, IncidentDetail } from "../components/Incident";

import { LiveMjpegImage } from "../components/LiveMjpegImage";

import { SourceSidebar } from "../components/SourceSidebar";

import type { AuthState } from "../hooks/useAuth";

import { useAnalysis } from "../hooks/useAnalysis";

import { useEvents } from "../hooks/useEvents";

import {
  cameraIsOnline,
  cameraStateLabel,
  currentLiveMetrics as validatedLiveMetrics,
  trafficCondition,
  useFreshnessClock,
} from "../lib/liveTruth";

import type {
  AnalysisFrame,
  CameraHealth,
  LiveMetricsSnapshot,
  ScenarioId,
  ScenarioInfo,
  TrafficEvent,
} from "../types";


const CAMERA_NAMES: Record<string, string> = {
  "camera-3": "DVR Camera 3",
  "camera-5": "DVR Camera 5",
  "camera-7": "DVR Camera 7",
};


export function MunicipalDashboard({ auth }: { auth: AuthState }) {
  const [source, setSource] = useState<
    | { kind: "LIVE_CAMERA"; id: string }
    | { kind: "RECORDED_SCENARIO"; id: ScenarioId }
  >({
    kind: "RECORDED_SCENARIO",
    id: "normal_traffic",
  });

  const sourceRef = useRef(source);

  sourceRef.current = source;

  const scenarioId: ScenarioId =
    source.kind === "RECORDED_SCENARIO"
      ? source.id
      : "normal_traffic";

  const selectedLiveCamera =
    source.kind === "LIVE_CAMERA"
      ? source.id
      : null;

  const now = useFreshnessClock();

  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);

  const [liveView, setLiveView] =
    useState<"live" | "ai">("live");

  const initializedLiveSource =
    useRef(false);

  const [liveCameras, setLiveCameras] =
    useState<CameraHealth[]>([]);

  const [liveMetrics, setLiveMetrics] =
    useState<LiveMetricsSnapshot | null>(null);

  const [liveEvents, setLiveEvents] =
    useState<TrafficEvent[]>([]);

  const [liveError, setLiveError] =
    useState<string | null>(null);

  const [reviewingLiveId, setReviewingLiveId] =
    useState<string | null>(null);

  const [videoTime, setVideoTime] =
    useState(0);

  const [analysisStarted, setAnalysisStarted] =
    useState(false);

  const [selectedEvent, setSelectedEvent] =
    useState<TrafficEvent | null>(null);

  const [scenarioError, setScenarioError] =
    useState<string | null>(null);

  const {
    events,
    loading,
    error,
    reviewingEventId,
    refresh,
    decide,
  } = useEvents(scenarioId);

  const {
    summary,
    timeline,
    error: analysisError,
    refresh: refreshAnalysis,
  } = useAnalysis(scenarioId);

  const liveMode =
    source.kind === "LIVE_CAMERA";

  const selectedHealth =
    liveCameras.find(
      (camera) =>
        camera.camera_id === selectedLiveCamera
    ) ?? null;


  useEffect(() => {
    const controller =
      new AbortController();

    void fetchScenarios(controller.signal)
      .then((items) => {
        setScenarios(items);
        setScenarioError(null);
      })
      .catch((requestError) => {
        if (
          !(
            requestError instanceof DOMException &&
            requestError.name === "AbortError"
          )
        ) {
          setScenarioError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load sources"
          );
        }
      });

    return () => controller.abort();
  }, []);


  useEffect(() => {
    let cancelled = false;

    let inFlight = false;

    const controller =
      new AbortController();

    async function refreshLive() {
      if (inFlight) return;

      inFlight = true;

      const cycle =
        new AbortController();

      const abortCycle = () =>
        cycle.abort();

      controller.signal.addEventListener(
        "abort",
        abortCycle
      );

      const timeout =
        window.setTimeout(
          abortCycle,
          4_000
        );

      try {
        try {
          const cameras =
            await fetchLiveCameras(
              cycle.signal
            );

          if (cancelled) return;

          setLiveCameras(cameras);

          if (
            !initializedLiveSource.current
          ) {
            initializedLiveSource.current =
              true;

            if (cameras.length) {
              setSource({
                kind: "LIVE_CAMERA",
                id: cameras[0].camera_id,
              });
            }
          }
        } catch {
          // Existing snapshots expire locally even if polling is unavailable.
        }


        if (
          selectedLiveCamera &&
          !cancelled
        ) {
          const [
            metrics,
            incidents,
          ] = await Promise.allSettled([
            fetchLiveMetrics(
              selectedLiveCamera,
              cycle.signal
            ),
            fetchLiveEvents(
              selectedLiveCamera,
              cycle.signal
            ),
          ]);


          if (!cancelled) {
            setLiveMetrics(
              metrics.status === "fulfilled"
                ? metrics.value
                : null
            );

            if (
              metrics.status === "fulfilled" &&
              metrics.value.health.camera_id ===
                selectedLiveCamera
            ) {
              const nextHealth =
                metrics.value.health;

              setLiveCameras(
                (current) =>
                  current.map(
                    (item) =>
                      item.camera_id ===
                        selectedLiveCamera &&
                      nextHealth.checked_at >=
                        item.checked_at
                        ? nextHealth
                        : item
                  )
              );
            }

            if (
              incidents.status ===
              "fulfilled"
            ) {
              setLiveEvents(
                incidents.value.events
              );
            }

            setLiveError(
              incidents.status ===
                "rejected"
                ? "Incident queue is unavailable. Saved incidents are retained."
                : null
            );
          }
        }
      } finally {
        window.clearTimeout(timeout);

        controller.signal.removeEventListener(
          "abort",
          abortCycle
        );

        inFlight = false;
      }
    }


    void refreshLive();

    const timer =
      window.setInterval(
        () => void refreshLive(),
        2_000
      );

    return () => {
      cancelled = true;

      controller.abort();

      window.clearInterval(timer);
    };
  }, [selectedLiveCamera]);


  const currentFrame = useMemo(() => {
    if (!timeline?.frames.length)
      return null;

    let selected:
      | AnalysisFrame
      | null = null;

    for (
      const frame of timeline.frames
    ) {
      if (
        frame.timestamp_sec >
        videoTime
      ) {
        break;
      }

      selected = frame;
    }

    return selected;
  }, [timeline, videoTime]);


  const currentLiveMetrics =
    validatedLiveMetrics(
      liveMetrics,
      selectedHealth,
      selectedLiveCamera,
      now
    );

  const displayedFrame =
    liveMode
      ? currentLiveMetrics
      : currentFrame;

  const previewOnline =
    cameraIsOnline(
      selectedHealth,
      now
    );

  const healthLabel =
    cameraStateLabel(
      selectedHealth,
      now
    );

  const visibleEvents =
    liveMode
      ? liveEvents
      : events.filter(
          (event) =>
            analysisStarted &&
            event.timestamp <=
              videoTime
        );


  /*
   * Live camera:
   *     use the latest validated live AI state.
   *
   * Recorded scenario:
   *     use the AI-computed traffic state
   *     attached to the current video frame.
   */
  const trafficStatus =
    trafficCondition(
      liveMode
        ? currentLiveMetrics?.traffic_state
        : currentFrame?.traffic_state
    );


  const previewFps =
    previewOnline
      ? selectedHealth!
          .preview_publication_fps
          .toFixed(1)
      : "—";

  const aiFps =
    currentLiveMetrics
      ? liveMetrics!.health
          .ai_inference_fps
          .toFixed(1)
      : "—";


  const selectedScenario =
    scenarios.find(
      (scenario) =>
        scenario.scenario_id ===
        scenarioId
    );


  const cameraName =
    liveMode
      ? CAMERA_NAMES[
          selectedLiveCamera!
        ] ??
        selectedLiveCamera
      : events[0]?.camera_name ??
        selectedScenario?.title ??
        "Loading source";


  const canReview =
    !auth.loading &&
    !auth.error &&
    (
      !auth.authRequired ||
      auth.user?.role ===
        "EMPLOYEE" ||
      auth.user?.role ===
        "ADMIN"
    );


  function selectScenario(
    next: ScenarioId
  ) {
    initializedLiveSource.current =
      true;

    setSource({
      kind: "RECORDED_SCENARIO",
      id: next,
    });

    setLiveMetrics(null);

    setLiveEvents([]);

    setVideoTime(0);

    setAnalysisStarted(false);

    setSelectedEvent(null);

    setLiveError(null);
  }


  function selectLive(
    cameraId: string
  ) {
    initializedLiveSource.current =
      true;

    setSource({
      kind: "LIVE_CAMERA",
      id: cameraId,
    });

    setLiveView("live");

    setSelectedEvent(null);

    setLiveMetrics(null);

    setLiveEvents([]);

    setLiveError(null);
  }


  async function decideOn(
    event: TrafficEvent,
    decision:
      | "verify"
      | "dismiss"
  ) {
    const origin = source;

    const stillSelected = () =>
      sourceRef.current.kind ===
        origin.kind &&
      sourceRef.current.id ===
        origin.id;


    if (
      liveMode &&
      selectedLiveCamera
    ) {
      setReviewingLiveId(
        event.event_id
      );

      try {
        const updated =
          await reviewLiveEvent(
            selectedLiveCamera,
            event.event_id,
            decision
          );

        if (!stillSelected())
          return;

        setLiveEvents(
          (current) =>
            current.map(
              (item) =>
                item.event_id ===
                  updated.event_id
                  ? updated
                  : item
            )
        );

        setSelectedEvent(
          updated
        );
      } finally {
        setReviewingLiveId(null);
      }

      return;
    }


    await decide(
      event.event_id,
      decision
    );

    if (!stillSelected())
      return;

    setSelectedEvent(
      (current) =>
        current?.event_id ===
        event.event_id
          ? {
              ...current,
              status:
                decision === "verify"
                  ? "VERIFIED"
                  : "DISMISSED",
            }
          : current
    );
  }


  const combinedError =
    liveMode
      ? liveError
      : scenarioError ??
        error ??
        analysisError;


  return (
    <div className="command-layout">

      <SourceSidebar
        scenarios={scenarios}
        selected={scenarioId}
        onSelect={selectScenario}
        liveCameras={liveCameras}
        selectedLiveCamera={
          selectedLiveCamera
        }
        onSelectLive={selectLive}
      />


      <main className="command-main">

        <section className="workspace-heading">
          <div>
            <span className="section-label">
              COMMAND CENTER
            </span>

            <h1>
              {cameraName}
            </h1>

            <p>
              Municipal traffic
              monitoring workspace
            </p>
          </div>

          <div className="recording-badge">
            <i />

            {liveMode
              ? "LIVE"
              : "RECORDED"}

            <small>
              {liveMode
                ? `${healthLabel} · Preview ${previewFps} FPS`
                : "Municipality Test Footage"}
            </small>
          </div>
        </section>


        {combinedError && (
          <div
            className="command-error"
            role="alert"
          >
            <span>
              {combinedError}
            </span>

            <button
              onClick={() => {
                if (liveMode) {
                  setLiveError(null);
                } else {
                  void refresh();
                  void refreshAnalysis();
                }
              }}
            >
              Retry
            </button>
          </div>
        )}


        <article className="feed-panel">

          <div className="feed-toolbar">

            <div>
              <span>
                {liveMode
                  ? liveView === "live"
                    ? "RAW LIVE CAMERA PREVIEW"
                    : "AI PROCESSED CAMERA FEED"
                  : "PROCESSED CAMERA FEED"}
              </span>

              <strong>
                {cameraName}
              </strong>
            </div>


            <div className="feed-toolbar-actions">

              {liveMode && (
                <div
                  className="live-view-toggle"
                  aria-label="Live camera view"
                >
                  <button
                    type="button"
                    className={
                      liveView ===
                      "live"
                        ? "active"
                        : ""
                    }
                    onClick={() =>
                      setLiveView(
                        "live"
                      )
                    }
                  >
                    LIVE VIEW
                  </button>

                  <button
                    type="button"
                    className={
                      liveView ===
                      "ai"
                        ? "active"
                        : ""
                    }
                    onClick={() =>
                      setLiveView(
                        "ai"
                      )
                    }
                  >
                    AI VIEW
                  </button>
                </div>
              )}


              <span
                className={`feed-state ${
                  (
                    liveMode
                      ? previewOnline
                      : summary?.status ===
                        "READY"
                  )
                    ? "ready"
                    : "waiting"
                }`}
              >
                {liveMode
                  ? healthLabel
                  : summary?.status ??
                    "CHECKING"}
              </span>


              <time>
                {liveMode
                  ? `Preview ${previewFps} · AI ${aiFps} FPS`
                  : `${videoTime.toFixed(1)}s`}
              </time>

            </div>
          </div>


          {liveMode &&
          selectedLiveCamera ? (
            <div className="command-stream">

              {previewOnline &&
              (liveView === "live" ||
                currentLiveMetrics) ? (
                <LiveMjpegImage
                  key={`${selectedLiveCamera}-${liveView}-${selectedHealth?.generation}-${selectedHealth?.last_connected_at}`}
                  cameraId={
                    selectedLiveCamera
                  }
                  mode={liveView}
                  className="command-video"
                  alt={
                    liveView ===
                    "live"
                      ? `Raw live preview for ${cameraName}`
                      : `AI processed view for ${cameraName}`
                  }
                />
              ) : (
                <div className="command-video-placeholder">
                  <span>
                    {previewOnline
                      ? "WAITING FOR AI — fresh analysis is unavailable."
                      : `${cameraName} is ${healthLabel.toLowerCase()}; no stale frame is shown.`}
                  </span>
                </div>
              )}

            </div>
          ) : summary?.annotated_video_available ? (

            <video
              key={scenarioId}
              className="command-video"
              controls
              preload="metadata"
              src={`/media/scenarios/${scenarioId}/annotated.mp4`}
              onPlay={(event) => {
                setAnalysisStarted(
                  true
                );

                setVideoTime(
                  event.currentTarget
                    .currentTime
                );
              }}
              onTimeUpdate={(event) =>
                setVideoTime(
                  event.currentTarget
                    .currentTime
                )
              }
              onSeeked={(event) => {
                setAnalysisStarted(
                  true
                );

                setVideoTime(
                  event.currentTarget
                    .currentTime
                );
              }}
              onEnded={(event) =>
                setVideoTime(
                  event.currentTarget
                    .currentTime
                )
              }
            >
              Your browser does not
              support MP4 video.
            </video>

          ) : (
            <div className="command-video-placeholder">
              <span>
                {summary?.message ??
                  "Checking real AI output files…"}
              </span>
            </div>
          )}


          <div className="feed-footer">

            <span>
              {liveMode
                ? liveView === "live"
                  ? "Raw source preview · independent from AI FPS"
                  : "Actual YOLO + ByteTrack output · runs at measured AI FPS"
                : "YOLO + ByteTrack annotated output"}
            </span>

            <span>
              Frame{" "}
              {displayedFrame?.frame ??
                "—"}
            </span>

            <span>
              {liveMode
                ? "Local DVR · server-side stream"
                : selectedScenario?.source_url ===
                    "user-provided"
                  ? "User-provided clip"
                  : "Licensed test footage"}
            </span>

          </div>

        </article>


        <section
          className="metric-strip"
          aria-label="Current traffic summary"
        >

          {[
            [
              "Vehicles",
              displayedFrame?.active_vehicle_count ??
                "—",
            ],
            [
              "Cars",
              displayedFrame?.cars ??
                "—",
            ],
            [
              "Buses",
              displayedFrame?.buses ??
                "—",
            ],
            [
              "Trucks",
              displayedFrame?.trucks ??
                "—",
            ],
            [
              "Motorcycles",
              displayedFrame?.motorcycles ??
                "—",
            ],
            [
              "People",
              displayedFrame?.people ??
                "—",
            ],
            [
              "Bicycles",
              displayedFrame?.bicycles ??
                "—",
            ],
            ...(liveMode
              ? [
                  [
                    "Tracks",
                    currentLiveMetrics?.active_track_count ??
                      "—",
                  ],
                ]
              : []),
          ].map(
            ([label, value]) => (
              <article
                key={label}
              >
                <span>
                  {label}
                </span>

                <strong>
                  {value}
                </strong>
              </article>
            )
          )}


          <article>
            <span>
              Traffic status
            </span>

            <strong
              className={`traffic-state ${trafficStatus
                .toLowerCase()
                .replace(
                  / /g,
                  "-"
                )}`}
            >
              {trafficStatus}
            </strong>
          </article>

        </section>


        <section className="data-note">

          <span>
            {liveMode
              ? currentLiveMetrics
                ? "REAL LIVE CAMERA DATA"
                : "WAITING FOR AI"
              : "REAL VIDEO-SYNCED DATA"}
          </span>

          <p>
            {liveMode
              ? currentLiveMetrics
                ? "Counts describe the latest fresh AI observation. Incident history is independent of current traffic."
                : "Live preview can continue while AI counts are unavailable. — means unknown; 0 means a fresh observation with no detections."
              : "Metrics update from the real AI analysis timeline as recorded footage plays. Traffic status is synchronized with the AI-computed state for the current video frame."}
          </p>

        </section>

      </main>


      <aside className="incident-rail">

        <div className="rail-heading">

          <div>
            <span>
              {liveMode
                ? "LIVE INCIDENTS"
                : "RECORDED INCIDENTS"}
            </span>

            <small>
              {liveMode
                ? "Real-time camera queue"
                : "Video-synchronized queue"}
            </small>
          </div>

          <b>
            {visibleEvents.length}
          </b>

        </div>


        {!liveMode &&
          loading && (
            <div className="rail-empty">
              Loading incidents…
            </div>
          )}


        {!liveMode &&
          !loading &&
          !analysisStarted && (
            <div className="rail-empty">
              <i>▶</i>

              <strong>
                Start recorded footage
              </strong>

              <span>
                Incidents will appear
                at their real video
                timestamp.
              </span>
            </div>
          )}


        {liveMode &&
          visibleEvents.length ===
            0 && (
            <div className="rail-empty">

              <strong>
                {liveError
                  ? "Incident queue unavailable"
                  : "No live incident"}
              </strong>

              <span>
                {liveError
                  ? "Saved incidents remain in the database."
                  : "The AI event queue is clear for this camera."}
              </span>

            </div>
          )}


        {!liveMode &&
          !loading &&
          analysisStarted &&
          visibleEvents.length ===
            0 && (
            <div className="rail-empty">

              <strong>
                No incident at this time
              </strong>

              <span>
                The AI event queue is
                clear for the current
                video position.
              </span>

            </div>
          )}


        <div className="rail-list">

          {visibleEvents.map(
            (event) => (
              <IncidentCard
                key={
                  event.event_id
                }
                event={event}
                scenarioId={
                  scenarioId
                }
                live={liveMode}
                canReview={
                  canReview
                }
                reviewing={
                  (liveMode
                    ? reviewingLiveId
                    : reviewingEventId) ===
                  event.event_id
                }
                onView={() =>
                  setSelectedEvent(
                    event
                  )
                }
                onDecision={(
                  decision
                ) =>
                  void decideOn(
                    event,
                    decision
                  )
                }
              />
            )
          )}

        </div>

      </aside>


      {selectedEvent && (
        <IncidentDetail
          event={selectedEvent}
          scenarioId={scenarioId}
          live={liveMode}
          evidenceSrc={
            liveMode &&
            selectedLiveCamera
              ? liveEvidenceUrl(
                  selectedLiveCamera,
                  selectedEvent.evidence_image
                )
              : undefined
          }
          canReview={canReview}
          reviewing={
            (liveMode
              ? reviewingLiveId
              : reviewingEventId) ===
            selectedEvent.event_id
          }
          onClose={() =>
            setSelectedEvent(
              null
            )
          }
          onDecision={(decision) =>
            void decideOn(
              selectedEvent,
              decision
            )
          }
        />
      )}

    </div>
  );
}