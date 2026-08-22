/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fleet: {
          bg: '#f8fafc',       // Slate 50
          card: '#ffffff',     // Clean white
          border: '#e2e8f0',   // Slate 200
          navy: '#0f172a',     // Slate 900
          charcoal: '#1e293b', // Slate 800
          muted: '#64748b',    // Slate 500
          primary: '#2563eb',  // Blue 600
          'primary-hover': '#1d4ed8', // Blue 700
          'primary-light': '#eff6ff', // Blue 50
          success: '#10b981',  // Emerald 500
          'success-light': '#ecfdf5',
          warning: '#f59e0b',  // Amber 500
          'warning-light': '#fffbeb',
          danger: '#ef4444',   // Red 500
          'danger-light': '#fef2f2',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        'subtle': '0 1px 3px 0 rgba(15, 23, 42, 0.05), 0 1px 2px -1px rgba(15, 23, 42, 0.05)',
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.03)',
      }
    },
  },
  plugins: [],
}
