import React, { useState, useEffect, useMemo } from 'react';
import {
  Truck,
  User,
  Plus,
  Pencil,
  Trash2,
  Save,
  RotateCcw,
  Search,
  AlertCircle,
  CheckCircle,
  X,
  GripVertical,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import { vehicleService } from '../services/vehicleService';
import { driverService } from '../services/driverService';

export default function VehicleManagementPage() {
  // Server-synced state
  const [vehicles, setVehicles] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Local assignment draft state: Map of driverId -> vehicleId (or null if unassigned)
  // initialized from server state
  const [workingAssignments, setWorkingAssignments] = useState({});
  // Track original server assignments: Map of driverId -> vehicleId (or null)
  const [serverAssignments, setServerAssignments] = useState({});

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('ALL'); // 'ALL' | 'AVAILABLE' | 'ASSIGNED'

  // Drag & Drop UX states
  const [draggedVehicleId, setDraggedVehicleId] = useState(null);
  const [dragOverDriverId, setDragOverDriverId] = useState(null);

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingVehicle, setEditingVehicle] = useState(null);
  const [deletingVehicle, setDeletingVehicle] = useState(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState(null);

  // Form states
  const [formData, setFormData] = useState({
    registration_number: '',
    model: '',
    vehicle_type: 'Heavy Haul',
  });
  const [formError, setFormError] = useState(null);
  const [savingAction, setSavingAction] = useState(false);

  // Load backend data
  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [vList, dList] = await Promise.all([
        vehicleService.getVehicles(),
        driverService.getDrivers(),
      ]);

      setVehicles(vList);
      setDrivers(dList);

      // Build server assignment mapping
      const serverMap = {};
      dList.forEach((d) => {
        const vId = d.vehicle ? d.vehicle.vehicle_id : null;
        serverMap[d.driver_id] = vId;
      });

      // Also check vehicles assigned_driver field if any driver wasn't in drivers list
      vList.forEach((v) => {
        if (v.assigned_driver && v.assigned_driver.driver_id) {
          if (serverMap[v.assigned_driver.driver_id] === undefined) {
            serverMap[v.assigned_driver.driver_id] = v.vehicle_id;
          }
        }
      });

      setServerAssignments(serverMap);
      setWorkingAssignments({ ...serverMap });
    } catch (err) {
      console.error('Failed to load fleet data:', err);
      setError('Could not load vehicles or drivers from server.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  // Derive changes count
  const modifiedDriverIds = useMemo(() => {
    const changed = [];
    const allDriverIds = new Set([
      ...Object.keys(serverAssignments),
      ...Object.keys(workingAssignments),
    ]);

    allDriverIds.forEach((idStr) => {
      const id = Number(idStr);
      const serverVal = serverAssignments[id] || null;
      const workingVal = workingAssignments[id] || null;
      if (serverVal !== workingVal) {
        changed.push(id);
      }
    });
    return changed;
  }, [serverAssignments, workingAssignments]);

  const hasUnsavedChanges = modifiedDriverIds.length > 0;

  // Determine current working status of each vehicle
  // Returns vehicleId -> assignedDriverObj (or null if available)
  const vehicleAssignedDriverMap = useMemo(() => {
    const map = {};
    Object.entries(workingAssignments).forEach(([dIdStr, vId]) => {
      if (vId) {
        const dId = Number(dIdStr);
        const dObj = drivers.find((d) => d.driver_id === dId);
        map[vId] = dObj || { driver_id: dId, name: `Driver #${dId}` };
      }
    });
    return map;
  }, [workingAssignments, drivers]);

  // Handle Drag & Drop logic (Local State Update Only)
  const handleDragStart = (e, vehicle) => {
    e.dataTransfer.setData('text/plain', vehicle.vehicle_id.toString());
    setDraggedVehicleId(vehicle.vehicle_id);
  };

  const handleDragEnd = () => {
    setDraggedVehicleId(null);
    setDragOverDriverId(null);
  };

  const handleDragOver = (e, driverId) => {
    e.preventDefault();
    if (dragOverDriverId !== driverId) {
      setDragOverDriverId(driverId);
    }
  };

  const handleDragLeave = (e, driverId) => {
    if (dragOverDriverId === driverId) {
      setDragOverDriverId(null);
    }
  };

  const assignVehicleToDriverLocal = (vehicleId, targetDriverId) => {
    setWorkingAssignments((prev) => {
      const next = { ...prev };

      // 1. Remove this vehicle from any other driver currently holding it
      Object.keys(next).forEach((dId) => {
        if (next[dId] === vehicleId) {
          next[dId] = null;
        }
      });

      // 2. Assign to target driver (replaces target driver's existing vehicle if any)
      next[targetDriverId] = vehicleId;
      return next;
    });
  };

  const removeVehicleFromDriverLocal = (driverId) => {
    setWorkingAssignments((prev) => ({
      ...prev,
      [driverId]: null,
    }));
  };

  const handleDrop = (e, targetDriverId) => {
    e.preventDefault();
    setDragOverDriverId(null);
    const vIdStr = e.dataTransfer.getData('text/plain');
    const vId = Number(vIdStr) || draggedVehicleId;

    if (vId) {
      assignVehicleToDriverLocal(vId, targetDriverId);
    }
  };

  // Discard changes
  const handleDiscardChanges = () => {
    setWorkingAssignments({ ...serverAssignments });
    showToast('Changes discarded.', 'info');
  };

  // Save changes to backend
  const handleSaveAssignments = async () => {
    if (!hasUnsavedChanges) return;

    setSavingAction(true);
    let successCount = 0;
    const errors = [];

    for (const driverId of modifiedDriverIds) {
      const targetVehicleId = workingAssignments[driverId];

      try {
        if (targetVehicleId) {
          await vehicleService.assignVehicle(driverId, targetVehicleId);
        } else {
          await vehicleService.unassignVehicle(driverId);
        }
        successCount++;
      } catch (err) {
        const dObj = drivers.find((d) => d.driver_id === driverId);
        const name = dObj ? dObj.name : `Driver #${driverId}`;
        errors.push(`Failed for ${name}: ${err.response?.data?.detail || err.message}`);
      }
    }

    setSavingAction(false);

    if (errors.length === 0) {
      showToast('Vehicle assignments saved successfully.', 'success');
      fetchData();
    } else {
      showToast(`Saved ${successCount} change(s), but encountered ${errors.length} error(s).`, 'error');
      console.error('Save assignment errors:', errors);
      fetchData();
    }
  };

  // Vehicle CRUD Actions
  const handleOpenAddModal = () => {
    setFormData({
      registration_number: '',
      model: '',
      vehicle_type: 'Heavy Haul',
    });
    setFormError(null);
    setIsAddModalOpen(true);
  };

  const handleCreateVehicle = async (e) => {
    e.preventDefault();
    setFormError(null);

    if (!formData.registration_number.trim() || !formData.model.trim()) {
      setFormError('Registration number and Model are required.');
      return;
    }

    try {
      setSavingAction(true);
      await vehicleService.createVehicle({
        registration_number: formData.registration_number.trim(),
        model: formData.model.trim(),
        vehicle_type: formData.vehicle_type,
      });
      setIsAddModalOpen(false);
      showToast('Vehicle created successfully.', 'success');
      fetchData();
    } catch (err) {
      setFormError(err.response?.data?.detail || err.message || 'Failed to create vehicle.');
    } finally {
      setSavingAction(false);
    }
  };

  const handleOpenEditModal = (vehicle) => {
    setEditingVehicle(vehicle);
    setFormData({
      registration_number: vehicle.registration_number,
      model: vehicle.model,
      vehicle_type: vehicle.vehicle_type,
    });
    setFormError(null);
  };

  const handleUpdateVehicle = async (e) => {
    e.preventDefault();
    if (!editingVehicle) return;

    setFormError(null);
    if (!formData.registration_number.trim() || !formData.model.trim()) {
      setFormError('Registration number and Model are required.');
      return;
    }

    try {
      setSavingAction(true);
      await vehicleService.updateVehicle(editingVehicle.vehicle_id, {
        registration_number: formData.registration_number.trim(),
        model: formData.model.trim(),
        vehicle_type: formData.vehicle_type,
      });
      setEditingVehicle(null);
      showToast('Vehicle updated successfully.', 'success');
      fetchData();
    } catch (err) {
      setFormError(err.response?.data?.detail || err.message || 'Failed to update vehicle.');
    } finally {
      setSavingAction(false);
    }
  };

  const handleOpenDeleteModal = (vehicle) => {
    setDeletingVehicle(vehicle);
    setDeleteErrorMessage(null);

    // Check if vehicle is currently assigned (either on server or in local working state)
    const assignedDriver = vehicleAssignedDriverMap[vehicle.vehicle_id];
    if (assignedDriver) {
      setDeleteErrorMessage(
        `Vehicle ${vehicle.registration_number} is currently assigned to ${assignedDriver.name} (#${assignedDriver.driver_id}). Remove the assignment before deleting this vehicle.`
      );
    }
  };

  const handleDeleteVehicle = async () => {
    if (!deletingVehicle || deleteErrorMessage) return;

    try {
      setSavingAction(true);
      await vehicleService.deleteVehicle(deletingVehicle.vehicle_id);
      setDeletingVehicle(null);
      showToast('Vehicle deleted successfully.', 'success');
      fetchData();
    } catch (err) {
      setDeleteErrorMessage(err.response?.data?.detail || err.message || 'Failed to delete vehicle.');
    } finally {
      setSavingAction(false);
    }
  };

  // Filtered vehicles logic
  const filteredVehicles = useMemo(() => {
    return vehicles.filter((v) => {
      const assignedDriver = vehicleAssignedDriverMap[v.vehicle_id];
      const isAssigned = Boolean(assignedDriver);

      // Filter status tab
      if (filterStatus === 'AVAILABLE' && isAssigned) return false;
      if (filterStatus === 'ASSIGNED' && !isAssigned) return false;

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesReg = v.registration_number.toLowerCase().includes(q);
        const matchesModel = v.model.toLowerCase().includes(q);
        const matchesType = v.vehicle_type.toLowerCase().includes(q);
        const matchesDriver = assignedDriver && assignedDriver.name.toLowerCase().includes(q);

        return matchesReg || matchesModel || matchesType || matchesDriver;
      }

      return true;
    });
  }, [vehicles, vehicleAssignedDriverMap, filterStatus, searchQuery]);

  const availableVehicles = useMemo(() => {
    return filteredVehicles.filter((v) => !vehicleAssignedDriverMap[v.vehicle_id]);
  }, [filteredVehicles, vehicleAssignedDriverMap]);

  const assignedVehicles = useMemo(() => {
    return filteredVehicles.filter((v) => Boolean(vehicleAssignedDriverMap[v.vehicle_id]));
  }, [filteredVehicles, vehicleAssignedDriverMap]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Toast Banner */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-xl border flex items-center gap-3 transition-all ${
            toast.type === 'error'
              ? 'bg-red-900/90 text-red-100 border-red-700'
              : toast.type === 'info'
              ? 'bg-blue-900/90 text-blue-100 border-blue-700'
              : 'bg-emerald-900/90 text-emerald-100 border-emerald-700'
          }`}
        >
          {toast.type === 'error' ? (
            <AlertCircle className="w-5 h-5 shrink-0 text-red-400" />
          ) : (
            <CheckCircle className="w-5 h-5 shrink-0 text-emerald-400" />
          )}
          <span className="text-sm font-medium">{toast.message}</span>
        </div>
      )}

      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-900/80 p-6 rounded-xl border border-slate-800 backdrop-blur-sm">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
              <Truck className="w-6 h-6" />
            </div>
            Vehicle Management
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Manage commercial vehicles and driver assignments using drag-and-drop
          </p>
        </div>

        <button
          onClick={handleOpenAddModal}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-colors shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4" />
          <span>Add Vehicle</span>
        </button>
      </div>

      {/* Unsaved Changes Banner */}
      {hasUnsavedChanges && (
        <div className="sticky top-4 z-40 bg-blue-950/90 border border-blue-700/60 p-4 rounded-xl shadow-2xl backdrop-blur-md flex flex-wrap items-center justify-between gap-4 animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 text-white rounded-lg animate-pulse">
              <Save className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-white">
                {modifiedDriverIds.length} unsaved assignment change
                {modifiedDriverIds.length > 1 ? 's' : ''}
              </h4>
              <p className="text-xs text-blue-300">
                Changes are local. Click &quot;Save Assignments&quot; to persist to the database.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleDiscardChanges}
              disabled={savingAction}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-800 border border-slate-700 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Discard Changes</span>
            </button>

            <button
              onClick={handleSaveAssignments}
              disabled={savingAction}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-lg shadow-emerald-600/20 disabled:opacity-50"
            >
              {savingAction ? (
                <span className="inline-block animate-spin">⌛</span>
              ) : (
                <Save className="w-4 h-4" />
              )}
              <span>Save Assignments</span>
            </button>
          </div>
        </div>
      )}

      {/* Search and Filters */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search by registration, model, type or driver..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 bg-slate-950/60 p-1 rounded-lg border border-slate-800">
          {['ALL', 'AVAILABLE', 'ASSIGNED'].map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterStatus(tab)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                filterStatus === tab
                  ? 'bg-blue-600 text-white font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.charAt(0) + tab.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Workspace Main Grid */}
      {loading ? (
        <div className="p-12 text-center text-slate-400 bg-slate-900/40 rounded-xl border border-slate-800">
          <div className="inline-block animate-spin mb-3 text-blue-500">⚙️</div>
          <p className="text-sm font-medium">Loading fleet data...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-red-950/40 border border-red-800/60 rounded-xl text-red-300 text-center">
          <AlertCircle className="w-8 h-8 mx-auto mb-2 text-red-400" />
          <p className="text-sm font-semibold">{error}</p>
          <button
            onClick={fetchData}
            className="mt-3 px-3 py-1.5 bg-red-800 hover:bg-red-700 text-white rounded text-xs font-medium"
          >
            Retry
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: VEHICLE INVENTORY PANEL (5 cols) */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-slate-900/80 rounded-xl border border-slate-800 overflow-hidden shadow-lg">
              <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Truck className="w-4 h-4 text-blue-400" />
                  <h2 className="text-sm font-bold text-slate-200 tracking-wide uppercase">
                    Available Vehicles
                  </h2>
                </div>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-700/50">
                  {availableVehicles.length} available
                </span>
              </div>

              <div className="p-4 space-y-3 max-h-[calc(100vh-280px)] overflow-y-auto">
                {availableVehicles.length === 0 ? (
                  <div className="p-8 text-center border-2 border-dashed border-slate-800 rounded-xl text-slate-500 text-xs">
                    No available vehicles match your search/filter.
                  </div>
                ) : (
                  availableVehicles.map((vehicle) => (
                    <div
                      key={vehicle.vehicle_id}
                      draggable={true}
                      onDragStart={(e) => handleDragStart(e, vehicle)}
                      onDragEnd={handleDragEnd}
                      className={`group relative p-4 rounded-xl border transition-all cursor-grab active:cursor-grabbing bg-slate-950/70 border-slate-800 hover:border-blue-500/60 hover:bg-slate-950 hover:shadow-xl hover:shadow-blue-500/5 ${
                        draggedVehicleId === vehicle.vehicle_id ? 'opacity-40 border-blue-500' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 text-slate-600 group-hover:text-blue-400 transition-colors">
                            <GripVertical className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-base font-bold text-white tracking-tight">
                                🚛 {vehicle.registration_number}
                              </span>
                            </div>
                            <h3 className="text-xs font-medium text-slate-300 mt-0.5">
                              {vehicle.model}
                            </h3>
                            <span className="inline-block text-[11px] font-medium text-slate-400 mt-1">
                              {vehicle.vehicle_type}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-col items-end gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-700/50 uppercase tracking-wider">
                            AVAILABLE
                          </span>

                          <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
                            <button
                              onClick={() => handleOpenEditModal(vehicle)}
                              className="p-1 rounded text-slate-400 hover:text-blue-400 hover:bg-slate-800"
                              title="Edit vehicle"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleOpenDeleteModal(vehicle)}
                              className="p-1 rounded text-slate-400 hover:text-red-400 hover:bg-slate-800"
                              title="Delete vehicle"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Accessible Non-Drag Assignment Fallback Dropdown */}
                      <div className="mt-3 pt-3 border-t border-slate-900 flex items-center justify-between text-xs">
                        <span className="text-slate-500 text-[11px]">Accessible action:</span>
                        <select
                          defaultValue=""
                          onChange={(e) => {
                            const dId = Number(e.target.value);
                            if (dId) {
                              assignVehicleToDriverLocal(vehicle.vehicle_id, dId);
                              e.target.value = '';
                            }
                          }}
                          className="bg-slate-900 border border-slate-800 text-slate-300 text-[11px] rounded px-2 py-1 focus:outline-none focus:border-blue-500"
                        >
                          <option value="" disabled>
                            Assign to driver...
                          </option>
                          {drivers.map((d) => (
                            <option key={d.driver_id} value={d.driver_id}>
                              {d.name} (#{d.driver_id})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* ASSIGNED VEHICLES SECTION */}
            {assignedVehicles.length > 0 && filterStatus !== 'AVAILABLE' && (
              <div className="bg-slate-900/60 rounded-xl border border-slate-800/80 overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-800 bg-slate-950/30 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-slate-400 tracking-wide uppercase">
                    Assigned Vehicles ({assignedVehicles.length})
                  </h3>
                </div>
                <div className="p-3 space-y-2 max-h-60 overflow-y-auto">
                  {assignedVehicles.map((vehicle) => {
                    const assignedDriver = vehicleAssignedDriverMap[vehicle.vehicle_id];
                    return (
                      <div
                        key={vehicle.vehicle_id}
                        className="p-3 rounded-lg bg-slate-950/40 border border-slate-800/60 flex items-center justify-between"
                      >
                        <div>
                          <div className="text-xs font-bold text-slate-200">
                            {vehicle.registration_number}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {vehicle.model} • {vehicle.vehicle_type}
                          </div>
                          <div className="text-[10px] text-blue-400 font-medium mt-0.5">
                            Assigned to {assignedDriver?.name} (#{assignedDriver?.driver_id})
                          </div>
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenEditModal(vehicle)}
                            className="p-1 text-slate-400 hover:text-blue-400"
                            title="Edit vehicle"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleOpenDeleteModal(vehicle)}
                            className="p-1 text-slate-400 hover:text-red-400"
                            title="Delete vehicle"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: DRIVER ASSIGNMENT PANEL (7 cols) */}
          <div className="lg:col-span-7 bg-slate-900/80 rounded-xl border border-slate-800 overflow-hidden shadow-lg">
            <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <User className="w-4 h-4 text-blue-400" />
                <h2 className="text-sm font-bold text-slate-200 tracking-wide uppercase">
                  Driver Assignments
                </h2>
              </div>
              <span className="text-xs text-slate-400">
                {drivers.length} registered driver{drivers.length !== 1 ? 's' : ''}
              </span>
            </div>

            <div className="p-5 space-y-4 max-h-[calc(100vh-280px)] overflow-y-auto">
              {drivers.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-xs">
                  No drivers registered in backend.
                </div>
              ) : (
                drivers.map((driver) => {
                  const assignedVehicleId = workingAssignments[driver.driver_id];
                  const assignedVehicle = vehicles.find((v) => v.vehicle_id === assignedVehicleId);
                  const isHovered = dragOverDriverId === driver.driver_id;
                  const isModified =
                    serverAssignments[driver.driver_id] !== workingAssignments[driver.driver_id];

                  return (
                    <div
                      key={driver.driver_id}
                      onDragOver={(e) => handleDragOver(e, driver.driver_id)}
                      onDragLeave={(e) => handleDragLeave(e, driver.driver_id)}
                      onDrop={(e) => handleDrop(e, driver.driver_id)}
                      className={`p-4 rounded-xl border transition-all ${
                        isHovered
                          ? 'border-blue-500 bg-blue-600/10 scale-[1.01] shadow-lg shadow-blue-500/10'
                          : isModified
                          ? 'border-blue-700/60 bg-slate-950/80 ring-1 ring-blue-500/40'
                          : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                      }`}
                    >
                      {/* Driver Header */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-blue-400">
                            {driver.name ? driver.name.charAt(0).toUpperCase() : '#'}
                          </div>
                          <div>
                            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                              <span>{driver.name}</span>
                              <span className="text-xs font-normal text-slate-400">
                                Driver #{driver.driver_id}
                              </span>
                            </h3>
                          </div>
                        </div>

                        {isModified && (
                          <span className="px-2 py-0.5 text-[10px] font-bold rounded bg-blue-900/80 text-blue-300 border border-blue-700">
                            Unsaved Change
                          </span>
                        )}
                      </div>

                      {/* Drop Zone Area */}
                      {assignedVehicle ? (
                        <div className="p-3.5 rounded-lg bg-slate-900 border border-blue-600/40 flex items-center justify-between gap-3 shadow-inner">
                          <div className="flex items-center gap-3">
                            <div className="p-2 rounded bg-blue-600/20 text-blue-400">
                              <Truck className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="text-sm font-bold text-white flex items-center gap-2">
                                <span>🚛 {assignedVehicle.registration_number}</span>
                              </div>
                              <div className="text-xs text-slate-300 font-medium">
                                {assignedVehicle.model}
                              </div>
                              <div className="text-[11px] text-slate-400">
                                {assignedVehicle.vehicle_type}
                              </div>
                            </div>
                          </div>

                          <button
                            onClick={() => removeVehicleFromDriverLocal(driver.driver_id)}
                            className="px-3 py-1.5 rounded text-xs font-semibold text-red-400 hover:text-red-300 hover:bg-red-950/60 border border-red-800/40 transition-colors"
                          >
                            Remove
                          </button>
                        </div>
                      ) : (
                        <div
                          className={`p-6 rounded-lg border-2 border-dashed text-center transition-colors flex flex-col items-center justify-center gap-1.5 ${
                            isHovered
                              ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                              : 'border-slate-800/80 bg-slate-900/30 text-slate-500'
                          }`}
                        >
                          <ArrowRight className="w-4 h-4 opacity-60" />
                          <span className="text-xs font-semibold tracking-wider uppercase">
                            {isHovered ? 'RELEASE TO ASSIGN VEHICLE' : 'DROP VEHICLE HERE'}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* Add Vehicle Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Truck className="w-5 h-5 text-blue-400" />
                Add New Vehicle
              </h3>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="mb-4 p-3 bg-red-950/50 border border-red-800 rounded-lg text-xs text-red-300">
                {formError}
              </div>
            )}

            <form onSubmit={handleCreateVehicle} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Registration Number *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. KA-04-E-4412"
                  value={formData.registration_number}
                  onChange={(e) =>
                    setFormData({ ...formData, registration_number: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Model *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Ashok Leyland 2820"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Vehicle Type *
                </label>
                <select
                  value={formData.vehicle_type}
                  onChange={(e) => setFormData({ ...formData, vehicle_type: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="Heavy Haul">Heavy Haul</option>
                  <option value="Cargo">Cargo</option>
                  <option value="Tipper">Tipper</option>
                  <option value="Tanker">Tanker</option>
                  <option value="Light Commercial">Light Commercial</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingAction}
                  className="px-4 py-2 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
                >
                  {savingAction ? 'Adding...' : 'Add Vehicle'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Vehicle Modal */}
      {editingVehicle && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Pencil className="w-4 h-4 text-blue-400" />
                Edit Vehicle Details
              </h3>
              <button
                onClick={() => setEditingVehicle(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="mb-4 p-3 bg-red-950/50 border border-red-800 rounded-lg text-xs text-red-300">
                {formError}
              </div>
            )}

            <form onSubmit={handleUpdateVehicle} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Registration Number *
                </label>
                <input
                  type="text"
                  required
                  value={formData.registration_number}
                  onChange={(e) =>
                    setFormData({ ...formData, registration_number: e.target.value })
                  }
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Model *</label>
                <input
                  type="text"
                  required
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Vehicle Type *
                </label>
                <select
                  value={formData.vehicle_type}
                  onChange={(e) => setFormData({ ...formData, vehicle_type: e.target.value })}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="Heavy Haul">Heavy Haul</option>
                  <option value="Cargo">Cargo</option>
                  <option value="Tipper">Tipper</option>
                  <option value="Tanker">Tanker</option>
                  <option value="Light Commercial">Light Commercial</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingVehicle(null)}
                  className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingAction}
                  className="px-4 py-2 rounded-lg text-xs font-bold bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50"
                >
                  {savingAction ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Vehicle Modal */}
      {deletingVehicle && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-md shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Trash2 className="w-5 h-5 text-red-400" />
                Delete Vehicle
              </h3>
              <button
                onClick={() => setDeletingVehicle(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {deleteErrorMessage ? (
              <div className="space-y-4">
                <div className="p-4 bg-amber-950/40 border border-amber-800/60 rounded-xl flex items-start gap-3 text-amber-200 text-xs leading-relaxed">
                  <ShieldAlert className="w-5 h-5 shrink-0 text-amber-400 mt-0.5" />
                  <div>
                    <p className="font-semibold text-amber-300 mb-1">Deletion Blocked</p>
                    <p>{deleteErrorMessage}</p>
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => setDeletingVehicle(null)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-xs text-slate-300 leading-relaxed">
                  Are you sure you want to delete vehicle{' '}
                  <strong className="text-white">{deletingVehicle.registration_number}</strong> (
                  {deletingVehicle.model})? This action cannot be undone.
                </p>

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setDeletingVehicle(null)}
                    className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleDeleteVehicle}
                    disabled={savingAction}
                    className="px-4 py-2 rounded-lg text-xs font-bold bg-red-600 hover:bg-red-500 text-white disabled:opacity-50"
                  >
                    {savingAction ? 'Deleting...' : 'Delete Vehicle'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
