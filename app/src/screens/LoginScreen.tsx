import React, { useRef, useState } from 'react';
import { Text } from 'react-native';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Banner, Button, Screen, TextField } from '../components/ui';
import { colors } from '../theme';

export function LoginScreen({ navigation }: any) {
  const { signIn } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const lock = useRef(false);

  const idErr = touched && identifier.trim().length < 3 ? 'Enter your phone number or email' : undefined;
  const pwErr = touched && !password ? 'Enter your password' : undefined;

  async function submit() {
    if (lock.current) return;
    setTouched(true);
    if (identifier.trim().length < 3 || !password) return;
    lock.current = true; setBusy(true); setError(null);
    try {
      await signIn(identifier.trim(), password);
    } catch (e) {
      setError(e instanceof ApiError ? (e.status === 401 ? 'Wrong phone/email or password.' : e.message) : 'Something went wrong.');
    } finally { lock.current = false; setBusy(false); }
  }

  return (
    <Screen>
      <Text style={{ fontSize: 28, fontWeight: '800', color: colors.primary, marginTop: 24 }}>Farmer Inventory</Text>
      <Text style={{ color: colors.muted, marginBottom: 16 }}>Sign in to manage your produce.</Text>
      {error ? <Banner text={error} /> : null}
      <TextField label="Phone or email" value={identifier} onChangeText={setIdentifier} keyboardType="email-address"
        placeholder="254712345678 or you@example.com" error={idErr} textContentType="username" />
      <TextField label="Password" value={password} onChangeText={setPassword} secureTextEntry error={pwErr} textContentType="password" />
      <Button title="Sign in" loading={busy} onPress={submit} />
      <Button title="Create an account" variant="secondary" onPress={() => navigation.navigate('Register')} />
    </Screen>
  );
}
