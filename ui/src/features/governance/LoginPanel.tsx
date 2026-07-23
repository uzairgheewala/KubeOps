import { useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { api, setApiScope, setApiToken } from "../../api/client";
import type { CurrentIdentity } from "../../types";

export function LoginPanel({ onAuthenticated }: { onAuthenticated: (identity: CurrentIdentity) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [organizationId, setOrganizationId] = useState("default");
  const [workspaceId, setWorkspaceId] = useState("default");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = async () => {
    setBusy(true); setError(null);
    try {
      const result = await api.login(username, password);
      setApiToken(result.token);
      setApiScope(organizationId, workspaceId);
      const identity = await api.me();
      setApiScope(identity.organization_id, identity.workspace_id);
      onAuthenticated(identity);
    } catch (reason) { setError((reason as Error).message); setApiToken(null); }
    finally { setBusy(false); }
  };

  return <main className="login-page"><section className="login-panel"><div className="brand-mark">K</div><div><small>KubeOps Release 1.0</small><h1>Authenticate to the control plane</h1><p>Production workspaces require a scoped Django identity and KubeOps role grant.</p></div><label className="field"><span>Organization</span><input value={organizationId} onChange={(event: ChangeEvent<HTMLInputElement>) => setOrganizationId(event.target.value)} /></label><label className="field"><span>Workspace</span><input value={workspaceId} onChange={(event: ChangeEvent<HTMLInputElement>) => setWorkspaceId(event.target.value)} /></label><label className="field"><span>Username</span><input autoComplete="username" value={username} onChange={(event: ChangeEvent<HTMLInputElement>) => setUsername(event.target.value)} /></label><label className="field"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)} onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => { if (event.key === "Enter") void login(); }} /></label>{error && <div className="error-banner">{error}</div>}<button type="button" className="button primary" disabled={busy || !username || !password || !organizationId || !workspaceId} onClick={login}>{busy ? "Authenticating…" : "Sign in"}</button></section></main>;
}
