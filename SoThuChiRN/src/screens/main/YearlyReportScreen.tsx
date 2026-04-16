import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Dimensions,
  ActivityIndicator,
  Animated,
  Easing,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { BarChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';

const { width } = Dimensions.get('window');

interface MonthData {
  month: number;
  income: number;
  expense: number;
  net: number;
}

export default function YearlyReportScreen({ navigation }: any) {
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [activeTab, setActiveTab] = useState(0); // 0: Chi tiêu, 1: Thu nhập, 2: Tổng
  const [monthlyBreakdown, setMonthlyBreakdown] = useState<MonthData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // Overall stats
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [totalNet, setTotalNet] = useState(0);
  const [avgValue, setAvgValue] = useState(0);

  const [renderChart, setRenderChart] = useState(false);
  const sweepAnim = useRef(new Animated.Value(0)).current;

  const fetchYearlyData = useCallback(async () => {
    setIsLoading(true);
    setRenderChart(false);
    try {
      const yearlyTransactions = await db.getTransactionsByYear(selectedYear);
      
      const breakdown: MonthData[] = Array.from({ length: 12 }, (_, i) => ({
        month: i + 1,
        income: 0,
        expense: 0,
        net: 0,
      }));

      let yearIncome = 0;
      let yearExpense = 0;

      yearlyTransactions.forEach(t => {
        // Parse date "dd/mm/yyyy" to get month
        const parts = t.date.split('/');
        if (parts.length === 3) {
          const m = parseInt(parts[1], 10);
          if (m >= 1 && m <= 12) {
            const idx = m - 1;
            if (t.type === 1) {
              breakdown[idx].income += t.amount;
              yearIncome += t.amount;
            } else {
              breakdown[idx].expense += t.amount;
              yearExpense += t.amount;
            }
            breakdown[idx].net = breakdown[idx].income - breakdown[idx].expense;
          }
        }
      });

      setMonthlyBreakdown(breakdown);
      setTotalIncome(yearIncome);
      setTotalExpense(yearExpense);
      setTotalNet(yearIncome - yearExpense);

      // Calculate Average based on active tab
      if (activeTab === 0) setAvgValue(yearExpense / 12);
      else if (activeTab === 1) setAvgValue(yearIncome / 12);
      else setAvgValue((yearIncome - yearExpense) / 12);

    } catch (error) {
      console.error('Error fetching yearly refactor data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedYear, activeTab]);

  useEffect(() => {
    fetchYearlyData();
  }, [fetchYearlyData]);

  useEffect(() => {
    if (!isLoading) {
      sweepAnim.setValue(0);
      const timer = setTimeout(() => {
        setRenderChart(true);
        Animated.timing(sweepAnim, {
          toValue: 1,
          duration: 1500,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: false,
        }).start();
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [isLoading, activeTab]);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
  };

  const changeYear = (delta: number) => {
    setSelectedYear(prev => prev + delta);
  };

  // Prepare chart data based on active tab
  const chartData = monthlyBreakdown.map((item, index) => {
    let value = 0;
    let label = `T${item.month}`;
    let frontColor = Colors.accentBlue;

    if (activeTab === 0) {
      value = item.expense;
      frontColor = Colors.accentExpense;
    } else if (activeTab === 1) {
      value = item.income;
      frontColor = Colors.accentIncome;
    } else {
      value = item.net;
      frontColor = item.net >= 0 ? Colors.accentIncome : Colors.accentExpense;
    }

    // Animated value for "sweep" effect
    const animatedValue = sweepAnim.interpolate({
      inputRange: [0, 1],
      outputRange: [0, value],
    });

    return {
      value: value || 1, // Visual placeholder for 0
      label: label,
      frontColor: frontColor,
      onPress: () => {},
      // Custom property for our renderer if needed
      origValue: value,
    };
  });

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <BlurView intensity={80} tint="dark" style={StyleSheet.absoluteFill} />
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={Colors.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Báo cáo năm {selectedYear}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {/* Year Picker */}
        <GlassBox padding={12} style={styles.yearPickerContainer}>
          <View style={styles.yearPicker}>
            <TouchableOpacity onPress={() => changeYear(-1)} style={styles.navBtn}>
              <Ionicons name="chevron-back" size={22} color={Colors.textPrimary} />
            </TouchableOpacity>
            <View style={styles.yearTextContainer}>
              <Text style={styles.yearText}>Năm {selectedYear}</Text>
              <Text style={styles.yearRange}>(01/01 - 31/12)</Text>
            </View>
            <TouchableOpacity onPress={() => changeYear(1)} style={styles.navBtn}>
              <Ionicons name="chevron-forward" size={22} color={Colors.textPrimary} />
            </TouchableOpacity>
          </View>
        </GlassBox>

        {/* Tab Selection */}
        <View style={styles.tabContainer}>
          <TouchableOpacity 
            style={[styles.tabBtn, activeTab === 0 && styles.tabBtnActive]} 
            onPress={() => setActiveTab(0)}
          >
            <Text style={[styles.tabText, activeTab === 0 && styles.tabTextActive]}>Chi tiêu</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.tabBtn, activeTab === 1 && styles.tabBtnActive]} 
            onPress={() => setActiveTab(1)}
          >
            <Text style={[styles.tabText, activeTab === 1 && styles.tabTextActive]}>Thu nhập</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.tabBtn, activeTab === 2 && styles.tabBtnActive]} 
            onPress={() => setActiveTab(2)}
          >
            <Text style={[styles.tabText, activeTab === 2 && styles.tabTextActive]}>Tổng</Text>
          </TouchableOpacity>
        </View>

        {/* Global Stats Grid */}
        <View style={styles.statsGrid}>
          {activeTab < 2 ? (
            <>
              <GlassBox style={styles.statCard} padding={12}>
                <Text style={styles.statLabel}>Tổng {activeTab === 0 ? 'chi' : 'thu'}</Text>
                <Text style={[styles.statValue, { color: activeTab === 0 ? Colors.accentExpense : Colors.accentIncome }]}>
                  {formatCurrency(activeTab === 0 ? totalExpense : totalIncome)}
                </Text>
              </GlassBox>
              <GlassBox style={styles.statCard} padding={12}>
                <Text style={styles.statLabel}>Trung bình tháng</Text>
                <Text style={[styles.statValue, { color: Colors.accentBlue }]}>
                  {formatCurrency(avgValue)}
                </Text>
              </GlassBox>
            </>
          ) : (
            <View style={{ width: '100%', gap: Spacing.md }}>
              <View style={styles.statsRow}>
                <GlassBox style={styles.statCard} padding={12}>
                  <Text style={styles.statLabel}>Tổng số dư</Text>
                  <Text style={[styles.statValue, { color: totalNet >= 0 ? Colors.accentIncome : Colors.accentExpense }]}>
                    {formatCurrency(totalNet)}
                  </Text>
                </GlassBox>
                <GlassBox style={styles.statCard} padding={12}>
                  <Text style={styles.statLabel}>Trung bình dư/tháng</Text>
                  <Text style={[styles.statValue, { color: Colors.accentBlue }]}>
                    {formatCurrency(avgValue)}
                  </Text>
                </GlassBox>
              </View>
              <View style={styles.statsRow}>
                <GlassBox style={styles.statCard} padding={12}>
                  <Text style={styles.statLabel}>Tổng thu nhập</Text>
                  <Text style={[styles.statValueSmall, { color: Colors.accentIncome }]}>
                    {formatCurrency(totalIncome)}
                  </Text>
                </GlassBox>
                <GlassBox style={styles.statCard} padding={12}>
                  <Text style={styles.statLabel}>Tổng chi tiêu</Text>
                  <Text style={[styles.statValueSmall, { color: Colors.accentExpense }]}>
                    {formatCurrency(totalExpense)}
                  </Text>
                </GlassBox>
              </View>
            </View>
          )}
        </View>

        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={Colors.accentBlue} />
          </View>
        ) : (
          <>
            <GlassBox style={styles.chartCard} padding={16}>
              <Text style={styles.chartTitle}>
                Biểu đồ {activeTab === 0 ? 'chi tiêu' : activeTab === 1 ? 'thu nhập' : 'biến động'} tháng
              </Text>
              <View style={styles.chartWrapper}>
                {renderChart && (
                  <BarChart
                    data={chartData}
                    width={width - 80}
                    height={200}
                    barWidth={18}
                    spacing={14}
                    roundedTop
                    hideRules
                    xAxisThickness={0}
                    yAxisThickness={0}
                    xAxisLabelTextStyle={{ color: Colors.textTertiary, fontSize: 10 }}
                    yAxisTextStyle={{ color: Colors.textTertiary, fontSize: 10 }}
                    noOfSections={4}
                    maxValue={Math.max(...chartData.map(d => Math.abs(d.origValue))) * 1.2 || 1000}
                    isAnimated
                    animationDuration={1500}
                  />
                )}
              </View>
            </GlassBox>

            <GlassBox style={styles.listCard} padding={0}>
              <View style={styles.listHeader}>
                <Text style={styles.listHeaderText}>Chi tiết từng tháng</Text>
              </View>
              {monthlyBreakdown.map((item, index) => {
                let displayValue = 0;
                let color = Colors.textPrimary;
                if (activeTab === 0) { displayValue = item.expense; color = Colors.accentExpense; }
                else if (activeTab === 1) { displayValue = item.income; color = Colors.accentIncome; }
                else { displayValue = item.net; color = item.net >= 0 ? Colors.accentIncome : Colors.accentExpense; }

                return (
                  <View key={index} style={[styles.monthItem, index === 11 && { borderBottomWidth: 0 }]}>
                    <Text style={styles.monthName}>Tháng {item.month}</Text>
                    <Text style={[styles.monthValue, { color }]}>
                      {activeTab < 2 ? 
                        (activeTab === 0 ? '-' : '+') + formatCurrency(displayValue) : 
                        formatCurrency(displayValue)
                      }
                    </Text>
                  </View>
                );
              })}
            </GlassBox>
          </>
        )}

        <View style={{ height: 60 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  header: {
    height: 90,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.md,
    paddingTop: 40,
    zIndex: 10,
  },
  headerTitle: { fontSize: FontSize.lg, fontWeight: 'bold', color: Colors.white },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  scrollContent: { padding: Spacing.md },
  yearPickerContainer: {
    marginBottom: Spacing.md,
  },
  yearPicker: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.md,
    flexWrap: 'nowrap',
  },
  navBtn: { 
    padding: 8,
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  yearTextContainer: { 
    alignItems: 'center',
    minWidth: 120,
  },
  yearText: { fontSize: FontSize.lg, fontWeight: 'bold', color: Colors.textPrimary },
  yearRange: { fontSize: 10, color: Colors.textTertiary, marginTop: -1 },
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderRadius: BorderRadius.xl,
    padding: 4,
    marginBottom: Spacing.md,
  },
  tabBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: BorderRadius.lg },
  tabBtnActive: { backgroundColor: 'rgba(255,255,255,0.1)' },
  tabText: { fontSize: FontSize.sm, color: Colors.textTertiary },
  tabTextActive: { color: Colors.white, fontWeight: 'bold' },
  statsGrid: { marginBottom: Spacing.md },
  statsRow: { flexDirection: 'row', gap: Spacing.md },
  statCard: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  statLabel: { fontSize: 10, color: Colors.textTertiary, marginBottom: 4 },
  statValue: { fontSize: FontSize.sm, fontWeight: 'bold' },
  statValueSmall: { fontSize: 12, fontWeight: 'bold' },
  loadingContainer: { height: 300, justifyContent: 'center', alignItems: 'center' },
  chartCard: { marginBottom: Spacing.md },
  chartTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textSecondary, marginBottom: 16 },
  chartWrapper: { alignItems: 'center', marginLeft: -20 },
  listCard: { overflow: 'hidden' },
  listHeader: { padding: 12, backgroundColor: 'rgba(255,255,255,0.03)', borderBottomWidth: 1, borderBottomColor: Colors.glassBorder },
  listHeaderText: { fontSize: FontSize.xs, fontWeight: 'bold', color: Colors.textTertiary },
  monthItem: { 
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    alignItems: 'center', 
    padding: 14, 
    borderBottomWidth: 1, 
    borderBottomColor: 'rgba(255,255,255,0.05)' 
  },
  monthName: { fontSize: FontSize.sm, color: Colors.textPrimary },
  monthValue: { fontSize: FontSize.sm, fontWeight: 'bold' },
});
