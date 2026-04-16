/**
 * UniversalDatePicker.tsx
 * A reusable, premium Glassmorphism date picker modal.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Modal,
  Pressable,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';
import { Colors, BorderRadius, FontSize, Spacing } from '../theme/colors';
import GlassBox from './GlassBox';

interface UniversalDatePickerProps {
  isVisible: boolean;
  currentMonth: number;
  currentYear: number;
  onSelect: (day: number, month: number, year: number) => void;
  onClose: () => void;
}

function getDaysInMonth(month: number, year: number): number {
  return new Date(year, month, 0).getDate();
}

export default function UniversalDatePicker({
  isVisible,
  currentMonth,
  currentYear,
  onSelect,
  onClose,
}: UniversalDatePickerProps) {
  const [pickerMonth, setPickerMonth] = useState(currentMonth);
  const [pickerYear, setPickerYear] = useState(currentYear);

  // Sync state when props change (especially when opening)
  useEffect(() => {
    if (isVisible) {
      setPickerMonth(currentMonth);
      setPickerYear(currentYear);
    }
  }, [isVisible, currentMonth, currentYear]);

  return (
    <Modal visible={isVisible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <BlurView intensity={20} tint="dark" style={StyleSheet.absoluteFill} />
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        
        <GlassBox style={styles.container} padding={20} intensity={60} borderRadius={24}>
          {/* Header with Year Selector */}
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setPickerYear(pickerYear - 1)}>
              <Ionicons name="chevron-back-circle" size={24} color={Colors.textTertiary} />
            </TouchableOpacity>
            <Text style={styles.title}>{pickerYear}</Text>
            <TouchableOpacity onPress={() => setPickerYear(pickerYear + 1)}>
              <Ionicons name="chevron-forward-circle" size={24} color={Colors.textTertiary} />
            </TouchableOpacity>
          </View>

          {/* Months Grid */}
          <View style={styles.monthsGrid}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => (
              <TouchableOpacity 
                key={m} 
                style={[styles.monthItem, pickerMonth === m && styles.monthActive]}
                onPress={() => setPickerMonth(m)}
              >
                <Text style={[styles.monthText, pickerMonth === m && styles.monthTextActive]}>
                  TH {m}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Days Scroll */}
          <View style={styles.daysContainer}>
            <Text style={styles.subTitle}>Chọn ngày nhanh</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} bounces={true}>
              {Array.from({ length: getDaysInMonth(pickerMonth, pickerYear) }, (_, i) => i + 1).map(d => (
                <TouchableOpacity 
                  key={d} 
                  style={styles.dayItem}
                  onPress={() => onSelect(d, pickerMonth, pickerYear)}
                >
                  <Text style={styles.dayText}>{d}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Apply Month Only */}
          <TouchableOpacity 
            style={styles.applyBtn}
            onPress={() => {
              // passing 0 or 1 as day to indicate month-only selection if needed, 
              // but here we just pass 1 as default and let the screen handle it
              onSelect(1, pickerMonth, pickerYear);
            }}
          >
            <Text style={styles.applyBtnText}>Xem cả tháng {pickerMonth}</Text>
          </TouchableOpacity>
        </GlassBox>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  container: { width: '100%', maxWidth: 320, backgroundColor: 'rgba(30, 30, 30, 0.8)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  header: { 
    flexDirection: 'row', 
    justifyContent: 'center', 
    alignItems: 'center', 
    gap: Spacing.xl,
    marginBottom: 20 
  },
  title: { fontSize: FontSize.xxl, fontWeight: '700', color: Colors.white },
  monthsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' },
  monthItem: { width: '30%', paddingVertical: 10, alignItems: 'center', borderRadius: BorderRadius.md, backgroundColor: 'rgba(255,255,255,0.03)' },
  monthActive: { backgroundColor: Colors.accentBlue },
  monthText: { fontSize: 12, fontWeight: '600', color: Colors.textSecondary },
  monthTextActive: { color: Colors.white },
  subTitle: { fontSize: FontSize.xs, color: Colors.textTertiary, marginVertical: 15, fontWeight: '600' },
  daysContainer: { marginBottom: 20 },
  dayItem: { width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.05)', alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  dayText: { color: Colors.white, fontSize: 12, fontWeight: '600' },
  applyBtn: { width: '100%', height: 48, borderRadius: BorderRadius.pill, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center', marginTop: 10 },
  applyBtnText: { color: Colors.white, fontWeight: '700', fontSize: FontSize.md },
});
