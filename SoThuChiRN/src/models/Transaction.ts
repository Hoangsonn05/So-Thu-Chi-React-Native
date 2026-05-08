/**
 * Model class for a financial transaction.
 * Giữ nguyên 1:1 từ Transaction.java
 *
 * id: Unique identifier (AUTOINCREMENT)
 * amount: Value of the transaction
 * note: Description
 * category: Category of income/expense
 * date: Date in format dd/MM/yyyy
 * type: 0 for Expense (Chi), 1 for Income (Thu)
 * createdBy: User who created the transaction
 * deviceName: Device name where transaction was created
 * deviceId: Device identifier
 */

export interface Transaction {
  id?: number;
  doc_id?: string;
  amount: number;
  note: string;
  category: string;
  date: string;       // format: dd/MM/yyyy
  type: number;        // 0 = Chi (Expense), 1 = Thu (Income)
  createdBy?: string;
  deviceName?: string;
  deviceId?: string;
  is_synced?: number; // 0 = chưa lưu lên mạng, 1 = đã lưu
}

export interface UserProfile {
  fullName: string | null;
  email: string | null;
  phone: string | null;
  password: string | null;
  username: string | null;
  photoURL: string | null;
}
