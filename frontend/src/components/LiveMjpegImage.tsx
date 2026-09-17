import { useEffect, useRef, useState } from "react";

const RETRY_DELAYS_MS = [500, 1_000, 2_000] as const;

type VisualStreamState = "LIVE" | "RECONNECTING" | "ERROR";

export function LiveMjpegImage({
  cameraId,
  alt,
  className,
  mode = "live",
}: {
  cameraId: string;
  alt: string;
  className?: string;
  mode?: "live" | "ai";
}) {
  const [retryToken, setRetryToken] = useState(0);
  const [streamState, setStreamState] = useState<VisualStreamState>("LIVE");
  const retryTimer = useRef<number | null>(null);
  const cameraGeneration = useRef(0);

  function clearRetryTimer() {
    if (retryTimer.current !== null) {
      window.clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  }

  useEffect(() => {
    cameraGeneration.current += 1;
    clearRetryTimer();
    setRetryToken(0);
    setStreamState("LIVE");
    return clearRetryTimer;
  }, [cameraId, mode]);

  function scheduleReconnect() {
    if (retryTimer.current !== null || streamState === "ERROR") return;
    if (retryToken >= RETRY_DELAYS_MS.length) {
      setStreamState("ERROR");
      return;
    }

    const expectedGeneration = cameraGeneration.current;
    setStreamState("RECONNECTING");
    retryTimer.current = window.setTimeout(() => {
      retryTimer.current = null;
      if (cameraGeneration.current !== expectedGeneration) return;
      setRetryToken((current) => current + 1);
    }, RETRY_DELAYS_MS[retryToken]);
  }

  function reconnectManually() {
    clearRetryTimer();
    setStreamState("RECONNECTING");
    setRetryToken((current) => current + 1);
  }

  const baseUrl = mode === "live"
    ? `/media/live-cameras/${encodeURIComponent(cameraId)}/preview.mjpg`
    : `/media/live-cameras/${encodeURIComponent(cameraId)}.mjpg`;
  const streamUrl = retryToken ? `${baseUrl}?retry=${retryToken}` : baseUrl;

  return (
    <>
      <img
        className={className}
        src={streamUrl}
        alt={alt}
        onError={scheduleReconnect}
        onLoad={() => {
          clearRetryTimer();
          setStreamState("LIVE");
        }}
      />
      {streamState !== "LIVE" && (
        <div className={`visual-stream-state ${streamState.toLowerCase()}`} role="status">
          <strong>Visual stream: {streamState}</strong>
          {streamState === "ERROR" && (
            <button type="button" onClick={reconnectManually}>Reconnect stream</button>
          )}
        </div>
      )}
    </>
  );
}
