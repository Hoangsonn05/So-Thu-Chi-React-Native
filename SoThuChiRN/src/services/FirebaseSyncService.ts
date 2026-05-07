/**
 * FirebaseSyncService.ts
 * Centralized logic for bi-directional synchronization between SQLite and Firebase Firestore.
 *
 * ──────────────────────────────────────────────────────────────────────────────
 * REAL-TIME LISTENER (startRealtimeListener / stopRealtimeListener)
 * ──────────────────────────────────────────────────────────────────────────────
 * Khi Telegram Bot (hoặc bất kỳ thiết bị nào khác) push dữ liệu lên Firestore,
 * onSnapshot sẽ phát hiện ngay lập tức và:
 *   1. Chỉ xử lý các document type "added" (document mới).
 *   2. Bỏ qua document nếu deviceId khớp với thiết bị hiện tại
 *      (tức là chính app đã push → đã có trong SQLite, không insert lại).
 *   3. Insert document mới vào SQLite.
 *   4. Gọi transactionEvents.emitChanged() → tất cả màn hình tự refresh.
 */

import { firestoreDb } from '../config/firebase';
import db from '../database/DatabaseHelper';
import { Transaction } from '../models/Transaction';
import { transactionEvents } from './TransactionEvents';
import * as Application from 'expo-application';

// Firestore unsubscribe function — giữ tham chiếu để hủy khi logout
type Unsubscribe = () => void;

class FirebaseSyncService {
  private isSyncing = false;
  private realtimeUnsubscribe: Unsubscribe | null = null;

  // ─── Device ID helpers ───────────────────────────────────────────────────────
  /**
   * Lấy Device ID an toàn. Dùng để filter tránh insert duplicate
   * khi chính app push lên Firestore và onSnapshot fires lại.
   */
  private async getDeviceId(): Promise<string> {
    try {
      // expo-application: getAndroidId() trên Android
      const id = Application.getAndroidId();
      return id ?? 'unknown_device';
    } catch {
      return 'unknown_device';
    }
  }

  // ─── Real-time Listener ───────────────────────────────────────────────────────

