/**
 * FirebaseSyncService.ts
 * Centralized logic for bi-directional synchronization between SQLite and Firebase Firestore.
 */

import { firestoreDb } from '../config/firebase';
import db from '../database/DatabaseHelper';
import { Transaction } from '../models/Transaction';

class FirebaseSyncService {
  private isSyncing = false;

  /**
   * Pull all transactions from Firestore and replace local SQLite data.
   * This is used during login and manual "Pull from Cloud" triggers.
   */
  async pullTransactions(uid: string): Promise<void> {
    try {
      // 1. Fetch from Firestore (users/{uid}/transactions)
      const snapshot = await firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('transactions')
        .get();

      if (snapshot.empty) {
        console.log('No transactions found on Cloud.');
        // If empty, we still clear local to maintain consistency
        await db.clearAllTransactions();
        return;
      }

      const cloudTransactions: Transaction[] = [];
      snapshot.forEach((doc) => {
        const data = doc.data();
        
        // Parse timestamp to dd/MM/yyyy
        let dateStr = '';
        if (data.timestamp) {
          const dateObj = data.timestamp.toDate();
          const day = String(dateObj.getDate()).padStart(2, '0');
          const month = String(dateObj.getMonth() + 1).padStart(2, '0');
          const year = dateObj.getFullYear();
          dateStr = `${day}/${month}/${year}`;
        } else if (data.date) {
            dateStr = data.date;
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

      // 2. Clear local transactions
      await db.clearAllTransactions();

      // 3. Batch insert cloud data into SQLite
      if (cloudTransactions.length > 0) {
        await db.addTransactions(cloudTransactions);
      }
      
      console.log(`Successfully synced ${cloudTransactions.length} transactions from Cloud.`);
    } catch (error) {
      console.error('FirebaseSyncService Error (pull):', error);
      throw error;
    }
  }

  /**
   * Push local transactions to Firestore.
   * Currently used to 'upload' local state to the cloud.
   */
  async pushTransactions(uid: string): Promise<void> {
    try {
      const localTransactions = await db.getAllTransactions();
      if (localTransactions.length === 0) return;

      const userDocRef = firestoreDb().collection('users').doc(uid);
      const batch = firestoreDb().batch();

      localTransactions.forEach((t, index) => {
        const [dd, mm, yyyy] = (t.date || '01/01/2024').split('/');
        const docId = `sync_${Date.now()}_${index}`; // Ensure unique ID for this push
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
   * Push a single transaction to Firestore with a specific prefix.
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

      // Mark as synced locally
      await db.markAsSynced([t.id]);
    } catch (error) {
      console.error(`FirebaseSyncService Error (pushSingle - ${prefix}):`, error);
      throw error;
    }
  }

  /**
   * Automatically push only unsynced transactions (is_synced = 0) and mark them as 1.
   */
  async pushUnsyncedTransactions(uid: string): Promise<void> {
    if (this.isSyncing) return;
    
    try {
      this.isSyncing = true;
      const unsyncedTransactions = await db.getUnsyncedTransactions();
      if (unsyncedTransactions.length === 0) return;

      console.log(`Starting background sync for ${unsyncedTransactions.length} transactions...`);

      // We process them sequentially or in small batches to avoid overwhelming the system
      for (const t of unsyncedTransactions) {
        await this.pushSingleTransaction(uid, t, 'sync');
      }
      
      console.log(`Successfully completed background sync.`);
    } catch (error) {
      console.error('FirebaseSyncService Error (pushUnsynced):', error);
    } finally {
      this.isSyncing = false;
    }
  }
}

export const syncService = new FirebaseSyncService();
export default syncService;
