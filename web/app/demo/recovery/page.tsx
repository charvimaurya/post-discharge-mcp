'use client';
import { useEffect, useRef, useState } from 'react';
import '@fontsource/source-serif-4/400.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/600.css';
import '../afterward.css';
import './recovery.css';
import { type WeekSummary } from '../../../lib/week-summary';
import { fetchRecoverySnapshot, type RecoveryDay } from '../../../lib/recovery-dashboard';
import { RecoveryDashboard } from './dashboard';

export default function RecoveryPage() {
  const [week, setWeek] = useState<WeekSummary | null>(null);
  const [day, setDay] = useState<RecoveryDay | null>(null);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
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
  return <div className="awapp recovery-app"><RecoveryDashboard week={week} day={day} selected={selected}
    loading={loading} error={error} onSelect={setSelected} onRefresh={() => setRefresh(v => v + 1)} /></div>;
}
