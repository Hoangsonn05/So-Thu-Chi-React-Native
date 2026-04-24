import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  StatusBar,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors } from '../../theme/colors';
import GlassBox from '../../components/GlassBox';
import { sessionService } from '../../services/SessionService';
import { firebaseAuth } from '../../config/firebase';

interface SessionItemProps {
  session: any;
  isCurrent: boolean;
  onRevoke: () => void;
}

function SessionItem({ session, isCurrent, onRevoke }: SessionItemProps) {
  return (
    <GlassBox className="mb-4" padding={16} intensity={isCurrent ? 30 : 15}>
      <View className="flex-row items-center">
        <View className={`w-10 h-10 rounded-full items-center justify-center mr-3 ${isCurrent ? 'bg-accent/20' : 'bg-white/5'}`}>
          <Ionicons 
            name={Platform.select({ ios: 'logo-apple', android: 'logo-android', default: 'phone-portrait' }) as any} 
            size={20} 
            color={isCurrent ? '#00B0FF' : '#999'} 
          />
        </View>
        <View className="flex-1">
          <Text className="text-base font-bold text-white">{session.deviceName || 'Thiết bị không tên'}</Text>
          <Text className="text-xs text-gray-500 mt-0.5">{session.deviceModel || 'Unknown Model'} • {session.osName} {session.osVersion}</Text>
          {session.lastActive && (
            <Text className="text-[10px] text-accent mt-1">
              Hoạt động: {session.lastActive.toDate ? session.lastActive.toDate().toLocaleString('vi-VN') : 'Vừa xong'}
            </Text>
          )}
        </View>
        {isCurrent ? (
          <View className="bg-income px-2.5 py-1 rounded-full">
            <Text className="text-[10px] font-extrabold text-white">Hiện tại</Text>
          </View>
        ) : (
          <TouchableOpacity className="p-2" onPress={onRevoke}>
            <Ionicons name="trash-outline" size={20} color="#FF5252" />
          </TouchableOpacity>
        )}
      </View>
    </GlassBox>
  );
}

export default function DeviceManagementScreen({ navigation }: any) {
  const [sessions, setSessions] = useState<any[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);

  const fetchSessions = async () => {
    const user = firebaseAuth().currentUser;
    if (!user) return;

    setIsLoading(true);
    try {
      const id = await sessionService.getDeviceId();
      setCurrentDeviceId(id);
      const activeSessions = await sessionService.getActiveSessions(user.uid);
      
      const sorted = activeSessions.sort((a, b) => {
        if (a.deviceId === id) return -1;
        if (b.deviceId === id) return 1;
        return (b.lastActive?.seconds || 0) - (a.lastActive?.seconds || 0);
      });
      
      setSessions(sorted);
    } catch (error) {
      console.error('Error fetching sessions:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleRevoke = (session: any) => {
    Alert.alert(
      'Xác nhận đăng xuất',
      `Bạn có chắc chắn muốn đăng xuất từ xa khỏi thiết bị "${session.deviceName}"? Thiết bị này sẽ bị xóa toàn bộ dữ liệu bộ nhớ đệm.`,
      [
        { text: 'Hủy', style: 'cancel' },
        { 
          text: 'Đăng xuất', 
          style: 'destructive',
          onPress: async () => {
            const user = firebaseAuth().currentUser;
            if (!user) return;
            try {
              await sessionService.revokeSession(user.uid, session.deviceId);
              setSessions(prev => prev.filter(s => s.deviceId !== session.deviceId));
              Alert.alert('Thành công', 'Đã yêu cầu đăng xuất từ xa cho thiết bị.');
            } catch (error) {
              Alert.alert('Lỗi', 'Không thể thực hiện yêu cầu.');
            }
          }
        }
      ]
    );
  };

  return (
    <View className="flex-1 bg-background">
      <StatusBar barStyle="light-content" />
      <View className="flex-row items-center justify-between pt-[50px] px-5 pb-[15px] bg-black/20">
        <TouchableOpacity className="p-2" onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color="#FFF" />
        </TouchableOpacity>
        <Text className="text-lg font-bold text-white">Quản lý đăng nhập</Text>
        <TouchableOpacity className="p-2" onPress={fetchSessions} disabled={isLoading}>
          <Ionicons name="refresh" size={20} color={isLoading ? '#555' : '#00B0FF'} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20 }} showsVerticalScrollIndicator={false}>
        <View className="items-center mb-[30px] px-5">
          <Ionicons name="shield-checkmark-outline" size={40} color="#00E676" className="mb-3" />
          <Text className="text-xl font-bold text-white mb-2">Bảo mật tài khoản</Text>
          <Text className="text-sm text-gray-500 text-center leading-5"> Danh sách các thiết bị hiện đang duy trì phiên đăng nhập vào tài khoản của bạn. Bạn có thể đăng xuất các thiết bị không nhận diện được.</Text>
        </View>

        {isLoading ? (
          <ActivityIndicator size="large" color="#00B0FF" className="mt-10" />
        ) : sessions.length === 0 ? (
          <View className="items-center mt-[60px]">
            <Text className="text-gray-500 text-base">Không tìm thấy phiên hoạt động nào.</Text>
          </View>
        ) : (
          sessions.map(session => (
            <SessionItem 
              key={session.deviceId} 
              session={session} 
              isCurrent={session.deviceId === currentDeviceId}
              onRevoke={() => handleRevoke(session)}
            />
          ))
        )}
        
        <View className="h-[40px]" />
      </ScrollView>
    </View>
  );
}
