// EXPO_PUBLIC_* values are compiled into the bundle and are PUBLIC. Only the API URL lives here:
// no Supabase service-role key or any other server secret is ever referenced by this app.
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000').replace(/\/$/, '');
export const PAGE_SIZE = 20;
// Refresh the access token this many ms BEFORE it expires so requests rarely hit a 401 at all.
export const REFRESH_SKEW_MS = 30_000;
