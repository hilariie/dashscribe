import { useCallback, useState, type DragEvent } from "react";

interface Props {
  onLoad: (
    videoUrl: string,
    sessionText: string,
    sessionName: string,
    audioUrl: string | null,
  ) => void;
  errorMessage?: string;
}

const VIDEO_EXTS = [".mp4", ".webm", ".mov", ".m4v"];
const SESSION_EXTS = [".jsonl", ".json", ".ndjson", ".txt"];
const AUDIO_EXTS = [".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"];

function classifyFile(file: File): "video" | "session" | "audio" | "unknown" {
  const lower = file.name.toLowerCase();
  if (VIDEO_EXTS.some((ext) => lower.endsWith(ext))) return "video";
  if (SESSION_EXTS.some((ext) => lower.endsWith(ext))) return "session";
  if (AUDIO_EXTS.some((ext) => lower.endsWith(ext))) return "audio";
  if (file.type.startsWith("video/")) return "video";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.includes("json") || file.type.includes("text")) return "session";
  return "unknown";
}

// Splash-screen file picker. Renders when no session is loaded yet (initial
// fetch failed or no query params provided). Three zones + drag-anywhere on
// the card. Files are routed by extension. The audio zone is optional —
// when present it carries the M4 TTS narration track.
export function FilePicker({ onLoad, errorMessage }: Props) {
  const [video, setVideo] = useState<File | null>(null);
  const [session, setSession] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const acceptFiles = useCallback((files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      const kind = classifyFile(file);
      if (kind === "video") setVideo(file);
      else if (kind === "session") setSession(file);
      else if (kind === "audio") setAudio(file);
    }
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) acceptFiles(e.dataTransfer.files);
    },
    [acceptFiles],
  );

  const handleSubmit = useCallback(async () => {
    if (!video || !session) return;
    try {
      const sessionText = await session.text();
      const videoUrl = URL.createObjectURL(video);
      const audioUrl = audio ? URL.createObjectURL(audio) : null;
      onLoad(videoUrl, sessionText, session.name, audioUrl);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Could not load files",
      );
    }
  }, [video, session, audio, onLoad]);

  const ready = video !== null && session !== null;

  return (
    <div
      className={`picker ${dragOver ? "picker--drag" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!dragOver) setDragOver(true);
      }}
      onDragLeave={(e) => {
        // Only clear when leaving the picker root, not its children.
        if (e.currentTarget === e.target) setDragOver(false);
      }}
      onDrop={handleDrop}
    >
      <div className="picker__inner">
        <span className="picker__eyebrow">Live VLM commentary</span>
        <h1 className="picker__title">Dashcam, narrated.</h1>
        <p className="picker__subtitle">Inspired by Wayve&rsquo;s LINGO-1.</p>

        {(errorMessage || submitError) && (
          <div className="picker__error">
            {errorMessage && <p>{errorMessage}</p>}
            {submitError && <p>{submitError}</p>}
          </div>
        )}

        <div className="picker__zones">
          <PickerZone
            label="Video"
            hint="MP4, MOV, WebM"
            accept="video/*"
            file={video}
            onPick={setVideo}
          />
          <PickerZone
            label="Session"
            hint="JSONL from capture.py"
            accept=".jsonl,.json,.ndjson,.txt,application/json,application/x-ndjson,text/plain"
            file={session}
            onPick={setSession}
          />
          <PickerZone
            label="TTS audio"
            hint="Optional .mp3 from render_tts.py"
            accept="audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac"
            file={audio}
            onPick={setAudio}
          />
        </div>

        <button
          className="picker__submit"
          type="button"
          disabled={!ready}
          onClick={handleSubmit}
        >
          Start playback
        </button>

        <p className="picker__hint">
          Or drop the files anywhere on this card.
        </p>
      </div>
    </div>
  );
}

function PickerZone({
  label,
  hint,
  accept,
  file,
  onPick,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onPick: (f: File) => void;
}) {
  const id = `picker-zone-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <label
      className={`picker-zone ${file ? "picker-zone--filled" : ""}`}
      htmlFor={id}
    >
      <div className="picker-zone__top">
        <span className="picker-zone__label">{label}</span>
        {file && <span className="picker-zone__check">●</span>}
      </div>
      <span className="picker-zone__hint">{file ? file.name : hint}</span>
      <input
        id={id}
        type="file"
        accept={accept}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPick(f);
        }}
      />
    </label>
  );
}
