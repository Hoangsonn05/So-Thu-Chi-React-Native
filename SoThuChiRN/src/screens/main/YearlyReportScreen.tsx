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
import { BarChart } from 'react-native-gifted-charts';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { transactionEvents } from '../../services/TransactionEvents';

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
    const unsubscribe = transactionEvents.subscribe(() => {
      fetchYearlyData();
    });

    return unsubscribe;
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

  const chartData = monthlyBreakdown.map((item) => {
    let value = 0;
    let label = `T${item.month}`;
    let frontColor = '#00B0FF';

    if (activeTab === 0) {
      value = item.expense;
      frontColor = '#FF5252';
    } else if (activeTab === 1) {
      value = item.income;
      frontColor = '#00E676';
    } else {
      value = item.net;
      frontColor = item.net >= 0 ? '#00E676' : '#FF5252';
    }

    return {
      value: value || 1,
      label: label,
      frontColor: frontColor,
      onPress: () => {},
      origValue: value,
    };
  });

  return (
    <View className="flex-1 bg-background">
      <View className="h-[90px] flex-row items-center justify-between px-4 pt-10 z-10">
        <BlurView intensity={80} tint="dark" className="absolute inset-0" />
        <TouchableOpacity className="w-10 h-10 items-center justify-center" onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text className="text-lg font-bold text-white">Báo cáo năm {selectedYear}</Text>
        <View className="w-10" />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }} showsVerticalScrollIndicator={false}>
        <GlassBox padding={12} className="mb-4">
          <View className="flex-row items-center justify-center gap-x-4">
            <TouchableOpacity onPress={() => changeYear(-1)} className="p-2 w-10 items-center">
              <Ionicons name="chevron-back" size={22} color="#FFF" />
            </TouchableOpacity>
            <View className="items-center min-w-[120px]">
              <Text className="text-lg font-bold text-white">Năm {selectedYear}</Text>
              <Text className="text-[10px] text-gray-500 mt-[-2px]">(01/01 - 31/12)</Text>
            </View>
            <TouchableOpacity onPress={() => changeYear(1)} className="p-2 w-10 items-center">
              <Ionicons name="chevron-forward" size={22} color="#FFF" />
            </TouchableOpacity>
          </View>
        </GlassBox>

        <View className="flex-row bg-white/5 rounded-2xl p-1 mb-4">
          {['Chi tiêu', 'Thu nhập', 'Tổng'].map((label, idx) => (
            <TouchableOpacity 
              key={idx}
              className={`flex-1 py-2.5 items-center rounded-xl ${activeTab === idx ? 'bg-white/10' : ''}`} 
              onPress={() => setActiveTab(idx)}
            >
              <Text className={`text-sm ${activeTab === idx ? 'text-white font-bold' : 'text-gray-500'}`}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View className="mb-4">
          {activeTab < 2 ? (
            <View className="flex-row gap-x-4">
              <GlassBox className="flex-1 items-center justify-center" padding={12}>
                <Text className="text-[10px] text-gray-500 mb-1">Tổng {activeTab === 0 ? 'chi' : 'thu'}</Text>
                <Text className={`text-sm font-bold ${activeTab === 0 ? 'text-expense' : 'text-income'}`}>
                  {formatCurrency(activeTab === 0 ? totalExpense : totalIncome)}
                </Text>
              </GlassBox>
              <GlassBox className="flex-1 items-center justify-center" padding={12}>
                <Text className="text-[10px] text-gray-500 mb-1">Trung bình tháng</Text>
                <Text className="text-sm font-bold text-accent">
                  {formatCurrency(avgValue)}
                </Text>
              </GlassBox>
            </View>
          ) : (
            <View className="gap-y-4">
              <View className="flex-row gap-x-4">
                <GlassBox className="flex-1 items-center justify-center" padding={12}>
                  <Text className="text-[10px] text-gray-500 mb-1">Tổng số dư</Text>
                  <Text className={`text-sm font-bold ${totalNet >= 0 ? 'text-income' : 'text-expense'}`}>
                    {formatCurrency(totalNet)}
                  </Text>
                </GlassBox>
                <GlassBox className="flex-1 items-center justify-center" padding={12}>
                  <Text className="text-[10px] text-gray-500 mb-1">Trung bình dư/tháng</Text>
                  <Text className="text-sm font-bold text-accent">
                    {formatCurrency(avgValue)}
                  </Text>
                </GlassBox>
              </View>
              <View className="flex-row gap-x-4">
                <GlassBox className="flex-1 items-center justify-center" padding={12}>
                  <Text className="text-[10px] text-gray-500 mb-1">Tổng thu nhập</Text>
                  <Text className="text-xs font-bold text-income">
                    {formatCurrency(totalIncome)}
                  </Text>
                </GlassBox>
                <GlassBox className="flex-1 items-center justify-center" padding={12}>
                  <Text className="text-[10px] text-gray-500 mb-1">Tổng chi tiêu</Text>
                  <Text className="text-xs font-bold text-expense">
                    {formatCurrency(totalExpense)}
                  </Text>
                </GlassBox>
              </View>
            </View>
          )}
        </View>

        {isLoading ? (
          <View className="h-[300px] justify-center items-center">
            <ActivityIndicator size="large" color="#00B0FF" />
          </View>
        ) : (
          <>
            <GlassBox className="mb-4" padding={16}>
              <Text className="text-sm font-semibold text-gray-400 mb-4">
                Biểu đồ {activeTab === 0 ? 'chi tiêu' : activeTab === 1 ? 'thu nhập' : 'biến động'} tháng
              </Text>
              <View className="items-center ml-[-20px]">
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
                    xAxisLabelTextStyle={{ color: '#999', fontSize: 10 }}
                    yAxisTextStyle={{ color: '#999', fontSize: 10 }}
                    noOfSections={4}
                    maxValue={Math.max(...chartData.map(d => Math.abs(d.origValue))) * 1.2 || 1000}
                    isAnimated
                    animationDuration={1500}
                  />
                )}
              </View>
            </GlassBox>

            <GlassBox className="overflow-hidden" padding={0}>
              <View className="p-3 bg-white/5 border-b border-white/10">
                <Text className="text-xs font-bold text-gray-500">Chi tiết từng tháng</Text>
              </View>
              {monthlyBreakdown.map((item, index) => {
                let displayValue = 0;
                let colorClass = 'text-white';
                if (activeTab === 0) { displayValue = item.expense; colorClass = 'text-expense'; }
                else if (activeTab === 1) { displayValue = item.income; colorClass = 'text-income'; }
                else { displayValue = item.net; colorClass = item.net >= 0 ? 'text-income' : 'text-expense'; }

                return (
                  <View key={index} className={`flex-row justify-between items-center p-3.5 border-b border-white/5 ${index === 11 ? 'border-b-0' : ''}`}>
                    <Text className="text-sm text-white font-medium">Tháng {item.month}</Text>
                    <Text className={`text-sm font-bold ${colorClass}`}>
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

        <View className="h-[60px]" />
      </ScrollView>
    </View>
  );
}
