import { registerRootComponent } from 'expo';
import messaging from '@react-native-firebase/messaging';

import App from './App';
import syncService from './src/services/FirebaseSyncService';
import { firebaseAuth } from './src/config/firebase';

// ─── FCM Background / Quit-state Handler ─────────────────────────────────────
// Đăng ký trước khi bất kỳ React component nào được mount.
// Khi app bị kill hoặc background, FCM sẽ gọi handler này khi nhận notification.
// Handler KHÔNG được là async arrow function — phải return Promise.
messaging().setBackgroundMessageHandler(async (remoteMessage) => {
  console.log('[FCM Background] Received message:', remoteMessage.data);

  // Chỉ xử lý nếu notification từ Telegram Bot sync
  if (remoteMessage.data?.type === 'TRANSACTION_ADDED') {
    try {
      const user = firebaseAuth().currentUser;
      if (user) {
        // Pull toàn bộ dữ liệu mới nhất từ Firestore về SQLite
        await syncService.pullTransactions(user.uid);
        console.log('[FCM Background] Pulled transactions after FCM notification.');
      }
    } catch (err) {
      console.error('[FCM Background] Pull failed:', err);
    }
  }
});

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
