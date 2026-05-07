import { useState, useEffect, useCallback } from 'react';
import Voice, { SpeechResultsEvent, SpeechErrorEvent } from '@react-native-voice/voice';
import { Platform, PermissionsAndroid } from 'react-native';
import { request, PERMISSIONS, RESULTS } from 'react-native-permissions';

/**
 * Custom Hook cho tính năng Voice-to-Text
 */
export const useVoiceRecognition = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [recognizedText, setRecognizedText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Khởi tạo các listeners
    Voice.onSpeechStart = () => {
      setIsRecording(true);
      setError(null);
    };

    Voice.onSpeechEnd = () => {
      setIsRecording(false);
    };

    Voice.onSpeechError = (e: SpeechErrorEvent) => {
      console.error('Speech Error:', e.error);
      setError(e.error?.message || 'Lỗi nhận diện giọng nói');
      setIsRecording(false);
    };

    Voice.onSpeechResults = (e: SpeechResultsEvent) => {
      if (e.value && e.value.length > 0) {
        setRecognizedText(e.value[0]);
      }
    };

    return () => {
      // Cleanup
      Voice.destroy().then(Voice.removeAllListeners);
    };
  }, []);

  const requestPermission = async () => {
    try {
      if (Platform.OS === 'android') {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: 'Quyền sử dụng Micro',
            message: 'Ứng dụng cần quyền truy cập Micro để nhập liệu bằng giọng nói.',
            buttonNeutral: 'Hỏi lại sau',
            buttonNegative: 'Từ chối',
            buttonPositive: 'Đồng ý',
          }
        );
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } else {
        const res = await request(PERMISSIONS.IOS.MICROPHONE);
        return res === RESULTS.GRANTED;
      }
    } catch (err) {
      console.warn(err);
      return false;
    }
  };

  const startRecording = useCallback(async () => {
    const hasPermission = await requestPermission();
    if (!hasPermission) {
      setError('Không có quyền sử dụng Micro');
      return;
    }

    try {
      setRecognizedText('');
      setError(null);
      await Voice.start('vi-VN');
    } catch (e) {
      console.error('Start Recording Error:', e);
      setError('Không thể khởi động Micro');
    }
  }, []);

  const stopRecording = useCallback(async () => {
    try {
      await Voice.stop();
      setIsRecording(false);
    } catch (e) {
      console.error('Stop Recording Error:', e);
    }
  }, []);

  return {
    isRecording,
    recognizedText,
    error,
    startRecording,
    stopRecording,
  };
};
