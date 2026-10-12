// Line icons copied from the mock-ups (docs/ui_mockups/source/theme.py), so the app and the mock-ups match.
const PATHS: Record<string, string> = {
  pill: "<rect x=\"2.5\" y=\"8\" width=\"19\" height=\"8\" rx=\"4\" transform=\"rotate(-40 12 12)\"/><path d=\"M9.2 8.6l5.6 6.8\"/>",
  walk: "<circle cx=\"13\" cy=\"4.2\" r=\"1.7\"/><path d=\"M12.6 7.6l-2.2 5 3.2 2.8.9 5.2\"/><path d=\"M10.4 12.6L8 20.6\"/><path d=\"M12.6 8.2l-3.4 1.6-.9 3\"/><path d=\"M13.4 9.4l1.6 2.4 2.8.9\"/>",
  exercise: "<path d=\"M6.5 7v10M17.5 7v10M3.2 9.5v5M20.8 9.5v5M6.5 12h11\"/>",
  calendar: "<rect x=\"3.5\" y=\"5\" width=\"17\" height=\"15.5\" rx=\"2.5\"/><path d=\"M3.5 10h17M8 3v4M16 3v4\"/>",
  mic: "<rect x=\"9\" y=\"3\" width=\"6\" height=\"11\" rx=\"3\"/><path d=\"M5.5 11.5a6.5 6.5 0 0013 0M12 18v3\"/>",
  check: "<path d=\"M5 12.5l4.5 4.5L19 7.5\"/>",
  bell: "<path d=\"M6 16.5V11a6 6 0 0112 0v5.5l1.5 2h-15z\"/><path d=\"M10 21h4\"/>",
  alert: "<path d=\"M12 4l9 15.5H3z\"/><path d=\"M12 10v4.5M12 17.2v.3\"/>",
  doc: "<path d=\"M6.5 3h8l4 4v14h-12z\"/><path d=\"M14.5 3v4h4M9.5 12h6M9.5 16h6\"/>",
  stop: "<circle cx=\"12\" cy=\"12\" r=\"8.5\"/><path d=\"M6 18L18 6\"/>",
  lock: "<rect x=\"5\" y=\"10.5\" width=\"14\" height=\"10\" rx=\"2.5\"/><path d=\"M8.5 10.5V8a3.5 3.5 0 017 0v2.5\"/>",
  family: "<circle cx=\"8\" cy=\"8\" r=\"3\"/><circle cx=\"17\" cy=\"9.5\" r=\"2.3\"/><path d=\"M2.5 20a5.5 5.5 0 0111 0M14.5 20a4 4 0 017 -2.5\"/>",
  pilot: "<path d=\"M4 19.5h16M7 16V9.5M12 16V5M17 16v-4\"/>",
  upload: "<path d=\"M12 16V5M7.5 9.5L12 5l4.5 4.5M5 19.5h14\"/>",
  arrow: "<path d=\"M5 12h14M13 6l6 6-6 6\"/>",
  ring: "<circle cx=\"12\" cy=\"12\" r=\"8\"/>",
  dashed: "<circle cx=\"12\" cy=\"12\" r=\"8\" stroke-dasharray=\"3.6 3.6\"/>",
  code: "<path d=\"M8.5 7.5L4 12l4.5 4.5M15.5 7.5L20 12l-4.5 4.5\"/>",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 24, stroke = 1.8 }: { name: string; size?: number; stroke?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" dangerouslySetInnerHTML={{ __html: PATHS[name] || '' }} />;
}

// The AfterWard mark: a sun over a horizon. Colours come from the CSS, so it turns white on the red bar.
export function Logo({ size = 30 }: { size?: number }) {
  return <svg className="logo" width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
    <rect width="30" height="30" rx="9" fill="#B3264F" />
    <path d="M9.2 18.6a5.8 5.8 0 0111.6 0z" fill="#FFF6EC" />
    <path d="M6 22.2h18" stroke="#FFF6EC" strokeWidth="2.2" strokeLinecap="round" />
    <path d="M15 7v2.4M8.3 9.9l1.6 1.7M21.7 9.9l-1.6 1.7" stroke="#FFF6EC" strokeWidth="1.8" strokeLinecap="round" />
  </svg>;
}
