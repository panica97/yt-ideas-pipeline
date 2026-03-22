import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { KeyRound, ArrowRight, AlertCircle, Sun, Moon } from 'lucide-react';
import { useTheme } from '../hooks/useTheme';

export default function LoginPage() {
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { isDark, toggle } = useTheme();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError('Enter an API key');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const baseURL = import.meta.env.VITE_API_URL || '/api';
      await axios.get(`${baseURL}/stats`, {
        headers: { 'X-API-Key': apiKey.trim() },
      });
      localStorage.setItem('irt_api_key', apiKey.trim());
      navigate('/');
    } catch {
      setError('Invalid API key or server unavailable');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-0 noise-bg flex items-center justify-center">
      {/* Theme toggle */}
      <button
        onClick={toggle}
        className="fixed top-4 right-4 z-50 w-9 h-9 rounded-lg flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-surface-2 transition-all duration-200 border border-border"
        title={isDark ? 'Light mode' : 'Dark mode'}
      >
        {isDark ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      <div className="w-full max-w-sm relative z-10 animate-slide-in">
        {/* Glow behind card */}
        <div className="absolute -inset-px rounded-xl bg-gradient-to-b from-accent/20 via-transparent to-transparent blur-xl opacity-50" />

        <div className="relative glass rounded-xl p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="w-14 h-14 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center mx-auto mb-4">
              <span className="text-accent font-bold text-xl font-mono">IR</span>
            </div>
            <h1 className="text-xl font-bold text-text-primary">IRT Dashboard</h1>
            <p className="text-xs text-text-muted mt-1">Ideas Research Team</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="apiKey" className="block text-xs text-text-muted uppercase tracking-wider mb-2">
                API Key
              </label>
              <div className="relative">
                <KeyRound size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter your API key"
                  className="w-full pl-10 pr-4 py-2.5 bg-surface-2 border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30 transition-all"
                  autoFocus
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-danger/10 border border-danger/20 animate-fade-in">
                <AlertCircle size={14} className="text-danger flex-shrink-0" />
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-accent hover:bg-accent-hover disabled:bg-surface-3 disabled:text-text-muted disabled:cursor-not-allowed text-text-primary text-sm font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 hover:shadow-glow-accent"
            >
              {loading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
