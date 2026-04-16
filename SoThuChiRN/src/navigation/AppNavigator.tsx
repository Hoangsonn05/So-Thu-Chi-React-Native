/**
 * AppNavigator.tsx
 * 
 * Tái tạo luồng navigation từ Android Native:
 * - SplashActivity → kiểm tra FirebaseAuth.currentUser
 *   - Nếu đã đăng nhập → HamchinhActivity (Main App with Bottom Tabs)
 *   - Nếu chưa → MainActivity (Login) ↔ DangkyActivity (Register)
 * 
 * Trong React Native:
 * - Auth Stack: Login ↔ Register (khi chưa đăng nhập)
 * - Main: Bottom Tab Navigator với 5 tabs (khi đã đăng nhập)
 *   - Nhập vào (Expense)
 *   - Lịch (Calendar)
 *   - Báo cáo (Report)
 *   - Ngân sách (Budget)
 *   - Khác (Settings)
 */

import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import LoginScreen from '../screens/auth/LoginScreen';
import RegisterScreen from '../screens/auth/RegisterScreen';
import MainTabNavigator from './MainTabNavigator';
import DeviceManagementScreen from '../screens/main/DeviceManagementScreen';
import AllTimeReportScreen from '../screens/main/AllTimeReportScreen';
import YearlyReportScreen from '../screens/main/YearlyReportScreen';
import { Colors } from '../theme/colors';

// Type definitions for navigation
export type AuthStackParamList = {
  Login: undefined;
  Register: undefined;
};

export type RootStackParamList = {
  Auth: undefined;
  Main: undefined;
  DeviceManager: undefined;
  AllTimeReport: undefined;
  YearlyReport: undefined;
};

const AuthStack = createNativeStackNavigator<AuthStackParamList>();
const RootStack = createNativeStackNavigator<RootStackParamList>();

/**
 * Auth Navigator — Login ↔ Register
 */
function AuthNavigator({ onLoginSuccess }: { onLoginSuccess: () => void }) {
  return (
    <AuthStack.Navigator
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
        contentStyle: { backgroundColor: Colors.spatialBg },
      }}
    >
      <AuthStack.Screen name="Login">
        {({ navigation }) => (
          <LoginScreen
            onNavigateToRegister={() => navigation.navigate('Register')}
            onLoginSuccess={onLoginSuccess}
          />
        )}
      </AuthStack.Screen>
      <AuthStack.Screen name="Register">
        {({ navigation }) => (
          <RegisterScreen
            onNavigateToLogin={() => navigation.goBack()}
            onRegisterSuccess={() => navigation.goBack()}
          />
        )}
      </AuthStack.Screen>
    </AuthStack.Navigator>
  );
}

/**
 * Root Navigator — Conditional routing based on auth state
 * Giữ nguyên logic từ SplashActivity.kt + MainActivity.java:
 * - Có FirebaseAuth.currentUser → Main (Bottom Tabs)
 * - Không có → Auth Stack
 */
export default function AppNavigator({
  isAuthenticated,
  onLoginSuccess,
}: {
  isAuthenticated: boolean;
  onLoginSuccess: () => void;
}) {
  return (
    <RootStack.Navigator screenOptions={{ headerShown: false }}>
      {isAuthenticated ? (
        <>
          <RootStack.Screen name="Main" component={MainTabNavigator} />
          <RootStack.Screen name="DeviceManager" component={DeviceManagementScreen} />
          <RootStack.Screen name="AllTimeReport" component={AllTimeReportScreen} />
          <RootStack.Screen name="YearlyReport" component={YearlyReportScreen} />
        </>
      ) : (
        <RootStack.Screen name="Auth">
          {() => <AuthNavigator onLoginSuccess={onLoginSuccess} />}
        </RootStack.Screen>
      )}
    </RootStack.Navigator>
  );
}
