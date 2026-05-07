/**
 * App.tsx - Root Component
 * 
 * Tái tạo luồng khởi tạo từ Android Native:
 * 
 * SplashActivity.kt logic:
 * 1. Kiểm tra FirebaseAuth.currentUser
 * 2. Nếu đã đăng nhập → vào Main App
 * 3. Nếu chưa → vào Auth Stack (Login/Register)
 * 
 * MainActivity.java logic:
 * - mAuth.getCurrentUser() != null → chuyển thẳng HamchinhActivity
 * - Nếu chưa → hiện LoginScreen
 * 
 * React Native equivalent:
 * - Firebase auth().onAuthStateChanged listener
 * - Conditional rendering Auth Stack vs Main Stack
 */

import React, { useState, useEffect } from 'react';
import './src/styles/global.css';
import { View, ActivityIndicator, StyleSheet, StatusBar, Alert } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { firebaseAuth, firestoreDb } from './src/config/firebase';
import messaging from '@react-native-firebase/messaging';
import AppNavigator from './src/navigation/AppNavigator';
import { Colors } from './src/theme/colors';
import NetInfo from '@react-native-community/netinfo';
import OfflineStatusModal from './src/components/OfflineStatusModal';
import { syncService } from './src/services/FirebaseSyncService';
import { transactionEvents } from './src/services/TransactionEvents';
import { notificationBridge } from './src/services/NotificationBridge';
import { BACKEND_URL } from './src/config/api';
import AIFloatingIsland from './src/components/AIFloatingIsland';
import AIChatModal from './src/components/AIChatModal';
import { db } from './src/database/DatabaseHelper';

