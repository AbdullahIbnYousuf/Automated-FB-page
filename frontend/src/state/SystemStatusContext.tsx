import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { loadSystemSnapshot } from "../api/system";
import { testFacebookConnection as requestFacebookConnectionTest } from "../api/facebook";
import type { FacebookConnectionStatus } from "../types/facebook";
import type { HealthStatus, SystemStatus } from "../types/system";

type BackendState = "loading" | "available" | "unavailable";

interface SystemStatusContextValue {
  backendState: BackendState;
  health: HealthStatus | null;
  status: SystemStatus | null;
  facebookConnection: FacebookConnectionStatus | null;
  refresh: () => Promise<void>;
  testFacebookConnection: () => Promise<FacebookConnectionStatus>;
}

const SystemStatusContext = createContext<SystemStatusContextValue | undefined>(
  undefined,
);

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [backendState, setBackendState] = useState<BackendState>("loading");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [facebookConnection, setFacebookConnection] =
    useState<FacebookConnectionStatus | null>(null);

  const refresh = useCallback(async () => {
    setBackendState("loading");
    try {
      const snapshot = await loadSystemSnapshot();
      setHealth(snapshot.health);
      setStatus(snapshot.status);
      setFacebookConnection(snapshot.facebook);
      setBackendState("available");
    } catch {
      setHealth(null);
      setStatus(null);
      setFacebookConnection(null);
      setBackendState("unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const testFacebookConnection = useCallback(async () => {
    const result = await requestFacebookConnectionTest();
    setFacebookConnection(result);
    return result;
  }, []);

  const value = useMemo(
    () => ({
      backendState,
      health,
      status,
      facebookConnection,
      refresh,
      testFacebookConnection,
    }),
    [backendState, facebookConnection, health, refresh, status, testFacebookConnection],
  );

  return (
    <SystemStatusContext.Provider value={value}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus(): SystemStatusContextValue {
  const context = useContext(SystemStatusContext);
  if (!context) {
    throw new Error("useSystemStatus must be used inside SystemStatusProvider");
  }
  return context;
}
