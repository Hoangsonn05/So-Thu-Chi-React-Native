import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { Ionicons } from '@expo/vector-icons';
import { EXPENSE_CATEGORIES, INCOME_CATEGORIES, CategoryItem } from '../../config/categories';
import NetInfo from '@react-native-community/netinfo';
import { syncService } from '../../services/FirebaseSyncService';
import UniversalDatePicker from '../../components/UniversalDatePicker';


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
        // Sync to cloud
        const netInfo = await NetInfo.fetch();
        const user = firebaseAuth().currentUser;
        
        if (user && netInfo.isConnected && netInfo.isInternetReachable !== false) {
          // Push immediately with 'legacy' prefix
          const newTx = await db.getAllTransactions().then(txs => txs.find(t => t.id === localId));
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
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.title}>Nhập giao dịch</Text>

        <View style={styles.typeSwitcher}>
          <TouchableOpacity 
            style={[styles.typeBtn, isExpense && styles.typeBtnActiveExpense]}
            onPress={() => { setIsExpense(true); setSelectedCategory(''); }}
          >
            <Text style={[styles.typeBtnText, isExpense && styles.typeBtnTextActive]}>CHI TIÊU</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.typeBtn, !isExpense && styles.typeBtnActiveIncome]}
            onPress={() => { setIsExpense(false); setSelectedCategory(''); }}
          >
            <Text style={[styles.typeBtnText, !isExpense && styles.typeBtnTextActive]}>THU NHẬP</Text>
          </TouchableOpacity>
        </View>

        <GlassBox style={styles.amountBox} padding={12} intensity={40}>
          <Text style={styles.inputLabel}>Số tiền</Text>
          <View style={styles.amountInputRow}>
            <TextInput
              style={[styles.amountInput, { color: isExpense ? Colors.accentExpense : Colors.accentIncome }]}
              value={amount}
              onChangeText={(text) => { if (/^\d*$/.test(text)) setAmount(text); }}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor={Colors.textTertiary}
            />
            <Text style={[styles.currency, { color: isExpense ? Colors.accentExpense : Colors.accentIncome }]}>đ</Text>
          </View>
        </GlassBox>

        <View style={styles.row}>
          <GlassBox style={styles.dateBox} padding={10} intensity={25}>
            <Text style={styles.smallLabel}>Ngày</Text>
            <View style={styles.dateControl}>
              <TouchableOpacity onPress={handlePrevDate}><Ionicons name="chevron-back" size={16} color={Colors.textPrimary} /></TouchableOpacity>
              <TouchableOpacity onPress={() => setIsPickerVisible(true)}>
                <Text style={styles.dateText}>{dateStr.split(' ')[0]}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleNextDate}><Ionicons name="chevron-forward" size={16} color={Colors.textPrimary} /></TouchableOpacity>
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

          <GlassBox style={styles.noteBox} padding={10} intensity={25}>
            <Text style={styles.smallLabel}>Ghi chú</Text>
            <TextInput
              style={styles.noteInput}
              value={note}
              onChangeText={setNote}
              placeholder="Ghi chú..."
              placeholderTextColor={Colors.textTertiary}
              numberOfLines={1}
            />
          </GlassBox>
        </View>

        <Text style={styles.sectionTitle}>Chọn danh mục</Text>
        
        <View style={styles.categoryGrid}>
          {activeCategories.map((category) => (
            <TouchableOpacity
              key={category.name}
              onPress={() => setSelectedCategory(category.name)}
              activeOpacity={0.7}
              style={styles.catWrapper}
            >
              <GlassBox 
                padding={8}
                style={[
                  styles.categoryCard, 
                  selectedCategory === category.name && { borderColor: isExpense ? Colors.accentExpense : Colors.accentIncome, borderWidth: 1 }
                ]}
                intensity={selectedCategory === category.name ? 50 : 20}
              >
                <Text style={styles.categoryEmoji}>{category.emoji}</Text>
                <Text 
                  style={[
                    styles.categoryName,
                    selectedCategory === category.name && { color: isExpense ? Colors.accentExpense : Colors.accentIncome, fontWeight: '600' }
                  ]}
                  numberOfLines={1}
                >
                  {category.name}
                </Text>
              </GlassBox>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity
          style={[
            styles.submitButton, 
            { backgroundColor: isExpense ? Colors.accentExpense : Colors.accentIncome },
            isSubmitting && { opacity: 0.6 }
          ]}
          onPress={handleSubmit}
          disabled={isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator color={Colors.white} />
          ) : (
            <Text style={styles.submitText}>
              Lưu {isExpense ? 'chi tiêu' : 'thu nhập'}
            </Text>
          )}
        </TouchableOpacity>

        <View style={{ height: 100 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  title: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.lg },
  typeSwitcher: {
    flexDirection: 'row',
    backgroundColor: Colors.bgSecondary,
    borderRadius: BorderRadius.md,
    padding: 4,
    marginBottom: Spacing.md,
  },
  typeBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: BorderRadius.md },
  typeBtnActiveExpense: { backgroundColor: Colors.accentExpense },
  typeBtnActiveIncome: { backgroundColor: Colors.accentIncome },
  typeBtnText: { color: Colors.textTertiary, fontSize: FontSize.xs, fontWeight: '700' },
  typeBtnTextActive: { color: Colors.white },
  amountBox: { height: 90, marginBottom: Spacing.md, justifyContent: 'center' },
  inputLabel: { fontSize: FontSize.xs, color: Colors.textSecondary, marginBottom: 2 },
  amountInputRow: { flexDirection: 'row', alignItems: 'center' },
  amountInput: { flex: 1, fontSize: 32, fontWeight: '700', padding: 0 },
  currency: { fontSize: 20, fontWeight: '600', marginLeft: 8 },
  row: { flexDirection: 'row', gap: Spacing.md, marginBottom: Spacing.lg },
  dateBox: { flex: 1, height: 75 },
  noteBox: { flex: 1.5, height: 75 },
  smallLabel: { fontSize: FontSize.xs, color: Colors.textTertiary, marginBottom: 4 },
  dateControl: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: Spacing.sm },
  dateText: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  noteInput: { fontSize: FontSize.lg, color: Colors.textPrimary, padding: 0 },
  sectionTitle: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.sm },
  categoryGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -4 },
  catWrapper: { width: '25%', padding: 4 }, // 4 columns for more density
  categoryCard: { height: 70, alignItems: 'center', justifyContent: 'center' },
  categoryEmoji: { fontSize: 22, marginBottom: 2 },
  categoryName: { fontSize: 10, color: Colors.textSecondary, textAlign: 'center' },
  submitButton: {
    marginTop: Spacing.xl,
    height: 48, // Compact height
    borderRadius: BorderRadius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitText: { color: Colors.white, fontSize: FontSize.lg, fontWeight: '600' },
});