interface AIDetectedTransaction {
  amount: number;
  note: string;
  category: string;
  date: string;
  shouldAutoSubmit: boolean;
  message: string;
  type: 0 | 1;
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isInitializing, setIsInitializing] = useState<boolean>(true);
  const [showNetworkGuard, setShowNetworkGuard] = useState<boolean>(false);
  const [hasDismissedGuard, setHasDismissedGuard] = useState<boolean>(false);
  const [isAIChatModalVisible, setIsAIChatModalVisible] = useState<boolean>(false);
  const [currentDate, setCurrentDate] = useState<string>(() => {
    const today = new Date();
    const formatter = new Intl.DateTimeFormat('vi-VN', {
      weekday: 'short',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    return formatter.format(today);
  });

  const toDdMmYyyy = (value?: string): string => {
    const fallback = new Date();
    const fallbackDate = `${String(fallback.getDate()).padStart(2, '0')}/${String(
      fallback.getMonth() + 1
    ).padStart(2, '0')}/${fallback.getFullYear()}`;

    if (!value) return fallbackDate;

    const match = value.match(/(\d{2})\/(\d{2})\/(\d{4})/);
    if (!match) return fallbackDate;

    return `${match[1]}/${match[2]}/${match[3]}`;
  };

  const handleAIDetectedTransaction = async (transactionData: AIDetectedTransaction) => {
    const amount = Number(transactionData?.amount || 0);
    const category = String(transactionData?.category || '').trim();
    const type = transactionData?.type === 1 ? 1 : 0;
    const note = String(transactionData?.note || transactionData?.message || 'Giao dịch từ AI').trim();
    const date = toDdMmYyyy(transactionData?.date);

    if (!amount || amount <= 0 || !category) {
      return;
    }

    try {
      const localId = await db.addTransaction({
        amount,
        note,
        category,
        date,
        type,
      });

      if (localId === -1) {
        Alert.alert('Lỗi', 'Không thể lưu giao dịch từ AI');
        return;
      }

      const netInfo = await NetInfo.fetch();
      const user = firebaseAuth().currentUser;

      if (user && netInfo.isConnected && netInfo.isInternetReachable !== false) {
        const allTransactions = await db.getAllTransactions();
        const newTx = allTransactions.find((t) => t.id === localId);
        if (newTx) {
          await syncService.pushSingleTransaction(user.uid, newTx, 'legacy');
        }
      }

      // Realtime update for active screens without tab switch
      transactionEvents.emitChanged();

      Alert.alert(
        '✅ Đã lưu',
        `Ghi nhận ${type === 0 ? 'chi' : 'thu'} ${amount.toLocaleString('vi-VN')} ₫`
      );
    } catch (error) {
      console.error('AI transaction save failed:', error);
      Alert.alert('Lỗi', 'Không thể lưu giao dịch AI vào ứng dụng');
    }
  };

  useEffect(() => {
    // Theo dõi trạng thái mạng
    const unsubscribeNet = NetInfo.addEventListener(state => {
      // Chỉ hiện cảnh báo nếu thực sự không có kết nối và chưa bị ẩn bởi người dùng trong phiên này
      if (state.isConnected === false && !hasDismissedGuard) {
        setShowNetworkGuard(true);
      } else if (state.isConnected === true) {
        setShowNetworkGuard(false);
        const user = firebaseAuth().currentUser;
        if (user && state.isInternetReachable !== false) {
          // Trì hoãn nhẹ để đảm bảo kết nối ổn định
          setTimeout(() => {
            syncService.pushUnsyncedTransactions(user.uid);
          }, 1500);
        }
      }
    });

    return () => unsubscribeNet();
  }, [hasDismissedGuard]);

  useEffect(() => {
    /**
     * Firebase Auth state listener
     * Giữ nguyên logic từ SplashActivity.kt:
     * - hasExistingSession = FirebaseAuth.getInstance().currentUser != null
     */
    let sessionUnsubscribe: (() => void) | null = null;

    const unsubscribe = firebaseAuth().onAuthStateChanged(async (user) => {
      setIsAuthenticated(!!user);
      
      if (user) {
        // Khởi động lắng nghe Session (Remote Logout)
        const { sessionService } = require('./src/services/SessionService');
        const localDb = require('./src/database/DatabaseHelper').default;

        // Đăng ký lại session (trong trường hợp app bị tắt ngang)
        // Dùng await để đảm bảo session sẵn sàng trước khi listener chạy
        await sessionService.registerSession(user.uid).catch(console.error);
 
        sessionUnsubscribe = sessionService.listenToCurrentSession(user.uid, async () => {
          Alert.alert(
            '⚠️ Đã đăng xuất',
            'Thiết bị của bạn đã bị đăng xuất từ xa và xóa sạch dữ liệu cục bộ nhằm bảo mật tài khoản.',
            [{ text: 'OK' }]
          );
          
          await localDb.clearAllData();
          await firebaseAuth().signOut();
        });

        // ── Khởi động real-time Firestore listener ──────────────────────────
        // Lắng nghe document mới từ Telegram Bot hoặc thiết bị khác push lên.
        // Khi có doc mới → tự động insert SQLite → emit event → UI refresh.
        syncService.startRealtimeListener(user.uid);

        // ── Đăng ký và lưu FCM token để server gửi silent push ─────────────
        // Silent push sẽ kích hoạt pullTransactions() khi app bị kill.
        try {
          const authStatus = await messaging().requestPermission();
          const enabled =
            authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
            authStatus === messaging.AuthorizationStatus.PROVISIONAL;

          if (enabled) {
            const fcmToken = await messaging().getToken();
            if (fcmToken) {
              // Lưu token vào Firestore để server đọc khi cần push
              await firestoreDb()
                .collection('users')
                .doc(user.uid)
                .set({ fcmToken }, { merge: true });
              console.log('[FCM] Token registered:', fcmToken.substring(0, 20) + '...');
            }
          }
        } catch (fcmErr) {
          // Không làm app crash nếu FCM lỗi
          console.warn('[FCM] Token registration failed (non-critical):', fcmErr);
        }

        // ── Cấu hình Native Notification Listener (Chỉ Android) ────────────
        await notificationBridge.setApiConfig(user.uid, BACKEND_URL);
        // Có thể prompt user bật quyền nếu chưa bật (tuỳ chọn)
        // await notificationBridge.promptToEnableIfRequired();

      } else {
        if (sessionUnsubscribe) {
          sessionUnsubscribe();
          sessionUnsubscribe = null;
        }
        // ── Hủy Firestore listener khi đăng xuất ───────────────────────────
        syncService.stopRealtimeListener();
      }

      if (isInitializing) setIsInitializing(false);
    });

    return () => {
      unsubscribe();
      if (sessionUnsubscribe) sessionUnsubscribe();
    };
  }, [isInitializing]);

  // Splash screen equivalent — loading state
  if (isInitializing) {
    return (
      <View style={styles.splashContainer}>
        <StatusBar barStyle="light-content" backgroundColor={Colors.bg} />
        <ActivityIndicator size="large" color={Colors.accentBlue} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: Colors.bg }}>
      <StatusBar barStyle="light-content" backgroundColor={Colors.bg} />
      <NavigationContainer>
        <AppNavigator
          isAuthenticated={isAuthenticated}
          onLoginSuccess={() => setIsAuthenticated(true)}
        />
      </NavigationContainer>
      
      <OfflineStatusModal 
        isVisible={showNetworkGuard} 
        onContinue={() => {
          setShowNetworkGuard(false);
          setHasDismissedGuard(true);
        }} 
      />

      {/* AI Float + Chat Modal (Only show when authenticated) */}
      {isAuthenticated && (
        <>
          <AIFloatingIsland
            isExpanded={isAIChatModalVisible}
            onPress={() => setIsAIChatModalVisible(true)}
            onExpandStart={() => {
              // Optional: trigger animation or analytics
            }}
          />

          <AIChatModal
            isVisible={isAIChatModalVisible}
            onClose={() => setIsAIChatModalVisible(false)}
            currentDate={currentDate}
            onTransactionDetected={handleAIDetectedTransaction}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  splashContainer: {
    flex: 1,
    backgroundColor: Colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
