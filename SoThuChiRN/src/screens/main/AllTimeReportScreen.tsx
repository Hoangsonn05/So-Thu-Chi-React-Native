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
import { PieChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';

const { width } = Dimensions.get('window');

const CHART_COLORS = [
  '#00E676', '#FF5252', '#00B0FF', '#FFD600',
  '#AA00FF', '#FF6D00', '#00BFA5', '#C6FF00',
];

interface ReportCategory {
  name: string;
  amount: number;
  percentage: number;
  color: string;
}

export default function AllTimeReportScreen({ navigation }: any) {
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [balance, setBalance] = useState(0);
  const [categories, setCategories] = useState<ReportCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeType, setActiveType] = useState(0); // 0: Expense, 1: Income
  const [renderChart, setRenderChart] = useState(false);
  
  const sweepAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.85)).current;
  const [sweepProgress, setSweepProgress] = useState(0);

  const fetchAllTimeData = useCallback(async () => {
    setIsLoading(true);
    setRenderChart(false);
    try {
      const summary = await db.getAllTimeSummary();
      setTotalIncome(summary[0]);
      setTotalExpense(summary[1]);
      setBalance(summary[2]);

      const allTransactions = await db.getAllTransactions();
      const filtered = allTransactions.filter(t => t.type === activeType);
      
      const catMap = new Map<string, number>();
      let total = 0;
      
      filtered.forEach(t => {
        const cat = t.category || 'Khác';
        catMap.set(cat, (catMap.get(cat) || 0) + t.amount);
        total += t.amount;
      });

      const processed: ReportCategory[] = Array.from(catMap.entries())
        .map(([name, amount], index) => ({
          name,
          amount,
          percentage: total > 0 ? (amount / total) * 100 : 0,
          color: CHART_COLORS[index % CHART_COLORS.length],
        }))
        .sort((a, b) => b.amount - a.amount);

      setCategories(processed);
    } catch (error) {
      console.error('Error fetching all-time data:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeType]);

  useEffect(() => {
    fetchAllTimeData();
  }, [fetchAllTimeData]);

  useEffect(() => {
    if (!isLoading && categories.length > 0) {
      sweepAnim.setValue(0);
      scaleAnim.setValue(0.85);
      setSweepProgress(0);
      
      const timer = setTimeout(() => {
        setRenderChart(true);
      }, 150);
      return () => clearTimeout(timer);
    } else {
      setRenderChart(false);
    }
  }, [isLoading, categories]);

  useEffect(() => {
    if (renderChart) {
      const listenerId = sweepAnim.addListener(({ value }) => {
        setSweepProgress(value);
      });

      Animated.parallel([
        Animated.timing(sweepAnim, {
          toValue: 1,
          duration: 2500,
          easing: Easing.bezier(0.4, 0, 0.2, 1),
          useNativeDriver: false,
        }),
        Animated.timing(scaleAnim, {
          toValue: 1,
          duration: 2200,
          easing: Easing.out(Easing.back(1.5)),
          useNativeDriver: false,
        })
      ]).start();

      return () => sweepAnim.removeListener(listenerId);
    }
  }, [renderChart]);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(amount);
  };

  // Calculate cumulative limit for manual sweep effect
  const totalAmount = categories.reduce((sum, c) => sum + c.amount, 0);
  let currentAccumulated = 0;
  const currentLimit = sweepProgress * totalAmount;

  const animatedPieData = categories.map((cat, idx) => {
    const startValue = currentAccumulated;
    currentAccumulated += cat.amount;
    
    let displayAmount = 0;
    if (currentLimit >= currentAccumulated) {
      displayAmount = cat.amount;
    } else if (currentLimit > startValue) {
      displayAmount = currentLimit - startValue;
    }

    return {
      value: displayAmount || 0.01, // Avoid 0 for gifted-charts
      color: cat.color,
    };
  });

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <BlurView intensity={80} tint="dark" style={StyleSheet.absoluteFill} />
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={Colors.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Báo cáo toàn kì</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <GlassBox style={styles.summaryCard} padding={20}>
          <Text style={styles.summaryTitle}>Tổng kết tài chính</Text>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryRow}>
            <View style={styles.summaryColumn}>
              <Text style={styles.summaryLabel}>Tổng thu</Text>
              <Text style={[styles.summaryValue, { color: Colors.accentIncome }]}>
                +{formatCurrency(totalIncome)}
              </Text>
            </View>
            <View style={styles.verticalDivider} />
            <View style={styles.summaryColumn}>
              <Text style={styles.summaryLabel}>Tổng chi</Text>
              <Text style={[styles.summaryValue, { color: Colors.accentExpense }]}>
                -{formatCurrency(totalExpense)}
              </Text>
            </View>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.totalRow}>
            <Text style={styles.totalLabel}>Số dư thực tế</Text>
            <Text style={[styles.totalValue, { color: balance >= 0 ? Colors.accentBlue : Colors.accentExpense }]}>
              {formatCurrency(balance)}
            </Text>
          </View>
        </GlassBox>

        <View style={styles.typeSelector}>
          <TouchableOpacity 
            style={[styles.typeBtn, activeType === 0 && styles.typeBtnActive]}
            onPress={() => setActiveType(0)}
          >
            <Text style={[styles.typeText, activeType === 0 && styles.typeTextActive]}>Chi tiêu</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.typeBtn, activeType === 1 && styles.typeBtnActive]}
            onPress={() => setActiveType(1)}
          >
            <Text style={[styles.typeText, activeType === 1 && styles.typeTextActive]}>Thu nhập</Text>
          </TouchableOpacity>
        </View>

        {isLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={Colors.accentBlue} />
          </View>
        ) : categories.length > 0 ? (
          <GlassBox style={styles.chartCard} padding={20}>
            <View style={styles.chartContainer}>
              <Animated.View style={{ 
                transform: [{ scale: scaleAnim }],
                opacity: sweepAnim.interpolate({ inputRange: [0, 0.1, 1], outputRange: [0, 1, 1] })
              }}>
                {renderChart && (
                  <PieChart
                    data={animatedPieData}
                    donut
                    sectionAutoFocus
                    radius={100}
                    innerRadius={70}
                    innerCircleColor={Colors.bg}
                    centerLabelComponent={() => (
                      <View style={{ justifyContent: 'center', alignItems: 'center' }}>
                        <Text style={{ fontSize: 22, color: Colors.textPrimary, fontWeight: 'bold' }}>
                          {Math.round(sweepProgress * 100)}%
                        </Text>
                        <Text style={{ fontSize: 12, color: Colors.textTertiary }}>Tiến độ</Text>
                      </View>
                    )}
                  />
                )}
              </Animated.View>
            </View>

            <View style={styles.categoryList}>
              {categories.map((item, index) => (
                <View key={index} style={styles.categoryItem}>
                  <View style={[styles.colorDot, { backgroundColor: item.color }]} />
                  <Text style={styles.categoryName}>{item.name}</Text>
                  <View style={styles.categoryRight}>
                    <Text style={styles.categoryAmount}>{formatCurrency(item.amount)}</Text>
                    <Text style={styles.categoryPercent}>{item.percentage.toFixed(1)}%</Text>
                  </View>
                </View>
              ))}
            </View>
          </GlassBox>
        ) : (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>Không có dữ liệu cho mục này</Text>
          </View>
        )}

        <View style={{ height: 40 }} />
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
  summaryCard: { marginBottom: Spacing.md },
  summaryTitle: { fontSize: FontSize.md, fontWeight: 'bold', color: Colors.textPrimary, marginBottom: 12 },
  summaryDivider: { height: 1, backgroundColor: Colors.glassBorder, marginVertical: 12, opacity: 0.3 },
  summaryRow: { flexDirection: 'row', alignItems: 'center' },
  summaryColumn: { flex: 1, alignItems: 'center' },
  summaryLabel: { fontSize: FontSize.xs, color: Colors.textTertiary, marginBottom: 4 },
  summaryValue: { fontSize: FontSize.md, fontWeight: 'bold' },
  verticalDivider: { width: 1, height: 30, backgroundColor: Colors.glassBorder, opacity: 0.3 },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  totalLabel: { fontSize: FontSize.sm, color: Colors.textSecondary },
  totalValue: { fontSize: FontSize.xl, fontWeight: 'bold' },
  typeSelector: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: BorderRadius.full,
    padding: 4,
    marginBottom: Spacing.md,
  },
  typeBtn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: BorderRadius.full },
  typeBtnActive: { backgroundColor: 'rgba(255, 255, 255, 0.1)' },
  typeText: { fontSize: FontSize.sm, color: Colors.textTertiary },
  typeTextActive: { color: Colors.textPrimary, fontWeight: 'bold' },
  loadingContainer: { height: 300, justifyContent: 'center', alignItems: 'center' },
  chartCard: { marginBottom: Spacing.md },
  chartContainer: { alignItems: 'center', marginVertical: 20 },
  categoryList: { marginTop: 10 },
  categoryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  colorDot: { width: 10, height: 10, borderRadius: 5, marginRight: 12 },
  categoryName: { flex: 1, fontSize: FontSize.sm, color: Colors.textPrimary },
  categoryRight: { alignItems: 'flex-end' },
  categoryAmount: { fontSize: FontSize.sm, fontWeight: 'bold', color: Colors.textPrimary },
  categoryPercent: { fontSize: FontSize.xs, color: Colors.textTertiary },
  emptyContainer: { height: 200, justifyContent: 'center', alignItems: 'center' },
  emptyText: { color: Colors.textTertiary, fontSize: FontSize.md },
});
