'use client';
import { useEffect, useRef, useState } from 'react';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/source-serif-4/600.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-sans/700.css';
import '../afterward.css';
import './recovery.css';
import { type WeekSummary } from '../../../lib/week-summary';
import { fetchRecoverySnapshot, type RecoveryDay } from '../../../lib/recovery-dashboard';
import { readToday } from '../../../lib/assistant-data';
import { Screen, TopBar, useFitFrame } from '../parts';
import { RecoveryDashboard } from './dashboard';

export default function RecoveryPage() {
  const frame = useFitFrame();
  const [week, setWeek] = useState<WeekSummary | null>(null);
  const [day, setDay] = useState<RecoveryDay | null>(null);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  // The top bar shows the same demo clock and patient name as Today; it stays blank if Today cannot be read.
  const [header, setHeader] = useState<{ clock: string; patient: string | null }>({ clock: '', patient: null });
  const sequence = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/today', { cache: 'no-store', signal: controller.signal })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) { const t = readToday(data); setHeader({ clock: t.clockLabel, patient: t.firstName }); } })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    let disposed = false;
    const controllers = new Set<AbortController>();
    async function load() {
      const request = ++sequence.current;
      const controller = new AbortController(); controllers.add(controller);
      setLoading(true);
      try {
        const { week: next, day: nextDay, date } = await fetchRecoverySnapshot(selected, controller.signal);
        if (!disposed && request === sequence.current) {
          setWeek(next); setDay(nextDay); setSelected(date); setError(false);
        }
      } catch {
        if (!disposed && request === sequence.current) { setError(true); setDay(null); }
      } finally {
        controllers.delete(controller);
        if (!disposed && request === sequence.current) setLoading(false);
      }
    }
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { disposed = true; clearInterval(timer); controllers.forEach(c => c.abort()); };
  }, [selected, refresh]);
  return <div className="awapp"><div className="aw-viewport">
    <div className="aw-frame" style={{ width: frame.width, height: frame.height, transform: `scale(${frame.scale})` }}>
      <Screen id="recovery">
        <TopBar clock={header.clock} patient={header.patient} />
        <RecoveryDashboard week={week} day={day} selected={selected} loading={loading} error={error}
          onSelect={setSelected} onRefresh={() => setRefresh(v => v + 1)} />
      </Screen>
    </div>
  </div></div>;
}
