import React, { useState } from 'react';
import { Alert, Platform } from 'react-native';
import { ApiError } from '../api/client';
import type { InventoryInput, InventoryItem } from '../api/types';
import { InventoryForm } from '../components/InventoryForm';
import { Button, ErrorState, Loading, Screen } from '../components/ui';
import { useDeleteItem, useProduceTypes, useProfile, useSaveItem } from '../hooks/queries';

export function InventoryEditScreen({ route, navigation }: any) {
  const item: InventoryItem | undefined = route.params?.item;
  const profile = useProfile();
  const types = useProduceTypes();
  const save = useSaveItem();
  const del = useDeleteItem();
  const [error, setError] = useState<string | null>(null);

  if (profile.isLoading || types.isLoading) return <Loading />;
  if (profile.isError || types.isError || !profile.data || !types.data)
    return <ErrorState message="Could not load the form data." onRetry={() => { profile.refetch(); types.refetch(); }} />;

  const sold = item?.status === 'sold';
  async function onSubmit(payload: InventoryInput) {
    setError(null);
    try {
      await save.mutateAsync({ id: item?.id, input: payload });
      navigation.goBack();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save. Please try again.');
    }
  }
  async function doDelete() {
    try { await del.mutateAsync(item!.id); navigation.goBack(); }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Could not delete.'); }
  }
  function confirmDelete() {
    // Alert.alert does nothing in a browser, so use the browser's own confirm dialog there.
    if (Platform.OS === 'web') {
      if (window.confirm('Delete this item? This removes it from your inventory.')) doDelete();
      return;
    }
    Alert.alert('Delete item?', 'This removes it from your inventory.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: doDelete },
    ]);
  }

  return (
    <Screen>
      <InventoryForm produceTypes={types.data} plots={profile.data.plots} initial={item} readOnly={sold}
        onSubmit={onSubmit} serverError={error} submitLabel={item ? 'Save changes' : 'Add item'} />
      {item && !sold ? <Button title="Delete item" variant="danger" loading={del.isPending} onPress={confirmDelete} /> : null}
    </Screen>
  );
}
