import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Ionicons } from '@expo/vector-icons';
import { transactionEvents } from '../../services/TransactionEvents';

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

  useEffect(() => {
    const unsubscribe = transactionEvents.subscribe(() => {
      loadData();
    });

    return unsubscribe;
  }, [loadData]);

  const monthYear = `${String(month).padStart(2, '0')}/${year}`;

  return (
    <View className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }} showsVerticalScrollIndicator={false}>
        <Text className="text-3xl font-bold text-white mb-6">Ngân sách</Text>

        <GlassBox className="flex-row items-center justify-between mb-4" padding={10} intensity={30}>
          <TouchableOpacity onPress={() => { if (month === 1) { setMonth(12); setYear(year - 1); } else setMonth(month - 1); }}>
            <Ionicons name="chevron-back" size={20} color="#FFF" />
          </TouchableOpacity>
          <Text className="text-lg font-bold text-white">{monthYear}</Text>
          <TouchableOpacity onPress={() => { if (month === 12) { setMonth(1); setYear(year + 1); } else setMonth(month + 1); }}>
            <Ionicons name="chevron-forward" size={20} color="#FFF" />
          </TouchableOpacity>
        </GlassBox>

        {budgetItems.map((item) => (
          <BudgetCard key={item.categoryName} item={item} />
        ))}
        <View className="h-[100px]" />
      </ScrollView>
    </View>
  );
}

function BudgetCard({ item }: { item: BudgetItem }) {
  const isWarning = item.percent >= 0.8 && item.percent < 1.0;
  const isAlert = item.percent >= 1.0;
  
  // Custom colors for status
  const accentColor = isAlert ? '#FF5252' : isWarning ? '#FFD600' : '#00E676';
  const barWidth = Math.min(item.percent, 1.0) * 100;

  return (
    <GlassBox className="mb-4" padding={12} intensity={20}>
      <View className="flex-row justify-between items-center mb-2.5">
        <Text className="text-lg font-bold text-white">{item.categoryName}</Text>
        <Text className={`text-xs font-bold ${isAlert ? 'text-expense' : 'text-gray-400'}`}>
          Còn {formatCurrency(item.remaining)}đ
        </Text>
      </View>

      <View className="flex-row items-center gap-x-2.5 mb-3">
        <View className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
          <View className="h-full rounded-full" style={{ width: `${barWidth}%`, backgroundColor: accentColor }} />
        </View>
        <Text className={`text-[10px] font-extrabold w-8`} style={{ color: accentColor }}>{Math.round(item.percent * 100)}%</Text>
      </View>

      <View className="flex-row justify-between">
        <View>
          <Text className="text-[10px] text-gray-500">Đã chi</Text>
          <Text className="text-xs font-bold text-gray-400">{formatCurrency(item.spentAmount)}đ</Text>
        </View>
        <View className="items-end">
          <Text className="text-[10px] text-gray-500">Ngân sách</Text>
          <Text className="text-xs font-bold text-gray-400">{formatCurrency(item.budgetAmount)}đ</Text>
        </View>
      </View>
    </GlassBox>
  );
}
