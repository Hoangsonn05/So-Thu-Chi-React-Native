/**
 * ExpensePlaceholder.tsx
 * 
 * Placeholder cho màn hình "Nhập vào" (Tiền chi / Tiền thu)
 * Sẽ được build đầy đủ ở Bước 3 từ MainExpenseScreen.kt
 * 
 * Preview các thành phần sẽ có:
 * - Segmented Control: Tiền chi / Tiền thu
 * - Glass Input Card: Ngày, Ghi chú, Số tiền
 * - Category Grid: 12 danh mục chi, 7 danh mục thu
 * - Submit Button: "Nhập khoản chi" / "Nhập khoản thu"
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius, Spacing } from '../../theme/colors';

export default function ExpensePlaceholder() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Nhập vào</Text>
        <Text style={styles.headerSubtitle}>Tiền chi / Tiền thu</Text>
      </View>

      {/* Preview Glass Card */}
      <View style={styles.card}>
        <Text style={styles.cardEmoji}>📝</Text>
        <Text style={styles.cardTitle}>Màn hình nhập giao dịch</Text>
        <Text style={styles.cardDesc}>
          Sẽ bao gồm:{'\n'}
          • Segmented Control (Tiền chi / Tiền thu){'\n'}
          • Chọn ngày với prev/next{'\n'}
          • Ghi chú{'\n'}
          • Số tiền (VNĐ){'\n'}
          • Lưới 12 danh mục chi tiêu{'\n'}
          • Lưới 7 danh mục thu nhập{'\n'}
          • Nút "Nhập khoản chi/thu"
        </Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Bước 3</Text>
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
    backgroundColor: Colors.primaryGreen,
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
