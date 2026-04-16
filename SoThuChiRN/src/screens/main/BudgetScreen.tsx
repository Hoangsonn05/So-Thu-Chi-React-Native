/**
 * BudgetScreen.tsx
 * Re-scaled Compact UI
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Ionicons } from '@expo/vector-icons';

interface BudgetItem {
  categoryName: string;
  budgetAmount: number;
  spentAmount: number;
  remaining: number;
  percent: number;
}

const DEFAULT_BUDGETS: Record<string, number> = {
  'Ăn uống': 3000000,
  'Chi tiêu': 2000000,
  'Quần áo': 1000000,
  'Mỹ phẩm': 500000,
  'Giao lưu': 1000000,
  'Y tế': 500000,
  'Giáo dục': 1000000,
  'Tiền điện': 500000,
  'Du lịch': 2000000,
  'Liên lạc': 200000,
  'Tiền nhà': 3000000,
  'Khác': 1000000,
};

function formatCurrency(amount: number): string {
  return amount.toLocaleString('vi-VN');
}

export default function BudgetScreen() {
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [year, setYear] = useState(new Date().getFullYear());
  const [budgetItems, setBudgetItems] = useState<BudgetItem[]>([]);

  const loadData = useCallback(async () => {
    try {
      const txns = await db.getTransactionsByMonth(month, year);
      const categorySpent: Record<string, number> = {};
      for (const t of txns) {
        if (t.type === 0) {
          categorySpent[t.category] = (categorySpent[t.category] || 0) + t.amount;
        }
      }
      const items: BudgetItem[] = Object.entries(DEFAULT_BUDGETS).map(
        ([categoryName, budgetAmount]) => {
          const spentAmount = categorySpent[categoryName] || 0;
          const remaining = budgetAmount - spentAmount;
          const percent = budgetAmount > 0 ? spentAmount / budgetAmount : 0;
          return { categoryName, budgetAmount, spentAmount, remaining, percent };
        }
      );
      setBudgetItems(items);
    } catch (e) { console.error(e); }
  }, [month, year]);

  useEffect(() => { loadData(); }, [loadData]);

  const monthYear = `${String(month).padStart(2, '0')}/${year}`;

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Ngân sách</Text>

        <GlassBox style={styles.monthHeader} padding={10} intensity={30}>
          <TouchableOpacity onPress={() => { if (month === 1) { setMonth(12); setYear(year - 1); } else setMonth(month - 1); }}>
            <Ionicons name="chevron-back" size={20} color={Colors.textPrimary} />
          </TouchableOpacity>
          <Text style={styles.monthLabel}>{monthYear}</Text>
          <TouchableOpacity onPress={() => { if (month === 12) { setMonth(1); setYear(year + 1); } else setMonth(month + 1); }}>
            <Ionicons name="chevron-forward" size={20} color={Colors.textPrimary} />
          </TouchableOpacity>
        </GlassBox>

        {budgetItems.map((item) => (
          <BudgetCard key={item.categoryName} item={item} />
        ))}
        <View style={{ height: 100 }} />
      </ScrollView>
    </View>
  );
}

function BudgetCard({ item }: { item: BudgetItem }) {
  const isWarning = item.percent >= 0.8 && item.percent < 1.0;
  const isAlert = item.percent >= 1.0;
  const accentColor = isAlert ? Colors.accentExpense : isWarning ? Colors.warning : Colors.accentIncome;
  const barWidth = Math.min(item.percent, 1.0) * 100;

  return (
    <GlassBox style={styles.budgetCard} padding={12} intensity={20}>
      <View style={styles.cardHeader}>
        <Text style={styles.catName}>{item.categoryName}</Text>
        <Text style={[styles.remaining, { color: isAlert ? Colors.accentExpense : Colors.textSecondary }]}>
          Còn {formatCurrency(item.remaining)}đ
        </Text>
      </View>

      <View style={styles.progressContainer}>
        <View style={styles.progressBarBg}>
          <View style={[styles.progressBarFill, { width: `${barWidth}%`, backgroundColor: accentColor }]} />
        </View>
        <Text style={[styles.percentLabel, { color: accentColor }]}>{Math.round(item.percent * 100)}%</Text>
      </View>

      <View style={styles.cardFooter}>
        <View>
          <Text style={styles.footerLabel}>Đã chi</Text>
          <Text style={styles.footerValue}>{formatCurrency(item.spentAmount)}đ</Text>
        </View>
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={styles.footerLabel}>Ngân sách</Text>
          <Text style={styles.footerValue}>{formatCurrency(item.budgetAmount)}đ</Text>
        </View>
      </View>
    </GlassBox>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  title: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.lg },
  monthHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: Spacing.md },
  monthLabel: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  budgetCard: { marginBottom: Spacing.md },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  catName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  remaining: { fontSize: 12, fontWeight: '600' },
  progressContainer: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  progressBarBg: { flex: 1, height: 6, borderRadius: 3, backgroundColor: 'rgba(255, 255, 255, 0.05)', overflow: 'hidden' },
  progressBarFill: { height: '100%', borderRadius: 3 },
  percentLabel: { fontSize: 10, fontWeight: '800', width: 30 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between' },
  footerLabel: { fontSize: 10, color: Colors.textTertiary },
  footerValue: { fontSize: 12, fontWeight: '600', color: Colors.textSecondary },
});
