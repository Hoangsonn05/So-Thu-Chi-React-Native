import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Ionicons } from '@expo/vector-icons';
import { EXPENSE_CATEGORIES, INCOME_CATEGORIES } from '../../config/categories';
import NetInfo from '@react-native-community/netinfo';
import { syncService } from '../../services/FirebaseSyncService';
import UniversalDatePicker from '../../components/UniversalDatePicker';
import { firebaseAuth } from '../../config/firebase';
import { transactionEvents } from '../../services/TransactionEvents';

function formatDate(date: Date): string {
  const days = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];
  const day = String(date.getDate()).padStart(2, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const year = date.getFullYear();
  const dayOfWeek = days[date.getDay()];
  return `${day}/${month}/${year} (${dayOfWeek})`;
}

export default function ExpenseScreen() {
  const [isExpense, setIsExpense] = useState(true);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPickerVisible, setIsPickerVisible] = useState(false);

  const activeCategories = isExpense ? EXPENSE_CATEGORIES : INCOME_CATEGORIES;
  const dateStr = formatDate(currentDate);

  const handlePrevDate = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() - 1);
    setCurrentDate(d);
  };

  const handleNextDate = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() + 1);
    setCurrentDate(d);
  };

  const handleSubmit = async () => {
    if (!selectedCategory || !amount.trim() || amount.trim() === '0') {
      Alert.alert('Thông báo', 'Vui lòng nhập đầy đủ thông tin!');
      return;
    }

    setIsSubmitting(true);
    try {
      const amountNum = parseInt(amount, 10);
      const dateClean = dateStr.split(' ')[0];
      const type = isExpense ? 0 : 1;

      const localId = await db.addTransaction({
        amount: amountNum,
        note: note.trim() || 'Không có ghi chú',
        category: selectedCategory,
        date: dateClean,
        type,
      });

      if (localId !== -1) {
        // Realtime refresh for all subscribed screens
        transactionEvents.emitChanged();

        // Sync to cloud
        const netInfo = await NetInfo.fetch();
        const user = firebaseAuth().currentUser;

        if (user && netInfo.isConnected && netInfo.isInternetReachable !== false) {
          // Push immediately with 'legacy' prefix
          const allTransactions = await db.getAllTransactions();
          const newTx = allTransactions.find(t => t.id === localId);
          if (newTx) {
            syncService.pushSingleTransaction(user.uid, newTx, 'legacy').catch(console.error);
          }
        }

        Alert.alert('Thành công', 'Đã lưu giao dịch');
        setAmount(''); setNote(''); setSelectedCategory('');
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <View className="flex-1 bg-background">
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <Text className="text-3xl font-bold text-white mb-6">Nhập giao dịch</Text>

        <View className="flex-row bg-white/5 rounded-2xl p-1 mb-4">
          <TouchableOpacity
            className={`flex-1 py-2.5 items-center rounded-xl ${isExpense ? 'bg-expense' : ''}`}
            onPress={() => { setIsExpense(true); setSelectedCategory(''); }}
          >
            <Text className={`text-[10px] font-bold ${isExpense ? 'text-white' : 'text-gray-400'}`}>CHI TIÊU</Text>
          </TouchableOpacity>
          <TouchableOpacity
            className={`flex-1 py-2.5 items-center rounded-xl ${!isExpense ? 'bg-income' : ''}`}
            onPress={() => { setIsExpense(false); setSelectedCategory(''); }}
          >
            <Text className={`text-[10px] font-bold ${!isExpense ? 'text-white' : 'text-gray-400'}`}>THU NHẬP</Text>
          </TouchableOpacity>
        </View>

        <GlassBox className="h-[90px] mb-4 justify-center" padding={12} intensity={40}>
          <Text className="text-xs text-gray-400 mb-0.5">Số tiền</Text>
          <View className="flex-row items-center">
            <TextInput
              className={`flex-1 text-3xl font-bold ${isExpense ? 'text-expense' : 'text-income'}`}
              value={amount}
              onChangeText={(text) => { if (/^\d*$/.test(text)) setAmount(text); }}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor="rgba(255,255,255,0.2)"
            />
            <Text className={`text-xl font-semibold ml-2 ${isExpense ? 'text-expense' : 'text-income'}`}>đ</Text>
          </View>
        </GlassBox>

        <View className="flex-row gap-x-4 mb-6">
          <GlassBox className="flex-1 h-[75px]" padding={10} intensity={25}>
            <Text className="text-[10px] text-gray-500 mb-1">Ngày</Text>
            <View className="flex-row items-center justify-center gap-x-2">
              <TouchableOpacity onPress={handlePrevDate}><Ionicons name="chevron-back" size={16} color="#FFF" /></TouchableOpacity>
              <TouchableOpacity onPress={() => setIsPickerVisible(true)}>
                <Text className="text-lg font-bold text-white">{dateStr.split(' ')[0]}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleNextDate}><Ionicons name="chevron-forward" size={16} color="#FFF" /></TouchableOpacity>
            </View>
          </GlassBox>

          <UniversalDatePicker
            isVisible={isPickerVisible}
            currentMonth={currentDate.getMonth() + 1}
            currentYear={currentDate.getFullYear()}
            onClose={() => setIsPickerVisible(false)}
            onSelect={(d, m, y) => {
              setCurrentDate(new Date(y, m - 1, d));
              setIsPickerVisible(false);
            }}
          />

          <GlassBox className="flex-[1.5] h-[75px]" padding={10} intensity={25}>
            <Text className="text-[10px] text-gray-500 mb-1">Ghi chú</Text>
            <TextInput
              className="text-lg p-0"
              style={{ color: '#FFFFFF', paddingVertical: 0 }}
              value={note}
              onChangeText={setNote}
              placeholder="Ghi chú..."
              placeholderTextColor="rgba(255,255,255,0.2)"
              numberOfLines={1}
              underlineColorAndroid="transparent"
            />
          </GlassBox>
        </View>

        <Text className="text-lg font-bold text-white mb-2">Chọn danh mục</Text>

        <View className="flex-row flex-wrap -mx-1">
          {activeCategories.map((category) => (
            <TouchableOpacity
              key={category.name}
              onPress={() => setSelectedCategory(category.name)}
              activeOpacity={0.7}
              className="w-1/4 p-1"
            >
              <View 
                style={[
                  {
                    height: 70,
                    backgroundColor: 'rgba(255,255,255,0.03)',
                    borderRadius: 12,
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderWidth: 1,
                    borderColor: 'transparent'
                  },
                  selectedCategory === category.name && { 
                    borderColor: isExpense ? Colors.accentExpense : Colors.accentIncome,
                  }
                ]}
              >
                <View style={{ width: 40, height: 40, alignItems: 'center', justifyContent: 'center', marginBottom: 2 }}>
                  <Text style={{ fontSize: 24 }}>{category.emoji}</Text>
                </View>
                <Text 
                  style={[
                    { fontSize: 10, textAlign: 'center', color: Colors.textSecondary },
                    selectedCategory === category.name && { color: isExpense ? Colors.accentExpense : Colors.accentIncome, fontWeight: '700' }
                  ]}
                  numberOfLines={1}
                >
                  {category.name}
                </Text>
              </View>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          className={`mt-8 h-12 rounded-full items-center justify-center ${isExpense ? 'bg-expense' : 'bg-income'} ${isSubmitting ? 'opacity-60' : ''}`}
          onPress={handleSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <Text className="text-white text-lg font-bold">
              Lưu {isExpense ? 'chi tiêu' : 'thu nhập'}
            </Text>
          )}
        </TouchableOpacity>

        <View className="h-[100px]" />
      </ScrollView>
    </View>
  );
}
