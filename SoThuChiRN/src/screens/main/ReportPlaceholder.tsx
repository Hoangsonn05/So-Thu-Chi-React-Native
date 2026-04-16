/**
 * ReportPlaceholder.tsx
 * 
 * Placeholder cho màn hình "Báo cáo"
 * Sẽ được build đầy đủ ở Bước 4 từ ReportScreens.kt
 * 
 * Preview các thành phần sẽ có:
 * - Period selector: Theo tháng / Theo năm
 * - Type selector: Chi tiêu / Thu nhập
 * - Date navigation: prev/next + date picker
 * - Summary cards: Chi tiêu / Thu nhập / Balance
 * - Pie chart + category breakdown list
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius, Spacing } from '../../theme/colors';

export default function ReportPlaceholder() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Báo cáo</Text>
        <Text style={styles.headerSubtitle}>Thống kê tài chính</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardEmoji}>📊</Text>
        <Text style={styles.cardTitle}>Báo cáo tài chính</Text>
        <Text style={styles.cardDesc}>
          Sẽ bao gồm:{'\n'}
          • Chuyển đổi: Theo tháng / Theo năm{'\n'}
          • Tab: Chi tiêu / Thu nhập{'\n'}
          • Navigation tháng/năm (prev/next){'\n'}
          • Thẻ tổng kết: Chi tiêu / Thu nhập / Cân đối{'\n'}
          • Biểu đồ tròn (Pie Chart){'\n'}
          • Danh sách chi tiết theo danh mục
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
    backgroundColor: '#FF9500',
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
