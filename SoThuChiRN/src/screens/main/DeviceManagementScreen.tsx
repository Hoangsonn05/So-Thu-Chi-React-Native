import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  StatusBar,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Colors, Spacing, BorderRadius, FontSize } from '../../theme/colors';
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
    <GlassBox style={styles.sessionCard} padding={16} intensity={isCurrent ? 30 : 15}>
      <View style={styles.sessionHeader}>
        <View style={[styles.iconContainer, isCurrent && styles.currentIconContainer]}>
          <Ionicons 
            name={Platform.select({ ios: 'logo-apple', android: 'logo-android', default: 'phone-portrait' })} 
            size={20} 
            color={isCurrent ? Colors.accentBlue : Colors.textTertiary} 
          />
        </View>
        <View style={styles.sessionInfo}>
          <Text style={styles.deviceName}>{session.deviceName || 'Thiết bị không tên'}</Text>
          <Text style={styles.deviceModel}>{session.deviceModel || 'Unknown Model'} • {session.osName} {session.osVersion}</Text>
          {session.lastActive && (
            <Text style={styles.lastActive}>
              Hoạt động: {session.lastActive.toDate ? session.lastActive.toDate().toLocaleString('vi-VN') : 'Vừa xong'}
            </Text>
          )}
        </View>
        {isCurrent ? (
          <View style={styles.currentBadge}>
            <Text style={styles.currentBadgeText}>Hiện tại</Text>
          </View>
        ) : (
          <TouchableOpacity style={styles.deleteBtn} onPress={onRevoke}>
            <Ionicons name="trash-outline" size={20} color={Colors.accentExpense} />
          </TouchableOpacity>
        )}
      </View>
    </GlassBox>
  );
}

import { Platform } from 'react-native';

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
      
      // Sort: current device first, then by lastActive
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
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />
      <View style={styles.header}>
        <TouchableOpacity style={styles.backBtn} onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={Colors.textPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Quản lý đăng nhập</Text>
        <TouchableOpacity style={styles.refreshBtn} onPress={fetchSessions} disabled={isLoading}>
          <Ionicons name="refresh" size={20} color={isLoading ? Colors.textTertiary : Colors.accentBlue} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.infoSection}>
          <Ionicons name="shield-checkmark-outline" size={40} color={Colors.accentIncome} style={{ marginBottom: 12 }} />
          <Text style={styles.infoTitle}>Bảo mật tài khoản</Text>
          <Text style={styles.infoDesc}> Danh sách các thiết bị hiện đang duy trì phiên đăng nhập vào tài khoản của bạn. Bạn có thể đăng xuất các thiết bị không nhận diện được.</Text>
        </View>

        {isLoading ? (
          <ActivityIndicator size="large" color={Colors.accentBlue} style={{ marginTop: 40 }} />
        ) : sessions.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>Không tìm thấy phiên hoạt động nào.</Text>
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
        
        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 50,
    paddingHorizontal: Spacing.lg,
    paddingBottom: 15,
    backgroundColor: 'rgba(0,0,0,0.2)',
  },
  backBtn: { padding: 8 },
  headerTitle: { fontSize: FontSize.lg, fontWeight: '700', color: Colors.textPrimary },
  refreshBtn: { padding: 8 },
  scrollContent: { padding: Spacing.lg },
  infoSection: { alignItems: 'center', marginBottom: 30, paddingHorizontal: 20 },
  infoTitle: { fontSize: FontSize.xl, fontWeight: '700', color: Colors.textPrimary, marginBottom: 8 },
  infoDesc: { fontSize: FontSize.sm, color: Colors.textTertiary, textAlign: 'center', lineHeight: 20 },
  sessionCard: { marginBottom: Spacing.md },
  sessionHeader: { flexDirection: 'row', alignItems: 'center' },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.05)',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  currentIconContainer: {
    backgroundColor: 'rgba(33, 150, 243, 0.15)',
  },
  sessionInfo: { flex: 1 },
  deviceName: { fontSize: FontSize.md, fontWeight: '600', color: Colors.textPrimary },
  deviceModel: { fontSize: FontSize.xs, color: Colors.textTertiary, marginTop: 2 },
  lastActive: { fontSize: 10, color: Colors.accentBlue, marginTop: 4 },
  deleteBtn: { padding: 8 },
  currentBadge: {
    backgroundColor: Colors.accentIncome,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  currentBadgeText: { fontSize: 10, fontWeight: '700', color: Colors.white },
  emptyState: { alignItems: 'center', marginTop: 60 },
  emptyText: { color: Colors.textTertiary, fontSize: FontSize.md },
});
