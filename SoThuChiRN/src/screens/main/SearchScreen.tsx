import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { exportService } from '../../services/ExportService';
import { getCategoryEmoji } from '../../config/categories';
import { transactionEvents } from '../../services/TransactionEvents';

export default function SearchScreen({ navigation }: any) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Transaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    handleSearch();
  }, [query]);

  useEffect(() => {
    const unsubscribe = transactionEvents.subscribe(() => {
      handleSearch();
    });

    return unsubscribe;
  }, [query]);

  const handleSearch = async () => {
    setIsLoading(true);
    try {
      if (query.trim().length > 0) {
        const filtered = await db.searchTransactions(query.trim());
        setResults(filtered);
      } else {
        const allTransactions = await db.getAllTransactions();
        setResults(allTransactions);
      }
    } catch (error) {
      console.error('Search error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const totalIncome = results.filter(t => t.type === 1).reduce((sum, t) => sum + t.amount, 0);
  const totalExpense = results.filter(t => t.type === 0).reduce((sum, t) => sum + t.amount, 0);
  const balance = totalIncome - totalExpense;

  const handleExportPDF = async () => {
    if (results.length === 0) return;
    try {
      await exportService.exportToPDF(results, `Ket_Qua_Tim_Kiem_${query}`);
    } catch (error) {
      alert('Không thể xuất PDF');
    }
  };

  return (
    <View className="flex-1 bg-background">
      {/* Header with Back Button */}
      <View className="flex-row items-center justify-between pt-[45px] px-6 mb-2">
        <TouchableOpacity onPress={() => navigation.goBack()} className="p-1">
          <Ionicons name="chevron-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text className="text-lg font-bold text-white">Tìm kiếm</Text>
        {results.length > 0 ? (
          <TouchableOpacity onPress={handleExportPDF} className="p-1">
            <Ionicons name="document-text-outline" size={24} color="#00B0FF" />
          </TouchableOpacity>
        ) : <View className="w-8" />}
      </View>

      {/* Search Input Bar - High Visibility Redesign */}
      <View className="px-6 mb-4">
        <View
          className="h-12 bg-white/10 rounded-2xl flex-row items-center px-4 border border-white/5"
        >
          <TextInput
            className="flex-1 text-base font-medium"
            style={{ color: '#FFFFFF', paddingVertical: 0 }}
            placeholder="Tìm kiếm giao dịch..."
            placeholderTextColor="#666"
            value={query}
            onChangeText={setQuery}
            autoFocus
            cursorColor="#00B0FF"
            selectionColor="rgba(0, 176, 255, 0.3)"
            underlineColorAndroid="transparent"
          />
          {query.length > 0 && (
            <TouchableOpacity onPress={() => setQuery('')} className="p-1">
              <Ionicons name="close-circle" size={20} color="#666" />
            </TouchableOpacity>
          )}
        </View>
      </View>

      {/* Summary Section - 3 Column Layout from Mockup */}
      <View className="px-6 mb-6">
        <View className="flex-row justify-between items-center">
          {/* Income Column */}
          <View className="flex-1 items-center">
            <Text className="text-[11px] text-gray-400 mb-1.5 font-medium">Thu nhập</Text>
            <Text className="text-lg font-bold text-accent" numberOfLines={1}>
              {totalIncome.toLocaleString()}đ
            </Text>
            <View className="w-10 h-[3px] bg-accent rounded-full mt-1.5" />
          </View>

          {/* Spacer */}
          <View className="w-[1px] h-8 bg-white/5" />

          {/* Expense Column */}
          <View className="flex-1 items-center">
            <Text className="text-[11px] text-gray-400 mb-1.5 font-medium">Chi phí</Text>
            <Text className="text-lg font-bold text-expense" numberOfLines={1}>
              {totalExpense.toLocaleString()}đ
            </Text>
            <View className="w-10 h-[3px] bg-expense rounded-full mt-1.5" />
          </View>

          {/* Spacer */}
          <View className="w-[1px] h-8 bg-white/5" />

          {/* Total/Balance Column */}
          <View className="flex-1 items-center">
            <Text className="text-[11px] text-gray-400 mb-1.5 font-medium">Tổng</Text>
            <Text className="text-lg font-bold text-accent" numberOfLines={1}>
              {balance >= 0 ? '+' : ''}{balance.toLocaleString()}đ
            </Text>
            <View className="w-10 h-[3px] bg-accent rounded-full mt-1.5" />
          </View>
        </View>

        {/* Underline separator for the whole section */}
        <View className="w-full h-[1px] bg-white/5 mt-6" />
      </View>

      {/* Results List */}
      {isLoading ? (
        <ActivityIndicator color="#00B0FF" className="mt-10" />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(_, index) => index.toString()}
          contentContainerStyle={{ paddingHorizontal: 24, paddingTop: 6, paddingBottom: 40 }}
          ListEmptyComponent={
            query.length > 0 ? (
              <View className="items-center mt-20">
                <Ionicons name="search-outline" size={48} color="rgba(255,255,255,0.05)" />
                <Text className="text-gray-500 mt-3 text-base">Không tìm thấy kết quả</Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <GlassBox className="mb-2" padding={12} intensity={25}>
              <View className="flex-row items-center justify-between">
                <View className="w-9 h-9 items-center justify-center mr-2">
                  <Text className="text-xl">{getCategoryEmoji(item.category)}</Text>
                </View>
                <View className="flex-1 mr-2">
                  <Text className="text-sm font-bold text-white" numberOfLines={1}>{item.category}</Text>
                  <Text className="text-[10px] text-gray-400 mt-0.5" numberOfLines={1}>{item.note || 'Không có ghi chú'}</Text>
                  <Text className="text-[8px] text-gray-600 mt-0.5">{item.date}</Text>
                </View>
                <Text className={`text-sm font-bold ${item.type === 1 ? 'text-income' : 'text-expense'}`}>
                  {item.type === 1 ? '+' : '-'}{item.amount.toLocaleString()}đ
                </Text>
              </View>
            </GlassBox>
          )}
        />
      )}
    </View>
  );
}
