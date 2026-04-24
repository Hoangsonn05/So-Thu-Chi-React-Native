import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Alert,
  TextInput,
} from 'react-native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { firebaseAuth, firestoreDb } from '../../config/firebase';
import { Ionicons } from '@expo/vector-icons';
import { syncService } from '../../services/FirebaseSyncService';
import { exportService } from '../../services/ExportService';
import TelegramBotModal from '../../components/TelegramBotModal';

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
  textColor = 'text-white',
  iconColor = '#00B0FF',
}: SettingsItemProps) {
  return (
    <TouchableOpacity className="flex-row items-center p-3" onPress={onPress} activeOpacity={0.6}>
      <View className="w-8 h-8 rounded-lg bg-white/5 items-center justify-center mr-3">
        <Ionicons name={icon} size={18} color={iconColor} />
      </View>
      <Text className={`flex-1 text-base font-medium ${textColor}`}>{title}</Text>
      <Ionicons name="chevron-forward" size={16} color="#999" />
    </TouchableOpacity>
  );
}

export default function SettingsScreen({ navigation }: any) {
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');
  const [isTelegramModalVisible, setIsTelegramModalVisible] = useState(false);

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
    <View className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 50 }} showsVerticalScrollIndicator={false}>
        <Text className="text-3xl font-bold text-white mb-6">Tài khoản</Text>

        <TouchableOpacity
          activeOpacity={0.8}
          onPress={() => !isEditingName && handleToggleEditName()}
        >
          <GlassBox className="flex-row items-center mb-6" padding={12} intensity={40}>
            <View className="w-12 h-12 rounded-full bg-white/10 items-center justify-center mr-3 border-[0.5px] border-white/20">
              <Ionicons name="person" size={24} color="#FFF" />
            </View>
            <View className="flex-1">
              {isEditingName ? (
                <View className="flex-1 mr-2">
                  <Text className="text-[10px] text-gray-500 mb-0.5">Đổi tên:</Text>
                  <View className="flex-row items-center bg-white/5 rounded-lg px-2 h-9">
                    <Text className="mr-1 text-xs">👤</Text>
                    <TextInput
                      className="flex-1 text-base p-0"
                      style={{ color: '#FFFFFF', paddingVertical: 0 }}
                      value={editName}
                      onChangeText={setEditName}
                      autoFocus
                      placeholder="Nhập tên mới..."
                      placeholderTextColor="#999"
                      underlineColorAndroid="transparent"
                    />
                  </View>
                </View>
              ) : (
                <>
                  <Text className="text-lg font-bold text-white">{userName || 'Người dùng'}</Text>
                  <Text className="text-xs text-gray-400">{userEmail || 'React Native User'}</Text>
                </>
              )}
            </View>
            <TouchableOpacity className="p-1" onPress={handleToggleEditName}>
              <Ionicons
                name={isEditingName ? "checkmark-circle" : "create-outline"}
                size={isEditingName ? 24 : 18}
                color={isEditingName ? '#00E676' : '#00B0FF'}
              />
            </TouchableOpacity>
          </GlassBox>
        </TouchableOpacity>

        <Text className="text-[10px] font-bold text-gray-500 mb-1.5 ml-1">ĐỒNG BỘ & LƯU TRỮ</Text>
        <GlassBox className="mb-6" padding={4} intensity={20}>
          <SettingsItem icon="cloud-upload-outline" title="Đẩy dữ liệu lên Cloud" onPress={handleSyncData} />
          <View className="h-[0.5px] bg-white/10 mx-3" />
          <SettingsItem icon="cloud-download-outline" title="Tải dữ liệu từ Cloud" onPress={handlePullSync} />
        </GlassBox>

        <Text className="text-[10px] font-bold text-gray-500 mb-1.5 ml-1">TIỆN ÍCH AI</Text>
        <GlassBox className="mb-6" padding={4} intensity={20}>
          <SettingsItem
            icon="paper-plane-outline"
            title="Kết nối Telegram Bot"
            onPress={() => setIsTelegramModalVisible(true)}
            iconColor="#00B0FF"
          />
        </GlassBox>

        <Text className="text-[10px] font-bold text-gray-500 mb-1.5 ml-1">CÔNG CỤ</Text>
        <GlassBox className="mb-6" padding={4} intensity={20}>
          <SettingsItem icon="search-outline" title="Tìm kiếm giao dịch" onPress={() => navigation.navigate('Search')} />
          <View className="h-[0.5px] bg-white/10 mx-3" />
          <SettingsItem icon="pie-chart-outline" title="Báo cáo toàn kì" onPress={() => navigation.navigate('AllTimeReport')} />
          <View className="h-[0.5px] bg-white/10 mx-3" />
          <SettingsItem icon="calendar-outline" title="Báo cáo trong năm" onPress={() => navigation.navigate('YearlyReport')} />
          <View className="h-[0.5px] bg-white/10 mx-3" />
          <SettingsItem icon="phone-portrait-outline" title="Quản lý thiết bị đăng nhập" onPress={() => navigation.navigate('DeviceManager')} />
          <View className="h-[0.5px] bg-white/10 mx-3" />
          <SettingsItem icon="document-text-outline" title="Xuất báo cáo PDF/Excel" onPress={handleExportExcel} />
        </GlassBox>

        <TouchableOpacity className="mt-4" onPress={handleLogout}>
          <GlassBox padding={10} intensity={15}>
            <View className="flex-row items-center justify-center gap-x-2">
              <Ionicons name="log-out-outline" size={20} color="#FF5252" />
              <Text className="text-expense text-base font-bold">Đăng xuất</Text>
            </View>
          </GlassBox>
        </TouchableOpacity>

        <View className="h-[120px]" />
      </ScrollView>

      <TelegramBotModal
        visible={isTelegramModalVisible}
        onClose={() => setIsTelegramModalVisible(false)}
      />
    </View>
  );
}
