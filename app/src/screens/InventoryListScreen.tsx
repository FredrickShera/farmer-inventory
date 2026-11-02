import React, { useMemo, useState } from 'react';
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { InventoryFilters, InventoryItem, InventoryStatus } from '../api/types';
import { Button, EmptyState, ErrorState, Loading, SelectField } from '../components/ui';
import { useInventory, useProduceTypes } from '../hooks/queries';
import { colors, MIN_TOUCH, space } from '../theme';
import { minorToKes } from '../utils/money';

const STATUS_OPTIONS = [{ value: 'all', label: 'All statuses' }, { value: 'available', label: 'Available' },
  { value: 'reserved', label: 'Reserved' }, { value: 'sold', label: 'Sold' }];

export function InventoryListScreen({ navigation }: any) {
  const [produce, setProduce] = useState<number | 'all'>('all');
  const [status, setStatus] = useState<InventoryStatus | 'all'>('all');
  const filters: InventoryFilters = useMemo(() => ({
    ...(produce !== 'all' ? { produce_type_id: produce } : {}), ...(status !== 'all' ? { status } : {}),
  }), [produce, status]);
  const q = useInventory(filters);
  const types = useProduceTypes();
  const items = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data]);
  // Pull-to-refresh must not be driven by background refetches/next-page loads.
  const [pulling, setPulling] = useState(false);
  const onRefresh = async () => { setPulling(true); try { await q.refetch(); } finally { setPulling(false); } };

  const header = (
    <View style={{ gap: space.xs }}>
      <Button title="+ Add inventory item" onPress={() => navigation.navigate('InventoryEdit')} />
      <SelectField label="Produce type" value={produce} onChange={setProduce}
        options={[{ value: 'all' as const, label: 'All produce' }, ...(types.data ?? []).map((t) => ({ value: t.id as number | 'all', label: t.name }))]} />
      <SelectField label="Status" value={status} onChange={(v) => setStatus(v as InventoryStatus | 'all')} options={STATUS_OPTIONS as any} />
    </View>
  );

  let body: React.ReactNode;
  if (q.isLoading) body = <Loading text="Loading your inventory…" />;
  else if (q.isError && items.length === 0) body = <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />;
  else body = (
    <FlatList<InventoryItem>
      data={items} keyExtractor={(i) => i.id} contentContainerStyle={styles.list} ListHeaderComponent={header}
      refreshControl={<RefreshControl refreshing={pulling} onRefresh={onRefresh} />}
      onEndReachedThreshold={0.4} onEndReached={() => q.hasNextPage && !q.isFetchingNextPage && q.fetchNextPage()}
      ListEmptyComponent={<EmptyState title="No inventory yet" hint={produce !== 'all' || status !== 'all' ? 'No items match these filters.' : 'Tap "Add inventory item" to record your first produce.'} />}
      ListFooterComponent={q.isFetchingNextPage ? <Loading text="Loading more…" /> : q.isError ? <ErrorState message="Could not load more." onRetry={() => q.fetchNextPage()} /> : undefined}
      renderItem={({ item }) => (
        <Pressable accessibilityRole="button" accessibilityLabel={`${item.produce_type}, ${item.quantity} ${item.unit}, ${item.status}`}
          style={styles.card} onPress={() => navigation.navigate('InventoryEdit', { item })}>
          <View style={styles.row}>
            <Text style={styles.title}>{item.produce_type}</Text>
            <Text style={[styles.badge, item.status === 'sold' && { color: colors.sold }]}>{item.status.toUpperCase()}</Text>
          </View>
          <Text style={styles.meta}>{Number(item.quantity)} {item.unit} · Grade {item.grade} · {item.plot_name}</Text>
          <Text style={styles.meta}>KES {minorToKes(item.asking_price_minor)} per {item.unit} · harvest {item.expected_harvest_date}</Text>
        </Pressable>
      )}
    />
  );
  return <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={['top']}>{body}</SafeAreaView>;
}

const styles = StyleSheet.create({
  list: { padding: space.lg, gap: space.sm, flexGrow: 1 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: space.lg, minHeight: MIN_TOUCH, borderWidth: 1, borderColor: colors.border },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontSize: 17, fontWeight: '700', color: colors.text }, badge: { fontSize: 12, fontWeight: '700', color: colors.primary },
  meta: { color: colors.muted, marginTop: 2 },
});
