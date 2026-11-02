import { minorToKes, parseKesToMinor, validatePrice } from '../src/utils/money';
import {
  normalisePhone, validateHarvestDate, validateNationalId, validatePassword, validatePhone, validateQuantity, validateRegister,
} from '../src/utils/validation';

describe('quantity', () => {
  it.each(['-1', '-0.5', '0', '0.00'])('blocks negative or zero: %s', (q) => {
    expect(validateQuantity(q)).toBeDefined();
  });
  it.each(['', 'abc', '1.234', '1e3'])('blocks malformed: %p', (q) => {
    expect(validateQuantity(q)).toBeDefined();
  });
  it.each(['1', '25.5', '0.01', '100.00'])('accepts %s', (q) => {
    expect(validateQuantity(q)).toBeUndefined();
  });
});

describe('phone and id', () => {
  it('normalises local and international forms to 2547XXXXXXXX', () => {
    expect(normalisePhone('0712 345 678')).toBe('254712345678');
    expect(normalisePhone('+254712345678')).toBe('254712345678');
    expect(validatePhone('0712345678')).toBeUndefined();
  });
  it('rejects non-2547 numbers', () => {
    expect(validatePhone('254112345678')).toBeDefined();
    expect(validatePhone('25471234')).toBeDefined();
  });
  it('national id is 6-9 digits', () => {
    expect(validateNationalId('12345678')).toBeUndefined();
    expect(validateNationalId('1234')).toBeDefined();
    expect(validateNationalId('12ab5678')).toBeDefined();
  });
});

describe('password, date, register', () => {
  it('requires 8+ chars with a letter and a number', () => {
    expect(validatePassword('short1')).toBeDefined();
    expect(validatePassword('allletters')).toBeDefined();
    expect(validatePassword('Passw0rd!')).toBeUndefined();
  });
  it('validates real calendar dates', () => {
    expect(validateHarvestDate('2026-12-31')).toBeUndefined();
    expect(validateHarvestDate('2026-02-30')).toBeDefined();
    expect(validateHarvestDate('31/12/2026')).toBeDefined();
  });
  it('register requires every location level', () => {
    const e = validateRegister({ full_name: 'Jane Doe', national_id: '12345678', phone: '0712345678', email: '', password: 'Passw0rd1', county: 'Nairobi', sub_county: '', ward: '' });
    expect(Object.keys(e).sort()).toEqual(['sub_county', 'ward']);
  });
});

describe('money', () => {
  it('parses to integer minor units without float error', () => {
    expect(parseKesToMinor('19.99')).toBe(1999);
    expect(parseKesToMinor('0.1')).toBe(10);
    expect(parseKesToMinor('1,250')).toBe(125000);
    expect(parseKesToMinor('12.345')).toBeNull();
    expect(parseKesToMinor('-3')).toBeNull();
  });
  it('formats and validates', () => {
    expect(minorToKes(125050)).toBe('1,250.50');
    expect(validatePrice('-1')).toBeDefined();
    expect(validatePrice('45.50')).toBeUndefined();
  });
});
