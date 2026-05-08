/**
 * DatabaseHelper - SQLite helper using expo-sqlite
 * 
 * Tái tạo 1:1 từ DatabaseHelper.java:
 * - Database name: SoThuChi.db
 * - Table: transactions (id, amount, note, category, date, type, created_by, device_name, device_id)
 * - Table: users (id, full_name, email, phone, password)
 * 
 * Giữ nguyên tên bảng và tên cột từ Android Native.
 */

import * as SQLite from 'expo-sqlite';
import { Transaction, UserProfile } from '../models/Transaction';
import { normalizeForSearch, prepareSearchQuery } from '../utils/textUtils';
import { getRelatedCategories } from '../config/thematicKeywords';

const DATABASE_NAME = 'SoThuChi.db';

// Table names (giữ nguyên từ Java)
const TABLE_TRANSACTIONS = 'transactions';
const TABLE_USERS = 'users';

// Transaction columns
const COLUMN_ID = 'id';
const COLUMN_AMOUNT = 'amount';
const COLUMN_NOTE = 'note';
const COLUMN_CATEGORY = 'category';
const COLUMN_DATE = 'date';
const COLUMN_TYPE = 'type';
const COLUMN_CREATED_BY = 'created_by';
const COLUMN_DEVICE_NAME = 'device_name';
const COLUMN_DEVICE_ID = 'device_id';
const COLUMN_SEARCH_CONTENT = 'search_content'; // New searchable column
const COLUMN_IS_SYNCED = 'is_synced'; // 0 = unsynced, 1 = synced

// User columns
const COLUMN_U_NAME = 'full_name';
const COLUMN_U_EMAIL = 'email';
const COLUMN_U_PHONE = 'phone';
const COLUMN_U_PASS = 'password';
const COLUMN_U_USERNAME = 'username';
const COLUMN_U_PHOTO = 'photo_url';

class DatabaseHelper {
  private db: SQLite.SQLiteDatabase | null = null;
  private initPromise: Promise<SQLite.SQLiteDatabase> | null = null;

