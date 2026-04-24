import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  Dimensions,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import SummaryCard from '../../components/SummaryCard';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { Ionicons } from '@expo/vector-icons';
import { LineChart, BarChart } from 'react-native-gifted-charts';
import { getCategoryEmoji } from '../../config/categories';
import { BlurView } from 'expo-blur';
import { CloudOff } from 'lucide-react-native';
import UniversalDatePicker from '../../components/UniversalDatePicker';
import { transactionEvents } from '../../services/TransactionEvents';

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
  const [chartMax, setChartMax] = useState(1000);
  const [chartMin, setChartMin] = useState(0);
  const [avgValue, setAvgValue] = useState(0);
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
      const rawValues = summaries.map(s => s.income - s.expense);
      const absValues = rawValues.map(v => Math.abs(v));
      const maxAbs = Math.max(...absValues, 100000);
      const avg = absValues.reduce((a, b) => a + b, 0) / 7;

      setChartMax(maxAbs * 1.3);
      setChartMin(0); // Always baseline 0 for absolute bar chart
      setAvgValue(avg);

      const formattedChartData = summaries.map((s) => ({
        value: Math.abs(s.income - s.expense),
        realValue: s.income - s.expense,
        label: s.date.split('/')[0],
        fullDate: s.date,
        frontColor: (s.income - s.expense) >= 0 ? '#00B0FF' : '#FF5252',
        barBorderColor: 'white',
        barBorderWidth: 1.5,
        topLabelComponent: () => null,
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

  useEffect(() => {
    const unsubscribe = transactionEvents.subscribe(() => {
      fetchData(selectedMonth, selectedYear);
    });

    return unsubscribe;
  }, [fetchData, selectedMonth, selectedYear]);

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
    <View className="flex-1 bg-background">
      <ScrollView
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }}
        refreshControl={
          <RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor="#FFF" />
        }
      >
        <View className="flex-row justify-between items-center mb-6">
          <View>
            <Text className="text-xs text-gray-400 font-medium">Xin chào,</Text>
            <Text className="text-3xl font-bold text-white">Sổ Thu Chi</Text>
          </View>
        </View>

        <View className="gap-y-4">
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

          <View className="flex-row gap-x-4">
            <GlassBox className="flex-1 h-[90px] justify-between" padding={12}>
              <View className="w-6 h-6 rounded-md bg-income/10 items-center justify-center mb-1">
                <Ionicons name="trending-up" size={14} color="#00E676" />
              </View>
              <Text className="text-xs text-gray-400">Thu nhập</Text>
              <Text className="text-lg font-bold text-income" numberOfLines={1}>
                +{monthlyIncome.toLocaleString()}
              </Text>
            </GlassBox>
            <GlassBox className="flex-1 h-[90px] justify-between" padding={12}>
              <View className="w-6 h-6 rounded-md bg-expense/10 items-center justify-center mb-1">
                <Ionicons name="trending-down" size={14} color="#FF5252" />
              </View>
              <Text className="text-xs text-gray-400">Đã chi</Text>
              <Text className="text-lg font-bold text-expense" numberOfLines={1}>
                -{monthlyExpense.toLocaleString()}
              </Text>
            </GlassBox>
          </View>

          <GlassBox className="h-[200px]" padding={12}>
            <Text className="text-sm font-bold text-white mb-2">Xu hướng 7 ngày</Text>
            <View className="items-center -ml-6">
              {chartData.length > 0 && (
                <BarChart
                  data={chartData}
                  width={width - 80}
                  height={150}
                  noOfSections={4}
                  barWidth={22}
                  spacing={18}
                  roundedTop
                  roundedBottom
                  barBorderWidth={1.5}
                  barBorderColor="white"
                  hideRules
                  xAxisThickness={0}
                  yAxisThickness={0}
                  yAxisLabelWidth={45}
                  maxValue={chartMax}
                  mostNegativeValue={0}
                  showReferenceLine1={true}
                  referenceLine1Position={avgValue}
                  referenceLine1Config={{
                    color: 'rgba(255, 255, 255, 0.5)',
                    thickness: 1,
                    dashWidth: 5,
                    dashGap: 5,
                  }}
                  formatYLabel={(label) => {
                    const val = parseInt(label);
                    if (Math.abs(val) >= 1000000) return `${(val / 1000000).toFixed(1)}M`;
                    if (Math.abs(val) >= 1000) return `${(val / 1000).toFixed(0)}k`;
                    return label;
                  }}
                  yAxisTextStyle={{ color: '#999', fontSize: 9 }}
                  xAxisLabelTextStyle={{ color: '#999', fontSize: 9 }}
                  isAnimated
                  renderTooltip={(item: any) => (
                    <View className="absolute -top-12 -left-10 z-50">
                      <BlurView intensity={90} tint="dark" className="p-2 rounded-xl border-[0.5px] border-white/30 min-w-[95px] items-center">
                        <Text className="text-[10px] text-gray-300 mb-0.5">{item.fullDate}</Text>
                        <Text className={`text-[12px] font-bold ${item.realValue >= 0 ? 'text-income' : 'text-expense'}`}>
                          {item.realValue >= 0 ? '+' : ''}{item.realValue.toLocaleString()}đ
                        </Text>
                      </BlurView>
                    </View>
                  )}
                />
              )}
            </View>
          </GlassBox>

          <View className="flex-row justify-between items-center mt-2 mb-1">
            <Text className="text-xl font-bold text-white">Gần đây (7)</Text>
            <TouchableOpacity onPress={() => navigation.navigate('Calendar')}>
              <Text className="text-xs font-bold text-accent">Tất cả</Text>
            </TouchableOpacity>
          </View>

          {recentTransactions.map((item, index) => (
            <GlassBox key={item.id?.toString() || index.toString()} className="mb-0.5" padding={10} intensity={25}>
              <View className="flex-row items-center">
                <View className="w-9 h-9 items-center justify-center mr-2">
                  <Text className="text-xl">{getCategoryEmoji(item.category)}</Text>
                </View>
                <View className="flex-1">
                  <Text className="text-lg font-bold text-white">{item.category}</Text>
                  <View className="flex-row items-center">
                    <Text className="text-xs text-gray-400">{item.date}</Text>
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
        <View className="h-[100px]" />
      </ScrollView>
    </View>
  );
}
