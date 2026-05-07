import { NativeModules, Platform, Alert } from 'react-native';

const { NotificationModule } = NativeModules;

class NotificationBridgeService {
  /**
   * Sets the API configuration in the native module so the WorkManager
   * knows where to send the notifications and as which user.
   * This handles iOS gracefully (does nothing).
   */
  async setApiConfig(uid: string, webhookUrl: string): Promise<boolean> {
    if (Platform.OS !== 'android') {
      console.log('[NotificationBridge] iOS does not support NotificationListener. Ignored.');
      return false;
    }
    
    if (!NotificationModule) {
      console.warn('[NotificationBridge] NotificationModule not found. Is it linked?');
      return false;
    }

    try {
      return await NotificationModule.setApiConfig(uid, webhookUrl);
    } catch (e) {
      console.error('[NotificationBridge] setApiConfig error:', e);
      return false;
    }
  }

  /**
   * Checks if the user has granted Notification Listener permission.
   */
  async isEnabled(): Promise<boolean> {
    if (Platform.OS !== 'android' || !NotificationModule) return false;
    try {
      return await NotificationModule.isNotificationListenerEnabled();
    } catch (e) {
      console.error('[NotificationBridge] isEnabled error:', e);
      return false;
    }
  }

  /**
   * Opens the Android Settings page for Notification Access.
   */
  openSettings(): void {
    if (Platform.OS === 'android' && NotificationModule) {
      NotificationModule.openNotificationListenerSettings();
    }
  }

  /**
   * Helper to prompt the user to enable the listener if not enabled.
   */
  async promptToEnableIfRequired(): Promise<void> {
    if (Platform.OS !== 'android') return;
    
    const enabled = await this.isEnabled();
    if (!enabled) {
      Alert.alert(
        'Cho phép đọc thông báo',
        'Để tự động ghi nhận giao dịch từ ngân hàng/ví điện tử, ứng dụng cần quyền Đọc Thông Báo. Nhấn Cài đặt để bật quyền này.',
        [
          { text: 'Hủy', style: 'cancel' },
          { text: 'Cài đặt', onPress: () => this.openSettings() }
        ]
      );
    }
  }
}

export const notificationBridge = new NotificationBridgeService();
