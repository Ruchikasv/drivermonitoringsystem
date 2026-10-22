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
  Trash2,
  CheckCircle2,
  Smartphone,
  ShieldAlert,
  Info,
  Maximize2,
} from 'lucide-react';
import { incidentService } from '../../services/incidentService';
import { driverService } from '../../services/driverService';
import { vehicleService } from '../../services/vehicleService';

export default function OwnerIncidentsPage() {
  const [incidents, setIncidents] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('ALL');
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [evidenceBlobUrl, setEvidenceBlobUrl] = useState(null);
  const [rawEvidenceBlobUrl, setRawEvidenceBlobUrl] = useState(null);
  const [activeEvidenceView, setActiveEvidenceView] = useState('warning');
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchData = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      const [incData, driverData, vehData] = await Promise.all([
        incidentService.getIncidents(200),
        driverService.getDrivers(),
        vehicleService.getVehicles(),
      ]);
      setIncidents(incData || []);
      setDrivers(driverData || []);
      setVehicles(vehData || []);
    } catch (err) {
      console.error('Failed to load incidents data:', err);
    } finally {
      if (!isBackground) setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      fetchData(true);
    }, 4000);
    const onFocus = () => fetchData(true);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const openEvidenceModal = async (inc, view = 'warning') => {
    console.log(`[IncidentsPage] Opening evidence modal for incident #${inc.incident_id} (view=${view}) | has_evidence=${inc.has_evidence} | has_raw=${inc.has_raw_evidence} | has_warning=${inc.has_warning_evidence}`);
    setSelectedEvidence(inc);
    setActiveEvidenceView(view);
    setEvidenceLoading(true);
    setEvidenceError(null);
    if (evidenceBlobUrl) {
      URL.revokeObjectURL(evidenceBlobUrl);
      setEvidenceBlobUrl(null);
    }
    if (rawEvidenceBlobUrl) {
      URL.revokeObjectURL(rawEvidenceBlobUrl);
      setRawEvidenceBlobUrl(null);
    }
    try {
      const warningUrl = await incidentService.fetchEvidenceBlob(inc.incident_id, 'warning');
      console.log(`[IncidentsPage] ✅ Warning evidence blob URL created for incident #${inc.incident_id}`);
      setEvidenceBlobUrl(warningUrl);

      if (inc.has_raw_evidence) {
        try {
          const rawUrl = await incidentService.fetchEvidenceBlob(inc.incident_id, 'raw');
          console.log(`[IncidentsPage] ✅ Raw driver frame blob URL created for incident #${inc.incident_id}`);
          setRawEvidenceBlobUrl(rawUrl);
        } catch (rawErr) {
          console.warn('Could not load companion raw frame blob:', rawErr);
        }
      }
    } catch (err) {
      console.error('Failed to load evidence screenshot blob:', err);
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        setEvidenceError('Authentication failed: Session invalid or unauthorized fleet access.');
      } else if (status === 404) {
        setEvidenceError('Evidence file not found on disk or was previously removed.');
      } else {
        setEvidenceError(err.message || 'Failed to retrieve evidence screenshot.');
      }
    } finally {
      setEvidenceLoading(false);
    }
  };

  const closeEvidenceModal = () => {
    setSelectedEvidence(null);
    if (evidenceBlobUrl) {
      URL.revokeObjectURL(evidenceBlobUrl);
      setEvidenceBlobUrl(null);
    }
    if (rawEvidenceBlobUrl) {
      URL.revokeObjectURL(rawEvidenceBlobUrl);
      setRawEvidenceBlobUrl(null);
    }
    setEvidenceError(null);
  };

  const handleDeleteEvidence = async () => {
    if (!deleteTarget) return;
    try {
      setDeleting(true);
      await incidentService.deleteEvidence(deleteTarget.incident_id);
      setDeleteTarget(null);
      if (selectedEvidence?.incident_id === deleteTarget.incident_id) {
        closeEvidenceModal();
      }
      await fetchData();
    } catch (err) {
      console.error('Failed to delete evidence:', err);
      alert(err.message || 'Failed to delete evidence screenshot.');
    } finally {
      setDeleting(false);
    }
  };

  const filteredIncidents = incidents.filter((inc) => {
    if (filterType === 'ALL') return true;
    const evt = (inc.event_type || '').toUpperCase();
    if (filterType === 'ALCOHOL') {
      return evt.includes('ALCOHOL');
    }
    return evt === filterType;
  });

  // Group filtered incidents by driver_id
  const driversMap = {};
  drivers.forEach((d) => {
    driversMap[d.driver_id] = d;
  });

  const vehiclesMap = {};
  vehicles.forEach((v) => {
    vehiclesMap[v.vehicle_id] = v;
  });

  // Group incidents
  const groupedByDriver = {};
  filteredIncidents.forEach((inc) => {
    if (!groupedByDriver[inc.driver_id]) {
      groupedByDriver[inc.driver_id] = [];
    }
    groupedByDriver[inc.driver_id].push(inc);
  });

  const driverIdsWithIncidents = Object.keys(groupedByDriver).map(Number);

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Drowsiness Incidents & Evidence
          </h1>
          <p className="text-sm text-slate-400">
            Real-time biometric incident logs and Level-3 composite screenshot evidence organized by commercial driver.
          </p>
        </div>

        <button
          onClick={fetchData}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh Logs
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-3">
        {['ALL', 'ALCOHOL', 'DISTRACTION', 'CRITICAL', 'WARNING', 'NUDGE'].map((type) => (
          <button
            key={type}
            onClick={() => setFilterType(type)}
            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition ${
              filterType === type
                ? 'bg-cyan-500 text-slate-950 shadow-md'
                : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {type === 'ALL'
              ? 'All Incidents'
              : type === 'ALCOHOL'
              ? 'Alcohol Lockouts'
              : type === 'DISTRACTION'
              ? 'Distraction Events'
              : `${type} Alerts`}
          </button>
        ))}
      </div>

      {/* Incident List Grouped by Driver */}
      {loading ? (
        <div className="py-20 text-center text-slate-500 text-sm">
          <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Loading Fleet Incidents & Evidence...
        </div>
      ) : driverIdsWithIncidents.length === 0 ? (
        <div className="py-16 text-center bg-slate-900/50 border border-slate-800 rounded-3xl p-8">
          <div className="w-12 h-12 bg-emerald-500/10 text-emerald-400 rounded-2xl flex items-center justify-center mx-auto mb-3">
            <CheckCircle2 className="w-6 h-6" />
          </div>
          <h3 className="text-lg font-bold text-white mb-1">No Incidents Recorded</h3>
          <p className="text-xs text-slate-400">
            {filterType === 'ALL'
              ? 'No drowsiness alerts have been recorded by the system yet.'
              : `No ${filterType.toLowerCase()} incidents recorded.`}
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {driverIdsWithIncidents.map((dId) => {
            const driver = driversMap[dId];
            const driverName = driver ? driver.name : `Driver #${dId}`;
            const driverIncidents = groupedByDriver[dId];
            const defaultVehicle = driver?.vehicle?.registration_number || 'Unassigned Unit';

            return (
              <div
                key={dId}
                className="bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-5"
              >
                {/* Driver Section Header */}
                <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-11 h-11 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold text-sm">
                      #{dId}
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-white flex items-center gap-2">
                        <span>{driverName}</span>
                      </h2>
                      <div className="text-xs text-slate-400 flex items-center gap-2">
                        <Truck className="w-3.5 h-3.5 text-slate-500" />
                        <span className="font-mono text-slate-300 font-semibold">{defaultVehicle}</span>
                        <span className="text-slate-500">•</span>
                        <span>{driverIncidents.length} recorded event{driverIncidents.length > 1 ? 's' : ''}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Driver's Evidence Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {driverIncidents.map((inc) => {
                    const evt = (inc.event_type || '').toLowerCase();
                    const isAlcohol = evt.includes('alcohol');
                    const isDistraction = evt === 'distraction';
                    const isCrit = evt === 'critical';
                    const isWarn = evt === 'warning';
                    const badgeBg = isAlcohol
                      ? 'bg-rose-600/25 border-rose-500/60 text-rose-300 animate-pulse'
                      : isDistraction
                      ? 'bg-purple-500/15 border-purple-500/30 text-purple-400'
                      : isCrit
                      ? 'bg-rose-500/15 border-rose-500/30 text-rose-400'
                      : isWarn
                      ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                      : 'bg-cyan-500/15 border-cyan-500/30 text-cyan-400';

                    const vehicleObj = inc.vehicle_id ? vehiclesMap[inc.vehicle_id] : null;
                    const vehReg = vehicleObj ? vehicleObj.registration_number : defaultVehicle;

                    return (
                      <div
                        key={inc.incident_id}
                        className={`bg-slate-950 border rounded-2xl p-4 flex flex-col justify-between hover:border-slate-700 transition ${
                          isAlcohol ? 'border-rose-600/50 shadow-lg shadow-rose-950/30' : 'border-slate-800/80'
                        }`}
                      >
                        <div>
                          {/* Incident Header */}
                          <div className="flex items-center justify-between mb-3">
                            <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border uppercase tracking-wide flex items-center gap-1.5 ${badgeBg}`}>
                              {isAlcohol && <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />}
                              {isDistraction && <Smartphone className="w-3.5 h-3.5" />}
                              {isCrit && <Flame className="w-3.5 h-3.5" />}
                              {isWarn && <AlertTriangle className="w-3.5 h-3.5" />}
                              {isAlcohol
                                ? 'CRITICAL: ALCOHOL LOCKOUT'
                                : isDistraction
                                ? `Distraction: ${inc.distraction_type || 'Phone'}`
                                : `Level ${inc.alert_level}: ${inc.event_type}`}
                            </span>
                            <span className="text-[11px] text-slate-500 font-mono">
                              #{inc.incident_id}
                            </span>
                          </div>

                          {/* Timestamp & Vehicle */}
                          <div className="text-xs text-slate-400 space-y-1 mb-3">
                            <div className="flex items-center gap-1.5">
                              <Clock className="w-3.5 h-3.5 text-slate-500" />
                              <span>{new Date(inc.timestamp).toLocaleString()}</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                              <Truck className="w-3.5 h-3.5 text-slate-500" />
                              <span className="font-mono text-slate-300">{vehReg}</span>
                            </div>
                          </div>

                          {/* Telemetry Snapshot */}
                          <div className="bg-slate-900 border border-slate-800 rounded-xl p-2.5 text-xs mb-4 font-mono">
                            {isAlcohol ? (
                              <div className="space-y-1.5">
                                <div>
                                  <span className="text-slate-500 block text-[10px]">MQ-3 SENSOR TELEMETRY</span>
                                  <span className="text-rose-300 font-bold">
                                    {inc.distraction_type || 'Potential Alcohol Vapor Detected'}
                                  </span>
                                </div>
                                <div className="text-[11px] text-slate-400 font-sans">
                                  Safety interlock engaged (HTTP 423). Vehicle ignition restricted.
                                </div>
                              </div>
                            ) : (
                              <div className="grid grid-cols-2 gap-2">
                                {isDistraction ? (
                                  <>
                                    <div>
                                      <span className="text-slate-500 block text-[10px]">CATEGORY</span>
                                      <span className="text-purple-300 font-bold capitalize">
                                        {inc.distraction_type || 'Phone visual'}
                                      </span>
                                    </div>
                                    <div>
                                      <span className="text-slate-500 block text-[10px]">DURATION</span>
                                      <span className="text-purple-400 font-bold">
                                        {inc.duration_seconds ? `${inc.duration_seconds.toFixed(1)}s` : '≥2.0s'}
                                      </span>
                                    </div>
                                  </>
                                ) : (
                                  <>
                                    <div>
                                      <span className="text-slate-500 block text-[10px]">EAR</span>
                                      <span className={inc.ear < 0.21 ? 'text-rose-400 font-bold' : 'text-slate-200'}>
                                        {inc.ear?.toFixed(3) || 'N/A'}
                                      </span>
                                    </div>
                                    <div>
                                      <span className="text-slate-500 block text-[10px]">MAR</span>
                                      <span className={inc.mar > 0.55 ? 'text-amber-400 font-bold' : 'text-slate-200'}>
                                        {inc.mar?.toFixed(3) || 'N/A'}
                                      </span>
                                    </div>
                                  </>
                                )}
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
                            )}
                          </div>
                        </div>

                        {/* Evidence Actions & Previews */}
                        <div>
                          {inc.has_evidence ? (
                            <div className="space-y-2.5">
                              {/* Responsive Thumbnail(s) */}
                              {inc.has_raw_evidence && inc.has_warning_evidence ? (
                                <div className="grid grid-cols-2 gap-2">
                                  {/* 1. Captured Driver Frame Thumbnail */}
                                  <div
                                    onClick={() => openEvidenceModal(inc, 'raw')}
                                    className="group relative cursor-pointer overflow-hidden rounded-xl border border-cyan-500/30 bg-slate-900 aspect-video hover:border-cyan-400 transition shadow-sm"
                                    title="Click to view captured driver camera frame"
                                  >
                                    <img
                                      src={incidentService.getEvidenceUrl(inc.incident_id, 'raw')}
                                      alt={`Driver Camera Capture #${inc.incident_id}`}
                                      className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                                      loading="lazy"
                                    />
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-transparent flex items-end p-1.5">
                                      <span className="text-[10px] font-bold text-cyan-300 flex items-center gap-1 drop-shadow">
                                        <Camera className="w-3 h-3 text-cyan-400" /> Driver Frame
                                      </span>
                                    </div>
                                  </div>

                                  {/* 2. Lockout Warning Screenshot Thumbnail */}
                                  <div
                                    onClick={() => openEvidenceModal(inc, 'warning')}
                                    className="group relative cursor-pointer overflow-hidden rounded-xl border border-rose-500/40 bg-slate-900 aspect-video hover:border-rose-400 transition shadow-sm"
                                    title="Click to view alcohol lockout warning screenshot"
                                  >
                                    <img
                                      src={incidentService.getEvidenceUrl(inc.incident_id, 'warning')}
                                      alt={`Warning Screenshot #${inc.incident_id}`}
                                      className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                                      loading="lazy"
                                    />
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-transparent to-transparent flex items-end p-1.5">
                                      <span className="text-[10px] font-bold text-rose-300 flex items-center gap-1 drop-shadow">
                                        <ShieldAlert className="w-3 h-3 text-rose-400" /> Warning Overlay
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                /* Single Evidence Thumbnail */
                                <div
                                  onClick={() => openEvidenceModal(inc, inc.has_raw_evidence ? 'raw' : 'warning')}
                                  className="group relative cursor-pointer overflow-hidden rounded-xl border border-slate-800 bg-slate-900 aspect-video hover:border-cyan-500/50 transition shadow-sm"
                                  title="Click to expand evidence screenshot"
                                >
                                  <img
                                    src={incidentService.getEvidenceUrl(inc.incident_id, inc.has_raw_evidence ? 'raw' : 'primary')}
                                    alt={`Incident #${inc.incident_id} Evidence`}
                                    className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                                    loading="lazy"
                                  />
                                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent flex items-end p-2 justify-between">
                                    <span className="text-[10px] font-bold text-slate-200 flex items-center gap-1 drop-shadow">
                                      <Camera className="w-3 h-3 text-cyan-400" />
                                      {isAlcohol ? 'Lockout Warning Evidence' : 'Level 3 Capture'}
                                    </span>
                                    <span className="text-[10px] text-cyan-400 font-bold bg-slate-950/80 px-1.5 py-0.5 rounded border border-cyan-500/30">
                                      Expand
                                    </span>
                                  </div>
                                </div>
                              )}

                              {/* Action Buttons */}
                              <div className="flex gap-2">
                                <button
                                  onClick={() => openEvidenceModal(inc, inc.has_raw_evidence ? 'raw' : 'warning')}
                                  className="flex-1 py-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5"
                                >
                                  <Maximize2 className="w-3.5 h-3.5" /> View Evidence
                                </button>
                                <button
                                  onClick={() => setDeleteTarget(inc)}
                                  className="px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition flex items-center justify-center"
                                  title="Delete Evidence Screenshot"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div className="text-center py-2 px-3 bg-slate-900/40 rounded-xl border border-slate-800/60 text-xs text-slate-500 italic flex items-center justify-center gap-1.5">
                              {inc.evidence_status === 'REMOVED' || (inc.evidence_path && !inc.has_evidence) ? (
                                <>
                                  <Trash2 className="w-3.5 h-3.5 text-slate-500" />
                                  <span>Evidence file removed</span>
                                </>
                              ) : (
                                <>
                                  <Info className="w-3.5 h-3.5 text-slate-500" />
                                  <span>
                                    {isAlcohol
                                      ? 'No camera capture during lockout'
                                      : inc.alert_level < 3
                                      ? 'Level 1/2: No screenshot captured'
                                      : 'No screenshot captured'}
                                  </span>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
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
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-rose-500/10 text-rose-400 border border-rose-500/20">
                    Level {selectedEvidence.alert_level} {selectedEvidence.event_type}
                  </span>
                </h3>
                <p className="text-xs text-slate-400">
                  Recorded at {new Date(selectedEvidence.timestamp).toLocaleString()}
                </p>
              </div>

              <button
                onClick={closeEvidenceModal}
                className="p-2 text-slate-400 hover:text-white rounded-xl bg-slate-800 hover:bg-slate-700 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Evidence Selector Tabs if dual screenshots exist */}
            {selectedEvidence.has_raw_evidence && selectedEvidence.has_warning_evidence && (
              <div className="flex items-center gap-2 px-5 pt-3 bg-slate-900 border-b border-slate-800">
                <button
                  onClick={() => setActiveEvidenceView('raw')}
                  className={`px-4 py-2 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 ${
                    activeEvidenceView === 'raw'
                      ? 'text-cyan-400 border-cyan-400 bg-slate-950/60'
                      : 'text-slate-400 border-transparent hover:text-white'
                  }`}
                >
                  <Camera className="w-3.5 h-3.5" /> Captured Driver Frame
                </button>
                <button
                  onClick={() => setActiveEvidenceView('warning')}
                  className={`px-4 py-2 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 ${
                    activeEvidenceView === 'warning'
                      ? 'text-rose-400 border-rose-400 bg-slate-950/60'
                      : 'text-slate-400 border-transparent hover:text-white'
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5" /> Lockout Warning Overlay
                </button>
              </div>
            )}

            {/* Evidence Image Viewport */}
            <div className="p-6 bg-slate-950 min-h-[320px] flex flex-col items-center justify-center">
              {evidenceLoading ? (
                <div className="text-center py-12 text-slate-400 text-xs">
                  <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  Authenticating & loading evidence screenshot...
                </div>
              ) : evidenceError ? (
                <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl text-rose-400 text-xs max-w-md text-center">
                  <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-rose-500" />
                  <p className="font-semibold mb-1">Unable to Display Evidence</p>
                  <p className="text-slate-400">{evidenceError}</p>
                </div>
              ) : (activeEvidenceView === 'raw' ? rawEvidenceBlobUrl || evidenceBlobUrl : evidenceBlobUrl || rawEvidenceBlobUrl) ? (
                <div className="space-y-2 text-center">
                  <img
                    src={activeEvidenceView === 'raw' ? rawEvidenceBlobUrl || evidenceBlobUrl : evidenceBlobUrl || rawEvidenceBlobUrl}
                    alt={`Incident #${selectedEvidence.incident_id} Evidence Screenshot`}
                    className="max-h-[60vh] w-auto rounded-2xl border border-slate-800 shadow-2xl object-contain mx-auto"
                  />
                  <span className="text-[11px] text-slate-400 font-medium">
                    {activeEvidenceView === 'raw'
                      ? 'Live camera frame captured at moment of sensor event'
                      : 'Styled composite warning screenshot with telemetry and lockout overlay'}
                  </span>
                </div>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 flex justify-between items-center bg-slate-900">
              <button
                onClick={() => {
                  setDeleteTarget(selectedEvidence);
                }}
                className="px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-xl text-xs font-bold transition flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete Screenshot
              </button>

              <button
                onClick={closeEvidenceModal}
                className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Evidence Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-7 max-w-md w-full text-center shadow-2xl animate-in zoom-in-95">
            <div className="w-12 h-12 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/30 flex items-center justify-center mx-auto mb-4">
              <Trash2 className="w-6 h-6" />
            </div>

            <h3 className="text-xl font-bold text-white mb-2">Delete Evidence Screenshot?</h3>
            <p className="text-xs text-slate-400 leading-relaxed mb-6">
              This will permanently delete the physical screenshot image file from disk and clear the evidence reference for Incident #{deleteTarget.incident_id}. The numerical incident metrics will remain in the database for safety reporting.
            </p>

            <div className="flex gap-3 justify-center">
              <button
                disabled={deleting}
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-300 bg-slate-800 hover:bg-slate-700 rounded-xl transition"
              >
                Cancel
              </button>
              <button
                disabled={deleting}
                onClick={handleDeleteEvidence}
                className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-500 rounded-xl transition flex items-center gap-1.5"
              >
                {deleting ? 'Deleting...' : 'Yes, Delete Evidence'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
