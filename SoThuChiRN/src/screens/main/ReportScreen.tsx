import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Dimensions,
  ActivityIndicator,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { PieChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { PanResponder, Animated, Easing } from 'react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';

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
}export default function ReportScreen() {
  const [period, setPeriod] = useState(0);
  const [type, setType] = useState(0);
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [year, setYear] = useState(new Date().getFullYear());
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [categories, setCategories] = useState<ReportCategory[]>([]);
  const [displayCategories, setDisplayCategories] = useState<ReportCategory[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<ReportCategory | null>(null);
  const [isPickerVisible, setIsPickerVisible] = useState(false);
  const [renderChart, setRenderChart] = useState(false);
  const sweepAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.85)).current;
  const [sweepProgress, setSweepProgress] = useState(0);

  // Manual Sweep Animation Logic with "Flowing" feel
  useEffect(() => {
    if (renderChart) {
      const listenerId = sweepAnim.addListener(({ value }) => {
        setSweepProgress(value);
      });

      // Parallel animations for "Glidng" effect
      Animated.parallel([
        Animated.timing(sweepAnim, {
          toValue: 1,
          duration: 2500, // Longer for a gliding feel
          easing: Easing.bezier(0.4, 0, 0.2, 1), // Standard smooth ease-in-out
          useNativeDriver: false, // Must be false due to addListener
        }),
        Animated.timing(scaleAnim, {
          toValue: 1,
          duration: 2200,
          easing: Easing.out(Easing.back(1.5)), // Subtle bounce at the end
          useNativeDriver: false,
        })
      ]).start();

      return () => sweepAnim.removeListener(listenerId);
    }
  }, [renderChart]);

  // Step-Data Logic: Transition from unmounted to mounted
  useEffect(() => {
    if (!isLoading && categories.length > 0) {
      // PRE-RESET: Reset values BEFORE mounting to avoid flickering previous states
      sweepAnim.setValue(0);
      scaleAnim.setValue(0.85);
      setSweepProgress(0);
      setRenderChart(false);

      const timer = setTimeout(() => {
        setRenderChart(true);
      }, 150); // Shorter delay but with clean reset
      return () => clearTimeout(timer);
    } else {
      setRenderChart(false);
    }
  }, [isLoading, categories, type, month, year]);
  // Rotation Animation
  const rotation = useRef(new Animated.Value(0)).current;
  const lastAngle = useRef(0);
  const rotationValue = useRef(0);
  const chartCenter = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const id = rotation.addListener(({ value }) => {
      rotationValue.current = value;
    });
    return () => rotation.removeListener(id);
  }, []);

  const stopRotation = () => {
    rotation.stopAnimation();
  };

  const measureChart = () => {
    if (panRef.current) {
      panRef.current.measure((x, y, width, height, pageX, pageY) => {
        if (width > 0) {
          chartCenter.current = { x: pageX + width / 2, y: pageY + height / 2 };
        }
      });
    }
  };

  const onChartLayout = () => {
    setTimeout(measureChart, 600);
  };

  const getAngleInfo = (x: number, y: number) => {
    if (chartCenter.current.x === 0) return { angle: 0, distance: 0 };
    const dx = x - chartCenter.current.x;
    const dy = y - chartCenter.current.y;
    const distance = Math.sqrt(dx * dx + dy * dy);
    const angle = Math.atan2(dy, dx) * (180 / Math.PI);
    return { angle, distance };
  };

  const panRef = useRef<View>(null);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gestureState) => {
        return Math.abs(gestureState.dx) > 5 || Math.abs(gestureState.dy) > 5;
      },
      onPanResponderGrant: (evt) => {
        stopRotation();
        measureChart();
        const { pageX, pageY } = evt.nativeEvent;
        const { angle } = getAngleInfo(pageX, pageY);
        lastAngle.current = angle;
      },
      onPanResponderMove: (evt) => {
        if (chartCenter.current.x === 0) return;
        
        const { pageX, pageY } = evt.nativeEvent;
        const { angle, distance } = getAngleInfo(pageX, pageY);
        
        // Dead-zone: If too close to center, rotation calculations become unstable
        if (distance < 30) return; 

        let delta = angle - lastAngle.current;
        
        if (delta > 180) delta -= 360;
        else if (delta < -180) delta += 360;
        
        rotation.setValue(rotationValue.current + delta);
        lastAngle.current = angle;
      },
      onPanResponderRelease: (_, gestureState) => {
        const velocity = (Math.abs(gestureState.vx) + Math.abs(gestureState.vy)) / 2;
        if (velocity > 0.02) {
          Animated.decay(rotation, {
            velocity: velocity * 0.5, // Much faster spin
            deceleration: 0.998, // Very low friction (spin for a long time)
            useNativeDriver: true,
          }).start();
        }
      },
    })
  ).current;

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      let txns: Transaction[];
      if (period === 0) txns = await db.getTransactionsByMonth(month, year);
      else if (period === 1) txns = await db.getTransactionsByYear(year);
      else txns = await db.getAllTransactions();

      let income = 0, expense = 0;
      for (const t of txns) {
        if (t.type === 1) income += t.amount;
        else expense += t.amount;
      }
      setTotalIncome(income);
      setTotalExpense(expense);

      const filtered = txns.filter(t => t.type === type);
      const catMap: Record<string, number> = {};
      let total = 0;
      for (const t of filtered) {
        catMap[t.category] = (catMap[t.category] || 0) + t.amount;
        total += t.amount;
      }

      const sorted = Object.entries(catMap)
        .sort(([, a], [, b]) => b - a)
        .map(([name, amount], i) => ({
          name, amount,
          percentage: total > 0 ? (amount / total) * 100 : 0,
          color: CHART_COLORS[i % CHART_COLORS.length],
        }));
      setCategories(sorted);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  }, [period, type, month, year]);

  useEffect(() => {
    setSelectedCategory(null); // Reset selection on period/type change
    loadData();
  }, [loadData]);

  const dateText = period === 0 ? `${month}/${year}` : period === 1 ? `${year}` : 'Tất cả';

  const handlePrev = () => {
    if (period === 0) {
      if (month === 1) { setMonth(12); setYear(y => y - 1); }
      else setMonth(m => m - 1);
    } else if (period === 1) setYear(y => y - 1);
  };

  const handleNext = () => {
    if (period === 0) {
      if (month === 12) { setMonth(1); setYear(y => y + 1); }
      else setMonth(m => m + 1);
    } else if (period === 1) setYear(y => y + 1);
  };

  const totalAmount = categories.reduce((s, c) => s + c.amount, 0);
  let currentLimit = totalAmount * sweepProgress;

  const pieData = categories.map((cat, index) => {
    const val = Math.min(cat.amount, Math.max(0, currentLimit));
    currentLimit -= val;
    
    return {
      value: val,
      color: cat.color,
      text: (sweepProgress === 1 && selectedCategory?.name === cat.name && cat.percentage > 5) ? `${cat.percentage.toFixed(0)}%` : '',
      focused: selectedCategory?.name === cat.name,
      categoryName: cat.name,
      percentage: cat.percentage,
    };
  });

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Báo cáo</Text>

        <View style={styles.periodRow}>
          {[{ id: 0, label: 'Tháng' }, { id: 1, label: 'Năm' }, { id: 2, label: 'Tất cả' }].map(p => (
            <TouchableOpacity
              key={p.id}
              style={[styles.periodBtn, period === p.id && styles.periodBtnActive]}
              onPress={() => setPeriod(p.id)}
            >
              <Text style={[styles.periodBtnText, period === p.id && styles.periodBtnTextActive]}>{p.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {period < 2 && (
          <GlassBox padding={8} intensity={20} style={styles.datePickerOuter}>
            <View style={styles.datePicker}>
              <TouchableOpacity onPress={handlePrev} style={styles.dateNavBtn}>
                <Ionicons name="chevron-back" size={20} color={Colors.textPrimary} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setIsPickerVisible(true)} style={styles.dateCenter}>
                <Text style={styles.dateValue}>{dateText}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleNext} style={styles.dateNavBtn}>
                <Ionicons name="chevron-forward" size={20} color={Colors.textPrimary} />
              </TouchableOpacity>
            </View>
          </GlassBox>
        )}

        <UniversalDatePicker 
          isVisible={isPickerVisible}
          currentMonth={month}
          currentYear={year}
          onClose={() => setIsPickerVisible(false)}
          onSelect={(_, m, y) => {
            setMonth(m);
            setYear(y);
            setIsPickerVisible(false);
          }}
        />

        <View style={styles.typeSwitcher}>
          <TouchableOpacity style={[styles.typeBtn, type === 0 && styles.typeBtnActiveExpense]} onPress={() => setType(0)}>
            <Text style={[styles.typeBtnText, type === 0 && styles.typeBtnTextActive]}>CHI TIÊU</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.typeBtn, type === 1 && styles.typeBtnActiveIncome]} onPress={() => setType(1)}>
            <Text style={[styles.typeBtnText, type === 1 && styles.typeBtnTextActive]}>THU NHẬP</Text>
          </TouchableOpacity>
        </View>

        <GlassBox style={styles.chartBox} padding={12}>
          {isLoading ? (
            <ActivityIndicator color={Colors.accentBlue} />
          ) : categories.length > 0 ? (
            <Animated.View 
              ref={panRef}
              onLayout={onChartLayout}
              style={[
                styles.chartInner, 
                { 
                  transform: [
                    { rotate: rotation.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '360deg'] }) },
                    { scale: scaleAnim }
                  ],
                  opacity: sweepAnim.interpolate({ inputRange: [0, 0.1, 1], outputRange: [0, 1, 1] })
                }
              ]}
              {...panResponder.panHandlers}
            >
              {renderChart ? (
                <PieChart
                    animate={false}
                    initialAngle={-90}
                    donut
                    showText
                    textColor="#fff"
                    radius={100}
                    innerRadius={55}
                    textSize={10}
                    data={pieData}
                    focusOnPress
                    toggleFocusOnPress={false}
                    extraRadiusForFocus={10}
                    onPress={(item: any) => {
                      if (selectedCategory?.name === item.categoryName) {
                        setSelectedCategory(null);
                      } else {
                        const fullCat = categories.find(c => c.name === item.categoryName);
                        setSelectedCategory(fullCat || null);
                      }
                    }}
                    centerLabelComponent={() => (
                      <View style={styles.centerContainer}>
                        {selectedCategory ? (
                          <View style={styles.tooltipInner}>
                            <Text style={styles.tooltipName} numberOfLines={1}>{selectedCategory.name}</Text>
                            <Text style={[styles.tooltipVal, { color: type === 0 ? Colors.accentExpense : Colors.accentIncome }]}>
                              {selectedCategory.amount.toLocaleString()}đ
                            </Text>
                            <Text style={styles.tooltipPercent}>{selectedCategory.percentage.toFixed(1)}%</Text>
                          </View>
                        ) : (
                          <View style={{ alignItems: 'center' }}>
                            <Text style={{ fontSize: 10, color: Colors.textSecondary }}>Tổng</Text>
                            {sweepProgress === 1 && (
                              <Text style={{ fontSize: 14, color: Colors.textPrimary, fontWeight: '700' }}>
                                {(type === 0 ? totalExpense : totalIncome).toLocaleString()}đ
                              </Text>
                            )}
                          </View>
                        )}
                      </View>
                    )}
                  />
              ) : (
                <View style={{ height: 200, width: 220, alignItems: 'center', justifyContent: 'center' }} />
              )}
            </Animated.View>
          ) : <Text style={styles.emptyText}>Chưa có dữ liệu</Text>}
        </GlassBox>

        <Text style={styles.sectionTitle}>Phân bổ danh mục</Text>
        {categories.map((cat, idx) => (
          <GlassBox key={idx} style={styles.catItem} padding={10} intensity={10}>
            <View style={styles.catRow}>
              <View style={[styles.catColor, { backgroundColor: cat.color }]} />
              <View style={styles.catInfo}>
                <Text style={styles.catName}>{cat.name}</Text>
                <Text style={styles.catPercent}>{cat.percentage.toFixed(1)}%</Text>
              </View>
              <Text style={[styles.catAmount, { color: type === 0 ? Colors.accentExpense : Colors.accentIncome }]}>
                {type === 0 ? '-' : '+'}{cat.amount.toLocaleString()}đ
              </Text>
            </View>
          </GlassBox>
        ))}
        <View style={{ height: 100 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  title: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.lg },
  periodRow: { flexDirection: 'row', gap: 6, marginBottom: Spacing.md },
  periodBtn: { flex: 1, height: 36, borderRadius: BorderRadius.md, backgroundColor: Colors.bgSecondary, alignItems: 'center', justifyContent: 'center' },
  periodBtnActive: { backgroundColor: Colors.accentBlue },
  periodBtnText: { color: Colors.textSecondary, fontSize: FontSize.xs, fontWeight: '600' },
  periodBtnTextActive: { color: Colors.white },
  datePickerOuter: { marginBottom: Spacing.md },
  datePicker: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'center', 
    gap: Spacing.md,
    flexWrap: 'nowrap'
  },
  dateValue: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  typeSwitcher: { flexDirection: 'row', backgroundColor: Colors.bgSecondary, borderRadius: BorderRadius.md, padding: 4, marginBottom: Spacing.lg },
  typeBtn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: BorderRadius.md },
  typeBtnActiveExpense: { backgroundColor: Colors.accentExpense },
  typeBtnActiveIncome: { backgroundColor: Colors.accentIncome },
  typeBtnText: { color: Colors.textTertiary, fontSize: 10, fontWeight: '800' },
  typeBtnTextActive: { color: Colors.white },
  chartBox: { minHeight: 260, justifyContent: 'center', alignItems: 'center', marginBottom: Spacing.lg },
  chartInner: { alignItems: 'center', justifyContent: 'center' },
  centerContainer: {
    width: 140,
    height: 140,
    borderRadius: 70,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
  },
  tooltipInner: {
    alignItems: 'center',
    padding: 10,
  },
  tooltipName: {
    fontSize: 10,
    color: Colors.textSecondary,
    marginBottom: 4,
    fontWeight: '600',
  },
  tooltipVal: {
    fontSize: 15,
    fontWeight: '800',
    marginBottom: 2,
  },
  tooltipPercent: {
    fontSize: 10,
    color: Colors.accentBlue,
    fontWeight: '700',
  },
  emptyText: { color: Colors.textTertiary, fontSize: FontSize.sm },
  sectionTitle: { fontSize: FontSize.xl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  catItem: { marginBottom: 6 },
  catRow: { flexDirection: 'row', alignItems: 'center' },
  catColor: { width: 10, height: 10, borderRadius: 5, marginRight: 12 },
  catInfo: { flex: 1 },
  catName: { fontSize: FontSize.md, color: Colors.textPrimary, fontWeight: '600' },
  catPercent: { fontSize: FontSize.xs, color: Colors.textTertiary },
  catAmount: { fontSize: FontSize.md, fontWeight: '600' },
});
