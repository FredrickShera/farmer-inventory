import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export interface StoredSession { accessToken: string; refreshToken: string; expiresAt: number }
export interface TokenStore {
  load(): Promise<StoredSession | null>;
  save(session: StoredSession): Promise<void>;
  clear(): Promise<void>;
}

const KEY = 'coop.session.v1';

/** Browser-only fallback for local testing: expo-secure-store has no web version. localStorage is
 *  readable by any script on the page, so this is NOT used on phones. */
const webTokenStore: TokenStore = {
  async load() {
    try {
      const raw = window.localStorage.getItem(KEY);
      return raw ? (JSON.parse(raw) as StoredSession) : null;
    } catch {
      return null;
    }
  },
  async save(session) {
    window.localStorage.setItem(KEY, JSON.stringify(session));
  },
  async clear() {
    window.localStorage.removeItem(KEY);
  },
};

/** Tokens live in the iOS Keychain / Android Keystore via expo-secure-store - never AsyncStorage. */
const nativeTokenStore: TokenStore = {
  async load() {
    try {
      const raw = await SecureStore.getItemAsync(KEY);
      return raw ? (JSON.parse(raw) as StoredSession) : null;
    } catch {
      return null; // unreadable/corrupt entry: behave as signed out
    }
  },
  async save(session) {
    await SecureStore.setItemAsync(KEY, JSON.stringify(session));
  },
  async clear() {
    await SecureStore.deleteItemAsync(KEY);
  },
};

export const secureTokenStore: TokenStore = Platform.OS === 'web' ? webTokenStore : nativeTokenStore;
