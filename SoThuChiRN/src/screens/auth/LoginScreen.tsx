/**
 * LoginScreen.tsx
 * 
 * Tái tạo 1:1 từ LoginScreen.kt (Jetpack Compose):
 * - 1 Language selector badge (Tiếng Việt) — góc phải trên
 * - 1 Title: "Chào mừng trở lại"
 * - 1 Glass Card chứa:
 *   - TextInput: Email hoặc Số điện thoại
 *   - TextInput: Mật khẩu (secure)
 *   - Row: Checkbox "Nhớ mật khẩu" + Link "Quên mật khẩu?"
 * - 1 Button Primary: "Đăng nhập" (green, pill shape)
 * - 1 Button Outlined: "Đăng ký tài khoản mới"
 * 
 * Logic từ MainActivity.java → loginUser():
 * - Validate empty → Firebase signInWithEmailAndPassword
 * - Fetch Firestore profile → Clear local DB → Save user local
 * - Fetch Firestore transactions → Batch insert SQLite → Navigate
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import { firebaseAuth, firestoreDb } from '../../config/firebase';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { syncService } from '../../services/FirebaseSyncService';

interface LoginScreenProps {
  onNavigateToRegister: () => void;
  onLoginSuccess: () => void;
}

export default function LoginScreen({ onNavigateToRegister, onLoginSuccess }: LoginScreenProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [emailFocused, setEmailFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  /**
   * Login logic — giữ nguyên 100% từ MainActivity.java loginUser()
   * Flow: Validate → Firebase Auth → Fetch Firestore Profile → Clear local → Save local → Fetch transactions → Insert SQLite
   */
  const handleLogin = async () => {
    // Validate empty (giữ nguyên từ Java)
    if (!email.trim() || !password.trim()) {
      Alert.alert('Thông báo', 'Vui lòng nhập Email và Mật khẩu!');
      return;
    }

    setIsLoading(true);

    try {
      // Firebase signInWithEmailAndPassword (giữ nguyên từ Java)
      const userCredential = await firebaseAuth().signInWithEmailAndPassword(
        email.trim(),
        password.trim()
      );

      const user = userCredential.user;
      if (!user) {
        Alert.alert('Lỗi', 'Tài khoản không tồn tại');
        setIsLoading(false);
        return;
      }

      const uid = user.uid;

      // Toast "Đang tải dữ liệu đám mây..." (giữ nguyên từ Java)
      // RN doesn't have Toast natively, use loading state instead

      try {
        // Fetch Firestore user profile (giữ nguyên từ Java: users/{uid})
        const profileDoc = await firestoreDb().collection('users').doc(uid).get();

        // 1. XÓA TOÀN BỘ DỮ LIỆU CŨ (giữ nguyên từ Java)
        await db.clearAllTransactions();

        // 2. Lưu lại bản ghi profile (giữ nguyên từ Java)
        if (profileDoc.exists()) {
          const data = profileDoc.data();
          await db.saveUserLocal(
            data?.fullName ?? null,
            email,
            data?.phone ?? null,
            password,
            data?.username ?? null
          );
        } else {
          await db.saveUserLocal(null, email, null, password, null);
        }

        // Đã xóa syncService.pullTransactions(uid) ở đây vì:
        // App.tsx sẽ tự động gọi syncService.startRealtimeListener(uid) ngay khi đăng nhập thành công.
        // onSnapshot của Firebase mặc định sẽ kéo toàn bộ dữ liệu ban đầu về máy dưới dạng 'added',
        // nên nếu để pullTransactions ở đây sẽ gây ra lỗi nhân đôi dữ liệu (Duplicate).
        
        // 4. ĐĂNG KÝ SESSION THIẾT BỊ (Chạy ngầm)
        const { sessionService } = require('../../services/SessionService');
        sessionService.registerSession(uid).catch((e: any) => {
          console.error('Background session registration error:', e);
        });

        // Chuyển vào app ngay lập tức
        onLoginSuccess();
      } catch (e) {
        // Nếu lỗi fetch Profile, đi thẳng vào (fallback - giữ nguyên từ Java)
        console.error('Error fetching profile:', e);
        onLoginSuccess();
      }
    } catch (error: any) {
      // NẾU THẤT BẠI (giữ nguyên từ Java)
      Alert.alert('Lỗi', 'Email hoặc mật khẩu không chính xác');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = () => {
    if (!email.trim()) {
      Alert.alert('Thông báo', 'Vui lòng nhập Email để khôi phục mật khẩu');
      return;
    }
    firebaseAuth()
      .sendPasswordResetEmail(email.trim())
      .then(() => {
        Alert.alert('Thành công', 'Email đặt lại mật khẩu đã được gửi!');
      })
      .catch((error: any) => {
        Alert.alert('Lỗi', error.message);
      });
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Language Selector Badge — giữ nguyên từ Kotlin */}
        <View style={styles.languageBadgeRow}>
          <View style={styles.languageBadge}>
            <Text style={styles.languageFlag}>🇻🇳</Text>
            <Text style={styles.languageText}>Tiếng Việt</Text>
          </View>
        </View>

        {/* Title — giữ nguyên từ Kotlin: "Chào mừng trở lại" */}
        <Text style={styles.title}>Chào mừng trở lại</Text>

        {/* Glass Login Card — giữ nguyên từ Kotlin */}
        <View style={styles.glassCard}>
          {/* Email TextInput */}
          <View style={styles.inputWrapper}>
            <Text style={[styles.inputLabel, emailFocused && styles.inputLabelFocused]}>
              Email hoặc Số điện thoại
            </Text>
            <TextInput
              style={[styles.textInput, emailFocused && styles.textInputFocused]}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              placeholderTextColor={Colors.placeholder}
              onFocus={() => setEmailFocused(true)}
              onBlur={() => setEmailFocused(false)}
            />
          </View>

          {/* Password TextInput */}
          <View style={[styles.inputWrapper, { marginTop: Spacing.lg }]}>
            <Text style={[styles.inputLabel, passwordFocused && styles.inputLabelFocused]}>
              Mật khẩu
            </Text>
            <TextInput
              style={[styles.textInput, passwordFocused && styles.textInputFocused]}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholderTextColor={Colors.placeholder}
              onFocus={() => setPasswordFocused(true)}
              onBlur={() => setPasswordFocused(false)}
            />
          </View>

          {/* Remember me + Forgot password row — giữ nguyên từ Kotlin */}
          <View style={styles.optionsRow}>
            <TouchableOpacity
              style={styles.checkboxRow}
              onPress={() => setRememberMe(!rememberMe)}
              activeOpacity={0.7}
            >
              <View style={[styles.checkbox, rememberMe && styles.checkboxChecked]}>
                {rememberMe && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.checkboxLabel}>Nhớ mật khẩu</Text>
            </TouchableOpacity>

            <TouchableOpacity onPress={handleForgotPassword} activeOpacity={0.7}>
              <Text style={styles.forgotText}>Quên mật khẩu?</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Login Button — giữ nguyên: Green, pill shape, height 60 */}
        <TouchableOpacity
          style={[styles.primaryButton, isLoading && styles.primaryButtonDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
          activeOpacity={0.8}
        >
          {isLoading ? (
            <ActivityIndicator color={Colors.white} size="small" />
          ) : (
            <Text style={styles.primaryButtonText}>Đăng nhập</Text>
          )}
        </TouchableOpacity>

        {/* Register Button — giữ nguyên: outlined, pill shape */}
        <TouchableOpacity
          style={styles.outlinedButton}
          onPress={onNavigateToRegister}
          activeOpacity={0.7}
        >
          <Text style={styles.outlinedButtonText}>Đăng ký tài khoản mới</Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.spatialBg,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: Spacing.xl,
    paddingBottom: Spacing.xxl,
  },

  // Language Badge — góc phải trên
  languageBadgeRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingTop: 56,
  },
  languageBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.spatialGlassCardBg,
    borderRadius: BorderRadius.lg,
    borderWidth: 1,
    borderColor: Colors.spatialGlassBorder,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  languageFlag: {
    fontSize: 16,
  },
  languageText: {
    marginLeft: 8,
    color: Colors.spatialTextPrimary,
    fontSize: FontSize.md,
    fontWeight: '700',
  },

  // Title
  title: {
    marginTop: 60,
    fontSize: FontSize.xxxl,
    fontWeight: '700',
    color: Colors.spatialTextPrimary,
  },

  // Glass Card
  glassCard: {
    marginTop: Spacing.xxxl,
    backgroundColor: Colors.spatialGlassCardBg,
    borderRadius: BorderRadius.xxl,
    borderWidth: 1,
    borderColor: Colors.spatialGlassBorder,
    padding: Spacing.xl,
    // Subtle shadow for glass effect
    shadowColor: Colors.black,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
    elevation: 2,
  },

  // Input
  inputWrapper: {
    marginBottom: 0,
  },
  inputLabel: {
    fontSize: FontSize.sm,
    color: Colors.spatialSparkleSilver,
    marginBottom: 6,
    fontWeight: '500',
  },
  inputLabelFocused: {
    color: Colors.primaryGreen,
  },
  textInput: {
    height: 48,
    borderWidth: 1,
    borderColor: Colors.spatialGlassBorder,
    borderRadius: BorderRadius.sm,
    paddingHorizontal: Spacing.lg,
    fontSize: FontSize.lg,
    color: Colors.spatialTextPrimary,
    backgroundColor: Colors.inputBackground,
  },
  textInputFocused: {
    borderColor: Colors.primaryGreen,
    borderWidth: 1.5,
  },

  // Options row (remember me + forgot password)
  optionsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.md,
  },
  checkboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: Colors.spatialGlassBorder,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  checkboxChecked: {
    backgroundColor: Colors.primaryGreen,
    borderColor: Colors.primaryGreen,
  },
  checkmark: {
    color: Colors.white,
    fontSize: 12,
    fontWeight: '700',
  },
  checkboxLabel: {
    color: Colors.spatialSparkleSilver,
    fontSize: FontSize.sm,
  },
  forgotText: {
    color: Colors.primaryGreen,
    fontSize: FontSize.md,
    fontWeight: '700',
  },

  // Primary Button — green, pill, 60dp height
  primaryButton: {
    marginTop: Spacing.xxl,
    backgroundColor: Colors.primaryGreen,
    borderRadius: BorderRadius.pill,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: Colors.primaryGreen,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
  },
  primaryButtonDisabled: {
    opacity: 0.7,
  },
  primaryButtonText: {
    color: Colors.white,
    fontSize: FontSize.xl,
    fontWeight: '700',
  },

  // Outlined Button — pill, 60dp height
  outlinedButton: {
    marginTop: 48,
    borderRadius: BorderRadius.pill,
    height: 60,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: Colors.spatialGlassBorder,
  },
  outlinedButtonText: {
    color: Colors.spatialTextPrimary,
    fontSize: FontSize.lg,
    fontWeight: '500',
  },
});
