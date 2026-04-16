/**
 * RegisterScreen.tsx
 * 
 * Tái tạo 1:1 từ RegisterScreen.kt (Jetpack Compose) + DangkyActivity.java:
 * - 1 Language selector badge (Tiếng Việt) — góc phải trên
 * - 1 Title: "Tạo tài khoản mới"
 * - 1 Glass Card chứa:
 *   - TextInput: Họ và Tên
 *   - TextInput: Email
 *   - TextInput: Số điện thoại
 *   - TextInput: Mật khẩu (tối thiểu 6 ký tự)
 *   - TextInput: Xác nhận lại mật khẩu
 * - 1 Checkbox + Label: "Tôi đã đọc và đồng ý với Điều khoản dịch vụ và Chính sách bảo mật"
 * - 1 Button Primary: "Đăng ký ngay"
 * - 1 Button Outlined: "Đã có tài khoản? Đăng nhập"
 * 
 * Logic từ DangkyActivity.java:
 * - Validate all empty fields
 * - Validate password != confirmPassword (từ RegisterScreen.kt)
 * - Validate termsAccepted (từ RegisterScreen.kt)
 * - Firebase createUserWithEmailAndPassword
 * - Clear local transactions → Save user local → Save to Firestore (users/{uid})
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

interface RegisterScreenProps {
  onNavigateToLogin: () => void;
  onRegisterSuccess: () => void;
}

export default function RegisterScreen({ onNavigateToLogin, onRegisterSuccess }: RegisterScreenProps) {
  // State — giữ nguyên 5 fields từ RegisterScreen.kt
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Focus states for input styling
  const [focusedField, setFocusedField] = useState<string | null>(null);

  /**
   * Register logic — giữ nguyên 100% từ DangkyActivity.java + RegisterScreen.kt
   */
  const handleRegister = async () => {
    // Validate terms (từ RegisterScreen.kt)
    if (!termsAccepted) {
      Alert.alert('Thông báo', 'Vui lòng đồng ý điều khoản');
      return;
    }

    // Validate password matching (từ RegisterScreen.kt)
    if (password !== confirmPassword) {
      Alert.alert('Thông báo', 'Mật khẩu không khớp');
      return;
    }

    // Validate all empty fields (từ DangkyActivity.java)
    if (!fullName.trim() || !email.trim() || !phone.trim() || !password.trim()) {
      Alert.alert('Thông báo', 'Vui lòng nhập đầy đủ tất cả thông tin!');
      return;
    }

    setIsLoading(true);

    try {
      // Firebase createUserWithEmailAndPassword (giữ nguyên từ Java)
      const userCredential = await firebaseAuth().createUserWithEmailAndPassword(
        email.trim(),
        password.trim()
      );

      const userId = userCredential.user.uid;

      // ĐẢM BẢO NGƯỜI MỚI CÓ DỮ LIỆU CỤC BỘ TRỐNG (giữ nguyên từ Java)
      await db.clearAllTransactions();

      // 1. Lưu SQLite local (giữ nguyên từ Java)
      await db.saveUserLocal(fullName, email, phone, password);

      // 2. Lưu Firestore (Cô lập UID) — giữ nguyên từ saveUserToFirestore trong Java
      await firestoreDb().collection('users').doc(userId).set(
        {
          fullName,
          email,
          phone,
          password,
          createdAt: firestoreDb.FieldValue.serverTimestamp(),
        },
        { merge: true }
      );

      Alert.alert('Thành công', 'Đăng ký thành công!', [
        {
          text: 'OK',
          onPress: () => onRegisterSuccess(),
        },
      ]);
    } catch (error: any) {
      // Lỗi (giữ nguyên từ Java)
      Alert.alert('Lỗi', error.message || 'Đã xảy ra lỗi khi đăng ký');
    } finally {
      setIsLoading(false);
    }
  };

  const renderInput = (
    label: string,
    value: string,
    onChangeText: (text: string) => void,
    fieldKey: string,
    options: {
      secureTextEntry?: boolean;
      keyboardType?: 'default' | 'email-address' | 'phone-pad';
      autoCapitalize?: 'none' | 'sentences' | 'words';
    } = {}
  ) => {
    const isFocused = focusedField === fieldKey;
    return (
      <View style={[styles.inputWrapper, fieldKey !== 'fullName' && { marginTop: Spacing.lg }]}>
        <Text style={[styles.inputLabel, isFocused && styles.inputLabelFocused]}>
          {label}
        </Text>
        <TextInput
          style={[styles.textInput, isFocused && styles.textInputFocused]}
          value={value}
          onChangeText={onChangeText}
          secureTextEntry={options.secureTextEntry}
          keyboardType={options.keyboardType ?? 'default'}
          autoCapitalize={options.autoCapitalize ?? 'sentences'}
          autoCorrect={false}
          placeholderTextColor={Colors.placeholder}
          onFocus={() => setFocusedField(fieldKey)}
          onBlur={() => setFocusedField(null)}
        />
      </View>
    );
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

        {/* Title — giữ nguyên: "Tạo tài khoản mới" */}
        <Text style={styles.title}>Tạo tài khoản mới</Text>

        {/* Glass Registration Card — giữ nguyên 5 fields từ RegisterScreen.kt */}
        <View style={styles.glassCard}>
          {renderInput('Họ và Tên', fullName, setFullName, 'fullName', {
            autoCapitalize: 'words',
          })}
          {renderInput('Email', email, setEmail, 'email', {
            keyboardType: 'email-address',
            autoCapitalize: 'none',
          })}
          {renderInput('Số điện thoại', phone, setPhone, 'phone', {
            keyboardType: 'phone-pad',
          })}
          {renderInput('Mật khẩu (tối thiểu 6 ký tự)', password, setPassword, 'password', {
            secureTextEntry: true,
          })}
          {renderInput('Xác nhận lại mật khẩu', confirmPassword, setConfirmPassword, 'confirmPassword', {
            secureTextEntry: true,
          })}
        </View>

        {/* Terms Checkbox + Label — giữ nguyên từ RegisterScreen.kt */}
        <TouchableOpacity
          style={styles.termsRow}
          onPress={() => setTermsAccepted(!termsAccepted)}
          activeOpacity={0.7}
        >
          <View style={[styles.checkbox, termsAccepted && styles.checkboxChecked]}>
            {termsAccepted && <Text style={styles.checkmark}>✓</Text>}
          </View>
          <Text style={styles.termsText}>
            Tôi đã đọc và đồng ý với Điều khoản dịch vụ và Chính sách bảo mật
          </Text>
        </TouchableOpacity>

        {/* Register Button — giữ nguyên: green primary, pill, 60dp */}
        <TouchableOpacity
          style={[styles.primaryButton, isLoading && styles.primaryButtonDisabled]}
          onPress={handleRegister}
          disabled={isLoading}
          activeOpacity={0.8}
        >
          {isLoading ? (
            <ActivityIndicator color={Colors.white} size="small" />
          ) : (
            <Text style={styles.primaryButtonText}>Đăng ký ngay</Text>
          )}
        </TouchableOpacity>

        {/* Navigate to Login — giữ nguyên: outlined, pill */}
        <TouchableOpacity
          style={styles.outlinedButton}
          onPress={onNavigateToLogin}
          activeOpacity={0.7}
        >
          <Text style={styles.outlinedButtonText}>Đã có tài khoản? Đăng nhập</Text>
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

  // Language Badge
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
    marginTop: 40,
    fontSize: FontSize.xxxl,
    fontWeight: '700',
    color: Colors.spatialTextPrimary,
  },

  // Glass Card
  glassCard: {
    marginTop: Spacing.xl,
    backgroundColor: Colors.spatialGlassCardBg,
    borderRadius: BorderRadius.xxl,
    borderWidth: 1,
    borderColor: Colors.spatialGlassBorder,
    padding: Spacing.xl,
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

  // Terms row
  termsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: Spacing.lg,
    paddingRight: Spacing.lg,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: Colors.spatialGlassBorder,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
    flexShrink: 0,
  },
  checkboxChecked: {
    backgroundColor: Colors.primaryGreen,
    borderColor: Colors.primaryGreen,
  },
  checkmark: {
    color: Colors.white,
    fontSize: 13,
    fontWeight: '700',
  },
  termsText: {
    flex: 1,
    color: Colors.spatialSparkleSilver,
    fontSize: FontSize.sm,
    lineHeight: 18,
  },

  // Primary Button
  primaryButton: {
    marginTop: Spacing.xl,
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

  // Outlined Button
  outlinedButton: {
    marginTop: Spacing.lg,
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
