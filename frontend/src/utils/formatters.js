/**
 * Utility Formatting Functions
 */

export function formatDate(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return isoString;
  }
}

export function formatDateTime(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return isoString;
  }
}

export function formatTimeOnly(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return isoString;
  }
}

export function formatDuration(minutes) {
  if (minutes == null || isNaN(minutes)) return '—';
  const hrs = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hrs === 0) return `${mins}m`;
  if (mins === 0) return `${hrs}h`;
  return `${hrs}h ${mins}m`;
}

export function getSafetyScoreCategory(score) {
  if (score >= 90) return { label: 'Excellent', color: 'text-emerald-600', bg: 'bg-emerald-500' };
  if (score >= 80) return { label: 'Good', color: 'text-blue-600', bg: 'bg-blue-500' };
  if (score >= 70) return { label: 'Fair', color: 'text-amber-600', bg: 'bg-amber-500' };
  return { label: 'At Risk', color: 'text-red-600', bg: 'bg-red-500' };
}