  /**
   * Open the database and create tables if they don't exist.
   */
  async open(): Promise<SQLite.SQLiteDatabase> {
    if (this.db) return this.db;
    if (this.initPromise) return this.initPromise;

    this.initPromise = (async () => {
      this.db = await SQLite.openDatabaseAsync(DATABASE_NAME);

      // Create tables (giữ nguyên schema từ Java)
      await this.db.execAsync(`
      CREATE TABLE IF NOT EXISTS ${TABLE_TRANSACTIONS} (
        ${COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
        ${COLUMN_AMOUNT} INTEGER,
        ${COLUMN_NOTE} TEXT,
        ${COLUMN_CATEGORY} TEXT,
        ${COLUMN_DATE} TEXT,
        ${COLUMN_TYPE} INTEGER,
        ${COLUMN_CREATED_BY} TEXT,
        ${COLUMN_DEVICE_NAME} TEXT,
        ${COLUMN_DEVICE_ID} TEXT,
        ${COLUMN_SEARCH_CONTENT} TEXT,
        ${COLUMN_IS_SYNCED} INTEGER DEFAULT 0
      );

      CREATE TABLE IF NOT EXISTS ${TABLE_USERS} (
        ${COLUMN_ID} INTEGER PRIMARY KEY AUTOINCREMENT,
        ${COLUMN_U_NAME} TEXT,
        ${COLUMN_U_EMAIL} TEXT,
        ${COLUMN_U_PHONE} TEXT,
        ${COLUMN_U_PASS} TEXT,
        ${COLUMN_U_USERNAME} TEXT,
        ${COLUMN_U_PHOTO} TEXT
      );
    `);

      // Migration: Add COLUMN_SEARCH_CONTENT and COLUMN_IS_SYNCED if missing
      try {
        const tableInfo = await this.db.getAllAsync<any>(`PRAGMA table_info(${TABLE_TRANSACTIONS})`);
        const hasSearchColumn = tableInfo.some((col: any) =>
          col.name && col.name.toLowerCase() === COLUMN_SEARCH_CONTENT.toLowerCase()
        );
        const hasSyncColumn = tableInfo.some((col: any) =>
          col.name && col.name.toLowerCase() === COLUMN_IS_SYNCED.toLowerCase()
        );

        if (!hasSearchColumn) {
          await this.db.execAsync(`ALTER TABLE ${TABLE_TRANSACTIONS} ADD COLUMN ${COLUMN_SEARCH_CONTENT} TEXT`);
          // Migrate existing rows - populate normalized content
          const rows = await this.db.getAllAsync<any>(`SELECT ${COLUMN_ID}, ${COLUMN_NOTE}, ${COLUMN_CATEGORY} FROM ${TABLE_TRANSACTIONS}`);
          for (const row of rows) {
            const content = ` ${normalizeForSearch(`${row.note} ${row.category}`)} `;
            await this.db.runAsync(
              `UPDATE ${TABLE_TRANSACTIONS} SET ${COLUMN_SEARCH_CONTENT} = ? WHERE ${COLUMN_ID} = ?`,
              [content, row.id]
            );
          }
        }

        if (!hasSyncColumn) {
          // All existing transactions were probably fetched from cloud or already synced, default them to 1
          await this.db.execAsync(`ALTER TABLE ${TABLE_TRANSACTIONS} ADD COLUMN ${COLUMN_IS_SYNCED} INTEGER DEFAULT 1`);
        }
      } catch (e: any) {
        // Silently ignore "duplicate column name" as it means we are already in sync
        if (e.message && e.message.includes('duplicate column name')) {
          console.log('Search column already exists, skipping migration.');
        } else {
          console.error('Migration error:', e);
        }
      }

      // Migration: Add COLUMN_U_USERNAME to users table if missing
      try {
        const usersTableInfo = await this.db.getAllAsync<any>(`PRAGMA table_info(${TABLE_USERS})`);
        const hasUsernameColumn = usersTableInfo.some((col: any) =>
          col.name && col.name.toLowerCase() === COLUMN_U_USERNAME.toLowerCase()
        );
        if (!hasUsernameColumn) {
          await this.db.execAsync(`ALTER TABLE ${TABLE_USERS} ADD COLUMN ${COLUMN_U_USERNAME} TEXT`);
          console.log('Migration: Added username column to users table.');
        }
      } catch (e: any) {
        console.error('Users migration error:', e);
      }

      // Migration: Add COLUMN_U_PHOTO to users table if missing
      try {
        const usersTableInfo = await this.db.getAllAsync<any>(`PRAGMA table_info(${TABLE_USERS})`);
        const hasPhotoColumn = usersTableInfo.some((col: any) =>
          col.name && col.name.toLowerCase() === COLUMN_U_PHOTO.toLowerCase()
        );
        if (!hasPhotoColumn) {
          await this.db.execAsync(`ALTER TABLE ${TABLE_USERS} ADD COLUMN ${COLUMN_U_PHOTO} TEXT`);
          console.log('Migration: Added photo_url column to users table.');
        }
      } catch (e: any) {
        console.error('Users photo migration error:', e);
      }

      return this.db;
    })();

    return this.initPromise;
  }

  /**
   * Chuyển đổi kết quả từ SQLite (snake_case) sang interface Transaction (camelCase)
   */
  private mapRowToTransaction(row: any): Transaction {
    return {
      id: row.id,
      amount: row.amount,
      note: row.note,
      category: row.category,
      date: row.date,
      type: row.type,
      createdBy: row.created_by,
      deviceName: row.device_name,
      deviceId: row.device_id,
      is_synced: row.is_synced
    };
  }

