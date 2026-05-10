import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CommentaryLog } from "./components/CommentaryLog";
import { FilePicker } from "./components/FilePicker";
import { VideoStage } from "./components/VideoStage";
import { useActiveDisplay } from "./hooks/useActiveDisplay";
import { useAudioSync } from "./hooks/useAudioSync";
import { useVideoTime } from "./hooks/useVideoTime";
import { buildDisplayTrack } from "./lib/displayTrack";
import {
  cadenceFromEntries,
  inferTtsPath,
  parseJsonl,
  SessionParseError,
} from "./lib/session";
import type { SessionEntry } from "./types";

interface QueryParams {
  videoUrl: string | null;
  sessionUrl: string | null;
}

function readQuery(): QueryParams {
  const params = new URLSearchParams(window.location.search);
  return {
    videoUrl: params.get("video"),
    sessionUrl: params.get("session"),
  };
}

type LoadState =
  | { kind: "loading" }
  | { kind: "picker"; reason?: string }
  | {
      kind: "ready";
      entries: SessionEntry[];
      videoUrl: string;
      audioUrl: string | null;
    };

export function App() {
  const { videoUrl, sessionUrl } = useMemo(readQuery, []);
  // Default route always shows the picker. Query params (?video=...&session=...)
  // are an explicit override that skips the picker on success.
  const [load, setLoad] = useState<LoadState>(() =>
    videoUrl && sessionUrl ? { kind: "loading" } : { kind: "picker" },
  );

  useEffect(() => {
    if (!videoUrl || !sessionUrl) return;
    let cancelled = false;
    const ttsUrl = inferTtsPath(sessionUrl);
    Promise.all([
      fetch(sessionUrl).then(async (resp) => {
        if (!resp.ok) {
          throw new Error(
            `failed to load session JSONL (${resp.status} ${resp.statusText})`,
          );
        }
        return parseJsonl(await resp.text());
      }),
      // HEAD-equivalent: a GET that resolves to ok|fail without throwing.
      // The audio is optional — a 404 just means no narration was rendered.
      fetch(ttsUrl, { method: "HEAD" })
        .then((resp) => (resp.ok ? ttsUrl : null))
        .catch(() => null),
    ])
      .then(([entries, audioUrl]) => {
        if (cancelled) return;
        if (entries.length === 0) {
          setLoad({
            kind: "picker",
            reason: `Session at ${sessionUrl} is empty.`,
          });
        } else {
          setLoad({ kind: "ready", entries, videoUrl, audioUrl });
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const reason =
          err instanceof SessionParseError
            ? `Could not parse ${sessionUrl}: ${err.message}`
            : err instanceof Error
              ? err.message
              : "unknown error";
        setLoad({ kind: "picker", reason });
      });
    return () => {
      cancelled = true;
    };
  }, [sessionUrl, videoUrl]);

  const onPickerLoad = useCallback(
    (
      pickedVideoUrl: string,
      sessionText: string,
      sessionName: string,
      pickedAudioUrl: string | null,
    ) => {
      try {
        const entries = parseJsonl(sessionText);
        if (entries.length === 0) {
          setLoad({
            kind: "picker",
            reason: `${sessionName} contains no entries.`,
          });
          return;
        }
        setLoad({
          kind: "ready",
          entries,
          videoUrl: pickedVideoUrl,
          audioUrl: pickedAudioUrl,
        });
      } catch (err) {
        setLoad({
          kind: "picker",
          reason:
            err instanceof SessionParseError
              ? `Could not parse ${sessionName}: ${err.message}`
              : err instanceof Error
                ? err.message
                : "unknown parse error",
        });
      }
    },
    [],
  );

  if (load.kind === "loading") {
    return <div className="app-bootstrap" />;
  }
  if (load.kind === "picker") {
    return <FilePicker onLoad={onPickerLoad} errorMessage={load.reason} />;
  }
  return (
    <AppLoaded
      entries={load.entries}
      videoUrl={load.videoUrl}
      audioUrl={load.audioUrl}
    />
  );
}

function AppLoaded({
  entries,
  videoUrl,
  audioUrl,
}: {
  entries: SessionEntry[];
  videoUrl: string;
  audioUrl: string | null;
}) {
  const [splashVisible, setSplashVisible] = useState(true);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const [audioEl, setAudioEl] = useState<HTMLAudioElement | null>(null);

  useEffect(() => {
    setVideoEl(videoRef.current);
  }, []);

  useEffect(() => {
    setAudioEl(audioRef.current);
  }, [audioUrl]);

  useAudioSync(videoEl, audioEl);

  const cadenceS = useMemo(() => cadenceFromEntries(entries), [entries]);
  const track = useMemo(() => buildDisplayTrack(entries), [entries]);
  const currentTime = useVideoTime(videoEl);
  const { active } = useActiveDisplay(track, currentTime);

  const recentEntry = useMemo<SessionEntry | null>(() => {
    if (entries.length === 0) return null;
    if (currentTime < entries[0].capture_t_s) return null;
    let lo = 0;
    let hi = entries.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >>> 1;
      if (entries[mid].capture_t_s <= currentTime) lo = mid;
      else hi = mid - 1;
    }
    return entries[lo];
  }, [entries, currentTime]);

  const visibleCount = useMemo(() => {
    if (entries.length === 0) return 0;
    let lo = 0;
    let hi = entries.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (entries[mid].capture_t_s <= currentTime) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  }, [entries, currentTime]);

  return (
    <div className="app">
      <VideoStage
        ref={videoRef}
        videoSrc={videoUrl}
        audioSrc={audioUrl}
        audioRef={audioRef}
        active={active}
        recentEntry={recentEntry}
        cadenceS={cadenceS}
        framesAnalysed={visibleCount}
        splashVisible={splashVisible}
        onLoadedData={() => {
          window.setTimeout(() => setSplashVisible(false), 250);
        }}
      />
      <CommentaryLog
        entries={entries}
        visibleCount={visibleCount}
        active={active}
      />
    </div>
  );
}
