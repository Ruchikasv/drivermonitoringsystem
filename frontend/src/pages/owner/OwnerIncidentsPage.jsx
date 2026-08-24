import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Flame,
  Eye,
  Camera,
  Calendar,
  User,
  Truck,
  RefreshCw,
  ExternalLink,
  X,
  Clock,
  Filter,
} from 'lucide-react';
import { incidentService } from '../../services/incidentService';

export default function OwnerIncidentsPage() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('ALL');
  const [selectedEvidence, setSelectedEvidence] = useState(null);

  const fetchIncidents = async () => {
    setLoading(true);
    try {
      const data = await incidentService.getIncidents(100);
      setIncidents(data);
    } catch (err) {
      console.error('Failed to load incidents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
  }, []);

  const filteredIncidents = incidents.filter((inc) => {
    if (filterType === 'ALL') return true;
    return inc.event_type.toUpperCase() === filterType;
  });

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Drowsiness Incidents & Evidence
          </h1>
          <p className="text-sm text-slate-400">
            Real-time biometric incident logs and composite screenshot evidence captured during commercial trips.
          </p>
        </div>

        <button
          onClick={fetchIncidents}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Logs
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-3">
        {['ALL', 'CRITICAL', 'WARNING', 'NUDGE'].map((type) => (
          <button
            key={type}
            onClick={() => setFilterType(type)}
            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition ${
              filterType === type
                ? 'bg-cyan-500 text-slate-950 shadow-md'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {type === 'ALL' ? 'All Incidents' : `${type} Alerts`}
          </button>
        ))}
      </div>

      {/* Incident List / Table */}
      {loading ? (
        <div className="py-20 text-center text-slate-500 text-sm">
          <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Loading Fleet Incidents...
        </div>
      ) : filteredIncidents.length === 0 ? (
        <div className="py-16 text-center bg-slate-900/50 border border-slate-800 rounded-3xl p-8">
          <div className="w-12 h-12 bg-emerald-500/10 text-emerald-400 rounded-2xl flex items-center justify-center mx-auto mb-3">
            <Camera className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-bold text-white mb-1">No Incidents Recorded</h3>
          <p className="text-xs text-slate-400">
            {filterType === 'ALL'
              ? 'No drowsiness alerts have been recorded by the system yet.'
              : `No ${filterType.toLowerCase()} incidents recorded.`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredIncidents.map((inc) => {
            const isCrit = inc.event_type.toLowerCase() === 'critical';
            const isWarn = inc.event_type.toLowerCase() === 'warning';

            const badgeBg = isCrit
              ? 'bg-rose-500/15 border-rose-500/30 text-rose-400'
              : isWarn
              ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
              : 'bg-cyan-500/15 border-cyan-500/30 text-cyan-400';

            return (
              <div
                key={inc.incident_id}
                className="bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-3xl p-5 flex flex-col justify-between transition-all hover:shadow-xl group"
              >
                <div>
                  {/* Top line badge */}
                  <div className="flex items-center justify-between mb-4">
                    <span className={`px-3 py-1 rounded-full text-[11px] font-bold border uppercase tracking-wide flex items-center gap-1.5 ${badgeBg}`}>
                      {isCrit && <Flame className="w-3.5 h-3.5" />}
                      {isWarn && <AlertTriangle className="w-3.5 h-3.5" />}
                      Level {inc.alert_level}: {inc.event_type}
                    </span>
                    <span className="text-[11px] text-slate-500 font-mono">
                      #{inc.incident_id}
                    </span>
                  </div>

                  {/* Driver & Vehicle */}
                  <div className="space-y-1 mb-4">
                    <div className="text-sm font-bold text-white flex items-center gap-2">
                      <User className="w-3.5 h-3.5 text-slate-400" />
                      <span>Driver #{inc.driver_id}</span>
                    </div>
                    <div className="text-xs text-slate-400 flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span>{new Date(inc.timestamp).toLocaleString()}</span>
                    </div>
                  </div>

                  {/* Telemetry Snapshot */}
                  <div className="bg-slate-950/80 border border-slate-800/80 rounded-2xl p-3.5 grid grid-cols-2 gap-2 text-xs mb-4 font-mono">
                    <div>
                      <span className="text-slate-500 block text-[10px]">EAR</span>
                      <span className={inc.ear < 0.21 ? 'text-rose-400 font-bold' : 'text-slate-200'}>
                        {inc.ear?.toFixed(3) || 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">MAR (Yawn)</span>
                      <span className={inc.mar > 0.55 ? 'text-amber-400 font-bold' : 'text-slate-200'}>
                        {inc.mar?.toFixed(3) || 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">PERCLOS</span>
                      <span className="text-slate-200">
                        {inc.perclos ? `${(inc.perclos * 100).toFixed(1)}%` : 'N/A'}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">KSS Score</span>
                      <span className="text-cyan-400 font-bold">
                        {inc.kss_score?.toFixed(1) || 'N/A'} / 9.0
                      </span>
                    </div>
                  </div>
                </div>

                {/* Evidence Button */}
                <div>
                  {inc.has_evidence ? (
                    <button
                      onClick={() => setSelectedEvidence(inc)}
                      className="w-full py-2.5 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-xl text-xs font-bold transition flex items-center justify-center gap-2"
                    >
                      <Camera className="w-3.5 h-3.5" /> View Evidence Screenshot
                    </button>
                  ) : (
                    <div className="text-center py-2 text-xs text-slate-600 italic">
                      No screenshot captured
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Evidence Viewer Modal */}
      {selectedEvidence && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-4xl w-full overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <span>Incident Evidence #{selectedEvidence.incident_id}</span>
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    {selectedEvidence.event_type}
                  </span>
                </h3>
                <p className="text-xs text-slate-400">
                  Recorded at {new Date(selectedEvidence.timestamp).toLocaleString()}
                </p>
              </div>

              <button
                onClick={() => setSelectedEvidence(null)}
                className="p-2 text-slate-400 hover:text-white rounded-xl bg-slate-800 hover:bg-slate-700 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Evidence Image Viewport */}
            <div className="p-6 bg-slate-950 flex flex-col items-center justify-center">
              <img
                src={incidentService.getEvidenceUrl(selectedEvidence.incident_id)}
                alt="Drowsiness Incident Evidence"
                className="max-h-[60vh] w-auto rounded-2xl border border-slate-800 shadow-2xl object-contain"
              />
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 flex justify-between items-center bg-slate-900">
              <div className="text-xs text-slate-400 font-mono">
                Storage: {selectedEvidence.evidence_path}
              </div>
              <button
                onClick={() => setSelectedEvidence(null)}
                className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
