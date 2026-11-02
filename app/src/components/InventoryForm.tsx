import React, { useMemo, useRef, useState } from 'react';
import { Text } from 'react-native';
import type { Grade, InventoryInput, InventoryItem, Plot, ProduceType, Unit } from '../api/types';
import { minorToInput, parseKesToMinor, validatePrice } from '../utils/money';
import { uuidv4 } from '../utils/uuid';
import { Errors, InventoryField, InventoryFormValues, validateInventory } from '../utils/validation';
import { colors } from '../theme';
import { Banner, Button, Segmented, SelectField, TextField } from './ui';

export const UNITS: Unit[] = ['kg', 'bag', 'crate'];
export const GRADES: Grade[] = ['A', 'B', 'C'];

interface Props {
  produceTypes: ProduceType[];
  plots: Plot[];
  initial?: InventoryItem;
  /** Sold items are shown read-only: no input can be edited and there is no submit button. */
  readOnly?: boolean;
  onSubmit: (payload: InventoryInput) => Promise<void>;
  submitLabel?: string;
  serverError?: string | null;
}

export function InventoryForm({ produceTypes, plots, initial, readOnly, onSubmit, submitLabel = 'Save item', serverError }: Props) {
  const activePlots = useMemo(() => plots.filter((p) => p.is_active || p.id === initial?.plot_id), [plots, initial]);
  const [v, setV] = useState<InventoryFormValues>(() => ({
    produce_type_id: initial?.produce_type_id ?? null,
    plot_id: initial?.plot_id ?? (activePlots.length === 1 ? activePlots[0].id : null),
    quantity: initial ? String(Number(initial.quantity)) : '',
    unit: initial?.unit ?? 'kg',
    grade: initial?.grade ?? 'A',
    expected_harvest_date: initial?.expected_harvest_date ?? '',
    price: initial ? minorToInput(initial.asking_price_minor) : '',
  }));
  const [touched, setTouched] = useState<Partial<Record<InventoryField, boolean>>>({});
  const [submitting, setSubmitting] = useState(false);
  // One id per opened form: if the user double-taps or retries after a timeout, the server returns the SAME record.
  const requestId = useRef(uuidv4());
  // Synchronous lock: state updates are async, so two taps in the same frame could both pass a `submitting` check.
  const lock = useRef(false);

  const all = validateInventory(v, validatePrice);
  const shown: Errors<InventoryField> = Object.fromEntries(Object.entries(all).filter(([k]) => touched[k as InventoryField])) as Errors<InventoryField>;
  const set = <K extends keyof InventoryFormValues>(k: K, val: InventoryFormValues[K], field?: InventoryField) => {
    setV((p) => ({ ...p, [k]: val }));
    if (field) setTouched((t) => ({ ...t, [field]: true }));
  };

  async function submit() {
    if (lock.current || readOnly) return;
    setTouched({ produce_type_id: true, plot_id: true, quantity: true, expected_harvest_date: true, price: true });
    if (Object.keys(all).length > 0) return;
    lock.current = true;
    setSubmitting(true);
    try {
      await onSubmit({
        plot_id: v.plot_id!, produce_type_id: v.produce_type_id!, quantity: v.quantity.trim(), unit: v.unit, grade: v.grade,
        expected_harvest_date: v.expected_harvest_date.trim(), asking_price_minor: parseKesToMinor(v.price)!,
        ...(initial ? {} : { client_request_id: requestId.current }),
      });
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }

  return (
    <>
      {readOnly ? <Banner text="This item is sold and can no longer be edited." /> : null}
      {serverError ? <Banner text={serverError} /> : null}
      <SelectField label="Produce type" disabled={readOnly} value={v.produce_type_id} error={shown.produce_type_id}
        options={produceTypes.map((p) => ({ value: p.id, label: p.name }))} onChange={(x) => set('produce_type_id', x, 'produce_type_id')} />
      <SelectField label="Plot" disabled={readOnly} value={v.plot_id} error={shown.plot_id}
        options={activePlots.map((p) => ({ value: p.id, label: `${p.name} (${p.ward})` }))} onChange={(x) => set('plot_id', x, 'plot_id')} />
      <TextField label="Quantity" editable={!readOnly} keyboardType="decimal-pad" value={v.quantity} placeholder="e.g. 25.5"
        error={shown.quantity} onChangeText={(t) => set('quantity', t, 'quantity')} />
      <Segmented label="Unit" disabled={readOnly} value={v.unit} options={UNITS} onChange={(x) => set('unit', x)} />
      <Segmented label="Quality grade" disabled={readOnly} value={v.grade} options={GRADES} onChange={(x) => set('grade', x)} />
      <TextField label="Expected harvest date" editable={!readOnly} value={v.expected_harvest_date} placeholder="YYYY-MM-DD"
        keyboardType="numbers-and-punctuation" maxLength={10} error={shown.expected_harvest_date}
        onChangeText={(t) => set('expected_harvest_date', t, 'expected_harvest_date')} />
      <TextField label="Asking price per unit (KES)" editable={!readOnly} keyboardType="decimal-pad" value={v.price} placeholder="e.g. 45.50"
        error={shown.price} onChangeText={(t) => set('price', t, 'price')} />
      {readOnly ? <Text style={{ color: colors.muted }}>Status: sold</Text> : (
        <Button title={submitLabel} loading={submitting} onPress={submit} />
      )}
    </>
  );
}
