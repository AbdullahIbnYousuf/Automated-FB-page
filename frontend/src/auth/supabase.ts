import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();

export const authConfigurationError =
  !supabaseUrl || !publishableKey
    ? "Supabase browser authentication is not configured for this build."
    : null;

export const supabase: SupabaseClient | null =
  supabaseUrl && publishableKey
    ? createClient(supabaseUrl, publishableKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      })
    : null;