  /**
   * Insert a new transaction (giữ nguyên logic từ addTransaction trong Java)
   */
  async addTransaction(t: Transaction): Promise<number> {
    const db = await this.open();
    const searchContent = ` ${normalizeForSearch(`${t.note} ${t.category}`)} `;
    // Nếu t.is_synced được set (ví dụ từ FirebaseSyncService kéo về), thì dùng giá trị đó, ngược lại mặc định là 0 (chưa sync)
    const isSynced = t.is_synced !== undefined ? t.is_synced : 0;
    
    const result = await db.runAsync(
      `INSERT INTO ${TABLE_TRANSACTIONS} (${COLUMN_AMOUNT}, ${COLUMN_NOTE}, ${COLUMN_CATEGORY}, ${COLUMN_DATE}, ${COLUMN_TYPE}, ${COLUMN_CREATED_BY}, ${COLUMN_DEVICE_NAME}, ${COLUMN_DEVICE_ID}, ${COLUMN_SEARCH_CONTENT}, ${COLUMN_IS_SYNCED}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [t.amount, t.note, t.category, t.date, t.type, t.createdBy ?? '', t.deviceName ?? '', t.deviceId ?? '', searchContent, isSynced]
    );
    return result.lastInsertRowId;
  }

  /**
   * Get all transactions ordered by id DESC (giữ nguyên từ Java)
   */
  async getAllTransactions(): Promise<Transaction[]> {
    const db = await this.open();
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} ORDER BY ${COLUMN_ID} DESC`
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Get transactions by month and year.
   * Date format: dd/MM/yyyy, filter bằng LIKE '%/MM/yyyy' (giữ nguyên từ Java)
   */
  async getTransactionsByMonth(month: number, year: number): Promise<Transaction[]> {
    const db = await this.open();
    const monthStr = month < 10 ? `0${month}` : `${month}`;
    const pattern = `%/${monthStr}/${year}%`;
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} LIKE ? ORDER BY ${COLUMN_ID} DESC`,
      [pattern]
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Get transactions by year (giữ nguyên từ Java)
   */
  async getTransactionsByYear(year: number): Promise<Transaction[]> {
    const db = await this.open();
    const pattern = `%/${year}%`;
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} LIKE ? ORDER BY ${COLUMN_ID} DESC`,
      [pattern]
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Get transactions by exact date (giữ nguyên từ Java)
   */
  async getTransactionsByDate(date: string): Promise<Transaction[]> {
    const db = await this.open();
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} = ? ORDER BY ${COLUMN_ID} DESC`,
      [date]
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Lấy tổng số tiền theo ngày và loại (0: Chi, 1: Thu)
   * Giữ nguyên từ getSumByDate trong Java
   */
  async getSumByDate(date: string, type: number): Promise<number> {
    const db = await this.open();
    const result = await db.getFirstAsync<{ total: number }>(
      `SELECT SUM(${COLUMN_AMOUNT}) as total FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} = ? AND ${COLUMN_TYPE} = ?`,
      [date, type]
    );
    return result?.total ?? 0;
  }

  /**
   * Lấy tổng Thu, Chi, Tổng của cả tháng
   * Giữ nguyên từ getSummaryByMonth trong Java
   * Returns [income, expense, balance]
   */
  async getSummaryByMonth(month: number, year: number): Promise<[number, number, number]> {
    const db = await this.open();
    const monthStr = month < 10 ? `0${month}` : `${month}`;
    const pattern = `%/${monthStr}/${year}`;

    const incomeResult = await db.getFirstAsync<{ total: number }>(
      `SELECT SUM(${COLUMN_AMOUNT}) as total FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} LIKE ? AND ${COLUMN_TYPE} = 1`,
      [pattern]
    );
    const expenseResult = await db.getFirstAsync<{ total: number }>(
      `SELECT SUM(${COLUMN_AMOUNT}) as total FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_DATE} LIKE ? AND ${COLUMN_TYPE} = 0`,
      [pattern]
    );

    const income = incomeResult?.total ?? 0;
    const expense = expenseResult?.total ?? 0;
    return [income, expense, income - expense];
  }

  /**
   * Lấy tổng tất cả Thu/Chi toàn bộ quá trình sử dụng
   * Giữ nguyên từ getAllTimeSummary trong Java
   */
  async getAllTimeSummary(): Promise<[number, number, number]> {
    const db = await this.open();

    const incomeResult = await db.getFirstAsync<{ total: number }>(
      `SELECT SUM(${COLUMN_AMOUNT}) as total FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_TYPE} = 1`
    );
    const expenseResult = await db.getFirstAsync<{ total: number }>(
      `SELECT SUM(${COLUMN_AMOUNT}) as total FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_TYPE} = 0`
    );

    const income = incomeResult?.total ?? 0;
    const expense = expenseResult?.total ?? 0;
    return [income, expense, income - expense];
  }

  /**
   * Xóa toàn bộ giao dịch cục bộ
   * Giữ nguyên từ clearAllTransactions trong Java
   */
  async clearAllTransactions(): Promise<void> {
    const db = await this.open();
    await db.runAsync(`DELETE FROM ${TABLE_TRANSACTIONS}`);
  }

  /**
   * Xóa toàn bộ dữ liệu (cả giao dịch và user)
   * Dùng khi đăng xuất
   */
  async clearAllData(): Promise<void> {
    const db = await this.open();
    await db.execAsync(`DELETE FROM ${TABLE_TRANSACTIONS}; DELETE FROM ${TABLE_USERS};`);
  }

  /**
   * Lưu thông tin người dùng - chỉ hỗ trợ 1 user local
   * Giữ nguyên từ saveUserLocal trong Java
   */
  async saveUserLocal(name: string | null, email: string | null, phone: string | null, pass: string | null, username: string | null = null, photoURL: string | null = null): Promise<void> {
    const db = await this.open();
    // Xóa thông tin cũ trước khi lưu mới (app này hỗ trợ 1 user local)
    await db.runAsync(`DELETE FROM ${TABLE_USERS}`);
    await db.runAsync(
      `INSERT INTO ${TABLE_USERS} (${COLUMN_U_NAME}, ${COLUMN_U_EMAIL}, ${COLUMN_U_PHONE}, ${COLUMN_U_PASS}, ${COLUMN_U_USERNAME}, ${COLUMN_U_PHOTO}) VALUES (?, ?, ?, ?, ?, ?)`,
      [name ?? '', email ?? '', phone ?? '', pass ?? '', username ?? '', photoURL ?? '']
    );
  }

  /**
   * Cập nhật một phần thông tin user local (partial update — không xóa toàn bộ)
   * Dùng cho tính năng chỉnh sửa profile và đổi mật khẩu.
   */
  async updateUserLocal(fields: Partial<{ fullName: string; email: string; phone: string; password: string; username: string; photoURL: string }>): Promise<void> {
    if (Object.keys(fields).length === 0) return;
    const db = await this.open();

    const columnMap: Record<string, string> = {
      fullName: COLUMN_U_NAME,
      email: COLUMN_U_EMAIL,
      phone: COLUMN_U_PHONE,
      password: COLUMN_U_PASS,
      username: COLUMN_U_USERNAME,
      photoURL: COLUMN_U_PHOTO,
    };

    const setClauses: string[] = [];
    const values: any[] = [];

    for (const [key, value] of Object.entries(fields)) {
      const col = columnMap[key];
      if (col) {
        setClauses.push(`${col} = ?`);
        values.push(value ?? '');
      }
    }

    if (setClauses.length === 0) return;
    await db.runAsync(
      `UPDATE ${TABLE_USERS} SET ${setClauses.join(', ')} WHERE 1=1`,
      values
    );
  }

  /**
   * Lấy thông tin user hiện tại
   * Giữ nguyên từ getLocalUser trong Java
   */
  async getLocalUser(): Promise<UserProfile | null> {
    const db = await this.open();
    const row = await db.getFirstAsync<{
      full_name: string;
      email: string;
      phone: string;
      password: string;
      username: string;
      photo_url: string;
    }>(`SELECT * FROM ${TABLE_USERS} LIMIT 1`);

    if (!row) return null;
    return {
      fullName: row.full_name,
      email: row.email,
      phone: row.phone,
      password: row.password,
      username: row.username ?? null,
      photoURL: row.photo_url ?? null,
    };
  }

  /**
   * Batch insert transactions (for syncing)
   * Giữ nguyên từ addTransactions trong Java
   */
  async addTransactions(transactions: Transaction[]): Promise<void> {
    const db = await this.open();
    // Sử dụng transaction của SQLite để tăng tốc độ nạp dữ liệu
    await db.withTransactionAsync(async () => {
      for (const t of transactions) {
        const searchContent = ` ${normalizeForSearch(`${t.note} ${t.category}`)} `;
        // data pulled from cloud is considered fully synced (1)
        await db.runAsync(
          `INSERT INTO ${TABLE_TRANSACTIONS} (${COLUMN_AMOUNT}, ${COLUMN_NOTE}, ${COLUMN_CATEGORY}, ${COLUMN_DATE}, ${COLUMN_TYPE}, ${COLUMN_CREATED_BY}, ${COLUMN_DEVICE_NAME}, ${COLUMN_DEVICE_ID}, ${COLUMN_SEARCH_CONTENT}, ${COLUMN_IS_SYNCED}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [t.amount, t.note, t.category, t.date, t.type, t.createdBy ?? '', t.deviceName ?? '', t.deviceId ?? '', searchContent, 1]
        );
      }
    });
  }
  /**
   * Lấy tổng Thu/Chi theo từng ngày trong một khoảng thời gian.
   * Phục vụ cho Biểu đồ Đường trên Dashboard.
   */
  async getDailySummariesInRange(dates: string[]): Promise<{ date: string, income: number, expense: number }[]> {
    const db = await this.open();
    const results = [];

    for (const date of dates) {
      const income = await this.getSumByDate(date, 1);
      const expense = await this.getSumByDate(date, 0);
      results.push({ date, income, expense });
    }

    return results;
  }

  /**
   * Tìm kiếm giao dịch nâng cao:
   * - Không dấu (Diacritic-insensitive)
   * - Tìm kiếm theo cụm từ (Flexible phrase matching)
   * - Tìm kiếm theo chủ đề liên quan (Thematic search)
   */
  async searchTransactions(query: string): Promise<Transaction[]> {
    const db = await this.open();

    // 1. Chuẩn hóa truy vấn (không dấu)
    const normalizedQuery = normalizeForSearch(query);
    // 2. Lấy danh sách các hạng mục liên quan theo chủ đề
    const relatedCategories = getRelatedCategories(normalizedQuery);

    let whereClause = `${COLUMN_SEARCH_CONTENT} LIKE ?`;
    let params: any[] = [`% ${normalizedQuery} %`];

    // 3. Nếu gõ "food" -> tìm các giao dịch có hạng mục "Ăn uống"
    if (relatedCategories.length > 0) {
      const categoryPlaceholders = relatedCategories.map(() => '?').join(',');
      whereClause += ` OR ${COLUMN_CATEGORY} IN (${categoryPlaceholders})`;
      params = [...params, ...relatedCategories];
    }

    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} WHERE ${whereClause} ORDER BY ${COLUMN_ID} DESC`,
      params
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Get all transactions that are not yet synced to the cloud
   */
  async getUnsyncedTransactions(): Promise<Transaction[]> {
    const db = await this.open();
    const rows = await db.getAllAsync<any>(
      `SELECT * FROM ${TABLE_TRANSACTIONS} WHERE ${COLUMN_IS_SYNCED} = 0 ORDER BY ${COLUMN_ID} ASC`
    );
    return rows.map(this.mapRowToTransaction);
  }

  /**
   * Mark an array of transaction IDs as successfully synced to the cloud
   */
  async markAsSynced(ids: number[]): Promise<void> {
    if (ids.length === 0) return;
    const db = await this.open();
    const placeholders = ids.map(() => '?').join(',');
    await db.runAsync(
      `UPDATE ${TABLE_TRANSACTIONS} SET ${COLUMN_IS_SYNCED} = 1 WHERE ${COLUMN_ID} IN (${placeholders})`,
      ids
    );
  }
}

// Singleton instance
export const db = new DatabaseHelper();
export default db;
