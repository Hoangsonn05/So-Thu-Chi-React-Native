/**
 * CalendarScreen.tsx
 * Re-scaled Compact UI
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Modal,
  Pressable,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import { BlurView } from 'expo-blur';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { Ionicons } from '@expo/vector-icons';
import QuickAddModal from '../../components/QuickAddModal';
import { getCategoryEmoji } from '../../config/categories';
import { CloudOff } from 'lucide-react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';

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

  // Picker States
  const [pickerMonth, setPickerMonth] = useState(month);
  const [pickerYear, setPickerYear] = useState(year);

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

  const lastDay = getDaysInMonth(month, year);
  const paddedMonth = String(month).padStart(2, '0');
  const dateRange = `${month}/${year}(01/${paddedMonth}-${lastDay}/${month})`;

  const handlePrevMonth = () => {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
  };
  const handleNextMonth = () => {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
  };

  const weeks = [];
  for (let i = 0; i < calendarDays.length; i += 7) weeks.push(calendarDays.slice(i, i + 7));

  const handleDayPress = (date: string) => {
    const now = Date.now();
    const DOUBLE_TAP_DELAY = 300;
    
    if (lastTap && (now - lastTap) < DOUBLE_TAP_DELAY) {
      // Double tap: Open Quick Add
      setSelectedDate(date);
      setIsModalVisible(true);
    } else {
      // Single tap: Focus on date
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
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Lịch sử</Text>

        <GlassBox padding={10} intensity={30} style={styles.monthSelectorOuter}>
          <TouchableOpacity 
            style={styles.monthSelector} 
            onPress={() => {
              setPickerMonth(month);
              setPickerYear(year);
              setIsPickerVisible(true);
            }}
          >
            <Ionicons name="calendar-outline" size={18} color={Colors.accentBlue} style={{ marginRight: 8 }} />
            <Text style={styles.monthLabel}>{dateRange}</Text>
            <Ionicons name="chevron-down" size={16} color={Colors.textTertiary} style={{ marginLeft: 4 }} />
          </TouchableOpacity>
        </GlassBox>

        <View style={styles.summaryRow}>
          <GlassBox style={styles.summaryTile} padding={10}>
            <Text style={styles.sumLabel}>Thu nhập</Text>
            <Text style={[styles.sumValue, { color: Colors.accentIncome }]}>+{totalIncome.toLocaleString()}đ</Text>
          </GlassBox>
          <GlassBox style={styles.summaryTile} padding={10}>
            <Text style={styles.sumLabel}>Chi tiêu</Text>
            <Text style={[styles.sumValue, { color: Colors.accentExpense }]}>-{totalExpense.toLocaleString()}đ</Text>
          </GlassBox>
        </View>

        <GlassBox style={styles.calendarCard} padding={8}>
          <View style={styles.dayHeaderRow}>
            {dayHeaders.map((d, i) => (
              <Text key={d} style={[styles.dayHeaderText, i === 0 && { color: Colors.accentExpense }, i === 6 && { color: Colors.accentBlue }]}>{d}</Text>
            ))}
          </View>
          {weeks.map((week, wi) => (
            <View key={wi} style={styles.weekRow}>
              {week.map((day, di) => (
                <TouchableOpacity 
                  key={di} 
                  style={[
                    styles.dayCell, 
                    day.isToday && styles.todayCell,
                    focusedDate === day.date && styles.focusedCell
                  ]}
                  onPress={() => handleDayPress(day.date)}
                  activeOpacity={0.7}
                >
                  <Text style={[
                    styles.dayText, 
                    !day.isCurrentMonth && styles.otherMonthText, 
                    day.isToday && styles.todayText,
                    focusedDate === day.date && { color: Colors.white, fontWeight: '700' }
                  ]}>{day.day}</Text>
                  <View style={styles.indicatorRow}>
                    {day.income > 0 && <View style={[styles.dot, { backgroundColor: Colors.accentIncome }]} />}
                    {day.expense > 0 && <View style={[styles.dot, { backgroundColor: Colors.accentExpense }]} />}
                  </View>
                </TouchableOpacity>
              ))}
            </View>
          ))}
        </GlassBox>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>
            {focusedDate ? `Ngày ${focusedDate.split('/')[0]}/${focusedDate.split('/')[1]}` : 'Trong tháng'}
          </Text>
          {focusedDate && (
            <TouchableOpacity onPress={() => setFocusedDate(null)}>
              <Text style={styles.clearFilter}>Hiện tất cả</Text>
            </TouchableOpacity>
          )}
        </View>

        {filteredGroups.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Ionicons name="receipt-outline" size={48} color="rgba(255,255,255,0.05)" />
            <Text style={styles.emptyText}>Không có giao dịch nào</Text>
          </View>
        ) : (
          filteredGroups.map((group) => (
          <View key={group.title} style={styles.groupContainer}>
            <View style={styles.groupHeader}>
              <Text style={styles.groupDate}>{group.title}</Text>
              <Text style={[styles.groupTotal, { color: group.total >= 0 ? Colors.accentIncome : Colors.accentExpense }]}>
                {group.total >= 0 ? '+' : ''}{group.total.toLocaleString()}đ
              </Text>
            </View>
            {group.data.map((item, idx) => (
              <GlassBox key={idx} style={styles.txItem} padding={10} intensity={10}>
                <View style={styles.txRow}>
                  <View style={[styles.catIcon, { backgroundColor: item.type === 1 ? 'rgba(0, 230, 118, 0.1)' : 'rgba(255, 82, 82, 0.1)' }]}>
                    <Text style={{ fontSize: 16 }}>{getCategoryEmoji(item.category)}</Text>
                  </View>
                  <View style={styles.txInfo}>
                    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                      <Text style={styles.txCatName}>{item.category}</Text>
                      {item.is_synced === 0 && (
                        <CloudOff size={10} color={Colors.textTertiary} style={{ marginLeft: 6 }} />
                      )}
                    </View>
                  </View>
                  <Text style={[styles.txAmount, { color: item.type === 1 ? Colors.accentIncome : Colors.accentExpense }]}>
                    {item.type === 1 ? '+' : '-'}{item.amount.toLocaleString()}đ
                  </Text>
                </View>
              </GlassBox>
            ))}
          </View>
        )))}
        <View style={{ height: 100 }} />
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

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  title: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.lg },
  monthSelectorOuter: { marginBottom: Spacing.md },
  monthSelector: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.md },
  monthLabel: { fontSize: FontSize.md, fontWeight: '700', color: Colors.textPrimary },
  summaryRow: { flexDirection: 'row', gap: Spacing.md, marginBottom: Spacing.md },
  summaryTile: { flex: 1, height: 70, justifyContent: 'center' },
  sumLabel: { fontSize: FontSize.xs, color: Colors.textSecondary },
  sumValue: { fontSize: FontSize.lg, fontWeight: '600' },
  calendarCard: { marginBottom: Spacing.lg },
  dayHeaderRow: { flexDirection: 'row', marginBottom: 6 },
  dayHeaderText: { flex: 1, textAlign: 'center', fontSize: 10, fontWeight: '700', color: Colors.textTertiary },
  weekRow: { flexDirection: 'row' },
  dayCell: { flex: 1, aspectRatio: 1, alignItems: 'center', justifyContent: 'center', borderRadius: 8 },
  todayCell: { backgroundColor: 'rgba(255, 255, 255, 0.08)', borderWidth: 0.5, borderColor: Colors.accentBlue },
  focusedCell: { backgroundColor: Colors.accentBlue, shadowColor: Colors.accentBlue, shadowOpacity: 0.5, shadowRadius: 10, elevation: 5 },
  dayText: { fontSize: 12, color: Colors.textPrimary },
  otherMonthText: { opacity: 0.2 },
  todayText: { fontWeight: '700', color: Colors.accentBlue },
  indicatorRow: { flexDirection: 'row', gap: 2, marginTop: 2, height: 3 },
  dot: { width: 3, height: 3, borderRadius: 1.5 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.sm },
  sectionTitle: { fontSize: FontSize.xl, fontWeight: '600', color: Colors.textPrimary },
  clearFilter: { fontSize: FontSize.xs, color: Colors.accentBlue, fontWeight: '600' },
  emptyContainer: { alignItems: 'center', justifyContent: 'center', paddingVertical: 40 },
  emptyText: { color: Colors.textTertiary, fontSize: FontSize.sm, marginTop: 10 },
  groupContainer: { marginBottom: Spacing.lg },
  groupHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  groupDate: { fontSize: 12, fontWeight: '600', color: Colors.textSecondary },
  groupTotal: { fontSize: 12, fontWeight: '600' },
  txItem: { marginBottom: 4 },
  txRow: { flexDirection: 'row', alignItems: 'center' },
  catIcon: { width: 34, height: 34, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  txInfo: { flex: 1 },
  txCatName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  txAmount: { fontSize: FontSize.lg, fontWeight: '600' },

  pickerApplyText: { color: Colors.white, fontWeight: '700', fontSize: FontSize.md },
});
