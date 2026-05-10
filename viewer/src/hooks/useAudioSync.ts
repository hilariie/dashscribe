import { useEffect } from "react";

const DRIFT_SNAP_S = 0.2;

// Mirror video playback state to a sibling <audio> element. The video is the
// authority; on play/pause/seek/ratechange the audio follows. A coarse drift
// snap covers cases where one element pauses to buffer.
export function useAudioSync(
  videoEl: HTMLVideoElement | null,
  audioEl: HTMLAudioElement | null,
): void {
  useEffect(() => {
    if (!videoEl || !audioEl) return;

    const snap = () => {
      if (Math.abs(audioEl.currentTime - videoEl.currentTime) > DRIFT_SNAP_S) {
        audioEl.currentTime = videoEl.currentTime;
      }
    };

    const onPlay = () => {
      snap();
      audioEl.playbackRate = videoEl.playbackRate;
      audioEl.play().catch(() => {
        // Autoplay rejected (no user gesture yet) — the video play() that
        // triggered this also requires the gesture, so the next user-driven
        // play will resolve it. Stay silent.
      });
    };
    const onPause = () => {
      audioEl.pause();
      snap();
    };
    const onEnded = () => audioEl.pause();
    const onSeeked = () => {
      audioEl.currentTime = videoEl.currentTime;
    };
    const onRateChange = () => {
      audioEl.playbackRate = videoEl.playbackRate;
    };

    videoEl.addEventListener("play", onPlay);
    videoEl.addEventListener("pause", onPause);
    videoEl.addEventListener("ended", onEnded);
    videoEl.addEventListener("seeked", onSeeked);
    videoEl.addEventListener("ratechange", onRateChange);

    if (!videoEl.paused) onPlay();

    return () => {
      videoEl.removeEventListener("play", onPlay);
      videoEl.removeEventListener("pause", onPause);
      videoEl.removeEventListener("ended", onEnded);
      videoEl.removeEventListener("seeked", onSeeked);
      videoEl.removeEventListener("ratechange", onRateChange);
    };
  }, [videoEl, audioEl]);
}
