import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Dimensions,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import SummaryCard from '../../components/SummaryCard';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { Ionicons } from '@expo/vector-icons';
import { LineChart } from 'react-native-gifted-charts';
import { getCategoryEmoji } from '../../config/categories';
import { BlurView } from 'expo-blur';
import { CloudOff } from 'lucide-react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';

const { width } = Dimensions.get('window');

export default function DashboardScreen() {
  const navigation = useNavigation<any>();
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  
  const [totalBalance, setTotalBalance] = useState(0);
  const [periodBalance, setPeriodBalance] = useState(0);
  const [monthlyIncome, setMonthlyIncome] = useState(0);
  const [monthlyExpense, setMonthlyExpense] = useState(0);
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([]);
  const [chartData, setChartData] = useState<any[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPickerVisible, setIsPickerVisible] = useState(false);

  const fetchData = useCallback(async (m: number, y: number) => {
    try {
      const [, , allTimeBal] = await db.getAllTimeSummary();
      setTotalBalance(allTimeBal);

      const [mIncome, mExpense] = await db.getSummaryByMonth(m, y);
      setMonthlyIncome(mIncome);
      setMonthlyExpense(mExpense);
      setPeriodBalance(mIncome - mExpense);

      const allTransactions = await db.getAllTransactions();
      setRecentTransactions(allTransactions.slice(0, 7));

      const dates = [];
      for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const day = String(d.getDate()).padStart(2, '0');
        const mo = String(d.getMonth() + 1).padStart(2, '0');
        const yr = d.getFullYear();
        dates.push(`${day}/${mo}/${yr}`);
      }

      const summaries = await db.getDailySummariesInRange(dates);
      const formattedChartData = summaries.map((s) => ({
        value: s.income - s.expense,
        label: s.date.split('/')[0],
        fullDate: s.date,
      }));
      setChartData(formattedChartData);
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchData(selectedMonth, selectedYear);
    }, [fetchData, selectedMonth, selectedYear])
  );

  const onRefresh = async () => {
    setIsRefreshing(true);
    await fetchData(selectedMonth, selectedYear);
    setIsRefreshing(false);
  };

  const handlePrevMonth = () => {
    if (selectedMonth === 1) {
      setSelectedMonth(12);
      setSelectedYear(selectedYear - 1);
    } else {
      setSelectedMonth(selectedMonth - 1);
    }
  };

  const handleNextMonth = () => {
    if (selectedMonth === 12) {
      setSelectedMonth(1);
      setSelectedYear(selectedYear + 1);
    } else {
      setSelectedMonth(selectedMonth + 1);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={Colors.white} />
        }
      >
        <View style={styles.header}>
          <View>
            <Text style={styles.greeting}>Xin chào,</Text>
            <Text style={styles.userName}>Sổ Thu Chi</Text>
          </View>
        </View>

        <View style={styles.bentoContainer}>
          {/* Enhanced Summary Card Component */}
          <SummaryCard 
            totalBalance={totalBalance}
            periodBalance={periodBalance}
            month={selectedMonth}
            year={selectedYear}
            onPrev={handlePrevMonth}
            onNext={handleNextMonth}
            onDatePress={() => setIsPickerVisible(true)}
          />

          <UniversalDatePicker 
            isVisible={isPickerVisible}
            currentMonth={selectedMonth}
            currentYear={selectedYear}
            onClose={() => setIsPickerVisible(false)}
            onSelect={(_, m, y) => {
              setSelectedMonth(m);
              setSelectedYear(y);
              setIsPickerVisible(false);
            }}
          />

          <View style={styles.row}>
            <GlassBox style={styles.halfTile} padding={10}>
              <View style={[styles.tileIconContainer, { backgroundColor: 'rgba(0, 230, 118, 0.08)' }]}>
                <Ionicons name="trending-up" size={14} color={Colors.accentIncome} />
              </View>
              <Text style={styles.miniLabel}>Thu nhập</Text>
              <Text style={[styles.miniAmount, { color: Colors.accentIncome }]} numberOfLines={1}>
                +{monthlyIncome.toLocaleString()}
              </Text>
            </GlassBox>
            <GlassBox style={styles.halfTile} padding={10}>
              <View style={[styles.tileIconContainer, { backgroundColor: 'rgba(255, 82, 82, 0.08)' }]}>
                <Ionicons name="trending-down" size={14} color={Colors.accentExpense} />
              </View>
              <Text style={styles.miniLabel}>Đã chi</Text>
              <Text style={[styles.miniAmount, { color: Colors.accentExpense }]} numberOfLines={1}>
                -{monthlyExpense.toLocaleString()}
              </Text>
            </GlassBox>
          </View>

          <GlassBox style={styles.chartTile} padding={10}>
            <Text style={[styles.tileLabel, { color: Colors.textPrimary }]}>Xu hướng 7 ngày</Text>
            <View style={styles.chartContainer}>
              {chartData.length > 0 && (
                <LineChart
                  data={chartData} width={width - 72} height={100} noOfSections={3} color={Colors.accentBlue} thickness={2}
                  startFillColor="rgba(0, 176, 255, 0.2)" endFillColor="rgba(0, 176, 255, 0.01)" startOpacity={0.3}
                  spacing={48}
                  rulesType="none"
                  yAxisTextStyle={{ color: Colors.textTertiary, fontSize: 8 }}
                  xAxisLabelTextStyle={{ color: Colors.textTertiary, fontSize: 8 }}
                  hideDataPoints={false}
                  dataPointsColor={Colors.accentBlue}
                  dataPointsRadius={4}
                  curved
                  pointerConfig={{
                    pointerStripUptoDataPoint: true,
                    pointerStripColor: 'rgba(255, 255, 255, 0.4)',
                    pointerStripWidth: 1,
                    strokeDashArray: [2, 4],
                    pointerColor: Colors.accentBlue,
                    radius: 5,
                    pointerLabelWidth: 100,
                    pointerLabelHeight: 45,
                    autoAdjustPointerLabelPosition: true,
                    persistPointer: true,
                    pointerVanishDelay: 0,
                    shiftPointerLabelX: -40,
                    shiftPointerLabelY: -35,
                    pointerLabelComponent: (items: any) => (
                      <View style={styles.tooltipContainer}>
                        <BlurView intensity={60} tint="dark" style={styles.tooltipBlur}>
                          <Text style={styles.tooltipDate}>{items[0].fullDate}</Text>
                          <Text style={[styles.tooltipVal, { color: items[0].value >= 0 ? Colors.accentIncome : Colors.accentExpense }]}>
                            {items[0].value >= 0 ? '+' : ''}{items[0].value.toLocaleString()}đ
                          </Text>
                        </BlurView>
                      </View>
                    ),
                  }}
                />
              )}
            </View>
          </GlassBox>

          <View style={styles.listHeader}>
            <Text style={styles.sectionTitle}>Gần đây (7)</Text>
            <TouchableOpacity onPress={() => navigation.navigate('Calendar')}>
              <Text style={styles.seeAll}>Tất cả</Text>
            </TouchableOpacity>
          </View>

          {recentTransactions.map((item, index) => (
            <GlassBox key={item.id?.toString() || index.toString()} style={styles.transactionItem} padding={10} intensity={20}>
              <View style={styles.txRow}>
                <View style={[styles.categoryIcon, { backgroundColor: item.type === 1 ? 'rgba(0, 230, 118, 0.1)' : 'rgba(255, 82, 82, 0.1)' }]}>
                  <Text style={{ fontSize: 16 }}>{getCategoryEmoji(item.category)}</Text>
                </View>
                <View style={styles.txInfo}>
                  <Text style={styles.txCategory}>{item.category}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <Text style={styles.txDate}>{item.date}</Text>
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
        <View style={{ height: 100 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: Spacing.lg },
  greeting: { fontSize: FontSize.xs, color: Colors.textSecondary, fontWeight: '500' },
  userName: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary },
  bentoContainer: { gap: Spacing.md },
  row: { flexDirection: 'row', gap: Spacing.md },
  halfTile: { flex: 1, height: 90, justifyContent: 'space-between' },
  tileIconContainer: { width: 24, height: 24, borderRadius: 6, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  miniLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: 2 },
  miniAmount: { fontSize: FontSize.lg, fontWeight: '600' },
  chartTile: { height: 160 },
  chartContainer: { marginTop: 10, alignItems: 'center', marginLeft: -25 },
  tooltipContainer: { justifyContent: 'center', alignItems: 'center' },
  tooltipBlur: { padding: 6, borderRadius: 8, borderWidth: 0.5, borderColor: 'rgba(255, 255, 255, 0.2)', minWidth: 80, alignItems: 'center' },
  tooltipDate: { fontSize: 8, color: Colors.textTertiary, marginBottom: 2 },
  tooltipVal: { fontSize: 10, fontWeight: '700' },
  listHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: Spacing.sm, marginBottom: 2 },
  sectionTitle: { fontSize: FontSize.xl, fontWeight: '600', color: Colors.textPrimary },
  seeAll: { fontSize: FontSize.xs, color: Colors.accentBlue, fontWeight: '600' },
  transactionItem: { marginBottom: 2 },
  txRow: { flexDirection: 'row', alignItems: 'center' },
  categoryIcon: { width: 34, height: 34, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  txInfo: { flex: 1 },
  txCategory: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  txDate: { fontSize: FontSize.xs, color: Colors.textTertiary },
  txAmount: { fontSize: FontSize.lg, fontWeight: '600' },
});
