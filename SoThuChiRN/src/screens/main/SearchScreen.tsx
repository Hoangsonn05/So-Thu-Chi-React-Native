/**
 * SearchScreen.tsx
 * Real-time transaction search with Glassmorphism UI and PDF Export.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Transaction } from '../../models/Transaction';
import { exportService } from '../../services/ExportService';

export default function SearchScreen({ navigation }: any) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Transaction[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    handleSearch();
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
    <View style={styles.container}>
      {/* Header with Back Button */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>Tìm kiếm</Text>
        {results.length > 0 && (
          <TouchableOpacity onPress={handleExportPDF} style={styles.exportBtn}>
            <Ionicons name="document-text-outline" size={24} color={Colors.accentBlue} />
          </TouchableOpacity>
        )}
      </View>

      {/* Search Input */}
      <View style={styles.searchWrapper}>
        <GlassBox style={styles.searchBox} padding={0} intensity={30}>
          <View style={styles.inputInner}>
            <Ionicons name="search" size={18} color={Colors.textTertiary} style={styles.searchIcon} />
            <TextInput
              style={styles.input}
              placeholder="Tìm ghi chú, hạng mục..."
              placeholderTextColor={Colors.textTertiary}
              value={query}
              onChangeText={setQuery}
              autoFocus
              selectionColor={Colors.accentBlue}
            />
            {query.length > 0 && (
              <TouchableOpacity onPress={() => setQuery('')} style={styles.clearBtn}>
                <Ionicons name="close-circle" size={16} color={Colors.textTertiary} />
              </TouchableOpacity>
            )}
          </View>
        </GlassBox>
      </View>

      {/* Persistent Summary Bar */}
      <View style={styles.summaryWrapper}>
        <GlassBox style={styles.summaryBox} padding={8} intensity={20}>
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Thu nhập</Text>
            <Text style={[styles.summaryValue, { color: Colors.accentIncome }]} numberOfLines={1} adjustsFontSizeToFit>
              +{totalIncome.toLocaleString()}đ
            </Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Chi phí</Text>
            <Text style={[styles.summaryValue, { color: Colors.accentExpense }]} numberOfLines={1} adjustsFontSizeToFit>
              -{totalExpense.toLocaleString()}đ
            </Text>
          </View>
          <View style={styles.summaryDivider} />
          <View style={styles.summaryItem}>
            <Text style={styles.summaryLabel}>Số dư</Text>
            <Text style={[styles.summaryValue, { color: Colors.textPrimary }]} numberOfLines={1} adjustsFontSizeToFit>
              {balance.toLocaleString()}đ
            </Text>
          </View>
        </GlassBox>
      </View>

      {/* Results List */}
      {isLoading ? (
        <ActivityIndicator color={Colors.accentBlue} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={results}
          keyExtractor={(_, index) => index.toString()}
          contentContainerStyle={styles.listContent}
          ListEmptyComponent={
            query.length > 0 ? (
              <View style={styles.emptyContainer}>
                <Ionicons name="search-outline" size={48} color={Colors.glassBorder} />
                <Text style={styles.emptyText}>Không tìm thấy kết quả</Text>
              </View>
            ) : null
          }
          renderItem={({ item }) => (
            <GlassBox style={styles.transactionItem} padding={12} intensity={20}>
              <View style={styles.txRow}>
                <View style={[styles.categoryIcon, { backgroundColor: item.type === 1 ? 'rgba(0, 230, 118, 0.1)' : 'rgba(255, 82, 82, 0.1)' }]}>
                  <Text style={{ fontSize: 16 }}>{item.category.split(' ')[0]}</Text>
                </View>
                <View style={styles.txInfo}>
                  <Text style={styles.txCategory} numberOfLines={1}>{item.category}</Text>
                  <Text style={styles.txNote} numberOfLines={1}>{item.note || 'Không có ghi chú'}</Text>
                  <Text style={styles.txDate}>{item.date}</Text>
                </View>
                <Text style={[styles.txAmount, { color: item.type === 1 ? Colors.accentIncome : Colors.accentExpense }]}>
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

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 45,
    paddingHorizontal: Spacing.xl,
    marginBottom: Spacing.sm,
    justifyContent: 'space-between',
  },
  backBtn: { padding: 4 },
  title: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  exportBtn: { padding: 4 },
  searchWrapper: { paddingHorizontal: Spacing.xl, marginBottom: Spacing.sm },
  searchBox: { height: 40, borderRadius: 10, overflow: 'hidden' },
  inputInner: { flex: 1, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10 },
  searchIcon: { marginRight: 6 },
  input: { flex: 1, color: Colors.textPrimary, fontSize: FontSize.sm, paddingVertical: 0 },
  clearBtn: { padding: 4 },
  summaryWrapper: { paddingHorizontal: Spacing.xl, marginBottom: Spacing.md },
  summaryBox: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  summaryItem: { flex: 1, alignItems: 'center' },
  summaryLabel: { fontSize: 9, color: Colors.textTertiary, textTransform: 'uppercase', marginBottom: 2 },
  summaryValue: { fontSize: FontSize.sm, fontWeight: '700' },
  summaryDivider: { width: 1, height: 15, backgroundColor: 'rgba(255, 255, 255, 0.1)' },
  listContent: { paddingHorizontal: Spacing.xl, paddingTop: 6, paddingBottom: 40 },
  transactionItem: { marginBottom: Spacing.xs },
  txRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  categoryIcon: { width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  txInfo: { flex: 1, marginRight: 8, flexShrink: 1 },
  txCategory: { fontSize: FontSize.xs, fontWeight: '600', color: Colors.textPrimary },
  txNote: { fontSize: 10, color: Colors.textSecondary, marginTop: 1 },
  txDate: { fontSize: 8, color: Colors.textTertiary, marginTop: 1 },
  txAmount: { fontSize: FontSize.sm, fontWeight: '700', flexShrink: 0, textAlign: 'right' },
  emptyContainer: { alignItems: 'center', marginTop: 100 },
  emptyText: { color: Colors.textTertiary, marginTop: 12, fontSize: FontSize.md },
});
