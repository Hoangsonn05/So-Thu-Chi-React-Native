/**
 * SettingsPlaceholder.tsx
 * 
 * Placeholder cho màn hình "Khác" (Cài đặt & Thống kê)
 * Sẽ được build đầy đủ ở Bước 4 từ MainKhacScreen.kt
 * 
 * Preview các thành phần sẽ có (từ MainKhacScreen.kt):
 * - Profile card: Avatar + Tên + Email
 * - Group "Tính năng": 4 items
 *   - Tìm kiếm giao dịch
 *   - Báo cáo toàn kì
 *   - Báo cáo chi tiêu năm
 *   - Biến động số dư
 * - Group "Công cụ & Bảo mật": 4 items
 *   - Đẩy dữ liệu lên Cloud
 *   - Tải dữ liệu từ Cloud
 *   - Xuất báo cáo PDF/Excel
 *   - Quản lý thiết bị đăng nhập
 * - Danger zone: Đăng xuất tài khoản
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius, Spacing } from '../../theme/colors';

export default function SettingsPlaceholder() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Khác</Text>
        <Text style={styles.headerSubtitle}>Cài đặt & Thống kê</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardEmoji}>⚙️</Text>
        <Text style={styles.cardTitle}>Cài đặt & Thống kê</Text>
        <Text style={styles.cardDesc}>
          Sẽ bao gồm:{'\n'}
          • Profile card (Avatar, Tên, Email){'\n'}
          • Tìm kiếm giao dịch{'\n'}
          • Báo cáo toàn kì / chi tiêu năm / biến động số dư{'\n'}
          • Đẩy/Tải dữ liệu Cloud{'\n'}
          • Xuất báo cáo PDF/Excel{'\n'}
          • Quản lý thiết bị đăng nhập{'\n'}
          • Đăng xuất tài khoản
        </Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Bước 4</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.spatialBg,
    paddingHorizontal: Spacing.xl,
  },
  header: {
    paddingTop: 60,
    paddingBottom: Spacing.xl,
  },
  headerTitle: {
    fontSize: FontSize.xxxl,
    fontWeight: '700',
    color: Colors.spatialTextPrimary,
  },
  headerSubtitle: {
    fontSize: FontSize.md,
    color: Colors.spatialSparkleSilver,
    marginTop: 4,
  },
  card: {
    backgroundColor: Colors.spatialGlassCardBg,
    borderRadius: BorderRadius.xxl,
    borderWidth: 1,
    borderColor: Colors.spatialGlassBorder,
    padding: Spacing.xl,
    alignItems: 'center',
    shadowColor: Colors.black,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
    elevation: 2,
  },
  cardEmoji: {
    fontSize: 48,
    marginBottom: Spacing.lg,
  },
  cardTitle: {
    fontSize: FontSize.xl,
    fontWeight: '700',
    color: Colors.spatialTextPrimary,
    marginBottom: Spacing.md,
  },
  cardDesc: {
    fontSize: FontSize.md,
    color: Colors.spatialSparkleSilver,
    lineHeight: 22,
    textAlign: 'left',
    alignSelf: 'stretch',
  },
  badge: {
    marginTop: Spacing.lg,
    backgroundColor: Colors.error,
    borderRadius: BorderRadius.pill,
    paddingHorizontal: Spacing.lg,
    paddingVertical: Spacing.sm,
  },
  badgeText: {
    color: Colors.white,
    fontSize: FontSize.sm,
    fontWeight: '700',
  },
});
