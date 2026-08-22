import React from 'react';
import { Loader2 } from 'lucide-react';

export default function LoadingState({ message = 'Loading fleet data…' }) {
  return (
    <div className="py-16 text-center flex flex-col items-center justify-center">
      <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-3" />
      <p className="text-sm font-medium text-slate-600">{message}</p>
    </div>
  );
}
