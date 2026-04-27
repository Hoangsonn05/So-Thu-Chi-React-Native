import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  Alert,
  TextInput,
  Image,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import db from '../../database/DatabaseHelper';
import { firebaseAuth, firestoreDb } from '../../config/firebase';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as FileSystem from 'expo-file-system';
import { syncService } from '../../services/FirebaseSyncService';
import { exportService } from '../../services/ExportService';
import TelegramBotModal from '../../components/TelegramBotModal';

const SettingsItem = ({ icon, title, onPress, iconColor = Colors.accentBlue }: any) => (
  <TouchableOpacity
    className="flex-row items-center justify-between p-4"
    onPress={onPress}
  >
    <View className="flex-row items-center">
      <View className="w-8 h-8 rounded-full bg-white/5 items-center justify-center mr-3">
        <Ionicons name={icon} size={18} color={iconColor} />
      </View>
      <Text className="text-white text-base">{title}</Text>
    </View>
    <Ionicons name="chevron-forward" size={16} color="rgba(255,255,255,0.3)" />
  </TouchableOpacity>
);

export default function SettingsScreen({ navigation }: any) {
  const [userName, setUserName] = useState('');
  const [userEmail, setUserEmail] = useState('');
  const [username, setUsername] = useState(''); // Field Username mới
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');
  const [isTelegramModalVisible, setIsTelegramModalVisible] = useState(false);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  useFocusEffect(
    React.useCallback(() => {
      (async () => {
        const user = await db.getLocalUser();
        if (user) {
          setUserName(user.fullName || '');
          setUserEmail(user.email || '');
          setUsername(user.username || '');
          setEditName(user.fullName || '');
          if ((user as any).photoURL) {
            setAvatarUrl((user as any).photoURL);
          }
        }
      })();
    }, [])
  );

  const handleToggleEditName = async () => {
    if (isEditingName) {
      if (editName.trim().length > 0) {
        try {
          const currentUser = firebaseAuth().currentUser;
          if (currentUser) {
            const newName = editName.trim();
            const uid = currentUser.uid;

            // 1. Cập nhật Firebase Auth Profile
            await currentUser.updateProfile({ displayName: newName });

            // 2. Cập nhật Firestore (để tab Trang Cá Nhân thấy được)
            await firestoreDb().collection('users').doc(uid).set(
              { fullName: newName },
              { merge: true }
            );

            // 3. Cập nhật SQLite local (chỉ cập nhật fullName, giữ các field khác)
            await db.updateUserLocal({ fullName: newName });

            setUserName(newName);
          }
          setIsEditingName(false);
        } catch (error) {
          Alert.alert('Lỗi', 'Không thể cập nhật tên');
        }
      } else {
        setIsEditingName(false);
      }
    } else {
      setIsEditingName(true);
    }
  };

  const handleUpdateAvatar = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    const cameraStatus = await ImagePicker.requestCameraPermissionsAsync();
    
    if (status !== 'granted' || cameraStatus.status !== 'granted') {
      Alert.alert('Quyền truy cập', 'Vui lòng cho phép ứng dụng truy cập thư viện và camera để cập nhật ảnh đại diện.');
      return;
    }

    Alert.alert(
      'Cập nhật ảnh đại diện',
      'Chọn phương thức bạn muốn sử dụng:',
      [
        { text: 'Chụp ảnh mới', onPress: () => pickImage(true) },
        { text: 'Chọn từ thư viện', onPress: () => pickImage(false) },
        { text: 'Hủy', style: 'cancel' }
      ]
    );
  };

  const pickImage = async (useCamera: boolean) => {
    try {
      let result;
      if (useCamera) {
        result = await ImagePicker.launchCameraAsync({
          allowsEditing: true,
          aspect: [1, 1],
          quality: 0.7,
        });
      } else {
        result = await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ImagePicker.MediaTypeOptions.Images,
          allowsEditing: true,
          aspect: [1, 1],
          quality: 0.7,
        });
      }

      if (!result.canceled && result.assets && result.assets[0].uri) {
        saveAvatarLocal(result.assets[0].uri);
      }
    } catch (error) {
      Alert.alert('Lỗi', 'Không thể mở trình chọn ảnh');
    }
  };

  const saveAvatarLocal = async (uri: string) => {
    setIsUploading(true);
    try {
      const user = firebaseAuth().currentUser;
      if (!user) return;

      const filename = `avatar_${user.uid}_${Date.now()}.jpg`;
      const localUri = `${FileSystem.documentDirectory}${filename}`;
      
      await FileSystem.copyAsync({
        from: uri,
        to: localUri
      });
      
      await db.saveUserLocal(userName, userEmail, null, null, null, localUri);
      
      setAvatarUrl(localUri);
      Alert.alert('Thành công', 'Ảnh đại diện đã được lưu cục bộ trên thiết bị');
    } catch (error: any) {
      console.error('Save error:', error);
      Alert.alert('Lỗi', 'Không thể lưu ảnh đại diện');
    } finally {
      setIsUploading(false);
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
          <GlassBox className="mb-6" padding={12} intensity={40}>
            <View style={{ flexDirection: 'row', alignItems: 'center', width: '100%' }}>
              <TouchableOpacity 
                className="w-12 h-12 rounded-full bg-white/10 items-center justify-center mr-3 border-[0.5px] border-white/20 overflow-hidden"
                onPress={handleUpdateAvatar}
                disabled={isUploading}
              >
                {isUploading ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : avatarUrl ? (
                  <Image source={{ uri: avatarUrl }} style={{ width: '100%', height: '100%' }} />
                ) : (
                  <Ionicons name="person" size={24} color="#FFF" />
                )}
              </TouchableOpacity>
              <View style={{ flex: 1 }}>
                {isEditingName ? (
                  <View style={{ marginRight: 8 }}>
                    <Text className="text-[10px] text-gray-400 mb-1">Đổi tên:</Text>
                    <View className="flex-row items-center bg-white/10 rounded-xl px-3 h-10 border border-white/10">
                      <Text className="mr-2 text-xs">👤</Text>
                      <TextInput
                        className="flex-1 text-base p-0"
                        style={{ color: '#FFFFFF', height: '100%', minWidth: 100 }}
                        value={editName}
                        onChangeText={setEditName}
                        autoFocus
                        placeholder="Nhập tên mới..."
                        placeholderTextColor="#666"
                        underlineColorAndroid="transparent"
                      />
                    </View>
                  </View>
                ) : (
                  <View>
                    <Text className="text-lg font-bold text-white">{userName || 'Người dùng'}</Text>
                    <TouchableOpacity onPress={() => navigation.navigate('ProfileDetail')}>
                      <Text 
                        className="text-xs" 
                        style={{ color: Colors.accentBlue, fontWeight: 'bold', textDecorationLine: 'underline', marginTop: 2 }}
                      >
                        {username ? `@${username}` : 'Trang Cá Nhân'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
              <TouchableOpacity className="p-2" onPress={handleToggleEditName}>
                <Ionicons
                  name={isEditingName ? "checkmark-circle" : "create-outline"}
                  size={isEditingName ? 26 : 18}
                  color={isEditingName ? '#00E676' : '#00B0FF'}
                />
              </TouchableOpacity>
            </View>
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
          <SettingsItem icon="pie-chart-outline" title="Báo cáo toàn kỳ" onPress={() => navigation.navigate('AllTimeReport')} />
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
