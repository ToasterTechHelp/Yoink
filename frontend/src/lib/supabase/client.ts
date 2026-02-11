import { createBrowserClient } from "@supabase/ssr";

export type BrowserClient = ReturnType<typeof createBrowserClient>;

let client: BrowserClient | null = null;

export function createClient(): BrowserClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) return null;

  if (!client) {
    client = createBrowserClient(url, key);
  }
  return client;
}
