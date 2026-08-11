import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";

import { authConfigurationError, supabase } from "./supabase";

interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  configurationError: string | null;
  passwordSetupRequired: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  updatePassword: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [passwordSetupRequired, setPasswordSetupRequired] = useState(() =>
    /(?:^|[&#?])type=(?:invite|recovery)(?:&|$)/.test(
      `${window.location.search}&${window.location.hash}`,
    ),
  );

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    let active = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (active) {
        setSession(data.session);
        setLoading(false);
      }
    });

    const { data } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
      if (event === "PASSWORD_RECOVERY") setPasswordSetupRequired(true);
    });

    return () => {
      active = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error(authConfigurationError ?? "Authentication unavailable.");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw new Error("Email or password was not accepted.");
  }, []);

  const signOut = useCallback(async () => {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut({ scope: "local" });
    if (error) throw new Error("Sign out could not be completed.");
  }, []);

  const updatePassword = useCallback(async (password: string) => {
    if (!supabase) throw new Error("Authentication is unavailable.");
    const { error } = await supabase.auth.updateUser({ password });
    if (error) throw new Error("The password could not be saved. Use at least 8 characters.");
    setPasswordSetupRequired(false);
    window.history.replaceState({}, document.title, window.location.pathname);
  }, []);

  const value = useMemo(
    () => ({
      session,
      loading,
      configurationError: authConfigurationError,
      passwordSetupRequired,
      signIn,
      signOut,
      updatePassword,
    }),
    [loading, passwordSetupRequired, session, signIn, signOut, updatePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
