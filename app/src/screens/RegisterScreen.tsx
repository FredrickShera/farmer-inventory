import React, { useMemo, useRef, useState } from 'react';
import { Text } from 'react-native';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Banner, Button, ErrorState, Loading, Screen, SelectField, TextField } from '../components/ui';
import { useLocations } from '../hooks/queries';
import { normalisePhone, RegisterField, validateRegister } from '../utils/validation';

const EMPTY: Record<RegisterField, string> = { full_name: '', national_id: '', phone: '', email: '', password: '', county: '', sub_county: '', ward: '' };

export function RegisterScreen() {
  const { register } = useAuth();
  const locations = useLocations();
  const [v, setV] = useState(EMPTY);
  const [touched, setTouched] = useState<Partial<Record<RegisterField, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverFields, setServerFields] = useState<Partial<Record<string, string>>>({});
  const lock = useRef(false);

  const errors = validateRegister(v);
  const err = (f: RegisterField) => (touched[f] ? errors[f] : undefined) ?? serverFields[f];
  const set = (f: RegisterField, val: string) => {
    setServerFields((s) => ({ ...s, [f]: undefined }));
    setTouched((t) => ({ ...t, [f]: true }));
    // dependent dropdowns: changing a parent clears its children
    setV((p) => ({ ...p, [f]: val, ...(f === 'county' ? { sub_county: '', ward: '' } : f === 'sub_county' ? { ward: '' } : {}) }));
  };

  const rows = locations.data ?? [];
  const counties = useMemo(() => [...new Set(rows.map((r) => r.county))].sort(), [rows]);
  const subCounties = useMemo(() => [...new Set(rows.filter((r) => r.county === v.county).map((r) => r.sub_county))].sort(), [rows, v.county]);
  const wards = useMemo(() => rows.filter((r) => r.county === v.county && r.sub_county === v.sub_county), [rows, v.county, v.sub_county]);

  async function submit() {
    if (lock.current) return;
    setTouched(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, true])));
    if (Object.keys(errors).length) return;
    const ward = wards.find((w) => String(w.ward_id) === v.ward);
    if (!ward) return;
    lock.current = true; setBusy(true); setError(null);
    try {
      await register({ full_name: v.full_name.trim(), national_id: v.national_id.trim(), phone: normalisePhone(v.phone),
        password: v.password, ward_id: ward.ward_id, ...(v.email.trim() ? { email: v.email.trim() } : {}) });
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message);
        const fields = Object.fromEntries((e.details ?? []).map((d) => [d.field, d.message]));
        setServerFields(fields);
      } else setError('Something went wrong.');
    } finally { lock.current = false; setBusy(false); }
  }

  if (locations.isLoading) return <Loading text="Loading locations…" />;
  if (locations.isError) return <ErrorState message="Could not load locations." onRetry={() => locations.refetch()} />;

  return (
    <Screen>
      <Text style={{ fontSize: 22, fontWeight: '800' }}>Register as a farmer</Text>
      {error ? <Banner text={error} /> : null}
      <TextField label="Full name" value={v.full_name} onChangeText={(t) => set('full_name', t)} autoCapitalize="words" error={err('full_name')} />
      <TextField label="National ID" value={v.national_id} onChangeText={(t) => set('national_id', t)} keyboardType="number-pad" error={err('national_id')} />
      <TextField label="Phone (2547XXXXXXXX)" value={v.phone} onChangeText={(t) => set('phone', t)} keyboardType="phone-pad" placeholder="254712345678" error={err('phone')} />
      <TextField label="Email (optional)" value={v.email} onChangeText={(t) => set('email', t)} keyboardType="email-address" error={err('email')} />
      <SelectField label="County" value={v.county || null} options={counties.map((c) => ({ value: c, label: c }))} onChange={(x) => set('county', x)} error={err('county')} />
      <SelectField label="Sub-county" value={v.sub_county || null} disabled={!v.county} options={subCounties.map((c) => ({ value: c, label: c }))} onChange={(x) => set('sub_county', x)} error={err('sub_county')} />
      <SelectField label="Ward" value={v.ward || null} disabled={!v.sub_county} options={wards.map((w) => ({ value: String(w.ward_id), label: w.ward }))} onChange={(x) => set('ward', x)} error={err('ward')} />
      <TextField label="Password" value={v.password} onChangeText={(t) => set('password', t)} secureTextEntry error={err('password')} textContentType="newPassword" />
      <Button title="Create account" loading={busy} onPress={submit} />
    </Screen>
  );
}
