/**
 * BudgetPlaceholder.tsx
 * 
 * Placeholder cho màn hình "Ngân sách"
 * Sẽ được build đầy đủ ở Bước 3 từ MainBudgetScreen.kt
 * 
 * Preview các thành phần sẽ có:
 * - Month navigation
 * - Budget progress bars per category
 * - Percentage display on progress
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius, Spacing } from '../../theme/colors';

export default function BudgetPlaceholder() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Ngân sách</Text>
        <Text style={styles.headerSubtitle}>Quản lý ngân sách chi tiêu</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardEmoji}>💰</Text>
        <Text style={styles.cardTitle}>Ngân sách tháng</Text>
        <Text style={styles.cardDesc}>
          Sẽ bao gồm:{'\n'}
          • Navigation tháng (prev/next){'\n'}
          • Thanh tiến trình ngân sách theo danh mục{'\n'}
          • Hiển thị phần trăm đã chi tiêu{'\n'}
          • Cài đặt hạn mức cho từng danh mục
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
    backgroundColor: '#5856D6',
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
