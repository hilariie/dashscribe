interface Props {
  visible: boolean;
}

// Title-card overlay shown until the video's first frame has loaded. Fades
// out via CSS when `visible` flips false.
export function Splash({ visible }: Props) {
  return (
    <div className={`splash ${visible ? "" : "splash--hidden"}`}>
      <div className="splash__inner">
        <span className="splash__eyebrow">Live VLM commentary</span>
        <h1 className="splash__title">Dashcam, narrated.</h1>
        <p className="splash__subtitle">
          Inspired by Wayve&rsquo;s LINGO-1.
        </p>
      </div>
    </div>
  );
}
