import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../theme/colors';
import GlassBox from './GlassBox';

interface SummaryCardProps {
  totalBalance: number;
  periodBalance: number;
  month: number;
  year: number;
  onPrev: () => void;
  onNext: () => void;
  onDatePress?: () => void;
}

const SummaryCard: React.FC<SummaryCardProps> = ({
  totalBalance,
  periodBalance,
  month,
  year,
  onPrev,
  onNext,
  onDatePress,
}) => {
  const formatCurrency = (val: number) => {
    return val.toLocaleString('vi-VN') + ' đ';
  };

  return (
    <GlassBox style={styles.container} padding={16} intensity={40}>
      <View style={styles.mainRow}>
        {/* Left Section: Total Balance */}
        <View style={styles.section}>
          <View style={styles.labelRow}>
            <Ionicons name="wallet-outline" size={14} color={Colors.accentBlue} />
            <Text style={styles.label}>Tổng tích lũy</Text>
          </View>
          <Text 
            style={styles.primaryAmount}
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.7}
          >
            {formatCurrency(totalBalance)}
          </Text>
        </View>

        {/* Vertical Divider */}
        <View style={styles.divider} />

        {/* Right Section: Time Nav + Monthly Balance */}
        <View style={[styles.section, styles.alignEnd]}>
          {/* Time Navigator */}
          <View style={styles.timeNav}>
            <TouchableOpacity onPress={onPrev} style={styles.navBtn}>
              <Ionicons name="chevron-back" size={14} color={Colors.textPrimary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={onDatePress}>
              <Text style={styles.dateText}>{`${String(month).padStart(2, '0')}/${year}`}</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={onNext} style={styles.navBtn}>
              <Ionicons name="chevron-forward" size={14} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>

          {/* Monthly Amount */}
          <Text 
            style={[
              styles.secondaryAmount, 
              { color: periodBalance >= 0 ? Colors.accentIncome : Colors.accentExpense }
            ]}
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.6}
          >
            {periodBalance >= 0 ? '+' : ''}{periodBalance.toLocaleString()}đ
          </Text>
        </View>
      </View>
    </GlassBox>
  );
};

const styles = StyleSheet.create({
  container: {
    height: 100,
    justifyContent: 'center',
  },
  mainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  section: {
    flex: 1,
  },
  alignEnd: {
    alignItems: 'flex-end',
  },
  labelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  label: {
    fontSize: 10,
    fontWeight: '500',
    color: Colors.textSecondary,
  },
  primaryAmount: {
    fontSize: 22, // Target 22px-24px
    fontWeight: '700',
    color: Colors.textPrimary,
  },
  divider: {
    width: 0.5,
    height: 40,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    marginHorizontal: Spacing.md,
  },
  timeNav: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: 6,
    paddingHorizontal: 4,
    paddingVertical: 2,
    marginBottom: 6,
  },
  navBtn: {
    padding: 2,
  },
  dateText: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.textPrimary,
    marginHorizontal: 4,
    minWidth: 44,
    textAlign: 'center',
  },
  secondaryAmount: {
    fontSize: 16, // Target 16px-18px
    fontWeight: '700',
  },
});

export default SummaryCard;
