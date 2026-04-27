/**
 * SessionService.ts
 * Manages device sessions on Firestore to support Remote Logout and device tracking.
 */

import { firestoreDb } from '../config/firebase';
import * as Device from 'expo-device';
import * as Application from 'expo-application';
import { Platform } from 'react-native';

class SessionService {
  /**
   * Get a unique identifier for the current device.
   */
  async getDeviceId(): Promise<string> {
    try {
      if (Platform.OS === 'android') {
        return Application.getAndroidId() || 'unknown_android';
      } else if (Platform.OS === 'ios') {
        const iosId = await Application.getIosIdForVendorAsync();
        return iosId || 'unknown_ios';
      }
      return 'unknown_device';
    } catch (error) {
      console.error('Error getting device ID:', error);
      return 'fallback_device_id';
    }
  }

  /**
   * Get the human-readable name of the current device.
   */
  getDeviceName(): string {
    return Device.deviceName || `${Device.brand} ${Device.modelName}` || 'Unknown Device';
  }

  /**
   * Register or update the current device session in Firestore.
   */
  async registerSession(uid: string): Promise<void> {
    try {
      const deviceId = await this.getDeviceId();
      const deviceName = this.getDeviceName();
      
      const devicesRef = firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('devices');

      // Check if session with this deviceId already exists (handles legacy random doc IDs)
      const existingQuery = await devicesRef.where('deviceId', '==', deviceId).limit(1).get();
      
      const sessionData = {
        deviceId,
        deviceName,
        deviceModel: Device.modelName,
        osName: Device.osName,
        osVersion: Device.osVersion,
        lastActive: firestoreDb.FieldValue.serverTimestamp(),
        appVersion: Application.nativeApplicationVersion || '1.0.0',
        status: 'active'
      };

      if (!existingQuery.empty) {
        // Overwrite and update the existing session
        await existingQuery.docs[0].ref.set(sessionData, { merge: true });
        console.log(`Session updated for existing device: ${deviceName} (${deviceId})`);
      } else {
        // Create new session entry using deviceId as the document ID for future stability
        await devicesRef.doc(deviceId).set(sessionData);
        console.log(`New session registered for device: ${deviceName} (${deviceId})`);
      }
    } catch (error) {
      console.error('Error registering session:', error);
    }
  }

  /**
   * Revoke a device session (Remote Logout trigger).
   */
  async revokeSession(uid: string, targetDeviceId: string): Promise<void> {
    try {
      await firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('devices')
        .doc(targetDeviceId)
        .delete();
      
      console.log(`Session revoked for device: ${targetDeviceId}`);
    } catch (error) {
      console.error('Error revoking session:', error);
      throw error;
    }
  }

  /**
   * Listen for changes to the current device's session.
   * If the document is deleted, it means the session was revoked.
   */
  listenToCurrentSession(uid: string, onRevoked: () => void): () => void {
    let isCancelled = false;
    let internalUnsubscribe: (() => void) | null = null;

    this.getDeviceId().then(deviceId => {
      if (isCancelled) return;

      const sessionRef = firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('devices')
        .doc(deviceId);

      let skipFirstEmpty = true;
      const unsubscribe = sessionRef.onSnapshot(snapshot => {
        if (!snapshot.exists) {
          if (skipFirstEmpty) {
            console.log('Initial session snapshot empty, waiting for registration...');
            skipFirstEmpty = false;
            return;
          }
          onRevoked();
        } else {
          skipFirstEmpty = false;
        }
      }, error => {
        console.error('Session listener error:', error);
      });

      internalUnsubscribe = unsubscribe;
    });

    return () => {
      isCancelled = true;
      if (internalUnsubscribe) {
        internalUnsubscribe();
      }
    };
  }

  /**
   * Fetch all active sessions for the current user.
   */
  async getActiveSessions(uid: string): Promise<any[]> {
    try {
      const snapshot = await firestoreDb()
        .collection('users')
        .doc(uid)
        .collection('devices')
        .get();
      
      return snapshot.docs.map(doc => doc.data());
    } catch (error) {
      console.error('Error fetching active sessions:', error);
      return [];
    }
  }
}

export const sessionService = new SessionService();
export default sessionService;
