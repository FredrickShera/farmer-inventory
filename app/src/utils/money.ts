// Money is handled as integer minor units (KES cents), parsed from text WITHOUT floating point,
// so 19.99 never becomes 1998.9999999999998.
export function parseKesToMinor(input: string): number | null {
  const s = input.trim().replace(/,/g, '');
  const m = /^(\d{1,10})(?:\.(\d{1,2}))?$/.exec(s);
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] ?? '').padEnd(2, '0') || '0');
}

export function validatePrice(input: string): string | undefined {
  if (!input.trim()) return 'Enter a price';
  if (input.trim().startsWith('-')) return 'Price cannot be negative';
  return parseKesToMinor(input) === null ? 'Use a number with up to 2 decimals' : undefined;
}

export function minorToKes(minor: number): string {
  const whole = Math.floor(minor / 100);
  const cents = String(minor % 100).padStart(2, '0');
  return `${whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${cents}`;
}

export function minorToInput(minor: number): string {
  return `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, '0')}`;
}
