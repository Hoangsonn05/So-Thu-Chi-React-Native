import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Dimensions,
  ActivityIndicator,
  Animated,
  Easing,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { PieChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
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
    const unsubscribe = transactionEvents.subscribe(() => {
      fetchAllTimeData();
    });

    return unsubscribe;
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

  const totalAmount = categories.reduce((sum, c) => sum + c.amount, 0);
  let currentAccumulated = 0;
  const currentLimit = sweepProgress * totalAmount;

  const animatedPieData = categories.map((cat) => {
    const startValue = currentAccumulated;
    currentAccumulated += cat.amount;
    
    let displayAmount = 0;
    if (currentLimit >= currentAccumulated) {
      displayAmount = cat.amount;
    } else if (currentLimit > startValue) {
      displayAmount = currentLimit - startValue;
    }

    return {
      value: displayAmount || 0.01,
      color: cat.color,
    };
  });

  return (
    <View className="flex-1 bg-background">
      <View className="h-[90px] flex-row items-center justify-between px-4 pt-10 z-10">
        <BlurView intensity={80} tint="dark" className="absolute inset-0" />
        <TouchableOpacity className="w-10 h-10 items-center justify-center" onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text className="text-lg font-bold text-white">Báo cáo toàn kì</Text>
        <View className="w-10" />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }} showsVerticalScrollIndicator={false}>
        <GlassBox className="mb-4" padding={20}>
          <Text className="text-base font-bold text-white mb-3">Tổng kết tài chính</Text>
          <View className="h-[1px] bg-white/10 my-3 opacity-30" />
          <View className="flex-row items-center">
            <View className="flex-1 items-center">
              <Text className="text-[10px] text-gray-500 mb-1">Tổng thu</Text>
              <Text className="text-base font-bold text-income">
                +{formatCurrency(totalIncome)}
              </Text>
            </View>
            <View className="w-[1px] h-8 bg-white/10 opacity-30" />
            <View className="flex-1 items-center">
              <Text className="text-[10px] text-gray-500 mb-1">Tổng chi</Text>
              <Text className="text-base font-bold text-expense">
                -{formatCurrency(totalExpense)}
              </Text>
            </View>
          </View>
          <View className="h-[1px] bg-white/10 my-3 opacity-30" />
          <View className="flex-row justify-between items-center">
            <Text className="text-sm text-gray-400">Số dư thực tế</Text>
            <Text className={`text-2xl font-bold ${balance >= 0 ? 'text-accent' : 'text-expense'}`}>
              {formatCurrency(balance)}
            </Text>
          </View>
        </GlassBox>

        <View className="flex-row bg-white/5 rounded-full p-1 mb-4">
          <TouchableOpacity 
            className={`flex-1 py-2 items-center rounded-full ${activeType === 0 ? 'bg-white/10' : ''}`}
            onPress={() => setActiveType(0)}
          >
            <Text className={`text-sm ${activeType === 0 ? 'text-white font-bold' : 'text-gray-500'}`}>Chi tiêu</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            className={`flex-1 py-2 items-center rounded-full ${activeType === 1 ? 'bg-white/10' : ''}`}
            onPress={() => setActiveType(1)}
          >
            <Text className={`text-sm ${activeType === 1 ? 'text-white font-bold' : 'text-gray-500'}`}>Thu nhập</Text>
          </TouchableOpacity>
        </View>

        {isLoading ? (
          <View className="h-[300px] justify-center items-center">
            <ActivityIndicator size="large" color="#00B0FF" />
          </View>
        ) : categories.length > 0 ? (
          <GlassBox className="mb-4" padding={20}>
            <View className="items-center my-5">
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
                    innerCircleColor="#0A0B1A"
                    centerLabelComponent={() => (
                      <View className="justify-center items-center">
                        <Text className="text-[22px] text-white font-bold">
                          {Math.round(sweepProgress * 100)}%
                        </Text>
                        <Text className="text-[12px] text-gray-500">Tiến độ</Text>
                      </View>
                    )}
                  />
                )}
              </Animated.View>
            </View>

            <View className="mt-2.5">
              {categories.map((item, index) => (
                <View key={index} className="flex-row items-center py-3 border-b border-white/5">
                  <View className="w-2.5 h-2.5 rounded-full mr-3" style={{ backgroundColor: item.color }} />
                  <Text className="flex-1 text-sm text-white font-medium">{item.name}</Text>
                  <View className="items-end">
                    <Text className="text-sm font-bold text-white">{formatCurrency(item.amount)}</Text>
                    <Text className="text-[10px] text-gray-500">{item.percentage.toFixed(1)}%</Text>
                  </View>
                </View>
              ))}
            </View>
          </GlassBox>
        ) : (
          <View className="h-[200px] justify-center items-center">
            <Text className="text-gray-500 text-base font-medium">Không có dữ liệu cho mục này</Text>
          </View>
        )}

        <View className="h-[40px]" />
      </ScrollView>
    </View>
  );
}
