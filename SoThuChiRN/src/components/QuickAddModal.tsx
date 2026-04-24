import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  Modal,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  Alert,
  ActivityIndicator,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  Dimensions,
  Animated,
  PanResponder,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../theme/colors';
import GlassBox from './GlassBox';
import { EXPENSE_CATEGORIES, INCOME_CATEGORIES } from '../config/categories';
import { db } from '../database/DatabaseHelper';
import { firebaseAuth, firestoreDb } from '../config/firebase';
import { Ionicons } from '@expo/vector-icons';
import NetInfo from '@react-native-community/netinfo';
import { syncService } from '../services/FirebaseSyncService';
import { transactionEvents } from '../services/TransactionEvents';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');
const MIN_SHEET_HEIGHT = SCREEN_HEIGHT * 0.5;
const MAX_SHEET_HEIGHT = SCREEN_HEIGHT * 0.9;

interface QuickAddModalProps {
  visible: boolean;
  date: string; // Format: dd/MM/yyyy
  onClose: () => void;
  onSuccess: () => void;
}

export default function QuickAddModal({ visible, date, onClose, onSuccess }: QuickAddModalProps) {
  const [isExpense, setIsExpense] = useState(true);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Animation & PanResponder
  const translateY = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const currentHeight = useRef(MIN_SHEET_HEIGHT);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, gestureState) => Math.abs(gestureState.dy) > 10,
      onPanResponderMove: (_, gestureState) => {
        // Calculate new position while dragging
        const newTranslateY = (SCREEN_HEIGHT - currentHeight.current) + gestureState.dy;
        // Limit upward drag to MAX_SHEET_HEIGHT
        if (newTranslateY < SCREEN_HEIGHT - MAX_SHEET_HEIGHT) return;
        translateY.setValue(newTranslateY);
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > 100) {
          // Drag down enough to close
          handleClose();
        } else if (gestureState.dy < -50) {
          // Drag up to expand
          expandSheet();
        } else {
          // Reset to current snap point
          snapToHeight(currentHeight.current);
        }
      },
    })
  ).current;

  useEffect(() => {
    if (visible) {
      // Small delay to ensure layout is ready or just start animation
      currentHeight.current = MIN_SHEET_HEIGHT;
      snapToHeight(MIN_SHEET_HEIGHT);
    } else {
      Animated.timing(translateY, {
        toValue: SCREEN_HEIGHT,
        duration: 250,
        useNativeDriver: true,
      }).start();
    }
  }, [visible]);

  const snapToHeight = (h: number) => {
    currentHeight.current = h;
    Animated.spring(translateY, {
      toValue: SCREEN_HEIGHT - h,
      useNativeDriver: true,
      friction: 8,
      tension: 40,
    }).start();
  };

  const expandSheet = () => {
    snapToHeight(MAX_SHEET_HEIGHT);
  };

  const handleClose = () => {
    Animated.timing(translateY, {
      toValue: SCREEN_HEIGHT,
      duration: 200,
      useNativeDriver: true,
    }).start(() => onClose());
  };

  const activeCategories = isExpense ? EXPENSE_CATEGORIES : INCOME_CATEGORIES;

  const handleSave = async () => {
    if (!amount || amount === '0' || !selectedCategory) {
      Alert.alert('Thông báo', 'Vui lòng nhập số tiền và chọn hạng mục');
      return;
    }

    setIsSubmitting(true);
    try {
      const amountNum = parseInt(amount, 10);
      const type = isExpense ? 0 : 1;

      const localId = await db.addTransaction({
        amount: amountNum,
        note: note.trim() || 'Thêm nhanh',
        category: selectedCategory,
        date: date,
        type: type,
      });

      if (localId !== -1) {
        // Realtime refresh for all subscribed screens
        transactionEvents.emitChanged();

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


        resetForm();
        handleClose();
        setTimeout(onSuccess, 300); // Wait for animation
      }
    } catch (e) {
      console.error(e);
      Alert.alert('Lỗi', 'Không thể lưu giao dịch');
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setAmount('');
    setNote('');
    setSelectedCategory('');
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none" // Controlled by Animated
      onRequestClose={handleClose}
    >
      <View style={styles.modalRoot}>
        <Pressable style={styles.overlay} onPress={handleClose} />
        <Animated.View
          style={[styles.animatedContainer, { transform: [{ translateY }] }]}
          {...panResponder.panHandlers}
        >
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.contentWrapper}
          >
            <GlassBox
              padding={Spacing.lg}
              intensity={60}
              style={styles.modalBox}
              borderRadius={BorderRadius.xl}
            >
              {/* Drag Handle */}
              <View style={styles.dragHandleContainer}>
                <View style={styles.dragHandle} />
              </View>

              <View style={styles.header}>
                <Text style={styles.headerTitle}>Thêm nhanh ({date})</Text>
                <TouchableOpacity onPress={handleClose} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                  <Ionicons name="close" size={24} color={Colors.white} />
                </TouchableOpacity>
              </View>

              <ScrollView showsVerticalScrollIndicator={false} bounces={false}>
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

                <View style={styles.amountRow}>
                  <TextInput
                    style={[styles.amountInput, { color: isExpense ? Colors.accentExpense : Colors.accentIncome }]}
                    value={amount}
                    onChangeText={(text) => { if (/^\d*$/.test(text)) setAmount(text); }}
                    keyboardType="numeric"
                    placeholder="0"
                    placeholderTextColor={Colors.placeholder}
                  />
                  <Text style={[styles.currency, { color: isExpense ? Colors.accentExpense : Colors.accentIncome }]}>đ</Text>
                </View>

                <TextInput
                  style={styles.noteInput}
                  value={note}
                  onChangeText={setNote}
                  placeholder="Ghi chú..."
                  placeholderTextColor={Colors.placeholder}
                />

                <Text style={styles.sectionTitle}>Danh mục</Text>
                <View style={styles.categoryGrid}>
                  {activeCategories.map((cat) => (
                    <TouchableOpacity
                      key={cat.name}
                      style={styles.catWrapper}
                      onPress={() => setSelectedCategory(cat.name)}
                    >
                      <View style={[
                        styles.catItem,
                        selectedCategory === cat.name && { borderColor: isExpense ? Colors.accentExpense : Colors.accentIncome, borderWidth: 1 }
                      ]}>
                        <View style={styles.emojiContainer}>
                          <Text style={styles.catEmoji}>{cat.emoji}</Text>
                        </View>
                        <Text
                          style={[styles.catName, selectedCategory === cat.name && { color: isExpense ? Colors.accentExpense : Colors.accentIncome, fontWeight: '700' }]}
                          numberOfLines={1}
                        >
                          {cat.name}
                        </Text>
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>

                <TouchableOpacity
                  style={[
                    styles.saveBtn,
                    { backgroundColor: isExpense ? Colors.accentExpense : Colors.accentIncome },
                    isSubmitting && { opacity: 0.6 }
                  ]}
                  onPress={handleSave}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <ActivityIndicator color={Colors.white} />
                  ) : (
                    <Text style={styles.saveBtnText}>Lưu giao dịch</Text>
                  )}
                </TouchableOpacity>
                <View style={{ height: 40 }} />
              </ScrollView>
            </GlassBox>
          </KeyboardAvoidingView>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalRoot: {
    flex: 1,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  animatedContainer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    // Bottom sheet style
    backgroundColor: 'transparent',
    borderTopLeftRadius: BorderRadius.xl,
    borderTopRightRadius: BorderRadius.xl,
    overflow: 'hidden',
    height: MAX_SHEET_HEIGHT,
  },
  contentWrapper: {
    flex: 1,
    height: '100%',
  },
  modalBox: {
    flex: 1,
    borderBottomLeftRadius: 0,
    borderBottomRightRadius: 0,
  },
  dragHandleContainer: {
    alignItems: 'center',
    paddingVertical: 10,
    marginTop: -5,
  },
  dragHandle: {
    width: 40,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: Spacing.md,
  },
  headerTitle: {
    fontSize: FontSize.lg,
    fontWeight: '700',
    color: Colors.white,
  },
  typeSwitcher: {
    flexDirection: 'row',
    backgroundColor: Colors.bgSecondary,
    borderRadius: BorderRadius.md,
    padding: 2,
    marginBottom: Spacing.lg,
  },
  typeBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: BorderRadius.md,
  },
  typeBtnActiveExpense: { backgroundColor: Colors.accentExpense },
  typeBtnActiveIncome: { backgroundColor: Colors.accentIncome },
  typeBtnText: { fontSize: FontSize.xs, fontWeight: '700', color: Colors.textTertiary },
  typeBtnTextActive: { color: Colors.white },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    marginBottom: Spacing.md,
  },
  amountInput: {
    fontSize: 40,
    fontWeight: '700',
    textAlign: 'center',
    minWidth: 100,
  },
  currency: {
    fontSize: 20,
    fontWeight: '600',
    marginLeft: 4,
  },
  noteInput: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: BorderRadius.sm,
    padding: Spacing.md,
    color: Colors.white,
    fontSize: FontSize.md,
    marginBottom: Spacing.lg,
  },
  sectionTitle: {
    fontSize: FontSize.sm,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.md,
  },
  categoryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -4,
    marginBottom: Spacing.lg,
  },
  catWrapper: {
    width: '25%',
    padding: 4,
  },
  catItem: {
    height: 70,
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderRadius: BorderRadius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emojiContainer: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  catEmoji: {
    fontSize: 20,
  },
  catName: {
    fontSize: 10,
    color: Colors.textSecondary,
    textAlign: 'center',
  },
  saveBtn: {
    height: 50,
    borderRadius: BorderRadius.pill,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: Spacing.sm,
  },
  saveBtnText: {
    color: Colors.white,
    fontSize: FontSize.lg,
    fontWeight: '700',
  },
});
