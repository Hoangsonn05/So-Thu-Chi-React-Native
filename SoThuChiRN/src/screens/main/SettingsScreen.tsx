/**
 * SettingsScreen.tsx
 * Re-scaled Compact UI
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  TextInput,
} from 'react-native';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { firebaseAuth, firestoreDb } from '../../config/firebase';
import { Ionicons } from '@expo/vector-icons';
import { syncService } from '../../services/FirebaseSyncService';
import { exportService } from '../../services/ExportService';

interface SettingsItemProps {
  icon: any;
  title: string;
  onPress: () => void;
  textColor?: string;
  iconColor?: string;
}

function SettingsItem({
  icon,
  title,
  onPress,
  textColor = Colors.textPrimary,
  iconColor = Colors.accentBlue,
}: SettingsItemProps) {
  return (
    <TouchableOpacity style={styles.settingsItem} onPress={onPress} activeOpacity={0.6}>
      <View style={styles.settingsIcon}>
        <Ionicons name={icon} size={18} color={iconColor} />
      </View>
      <Text style={[styles.settingsTitle, { color: textColor }]}>{title}</Text>
      <Ionicons name="chevron-forward" size={16} color={Colors.textTertiary} />
    </TouchableOpacity>
  );
}

export default function SettingsScreen({ navigation }: any) {
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');

  useEffect(() => {
    (async () => {
      const user = await db.getLocalUser();
      if (user) {
        setUserName(user.fullName || '');
        setUserEmail(user.email || '');
        setEditName(user.fullName || '');
      }
    })();
  }, []);

  const handleToggleEditName = async () => {
    if (isEditingName) {
      if (!editName.trim()) {
        Alert.alert('Lỗi', 'Tên không được để trống');
        return;
      }

      try {
        const user = await db.getLocalUser();
        await db.saveUserLocal(
          editName.trim(),
          user?.email || null,
          user?.phone || null,
          user?.password || null
        );

        const currentUser = firebaseAuth().currentUser;
        if (currentUser) {
          await currentUser.updateProfile({ displayName: editName.trim() });
          await firestoreDb().collection('users').doc(currentUser.uid).set({
            fullName: editName.trim(),
            updatedAt: firestoreDb.FieldValue.serverTimestamp(),
          }, { merge: true });
        }

        setUserName(editName.trim());
        setIsEditingName(false);
        Alert.alert('Thành công', 'Đã cập nhật tên người dùng');
      } catch (e) {
        Alert.alert('Lỗi', 'Không thể cập nhật tên');
        console.error(e);
      }
    } else {
      setEditName(userName);
      setIsEditingName(true);
    }
  };

  const handleSyncData = async () => {
    try {
      const user = firebaseAuth().currentUser;
      if (!user) { Alert.alert('Lỗi', 'Chưa đăng nhập'); return; }
      Alert.alert('Đang xử lý', 'Đang đẩy dữ liệu lên Cloud...');
      await syncService.pushTransactions(user.uid);
      Alert.alert('Thành công', 'Đã đồng bộ dữ liệu lên Cloud');
    } catch (e) {
      Alert.alert('Lỗi', 'Đồng bộ thất bại');
    }
  };

  const handlePullSync = async () => {
    try {
      const user = firebaseAuth().currentUser;
      if (!user) { Alert.alert('Lỗi', 'Chưa đăng nhập'); return; }
      Alert.alert('Đang xử lý', 'Đang tải dữ liệu từ Cloud...');
      await syncService.pullTransactions(user.uid);
      Alert.alert('Thành công', 'Đã tải dữ liệu từ Cloud');
    } catch (e) {
      Alert.alert('Lỗi', 'Tải dữ liệu thất bại');
    }
  };

  const handleLogout = () => {
    Alert.alert('Đăng xuất', 'Xác nhận đăng xuất? Dữ liệu cục bộ sẽ được xóa sạch để bảo mật.', [
      { text: 'Hủy', style: 'cancel' },
      {
        text: 'Đăng xuất',
        style: 'destructive',
        onPress: async () => {
          try {
            await db.clearAllData();
            await firebaseAuth().signOut();
          } catch (e) {
            console.error('Logout error:', e);
            await firebaseAuth().signOut();
          }
        }
      },
    ]);
  };

  const handleExportExcel = async () => {
    try {
      const user = firebaseAuth().currentUser;
      if (!user) {
        Alert.alert('Lỗi', 'Chưa đăng nhập để gửi báo cáo');
        return;
      }

      if (!userEmail) {
        Alert.alert('Lỗi', 'Không tìm thấy địa chỉ Email người dùng');
        return;
      }

      Alert.alert('Đang xử lý', 'Đang gửi yêu cầu báo cáo tới Server...');

      const result = await exportService.triggerEmailReport(user.uid, userEmail);

      if (result.success) {
        Alert.alert('Thành công', result.message);
      } else {
        Alert.alert('Lỗi', result.message);
      }
    } catch (error) {
      Alert.alert('Lỗi', 'Đã xảy ra lỗi không xác định khi gửi báo cáo');
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Tài khoản</Text>

        <TouchableOpacity
          activeOpacity={0.8}
          onPress={() => !isEditingName && handleToggleEditName()}
        >
          <GlassBox style={styles.profileCard} padding={12} intensity={40}>
            <View style={styles.avatar}>
              <Ionicons name="person" size={24} color={Colors.white} />
            </View>
            <View style={styles.profileInfo}>
              {isEditingName ? (
                <View style={styles.editInputContainer}>
                  <Text style={styles.editLabel}>Đổi tên:</Text>
                  <View style={styles.inputWrapper}>
                    <Text style={styles.prefix}>👤</Text>
                    <TextInput
                      style={styles.nameInput}
                      value={editName}
                      onChangeText={setEditName}
                      autoFocus
                      placeholder="Nhập tên mới..."
                      placeholderTextColor={Colors.textTertiary}
                    />
                  </View>
                </View>
              ) : (
                <>
                  <Text style={styles.profileName}>{userName || 'Người dùng'}</Text>
                  <Text style={styles.profileEmail}>{userEmail || 'React Native User'}</Text>
                </>
              )}
            </View>
            <TouchableOpacity style={styles.editBtn} onPress={handleToggleEditName}>
              <Ionicons
                name={isEditingName ? "checkmark-circle" : "create-outline"}
                size={isEditingName ? 24 : 18}
                color={isEditingName ? Colors.accentIncome : Colors.accentBlue}
              />
            </TouchableOpacity>
          </GlassBox>
        </TouchableOpacity>

        <Text style={styles.sectionTitle}>Đồng bộ & Lưu trữ</Text>
        <GlassBox style={styles.groupCard} padding={4} intensity={20}>
          <SettingsItem icon="cloud-upload-outline" title="Đẩy dữ liệu lên Cloud" onPress={handleSyncData} />
          <View style={styles.divider} />
          <SettingsItem icon="cloud-download-outline" title="Tải dữ liệu từ Cloud" onPress={handlePullSync} />
        </GlassBox>

        <Text style={styles.sectionTitle}>Công cụ</Text>
        <GlassBox style={styles.groupCard} padding={4} intensity={20}>
          <SettingsItem icon="search-outline" title="Tìm kiếm giao dịch" onPress={() => navigation.navigate('Search')} />
          <View style={styles.divider} />
          <SettingsItem icon="pie-chart-outline" title="Báo cáo toàn kì" onPress={() => navigation.navigate('AllTimeReport')} />
          <View style={styles.divider} />
          <SettingsItem icon="calendar-outline" title="Báo cáo trong năm" onPress={() => navigation.navigate('YearlyReport')} />
          <View style={styles.divider} />
          <SettingsItem icon="phone-portrait-outline" title="Quản lý thiết bị đăng nhập" onPress={() => navigation.navigate('DeviceManager')} />
          <View style={styles.divider} />
          <SettingsItem icon="document-text-outline" title="Xuất báo cáo PDF/Excel" onPress={handleExportExcel} />
        </GlassBox>

        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <GlassBox padding={10} intensity={15}>
            <View style={styles.logoutContent}>
              <Ionicons name="log-out-outline" size={20} color={Colors.accentExpense} />
              <Text style={styles.logoutText}>Đăng xuất</Text>
            </View>
          </GlassBox>
        </TouchableOpacity>

        <View style={{ height: 120 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  scrollContent: { paddingHorizontal: Spacing.xl, paddingTop: 50 },
  title: { fontSize: FontSize.xxxl, fontWeight: '600', color: Colors.textPrimary, marginBottom: Spacing.lg },
  profileCard: { flexDirection: 'row', alignItems: 'center', marginBottom: Spacing.lg },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: 'rgba(255, 255, 255, 0.1)', alignItems: 'center', justifyContent: 'center', marginRight: 12, borderWidth: 0.5, borderColor: Colors.glassBorder },
  profileInfo: { flex: 1 },
  profileName: { fontSize: FontSize.lg, fontWeight: '600', color: Colors.textPrimary },
  profileEmail: { fontSize: FontSize.xs, color: Colors.textTertiary },
  editBtn: { padding: 5 },
  sectionTitle: { fontSize: FontSize.sm, fontWeight: '600', color: Colors.textTertiary, marginBottom: 6, marginLeft: 4 },
  groupCard: { marginBottom: Spacing.lg },
  settingsItem: { flexDirection: 'row', alignItems: 'center', padding: 12 },
  settingsIcon: { width: 32, height: 32, borderRadius: 8, backgroundColor: 'rgba(255, 255, 255, 0.05)', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  settingsTitle: { flex: 1, fontSize: FontSize.md, fontWeight: '500' },
  divider: { height: 1, backgroundColor: Colors.glassBorder, marginHorizontal: 12 },
  logoutBtn: { marginTop: Spacing.md },
  logoutContent: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  logoutText: { color: Colors.accentExpense, fontSize: FontSize.md, fontWeight: '600' },
  editInputContainer: { flex: 1, marginRight: 8 },
  editLabel: { fontSize: 10, color: Colors.textTertiary, marginBottom: 2 },
  inputWrapper: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 8, paddingHorizontal: 8, height: 36 },
  prefix: { marginRight: 4, fontSize: 12 },
  nameInput: { flex: 1, color: Colors.textPrimary, fontSize: FontSize.md, paddingVertical: 0 },
});
