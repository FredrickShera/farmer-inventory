export type Unit = 'kg' | 'bag' | 'crate';
export type Grade = 'A' | 'B' | 'C';
export type InventoryStatus = 'available' | 'reserved' | 'sold';

export interface SessionUser { id: string; role: 'farmer' | 'officer' | 'admin'; farmer_id: string | null }
export interface TokenResponse {
  access_token: string; refresh_token: string; token_type: string;
  expires_in: number; expires_at: number; user: SessionUser | null;
}
export interface Location { ward_id: number; ward: string; sub_county_id: number; sub_county: string; county_id: number; county: string }
export interface ProduceType { id: number; name: string; category: string }
export interface Plot {
  id: string; name: string; ward_id: number; ward: string; sub_county: string; county: string;
  size_acres: string | null; is_active: boolean;
}
export interface Farmer {
  id: string; full_name: string; national_id: string; phone: string; email: string | null;
  ward_id: number; ward: string; sub_county: string; county: string; status: string;
  created_at: string; updated_at: string; plots: Plot[];
}
export interface InventoryItem {
  id: string; farmer_id: string; farmer_name: string; plot_id: string; plot_name: string;
  ward_id: number; ward: string; produce_type_id: number; produce_type: string;
  quantity: string; unit: Unit; grade: Grade; status: InventoryStatus;
  expected_harvest_date: string; asking_price_minor: number; currency: string;
  sold_at: string | null; created_at: string; updated_at: string;
}
export interface Page<T> { items: T[]; page: number; page_size: number; total: number; has_more: boolean }

export interface RegisterInput {
  full_name: string; national_id: string; phone: string; password: string; ward_id: number; email?: string;
}
export interface InventoryInput {
  plot_id: string; produce_type_id: number; quantity: string; unit: Unit; grade: Grade;
  expected_harvest_date: string; asking_price_minor: number; client_request_id?: string;
}
export interface InventoryFilters { produce_type_id?: number; status?: InventoryStatus }
