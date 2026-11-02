import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { InventoryForm } from '../src/components/InventoryForm';
import type { InventoryItem, Plot, ProduceType } from '../src/api/types';

const produce: ProduceType[] = [{ id: 1, name: 'Maize', category: 'cereal' }];
const plots: Plot[] = [{ id: 'p1', name: 'Home plot', ward_id: 1, ward: 'Kitisuru', sub_county: 'Westlands', county: 'Nairobi', size_acres: null, is_active: true }];
const soldItem: InventoryItem = {
  id: 'i1', farmer_id: 'f1', farmer_name: 'A', plot_id: 'p1', plot_name: 'Home plot', ward_id: 1, ward: 'Kitisuru', produce_type_id: 1,
  produce_type: 'Maize', quantity: '10.00', unit: 'bag', grade: 'B', status: 'sold', expected_harvest_date: '2026-10-01',
  asking_price_minor: 250000, currency: 'KES', sold_at: '2026-10-02T00:00:00Z', created_at: '', updated_at: '',
};

async function pickProduce() {
  await fireEvent.press(screen.getByLabelText('Produce type'));
  await fireEvent.press(await screen.findByLabelText('Maize'));
}

describe('InventoryForm', () => {
  it('blocks a negative quantity with an inline error and never calls onSubmit', async () => {
    const onSubmit = jest.fn(async () => {});
    await render(<InventoryForm produceTypes={produce} plots={plots} onSubmit={onSubmit} />);
    await pickProduce();
    await fireEvent.changeText(screen.getByLabelText('Quantity'), '-5');
    await fireEvent.changeText(screen.getByLabelText('Expected harvest date'), '2026-12-01');
    await fireEvent.changeText(screen.getByLabelText('Asking price per unit (KES)'), '45.50');
    await fireEvent.press(screen.getByLabelText('Save item'));
    expect(await screen.findByText('Quantity cannot be negative')).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('blocks zero quantity', async () => {
    const onSubmit = jest.fn(async () => {});
    await render(<InventoryForm produceTypes={produce} plots={plots} onSubmit={onSubmit} />);
    await pickProduce();
    await fireEvent.changeText(screen.getByLabelText('Quantity'), '0');
    await fireEvent.changeText(screen.getByLabelText('Expected harvest date'), '2026-12-01');
    await fireEvent.changeText(screen.getByLabelText('Asking price per unit (KES)'), '10');
    await fireEvent.press(screen.getByLabelText('Save item'));
    expect(await screen.findByText('Quantity must be greater than zero')).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('a double tap submits exactly once and sends integer minor units + an idempotency key', async () => {
    const onSubmit = jest.fn(() => new Promise<void>((res) => setTimeout(res, 40)));
    await render(<InventoryForm produceTypes={produce} plots={plots} onSubmit={onSubmit} />);
    await pickProduce();
    await fireEvent.changeText(screen.getByLabelText('Quantity'), '25.5');
    await fireEvent.changeText(screen.getByLabelText('Expected harvest date'), '2026-12-01');
    await fireEvent.changeText(screen.getByLabelText('Asking price per unit (KES)'), '45.50');
    const save = screen.getByLabelText('Save item');
    // three taps in the same frame, before the first request has finished
    const tap = () => save.props.onClick({ stopPropagation() {}, preventDefault() {}, nativeEvent: {} });
    await act(async () => { tap(); tap(); tap(); });
    await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const payload = (onSubmit.mock.calls[0] as any[])[0];
    expect(payload).toMatchObject({ plot_id: 'p1', produce_type_id: 1, quantity: '25.5', unit: 'kg', grade: 'A', asking_price_minor: 4550 });
    expect(payload.client_request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('shows sold items read-only: banner, no save button, disabled inputs', async () => {
    const onSubmit = jest.fn(async () => {});
    await render(<InventoryForm produceTypes={produce} plots={plots} initial={soldItem} readOnly onSubmit={onSubmit} />);
    expect(screen.getByText('This item is sold and can no longer be edited.')).toBeTruthy();
    expect(screen.queryByLabelText('Save item')).toBeNull();
    expect(screen.getByLabelText('Quantity').props.editable).toBe(false);
  });
});
