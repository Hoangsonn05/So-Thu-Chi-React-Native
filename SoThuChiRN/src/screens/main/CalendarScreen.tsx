import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import { BlurView } from 'expo-blur';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { Ionicons } from '@expo/vector-icons';
import QuickAddModal from '../../components/QuickAddModal';
import { getCategoryEmoji } from '../../config/categories';
import { CloudOff } from 'lucide-react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';
import { transactionEvents } from '../../services/TransactionEvents';

interface CalendarDay {
  day: string;
  date: string;
  income: number;
  expense: number;
  isCurrentMonth: boolean;
  isToday: boolean;
}

interface HistoryGroup {
  title: string;
  total: number;
  data: Transaction[];
}

function getDaysInMonth(month: number, year: number): number {
  return new Date(year, month, 0).getDate();
}

function buildCalendarDays(month: number, year: number, transactions: Transaction[]): CalendarDay[] {
  const days: CalendarDay[] = [];
  const today = new Date();
  const firstDay = new Date(year, month - 1, 1).getDay();
  const daysInMonth = getDaysInMonth(month, year);
  const prevMonthDays = getDaysInMonth(month - 1 || 12, month === 1 ? year - 1 : year);

  const incomeMap: Record<string, number> = {};
  const expenseMap: Record<string, number> = {};
  for (const t of transactions) {
    if (t.type === 1) incomeMap[t.date] = (incomeMap[t.date] || 0) + t.amount;
    else expenseMap[t.date] = (expenseMap[t.date] || 0) + t.amount;
  }

  for (let i = firstDay - 1; i >= 0; i--) {
    const d = prevMonthDays - i;
    const pm = month === 1 ? 12 : month - 1;
    const py = month === 1 ? year - 1 : year;
    const dateStr = `${String(d).padStart(2, '0')}/${String(pm).padStart(2, '0')}/${py}`;
    days.push({ day: String(d), date: dateStr, income: 0, expense: 0, isCurrentMonth: false, isToday: false });
  }

  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${String(d).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`;
    const isToday = d === today.getDate() && month === today.getMonth() + 1 && year === today.getFullYear();
    days.push({
      day: String(d), date: dateStr,
      income: incomeMap[dateStr] || 0,
      expense: expenseMap[dateStr] || 0,
      isCurrentMonth: true, isToday
    });
  }

  const remaining = 42 - days.length;
  for (let d = 1; d <= remaining; d++) {
    const nm = month === 12 ? 1 : month + 1;
    const ny = month === 12 ? year + 1 : year;
    const dateStr = `${String(d).padStart(2, '0')}/${String(nm).padStart(2, '0')}/${ny}`;
    days.push({ day: String(d), date: dateStr, income: 0, expense: 0, isCurrentMonth: false, isToday: false });
  }
  return days;
}

function groupTransactionsByDate(transactions: Transaction[]): HistoryGroup[] {
  const map: Record<string, Transaction[]> = {};
  for (const t of transactions) {
    if (!map[t.date]) map[t.date] = [];
    map[t.date].push(t);
  }
  return Object.entries(map).sort(([a], [b]) => {
    const [da, ma, ya] = a.split('/').map(Number);
    const [db2, mb, yb] = b.split('/').map(Number);
    return new Date(yb, mb - 1, db2).getTime() - new Date(ya, ma - 1, da).getTime();
  }).map(([date, txns]) => ({
    title: date,
    total: txns.reduce((sum, t) => sum + (t.type === 1 ? t.amount : -t.amount), 0),
    data: txns
  }));
}

const dayHeaders = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];

export default function CalendarScreen() {
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [year, setYear] = useState(new Date().getFullYear());
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [calendarDays, setCalendarDays] = useState<CalendarDay[]>([]);
  const [historyGroups, setHistoryGroups] = useState<HistoryGroup[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isPickerVisible, setIsPickerVisible] = useState(false);
  const [selectedDate, setSelectedDate] = useState('');
  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const [lastTap, setLastTap] = useState(0);

  const loadData = useCallback(async () => {
    try {
      const txns = await db.getTransactionsByMonth(month, year);
      let inc = 0, exp = 0;
      for (const t of txns) { if (t.type === 1) inc += t.amount; else exp += t.amount; }
      setTotalIncome(inc); setTotalExpense(exp);
      setCalendarDays(buildCalendarDays(month, year, txns));
      setHistoryGroups(groupTransactionsByDate(txns));
    } catch (e) { console.error(e); }
  }, [month, year]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const unsubscribe = transactionEvents.subscribe(() => {
      loadData();
    });

    return unsubscribe;
  }, [loadData]);

  const lastDay = getDaysInMonth(month, year);
  const paddedMonth = String(month).padStart(2, '0');
  const dateRange = `${month}/${year} (01/${paddedMonth}-${lastDay}/${month})`;

  const weeks = [];
  for (let i = 0; i < calendarDays.length; i += 7) weeks.push(calendarDays.slice(i, i + 7));

  const handleDayPress = (date: string) => {
    const now = Date.now();
    const DOUBLE_TAP_DELAY = 300;
    
    if (lastTap && (now - lastTap) < DOUBLE_TAP_DELAY) {
      setSelectedDate(date);
      setIsModalVisible(true);
    } else {
      setFocusedDate(focusedDate === date ? null : date);
      setLastTap(now);
    }
  };

  const jumpToDate = (d: number, m: number, y: number) => {
    const dateStr = `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`;
    setMonth(m);
    setYear(y);
    setFocusedDate(dateStr);
    setIsPickerVisible(false);
  };

  const filteredGroups = focusedDate 
    ? historyGroups.filter(g => g.title === focusedDate)
    : historyGroups;

  return (
    <View className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }} showsVerticalScrollIndicator={false}>
        <Text className="text-3xl font-bold text-white mb-6">Lịch sử</Text>

        <GlassBox padding={10} intensity={30} className="mb-4">
          <TouchableOpacity 
            className="flex-row items-center justify-center gap-x-4" 
            onPress={() => setIsPickerVisible(true)}
          >
            <Ionicons name="calendar-outline" size={18} color="#00B0FF" />
            <Text className="text-base font-bold text-white">{dateRange}</Text>
            <Ionicons name="chevron-down" size={16} color="#999" />
          </TouchableOpacity>
        </GlassBox>

        <View className="flex-row gap-4 mb-4">
          <GlassBox className="flex-1 h-[70px] justify-center" padding={10}>
            <Text className="text-[10px] text-gray-400">Thu nhập</Text>
            <Text className="text-lg font-bold text-income">+{totalIncome.toLocaleString()}đ</Text>
          </GlassBox>
          <GlassBox className="flex-1 h-[70px] justify-center" padding={10}>
            <Text className="text-[10px] text-gray-400">Chi tiêu</Text>
            <Text className="text-lg font-bold text-expense">-{totalExpense.toLocaleString()}đ</Text>
          </GlassBox>
        </View>

        <GlassBox className="mb-6 rounded-2xl" padding={8}>
          <View className="flex-row mb-1.5">
            {dayHeaders.map((d, i) => (
              <Text key={d} className={`flex-1 text-center text-[10px] font-bold ${i === 0 ? 'text-expense' : i === 6 ? 'text-accent' : 'text-gray-500'}`}>{d}</Text>
            ))}
          </View>
          {weeks.map((week, wi) => (
            <View key={wi} style={{ flexDirection: 'row' }}>
              {week.map((day, di) => (
                <TouchableOpacity 
                  key={di} 
                  style={[
                    { 
                      flex: 1, 
                      aspectRatio: 1, 
                      alignItems: 'center', 
                      justifyContent: 'center', 
                      borderRadius: 12,
                      margin: 2
                    },
                    day.isToday && { backgroundColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderColor: Colors.accentBlue + '44' },
                    focusedDate === day.date && { borderWidth: 2, borderColor: Colors.accentBlue, backgroundColor: 'transparent' }
                  ]}
                  onPress={() => handleDayPress(day.date)}
                  activeOpacity={0.7}
                >
                  <Text style={[
                    { fontSize: 12, color: Colors.white },
                    !day.isCurrentMonth && { opacity: 0.2 },
                    day.isToday && { fontWeight: 'bold', color: Colors.accentBlue },
                    focusedDate === day.date && { color: Colors.white, fontWeight: 'bold' }
                  ]}>
                    {day.day}
                  </Text>
                  <View style={{ flexDirection: 'row', marginTop: 2, height: 3 }}>
                    {day.income > 0 && <View style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: Colors.accentIncome, marginRight: 2 }} />}
                    {day.expense > 0 && <View style={{ width: 3, height: 3, borderRadius: 1.5, backgroundColor: Colors.accentExpense }} />}
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          ))}
        </GlassBox>

        <View className="flex-row justify-between items-center mb-2">
          <Text className="text-xl font-bold text-white">
            {focusedDate ? `Ngày ${focusedDate.split('/')[0]}/${focusedDate.split('/')[1]}` : 'Trong tháng'}
          </Text>
          {focusedDate && (
            <TouchableOpacity onPress={() => setFocusedDate(null)}>
              <Text className="text-xs font-bold text-accent">Hiện tất cả</Text>
            </TouchableOpacity>
          )}
        </View>

        {filteredGroups.length === 0 ? (
          <View className="items-center justify-center py-10">
            <Ionicons name="receipt-outline" size={48} color="rgba(255,255,255,0.05)" />
            <Text className="text-sm text-gray-500 mt-2.5">Không có giao dịch nào</Text>
          </View>
        ) : (
          filteredGroups.map((group) => (
          <View key={group.title} className="mb-6">
            <View className="flex-row justify-between mb-1">
              <Text className="text-xs font-bold text-gray-400">{group.title}</Text>
              <Text className={`text-xs font-bold ${group.total >= 0 ? 'text-income' : 'text-expense'}`}>
                {group.total >= 0 ? '+' : ''}{group.total.toLocaleString()}đ
              </Text>
            </View>
            {group.data.map((item, idx) => (
              <GlassBox key={idx} className="mb-1" padding={10} intensity={10}>
                <View className="flex-row items-center">
                  <View className="w-9 h-9 items-center justify-center mr-2">
                    <Text className="text-xl">{getCategoryEmoji(item.category)}</Text>
                  </View>
                  <View className="flex-1">
                    <View className="flex-row items-center">
                      <Text className="text-lg font-bold text-white">{item.category}</Text>
                      {item.is_synced === 0 && (
                        <CloudOff size={10} color="#999" className="ml-1.5" />
                      )}
                    </View>
                  </View>
                  <Text className={`text-lg font-bold ${item.type === 1 ? 'text-income' : 'text-expense'}`}>
                    {item.type === 1 ? '+' : '-'}{item.amount.toLocaleString()}đ
                  </Text>
                </View>
              </GlassBox>
            ))}
          </View>
        )))}
        <View className="h-[100px]" />
      </ScrollView>

      <QuickAddModal
        visible={isModalVisible}
        date={selectedDate}
        onClose={() => setIsModalVisible(false)}
        onSuccess={() => {
          setIsModalVisible(false);
          loadData();
        }}
      />

      <UniversalDatePicker 
        isVisible={isPickerVisible}
        currentMonth={month}
        currentYear={year}
        onClose={() => setIsPickerVisible(false)}
        onSelect={(d, m, y) => jumpToDate(d, m, y)}
      />
    </View>
  );
}
