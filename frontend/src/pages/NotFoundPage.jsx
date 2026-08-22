import React from 'react';
import { Link } from 'react-router-dom';
import { AlertOctagon, ArrowLeft } from 'lucide-react';

export default function NotFoundPage() {
  return (
    <div className="py-24 text-center flex flex-col items-center justify-center">
      <div className="w-14 h-14 rounded-2xl bg-red-50 border border-red-200 flex items-center justify-center text-red-600 mb-4">
        <AlertOctagon className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900">404 — Page Not Found</h1>
      <p className="text-xs text-slate-500 max-w-sm mt-1 mb-6">
        The requested navigation endpoint does not exist in the fleet management console.
      </p>
      <Link
        to="/"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Return to Dashboard Overview
      </Link>
    </div>
  );
}
