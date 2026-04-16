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
import { View, ActivityIndicator, StyleSheet, StatusBar } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { firebaseAuth } from './src/config/firebase';
import AppNavigator from './src/navigation/AppNavigator';
import { Colors } from './src/theme/colors';
import NetInfo from '@react-native-community/netinfo';
import OfflineStatusModal from './src/components/OfflineStatusModal';
import { syncService } from './src/services/FirebaseSyncService';

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isInitializing, setIsInitializing] = useState<boolean>(true);
  const [showNetworkGuard, setShowNetworkGuard] = useState<boolean>(false);
  const [hasDismissedGuard, setHasDismissedGuard] = useState<boolean>(false);

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
        const db = require('./src/database/DatabaseHelper').default;

        // Đăng ký lại session (trong trường hợp app bị tắt ngang)
        // Bỏ await để tránh treo Splash Screen nếu app mở lên khi không có mạng
        sessionService.registerSession(user.uid).catch(console.error);

        sessionUnsubscribe = sessionService.listenToCurrentSession(user.uid, async () => {
          Alert.alert(
            '⚠️ Đã đăng xuất',
            'Thiết bị của bạn đã bị đăng xuất từ xa và xóa sạch dữ liệu cục bộ nhằm bảo mật tài khoản.',
            [{ text: 'OK' }]
          );
          
          await db.clearAllData();
          await firebaseAuth().signOut();
        });
      } else {
        if (sessionUnsubscribe) {
          sessionUnsubscribe();
          sessionUnsubscribe = null;
        }
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