  /**
   * Bắt đầu lắng nghe thay đổi real-time từ Firestore.
   * Gọi sau khi user đăng nhập thành công.
   * Tự động hủy listener cũ nếu đã tồn tại.
   */
  startRealtimeListener(uid: string): void {
    // Hủy listener cũ nếu có (ví dụ: switch account)
    this.stopRealtimeListener();

    console.log('[FirebaseSync] Starting real-time Firestore listener...');

    const collectionRef = firestoreDb()
      .collection('users')
      .doc(uid)
      .collection('transactions');

    this.realtimeUnsubscribe = collectionRef.onSnapshot(
      async (snapshot) => {
        // Chỉ xử lý document ĐƯỢC THÊM MỚI (không xử lý modified/removed)
        const addedChanges = snapshot.docChanges().filter(
          (change) => change.type === 'added'
        );

        if (addedChanges.length === 0) return;

        const currentDeviceId = await this.getDeviceId();
        let hasNewData = false;

        for (const change of addedChanges) {
          const data = change.doc.data();
          const docId = change.doc.id;

          // ── Kiểm tra tránh duplicate ──────────────────────────────────────
          // Nếu document do chính thiết bị này push (sync_xxx / legacy_xxx)
          // thì bỏ qua vì đã tồn tại trong SQLite.
          const docDeviceId: string = data.deviceId || '';
          const isFromThisDevice =
            docDeviceId !== 'telegram_bot' &&
            docDeviceId !== '' &&
            docDeviceId === currentDeviceId;

          if (isFromThisDevice) {
            console.log(`[FirebaseSync] Skipping own doc: ${docId}`);
            continue;
          }

          // ── Parse date từ Firestore ──────────────────────────────────────
          let dateStr = '';
          if (data.date && typeof data.date === 'string') {
            // Ưu tiên field "date" (dd/MM/yyyy) — đúng format app
            dateStr = data.date;
          } else if (data.timestamp) {
            try {
              const dateObj = data.timestamp.toDate();
              const day = String(dateObj.getDate()).padStart(2, '0');
              const month = String(dateObj.getMonth() + 1).padStart(2, '0');
              const year = dateObj.getFullYear();
              dateStr = `${day}/${month}/${year}`;
            } catch {
              dateStr = new Date().toLocaleDateString('vi-VN').replace(/\//g, '/');
            }
          }

          if (!dateStr) {
            const now = new Date();
            dateStr = `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
          }

          const newTransaction: Transaction = {
            amount: Number(data.amount) || 0,
            note: String(data.note || ''),
            category: String(data.category || 'Khác'),
            date: dateStr,
            type: Number(data.type) === 1 ? 1 : 0,
            createdBy: String(data.createdBy || uid),
            deviceName: String(data.deviceName || ''),
            deviceId: String(data.deviceId || ''),
          };

          // Bỏ qua giao dịch không hợp lệ
          if (newTransaction.amount <= 0) {
            console.warn(`[FirebaseSync] Skipping invalid amount doc: ${docId}`);
            continue;
          }

          try {
            await db.addTransaction(newTransaction);
            hasNewData = true;
            console.log(
              `[FirebaseSync] ✅ Inserted from Firestore: ${docId} | ${newTransaction.category} | ${newTransaction.amount}`
            );
          } catch (insertErr) {
            console.error(`[FirebaseSync] Insert error for ${docId}:`, insertErr);
          }
        }

        // Chỉ emit event nếu thực sự có dữ liệu mới được insert
        if (hasNewData) {
          transactionEvents.emitChanged();
          console.log('[FirebaseSync] 🔔 UI refresh triggered.');
        }
      },
      (error) => {
        // Lỗi mạng / permission — không crash app
        console.error('[FirebaseSync] onSnapshot error:', error);
      }
    );

    console.log('[FirebaseSync] Real-time listener started ✅');
  }

  /**
   * Hủy real-time listener. Gọi khi user đăng xuất.
   */
  stopRealtimeListener(): void {
    if (this.realtimeUnsubscribe) {
      this.realtimeUnsubscribe();
      this.realtimeUnsubscribe = null;
      console.log('[FirebaseSync] Real-time listener stopped.');
    }
  }

  // ─── One-shot Pull (dùng khi login / manual sync) ────────────────────────────

  /**
   * Pull all transactions từ Firestore và thay thế dữ liệu SQLite cục bộ.
   * Dùng khi đăng nhập và khi user bấm "Pull from Cloud".
   */
  async pullTransactions(uid: string): Promise<void> {
    try {
      const snapshot = await firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('transactions')
        .get();

      if (snapshot.empty) {
        console.log('No transactions found on Cloud.');
        await db.clearAllTransactions();
        transactionEvents.emitChanged();
        return;
      }

      const cloudTransactions: Transaction[] = [];
      snapshot.forEach((doc) => {
        const data = doc.data();

        let dateStr = '';
        if (data.date && typeof data.date === 'string') {
          dateStr = data.date;
        } else if (data.timestamp) {
          try {
            const dateObj = data.timestamp.toDate();
            const day = String(dateObj.getDate()).padStart(2, '0');
            const month = String(dateObj.getMonth() + 1).padStart(2, '0');
            const year = dateObj.getFullYear();
            dateStr = `${day}/${month}/${year}`;
          } catch {
            dateStr = '';
          }
        }

        if (!dateStr) {
          const now = new Date();
          dateStr = `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()}`;
        }

        cloudTransactions.push({
          amount: data.amount || 0,
          note: data.note || '',
          category: data.category || '',
          date: dateStr,
          type: data.type || 0,
          createdBy: data.createdBy || uid,
          deviceName: data.deviceName || '',
          deviceId: data.deviceId || '',
        });
      });

      await db.clearAllTransactions();

      if (cloudTransactions.length > 0) {
        await db.addTransactions(cloudTransactions);
      }

      transactionEvents.emitChanged();
      console.log(`Successfully synced ${cloudTransactions.length} transactions from Cloud.`);
    } catch (error) {
      console.error('FirebaseSyncService Error (pull):', error);
      throw error;
    }
  }

  // ─── Push ─────────────────────────────────────────────────────────────────────

  /**
   * Push toàn bộ giao dịch local lên Firestore.
   */
  async pushTransactions(uid: string): Promise<void> {
    try {
      const localTransactions = await db.getAllTransactions();
      if (localTransactions.length === 0) return;

      const userDocRef = firestoreDb().collection('users').doc(uid);
      const batch = firestoreDb().batch();

      localTransactions.forEach((t, index) => {
        const [dd, mm, yyyy] = (t.date || '01/01/2024').split('/');
        const docId = `sync_${Date.now()}_${index}`;
        const docRef = userDocRef.collection('transactions').doc(docId);

        batch.set(docRef, {
          amount: t.amount || 0,
          note: t.note || '',
          category: t.category || '',
          type: t.type || 0,
          timestamp: new Date(parseInt(yyyy, 10), parseInt(mm, 10) - 1, parseInt(dd, 10)),
          yearMonth: `${yyyy}-${mm}`,
          year: parseInt(yyyy, 10),
          lastUpdated: new Date(),
          createdBy: t.createdBy || uid || '',
          deviceName: t.deviceName || '',
          deviceId: t.deviceId || '',
        }, { merge: true });
      });

      await batch.commit();
      console.log('Successfully pushed local data to Cloud.');
    } catch (error) {
      console.error('FirebaseSyncService Error (push):', error);
      throw error;
    }
  }

  /**
   * Push một giao dịch đơn lên Firestore.
   */
  async pushSingleTransaction(uid: string, t: Transaction, prefix: 'legacy' | 'sync'): Promise<void> {
    try {
      if (!t.id) return;

      const [dd, mm, yyyy] = (t.date || '01/01/2024').split('/');
      const docId = `${prefix}_${t.id}`;
      const docRef = firestoreDb().collection('users').doc(uid).collection('transactions').doc(docId);

      await docRef.set({
        amount: t.amount || 0,
        note: t.note || '',
        category: t.category || '',
        type: t.type || 0,
        timestamp: new Date(parseInt(yyyy, 10), parseInt(mm, 10) - 1, parseInt(dd, 10)),
        yearMonth: `${yyyy}-${mm}`,
        year: parseInt(yyyy, 10),
        lastUpdated: new Date(),
        createdBy: t.createdBy || uid || '',
        deviceName: t.deviceName || '',
        deviceId: t.deviceId || '',
      }, { merge: true });

      await db.markAsSynced([t.id]);
      transactionEvents.emitChanged();
    } catch (error) {
      console.error(`FirebaseSyncService Error (pushSingle - ${prefix}):`, error);
      throw error;
    }
  }

  /**
   * Push tất cả giao dịch chưa sync (is_synced = 0).
   */
  async pushUnsyncedTransactions(uid: string): Promise<void> {
    if (this.isSyncing) return;

    try {
      this.isSyncing = true;
      const unsyncedTransactions = await db.getUnsyncedTransactions();
      if (unsyncedTransactions.length === 0) return;

      console.log(`Starting background sync for ${unsyncedTransactions.length} transactions...`);

      for (const t of unsyncedTransactions) {
        await this.pushSingleTransaction(uid, t, 'sync');
      }

      console.log('Successfully completed background sync.');
    } catch (error) {
      console.error('FirebaseSyncService Error (pushUnsynced):', error);
    } finally {
      this.isSyncing = false;
    }
  }
}

export const syncService = new FirebaseSyncService();
export default syncService;
