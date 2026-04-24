'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Bot, Database, Loader2, AlertCircle } from 'lucide-react';
import { checkHealth, connectDatabase } from '@/lib/api';
import { useAppStore } from '@/store/useStore';

export default function LoginPage() {
  const router = useRouter();
  const { connectionId, setConnection } = useAppStore();

  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // form fields
  const [server, setServer] = useState('');
  const [database, setDatabase] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [port, setPort] = useState(1433);
  const [useMfa, setUseMfa] = useState(true);
  const [refreshSchema, setRefreshSchema] = useState(false);
  const [useWholegraph, setUseWholegraph] = useState(true);

  useEffect(() => {
    // Redirect if already connected
    if (connectionId) {
      router.replace('/chat');
      return;
    }
    checkHealth().then(setBackendOk);
  }, [connectionId, router]);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!server || !database || !username) {
      setError('Please fill in Server, Database, and Username.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = await connectDatabase({
        server,
        database,
        username,
        password: password || undefined,
        port,
        auth_method: useMfa ? 'azure_ad' : 'sql',
        use_mfa: useMfa,
        refresh_schema: refreshSchema,
        use_wholegraph: useWholegraph,
      });
      setConnection(data.connection_id, `${server}/${database}`);
      router.push('/chat');
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        (err as Error)?.message ||
        'Connection failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        {/* Header */}
        <div className="flex items-center gap-3 mb-8">
          <Bot className="text-blue-600 w-10 h-10" />
          <div>
            <h1 className="text-2xl font-bold">SQL Agent</h1>
            <p className="text-sm text-gray-500">Multi-Agent Edition</p>
          </div>
        </div>

        {/* Backend status banner */}
        {backendOk === false && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>
              Cannot reach backend at{' '}
              <code className="font-mono">
                {process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001'}
              </code>
              . Start it with <code className="font-mono">python run.py</code> in the backend
              folder.
            </span>
          </div>
        )}

        {/* Connection form */}
        <form
          onSubmit={handleConnect}
          className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 space-y-5"
        >
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Database className="w-5 h-5 text-blue-500" />
            Database Connection
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Label>Server</Label>
              <Input
                value={server}
                onChange={setServer}
                placeholder="your-server.database.windows.net"
                required
              />
            </div>
            <div>
              <Label>Database</Label>
              <Input value={database} onChange={setDatabase} placeholder="Caboodle" required />
            </div>
            <div>
              <Label>Port</Label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(Number(e.target.value))}
                min={1}
                max={65535}
                className="field"
              />
            </div>
            <div className="col-span-2">
              <Label>Username</Label>
              <Input value={username} onChange={setUsername} placeholder="user@domain.com" required />
            </div>
            <div className="col-span-2">
              <Label>Password (optional for MFA)</Label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Leave blank for Azure AD MFA"
                className="field"
              />
            </div>
          </div>

          {/* Toggles */}
          <div className="space-y-2 border-t pt-4">
            <Toggle
              label="Azure AD MFA"
              description="Use interactive browser login"
              checked={useMfa}
              onChange={setUseMfa}
            />
            <Toggle
              label="Use Wholegraph schema"
              description="Load pre-built schema graph"
              checked={useWholegraph}
              onChange={setUseWholegraph}
            />
            <Toggle
              label="Re-fetch schema on connect"
              description="Ignore cached schema and extract fresh"
              checked={refreshSchema}
              onChange={setRefreshSchema}
            />
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || backendOk === false}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold py-2.5 transition-colors"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            {loading ? 'Connecting…' : 'Connect'}
          </button>
        </form>
      </div>

      <style jsx global>{`
        .field {
          width: 100%;
          border: 1px solid #e5e7eb;
          border-radius: 0.5rem;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          outline: none;
        }
        .field:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
        }
      `}</style>
    </div>
  );
}

// ── Mini components ──────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-sm font-medium text-gray-700 mb-1">{children}</label>;
}

function Input({
  value,
  onChange,
  placeholder,
  required,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      required={required}
      className="field"
    />
  );
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between cursor-pointer select-none">
      <div>
        <span className="text-sm font-medium text-gray-700">{label}</span>
        {description && <p className="text-xs text-gray-400">{description}</p>}
      </div>
      <div
        onClick={() => onChange(!checked)}
        className={`w-10 h-6 rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-gray-300'} relative`}
      >
        <span
          className={`absolute top-0.5 left-0.5 bg-white w-5 h-5 rounded-full shadow transition-transform ${checked ? 'translate-x-4' : ''}`}
        />
      </div>
    </label>
  );
}
