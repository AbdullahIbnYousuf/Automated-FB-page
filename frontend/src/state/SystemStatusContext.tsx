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
import type { HealthStatus, SystemStatus } from "../types/system";

type BackendState = "loading" | "available" | "unavailable";

interface SystemStatusContextValue {
  backendState: BackendState;
  health: HealthStatus | null;
  status: SystemStatus | null;
  refresh: () => Promise<void>;
}

const SystemStatusContext = createContext<SystemStatusContextValue | undefined>(
  undefined,
);

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [backendState, setBackendState] = useState<BackendState>("loading");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);

  const refresh = useCallback(async () => {
    setBackendState("loading");
    try {
      const snapshot = await loadSystemSnapshot();
      setHealth(snapshot.health);
      setStatus(snapshot.status);
      setBackendState("available");
    } catch {
      setHealth(null);
      setStatus(null);
      setBackendState("unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({ backendState, health, status, refresh }),
    [backendState, health, refresh, status],
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
