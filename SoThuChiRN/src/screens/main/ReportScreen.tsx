import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Dimensions,
  ActivityIndicator,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { PieChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { PanResponder, Animated, Easing } from 'react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';
import { transactionEvents } from '../../services/TransactionEvents';

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

export default function ReportScreen() {
  const [period, setPeriod] = useState(0);
  const [type, setType] = useState(0);
  const [month, setMonth] = useState(new Date().getMonth() + 1);
  const [year, setYear] = useState(new Date().getFullYear());
  const [totalIncome, setTotalIncome] = useState(0);
  const [totalExpense, setTotalExpense] = useState(0);
  const [categories, setCategories] = useState<ReportCategory[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<ReportCategory | null>(null);
  const [isPickerVisible, setIsPickerVisible] = useState(false);
  const [renderChart, setRenderChart] = useState(false);
  const sweepAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.85)).current;
  const [sweepProgress, setSweepProgress] = useState(0);

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

  useEffect(() => {
    if (!isLoading && categories.length > 0) {
      sweepAnim.setValue(0);
      scaleAnim.setValue(0.85);
      setSweepProgress(0);
      setRenderChart(false);

      const timer = setTimeout(() => {
        setRenderChart(true);
      }, 150);
      return () => clearTimeout(timer);
    } else {
      setRenderChart(false);
    }
  }, [isLoading, categories, type, month, year]);

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
            velocity: velocity * 0.5,
            deceleration: 0.998,
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
    setSelectedCategory(null);
    loadData();
  }, [loadData]);

  useEffect(() => {
    const unsubscribe = transactionEvents.subscribe(() => {
      loadData();
    });

    return unsubscribe;
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

  const pieData = categories.map((cat) => {
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
    <View className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }} showsVerticalScrollIndicator={false}>
        <Text className="text-3xl font-bold text-white mb-6">Báo cáo</Text>

        <View className="flex-row bg-white/5 rounded-2xl p-1 mb-4">
          {[{ id: 0, label: 'Tháng' }, { id: 1, label: 'Năm' }, { id: 2, label: 'Tất cả' }].map(p => (
            <TouchableOpacity
              key={p.id}
              className={`flex-1 h-9 rounded-xl items-center justify-center ${period === p.id ? 'bg-accent' : ''}`}
              onPress={() => setPeriod(p.id)}
            >
              <Text className={`text-xs font-bold ${period === p.id ? 'text-white' : 'text-gray-400'}`}>{p.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {period < 2 && (
          <GlassBox padding={10} intensity={20} className="mb-4">
            <View className="flex-row items-center justify-center gap-x-6">
              <TouchableOpacity onPress={handlePrev} className="p-1">
                <Ionicons name="chevron-back" size={20} color="#FFF" />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setIsPickerVisible(true)}>
                <Text className="text-lg font-bold text-white">{dateText}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleNext} className="p-1">
                <Ionicons name="chevron-forward" size={20} color="#FFF" />
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

        <View className="flex-row bg-white/5 rounded-2xl p-1 mb-6">
          <TouchableOpacity 
            className={`flex-1 py-2 items-center rounded-xl ${type === 0 ? 'bg-expense' : ''}`} 
            onPress={() => setType(0)}
          >
            <Text className={`text-[10px] font-extrabold ${type === 0 ? 'text-white' : 'text-gray-400'}`}>CHI TIÊU</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            className={`flex-1 py-2 items-center rounded-xl ${type === 1 ? 'bg-income' : ''}`} 
            onPress={() => setType(1)}
          >
            <Text className={`text-[10px] font-extrabold ${type === 1 ? 'text-white' : 'text-gray-400'}`}>THU NHẬP</Text>
          </TouchableOpacity>
        </View>

        <GlassBox className="min-h-[260px] justify-center items-center mb-6" padding={12}>
          {isLoading ? (
            <ActivityIndicator color="#00B0FF" />
          ) : categories.length > 0 ? (
            <Animated.View 
              ref={panRef}
              onLayout={onChartLayout}
              style={[
                { 
                  alignItems: 'center', 
                  justifyContent: 'center',
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
                    onPress={(item: any) => {
                      if (selectedCategory?.name === item.categoryName) {
                        setSelectedCategory(null);
                      } else {
                        const fullCat = categories.find(c => c.name === item.categoryName);
                        setSelectedCategory(fullCat || null);
                      }
                    }}
                    centerLabelComponent={() => (
                      <View className="w-[140px] h-[140px] rounded-full items-center justify-center bg-white/5">
                        {selectedCategory ? (
                          <View className="items-center p-2.5">
                            <Text className="text-[10px] text-gray-400 mb-1 font-semibold" numberOfLines={1}>{selectedCategory.name}</Text>
                            <Text className={`text-base font-extrabold mb-0.5 ${type === 0 ? 'text-expense' : 'text-income'}`}>
                              {selectedCategory.amount.toLocaleString()}đ
                            </Text>
                            <Text className="text-[10px] text-accent font-bold">{selectedCategory.percentage.toFixed(1)}%</Text>
                          </View>
                        ) : (
                          <View className="items-center">
                            <Text className="text-[10px] text-gray-500">Tổng</Text>
                            {sweepProgress === 1 && (
                              <Text className="text-sm text-white font-bold">
                                {(type === 0 ? totalExpense : totalIncome).toLocaleString()}đ
                              </Text>
                            )}
                          </View>
                        )}
                      </View>
                    )}
                  />
              ) : (
                <View className="h-[200px] w-[220px] items-center justify-center" />
              )}
            </Animated.View>
          ) : <Text className="text-sm text-gray-500">Chưa có dữ liệu</Text>}
        </GlassBox>

        <Text className="text-xl font-bold text-white mb-3">Phân bổ danh mục</Text>
        {categories.map((cat, idx) => (
          <GlassBox key={idx} className="mb-1.5" padding={10} intensity={10}>
            <View className="flex-row items-center">
              <View className="w-2.5 h-2.5 rounded-full mr-3" style={{ backgroundColor: cat.color }} />
              <View className="flex-1">
                <Text className="text-base text-white font-bold">{cat.name}</Text>
                <Text className="text-xs text-gray-500">{cat.percentage.toFixed(1)}%</Text>
              </View>
              <Text className={`text-base font-bold ${type === 0 ? 'text-expense' : 'text-income'}`}>
                {type === 0 ? '-' : '+'}{cat.amount.toLocaleString()}đ
              </Text>
            </View>
          </GlassBox>
        ))}
        <View className="h-[100px]" />
      </ScrollView>
    </View>
  );
}
