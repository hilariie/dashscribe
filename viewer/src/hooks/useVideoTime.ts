import { useEffect, useState } from "react";

// rAF-driven currentTime tracker. The native 'timeupdate' event fires at
// ~250 ms intervals which is too coarse for sub-second subtitle alignment;
// requestAnimationFrame gives us per-frame accuracy while playing.
export function useVideoTime(videoEl: HTMLVideoElement | null): number {
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    if (!videoEl) return;
    let raf = 0;
    let active = true;

    const tick = () => {
      if (!active) return;
      setCurrentTime(videoEl.currentTime);
      raf = requestAnimationFrame(tick);
    };

    const onPlay = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };
    const onPauseOrEnd = () => {
      cancelAnimationFrame(raf);
      // Snap once on pause so seeking-while-paused still updates the UI.
      setCurrentTime(videoEl.currentTime);
    };
    const onSeek = () => setCurrentTime(videoEl.currentTime);

    videoEl.addEventListener("play", onPlay);
    videoEl.addEventListener("pause", onPauseOrEnd);
    videoEl.addEventListener("ended", onPauseOrEnd);
    videoEl.addEventListener("seeked", onSeek);
    videoEl.addEventListener("loadedmetadata", onSeek);

    if (!videoEl.paused) onPlay();

    return () => {
      active = false;
      cancelAnimationFrame(raf);
      videoEl.removeEventListener("play", onPlay);
      videoEl.removeEventListener("pause", onPauseOrEnd);
      videoEl.removeEventListener("ended", onPauseOrEnd);
      videoEl.removeEventListener("seeked", onSeek);
      videoEl.removeEventListener("loadedmetadata", onSeek);
    };
  }, [videoEl]);

  return currentTime;
}
