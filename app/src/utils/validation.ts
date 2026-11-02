// Pure validation rules, shared by the screens and unit-tested. They mirror the API/DB rules, but the
// server stays the source of truth: these only give instant, inline feedback.
export type Errors<T extends string = string> = Partial<Record<T, string>>;

export function normalisePhone(raw: string): string {
  let p = raw.replace(/[\s\-()]/g, '');
  if (p.startsWith('+')) p = p.slice(1);
  if (/^07\d{8}$/.test(p)) p = '254' + p.slice(1);
  return p;
}

export const validateFullName = (v: string) => (v.trim().length >= 2 ? undefined : 'Enter your full name');
export const validateNationalId = (v: string) => (/^\d{6,9}$/.test(v.trim()) ? undefined : 'National ID must be 6-9 digits');
export const validatePhone = (v: string) =>
  /^2547\d{8}$/.test(normalisePhone(v)) ? undefined : 'Use 2547XXXXXXXX (e.g. 254712345678)';
export const validateEmail = (v: string) => (!v.trim() || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim()) ? undefined : 'Enter a valid email');
export function validatePassword(v: string) {
  if (v.length < 8) return 'At least 8 characters';
  if (!/[A-Za-z]/.test(v) || !/\d/.test(v)) return 'Include a letter and a number';
  return undefined;
}

export type RegisterField = 'full_name' | 'national_id' | 'phone' | 'email' | 'password' | 'county' | 'sub_county' | 'ward';
export function validateRegister(v: Record<RegisterField, string>): Errors<RegisterField> {
  const e: Errors<RegisterField> = {
    full_name: validateFullName(v.full_name), national_id: validateNationalId(v.national_id),
    phone: validatePhone(v.phone), email: validateEmail(v.email), password: validatePassword(v.password),
    county: v.county ? undefined : 'Select a county', sub_county: v.sub_county ? undefined : 'Select a sub-county',
    ward: v.ward ? undefined : 'Select a ward',
  };
  return Object.fromEntries(Object.entries(e).filter(([, m]) => m)) as Errors<RegisterField>;
}

/** Quantity must be a positive number with at most 2 decimals. Zero and negatives are blocked. */
export function validateQuantity(v: string): string | undefined {
  const s = v.trim();
  if (!s) return 'Enter a quantity';
  if (!/^-?\d+(\.\d+)?$/.test(s)) return 'Enter a number';
  if (s.startsWith('-')) return 'Quantity cannot be negative';
  if (!/^\d+(\.\d{1,2})?$/.test(s)) return 'Use at most 2 decimal places';
  if (Number(s) <= 0) return 'Quantity must be greater than zero';
  if (Number(s) >= 1e10) return 'Quantity is too large';
  return undefined;
}

export function validateHarvestDate(v: string): string | undefined {
  const s = v.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return 'Use YYYY-MM-DD';
  const d = new Date(`${s}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== s) return 'That is not a real date';
  return undefined;
}

export type InventoryField = 'produce_type_id' | 'plot_id' | 'quantity' | 'expected_harvest_date' | 'price';
export interface InventoryFormValues {
  produce_type_id: number | null; plot_id: string | null; quantity: string; unit: 'kg' | 'bag' | 'crate';
  grade: 'A' | 'B' | 'C'; expected_harvest_date: string; price: string;
}
export function validateInventory(v: InventoryFormValues, priceCheck: (s: string) => string | undefined): Errors<InventoryField> {
  const e: Errors<InventoryField> = {
    produce_type_id: v.produce_type_id ? undefined : 'Select a produce type',
    plot_id: v.plot_id ? undefined : 'Select a plot',
    quantity: validateQuantity(v.quantity),
    expected_harvest_date: validateHarvestDate(v.expected_harvest_date),
    price: priceCheck(v.price),
  };
  return Object.fromEntries(Object.entries(e).filter(([, m]) => m)) as Errors<InventoryField>;
}
