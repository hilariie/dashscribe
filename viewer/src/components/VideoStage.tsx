import { forwardRef, type Ref } from "react";
import type { DisplayEntry, SessionEntry } from "../types";
import { HUD } from "./HUD";
import { SubtitleOverlay } from "./SubtitleOverlay";
import { Splash } from "./Splash";

interface Props {
  videoSrc: string;
  audioSrc: string | null;
  audioRef: Ref<HTMLAudioElement>;
  active: DisplayEntry | null;
  recentEntry: SessionEntry | null;
  cadenceS: number;
  framesAnalysed: number;
  splashVisible: boolean;
  onLoadedData: () => void;
}

// Owns the <video> element ref, with HUD overlaid at the top, subtitle
// overlay at the bottom, and the splash card fading away on first play.
// When `audioSrc` is set, a hidden <audio> sibling carries the M4 TTS track;
// useAudioSync in App.tsx mirrors video state into it.
export const VideoStage = forwardRef<HTMLVideoElement, Props>(
  function VideoStage(
    {
      videoSrc,
      audioSrc,
      audioRef,
      active,
      recentEntry,
      cadenceS,
      framesAnalysed,
      splashVisible,
      onLoadedData,
    },
    ref,
  ) {
    return (
      <div className="video-stage">
        <video
          ref={ref}
          className="video-stage__video"
          src={videoSrc}
          controls
          playsInline
          preload="auto"
          onLoadedData={onLoadedData}
        />
        {audioSrc && (
          <audio
            ref={audioRef}
            src={audioSrc}
            preload="auto"
            style={{ display: "none" }}
          />
        )}
        <HUD
          cadenceS={cadenceS}
          framesAnalysed={framesAnalysed}
          active={active}
          recentEntry={recentEntry}
        />
        <SubtitleOverlay active={active} />
        <Splash visible={splashVisible} />
      </div>
    );
  },
);
