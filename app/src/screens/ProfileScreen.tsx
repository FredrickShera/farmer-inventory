import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { Button, ErrorState, Loading, Screen } from '../components/ui';
import { useProfile } from '../hooks/queries';
import { colors } from '../theme';

const Row = ({ k, v }: { k: string; v: string }) => (
  <View style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border }}>
    <Text style={{ color: colors.muted, fontSize: 13 }}>{k}</Text><Text style={{ fontSize: 16, color: colors.text }}>{v}</Text>
  </View>
);

export function ProfileScreen() {
  const { signOut } = useAuth();
  const q = useProfile();
  const [busy, setBusy] = useState(false);
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <ErrorState message={(q.error as Error)?.message ?? 'Could not load profile'} onRetry={() => q.refetch()} />;
  const f = q.data;
  return (
    <Screen>
      <Text style={{ fontSize: 22, fontWeight: '800', color: colors.text }}>{f.full_name}</Text>
      <Row k="National ID" v={f.national_id} /><Row k="Phone" v={f.phone} />
      <Row k="Email" v={f.email ?? '—'} /><Row k="Status" v={f.status} />
      <Row k="Home ward" v={`${f.ward}, ${f.sub_county}, ${f.county}`} />
      <Text style={{ fontSize: 18, fontWeight: '700', marginTop: 16 }}>Plots</Text>
      {f.plots.map((p) => <Row key={p.id} k={p.is_active ? 'Plot' : 'Plot (inactive)'} v={`${p.name} · ${p.ward}${p.size_acres ? ` · ${Number(p.size_acres)} acres` : ''}`} />)}
      <Button title="Log out" variant="danger" loading={busy} onPress={async () => { setBusy(true); try { await signOut(); } finally { setBusy(false); } }} />
    </Screen>
  );
}
