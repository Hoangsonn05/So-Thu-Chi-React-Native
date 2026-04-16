/**
 * CalendarPlaceholder.tsx
 * 
 * Placeholder cho màn hình "Lịch" (Lịch giao dịch)
 * Sẽ được build đầy đủ ở Bước 3 từ MainCalendarScreen.kt
 * 
 * Preview các thành phần sẽ có:
 * - Top bar: "Lịch giao dịch" + Search icon
 * - Month selector: prev/next + month/year display
 * - Summary card: Thu nhập / Chi tiêu / Thực thu
 * - Calendar grid: 7x6 days với income/expense dots
 * - History list: grouped by date
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Colors, FontSize, BorderRadius, Spacing } from '../../theme/colors';

export default function CalendarPlaceholder() {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Lịch</Text>
        <Text style={styles.headerSubtitle}>Lịch giao dịch</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardEmoji}>📅</Text>
        <Text style={styles.cardTitle}>Lịch giao dịch</Text>
        <Text style={styles.cardDesc}>
          Sẽ bao gồm:{'\n'}
          • Thanh chọn tháng (prev/next){'\n'}
          • Thẻ tổng kết: Thu nhập / Chi tiêu / Thực thu{'\n'}
          • Lưới lịch 7x6 với chấm màu{'\n'}
          • Danh sách lịch sử giao dịch theo ngày{'\n'}
          • Nút tìm kiếm giao dịch
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
    backgroundColor: '#007AFF',
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
