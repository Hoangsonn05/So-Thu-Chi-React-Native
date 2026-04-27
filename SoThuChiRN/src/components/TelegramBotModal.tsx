import React, { useState } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { Colors, BorderRadius, Spacing } from '../theme/colors';
import GlassBox from './GlassBox';
import { firebaseAuth, firestoreDb } from '../config/firebase';
import Constants from 'expo-constants';

interface TelegramBotModalProps {
  visible: boolean;
  onClose: () => void;
}

export default function TelegramBotModal({ visible, onClose }: TelegramBotModalProps) {
  const [token, setToken] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // You can set the local server IP here if testing on emulator
  // Or use localhost for iOS emulator, 10.0.2.2 for Android emulator
  // However, the backend will use BASE_WEBHOOK_URL to set the webhook to Telegram.
  // Sử dụng biến môi trường EXPO_PUBLIC_API_URL (Production domain)
  const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL;

  const handleConnect = async () => {
    const trimmedToken = token.trim();
    if (!trimmedToken) {
      Alert.alert('Lỗi', 'Vui lòng nhập Bot Token');
      return;
    }

    const user = firebaseAuth().currentUser;
    if (!user) {
      Alert.alert('Lỗi', 'Chưa đăng nhập!');
      return;
    }

    if (!API_BASE_URL) {
      Alert.alert('Lỗi cấu hình', 'Thiếu EXPO_PUBLIC_API_URL trong file .env');
      return;
    }

    setIsLoading(true);

    const url = `${API_BASE_URL}/api/telegram/setup-bot`;
    console.log("Calling URL:", url);

    try {
      // 1. Gửi request đến backend để thiết lập webhook
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          bot_token: trimmedToken,
          firebase_uid: user.uid,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP Error! Status: ${response.status}`);
      }

      const data = await response.json();

      if (data.status === 'ok') {
        Alert.alert('Thành công', 'Đã kết nối Telegram Bot thành công! Hãy gửi tin nhắn cho bot của bạn ngay.');
        onClose();
        setToken('');
      } else {
        Alert.alert('Lỗi từ Server', data.message || 'Không thể thiết lập webhook.');
      }
    } catch (error: any) {
      console.error('Setup bot error:', error);
      // Hiển thị lỗi chi tiết lên màn hình điện thoại
      Alert.alert(
        'Lỗi kết nối mạng', 
        `Nội dung: ${error.message}\n\nĐảm bảo Server đang active và URL trong .env là chính xác.`
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <BlurView
          intensity={40}
          tint="dark"
          style={StyleSheet.absoluteFill}
        >
          <View className="flex-1 justify-center items-center px-4 bg-black/40">
            <View className="w-full max-w-sm">
              <GlassBox padding={24} intensity={80} className="bg-[#1E1E1E]/95">
                {/* Header */}
                <View className="flex-row justify-between items-center mb-6">
                  <View className="flex-row items-center">
                    <Ionicons name="paper-plane" size={24} color="#00B0FF" />
                    <Text className="text-xl font-bold text-white ml-2">Telegram Bot</Text>
                  </View>
                  <TouchableOpacity onPress={onClose} hitSlop={{ top: 10, right: 10, bottom: 10, left: 10 }}>
                    <Ionicons name="close" size={24} color="#A0A0A0" />
                  </TouchableOpacity>
                </View>

                {/* Instructions */}
                <Text className="text-gray-300 text-sm mb-4 leading-5">
                  Nhập mã Token của Telegram Bot cá nhân của bạn. Dữ liệu tài chính sẽ được định tuyến riêng tư vào tài khoản này.
                </Text>

                {/* Input Field */}
                <View className="mb-6">
                  <Text className="text-[10px] font-bold text-gray-500 mb-2 uppercase tracking-wider">Bot Token</Text>
                  <View className="flex-row items-center bg-white/10 rounded-xl border border-white/20 px-3 h-12">
                    <Ionicons name="key-outline" size={18} color="#A0AEC0" />
                    <TextInput
                      className="flex-1 text-base text-white ml-2"
                      placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                      placeholderTextColor="#777777"
                      value={token}
                      onChangeText={setToken}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                </View>

                {/* Action Button */}
                <TouchableOpacity 
                  onPress={handleConnect}
                  disabled={isLoading}
                  activeOpacity={0.8}
                >
                  <View className="bg-primaryGreen h-12 rounded-xl items-center justify-center flex-row">
                    {isLoading ? (
                      <ActivityIndicator color="#FFFFFF" />
                    ) : (
                      <>
                        <Ionicons name="link" size={18} color="#FFFFFF" />
                        <Text className="text-white font-bold text-base ml-2">Kết nối Bot</Text>
                      </>
                    )}
                  </View>
                </TouchableOpacity>

              </GlassBox>
            </View>
          </View>
        </BlurView>
      </KeyboardAvoidingView>
    </Modal>
  );
}
