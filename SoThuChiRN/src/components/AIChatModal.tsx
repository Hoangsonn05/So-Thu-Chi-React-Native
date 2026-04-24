/**
 * AI Chat Modal Component (Expanded State)
 * 
 * - Popup lớn với chat history
 * - Input field cho text
 * - Voice button (microphone)
 * - Animated smooth expand/collapse
 * - Suggestion chips
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  ScrollView,
  Pressable,
  Animated,
  StyleSheet,
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  Modal,
  Dimensions,
  PanResponder,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import {
  aiAssistantService,
  parseAIResponse,
} from '../services/AIAssistantService';
import { AI_CONFIG } from '../config/AIConfig';

interface AIChatModalProps {
  isVisible: boolean;
  onClose?: () => void;
  onTransactionDetected?: (data: any) => void;
  currentDate: string;
  currentBalance?: number;
}

const AIChatModal: React.FC<AIChatModalProps> = ({
  isVisible,
  onClose,
  onTransactionDetected,
  currentDate,
  currentBalance,
}) => {
  const { height: SCREEN_HEIGHT } = Dimensions.get('window');
  const FULL_HEIGHT = SCREEN_HEIGHT * 0.95;
  const PARTIAL_HEIGHT = SCREEN_HEIGHT * 0.6;
  const PARTIAL_TRANSLATE_Y = FULL_HEIGHT - PARTIAL_HEIGHT;

  const [input, setInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [messages, setMessages] = useState<
    Array<{
      role: 'user' | 'assistant';
      content: string;
      data?: any;
      timestamp: number;
    }>
  >([]);
  const [isListening, setIsListening] = useState(false);
  const scrollViewRef = useRef<ScrollView>(null);
  const inputRef = useRef<TextInput>(null);
  const sheetY = useRef(new Animated.Value(SCREEN_HEIGHT)).current; // Unified vertical position
  const [isExpanded, setIsExpanded] = useState(false);
  const isExpandedRef = useRef(false);

  const setExpandedState = (expanded: boolean) => {
    isExpandedRef.current = expanded;
    setIsExpanded(expanded);
  };

  const animateSheet = (toValue: number, expanded: boolean) => {
    setExpandedState(expanded);
    Animated.spring(sheetY, {
      toValue,
      useNativeDriver: true,
      friction: 8,
      tension: 40,
    }).start();
  };

  const suggestionChips = AI_CONFIG.SUGGESTION_CHIPS;

  // Open/close lifecycle
  useEffect(() => {
    if (isVisible) {
      // Open at full height immediately as requested
      animateSheet(0, true);
      
      // Auto-focus input after a short delay for smooth animation
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 400);
      return () => clearTimeout(timer);
    }

    setExpandedState(false);
    Animated.timing(sheetY, {
      toValue: SCREEN_HEIGHT,
      duration: 300,
      useNativeDriver: true,
    }).start();
  }, [isVisible, PARTIAL_TRANSLATE_Y, SCREEN_HEIGHT, sheetY]);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (evt, gestureState) => {
        return Math.abs(gestureState.dy) > 5;
      },
      onPanResponderGrant: () => {
        sheetY.stopAnimation();
      },
      onPanResponderMove: (evt, gestureState) => {
        const startY = isExpandedRef.current ? 0 : PARTIAL_TRANSLATE_Y;
        let newY = startY + gestureState.dy;

        // Kháng cự khi kéo quá giới hạn trên (FULL_HEIGHT)
        if (newY < 0) newY = newY * 0.3;
        if (newY > SCREEN_HEIGHT) newY = SCREEN_HEIGHT;

        sheetY.setValue(newY);
      },
      onPanResponderRelease: (evt, gestureState) => {
        sheetY.stopAnimation((currentY) => {
          const upwardEnough = gestureState.dy < -35 || currentY < PARTIAL_TRANSLATE_Y * 0.5;
          const closeEnough = gestureState.dy > 140 || currentY > PARTIAL_TRANSLATE_Y + 160;

          if (upwardEnough) {
            animateSheet(0, true);
            return;
          }

          if (closeEnough) {
            handleClose();
            return;
          }

          const snapTo = currentY < PARTIAL_TRANSLATE_Y / 2 ? 0 : PARTIAL_TRANSLATE_Y;
          animateSheet(snapTo, snapTo === 0);
        });
      },
    })
  ).current;

  // Auto-scroll to bottom
  useEffect(() => {
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, [messages]);

  const handleSubmit = async () => {
    if (!input.trim() || isProcessing) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: userMessage,
        timestamp: Date.now(),
      },
    ]);

    setIsProcessing(true);

    try {
      const response = await aiAssistantService.processUserInput(userMessage, {
        currentDate,
        currentBalance,
      });

      const parsedData = parseAIResponse(response);

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.thong_bao || 'Đã xử lý yêu cầu',
          data: parsedData,
          timestamp: Date.now(),
        },
      ]);

      // Notify parent for persistence flow (local DB + Firebase)
      if (
        onTransactionDetected &&
        parsedData.amount > 0 &&
        String(parsedData.category || '').trim().length > 0
      ) {
        await Promise.resolve(onTransactionDetected(parsedData));
      }
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : 'Lỗi không xác định';
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ Lỗi: ${errorMsg}. Vui lòng thử lại.`,
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleChipPress = (chipText: string) => {
    // Remove emoji from chip
    const cleanText = chipText.replace(/^[^\p{L}\p{N}]+/u, '').trim();
    setInput(cleanText);
  };

  const handleVoicePress = async () => {
    setIsListening(true);
    try {
      // Note: Voice transcription requires Speech Recognition API
      // In a real app, integrate react-native-speech-recognizer or similar
      // For now, this is a placeholder
      alert('Voice input feature requires platform-specific setup');
    } catch (error) {
      console.error('Voice input error:', error);
    } finally {
      setIsListening(false);
    }
  };

  const handleClose = () => {
    Keyboard.dismiss();
    setExpandedState(false);
    onClose?.();
  };

  const opacity = sheetY.interpolate({
    inputRange: [0, PARTIAL_TRANSLATE_Y, SCREEN_HEIGHT],
    outputRange: [1, 1, 0],
    extrapolate: 'clamp',
  });

  return (
    <Modal
      visible={isVisible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
    >
      {/* Overlay */}
      <Animated.View
        style={[
          styles.overlay,
          {
            opacity,
            pointerEvents: isVisible ? 'auto' : 'none',
          },
        ]}
      >
        <Pressable
          style={styles.overlayTouchable}
          onPress={handleClose}
          pointerEvents="auto"
        />
      </Animated.View>

      {/* Modal Container */}
      <Animated.View
        style={[
          styles.modalContainer,
          {
            height: FULL_HEIGHT,
            transform: [{ translateY: sheetY }],
          },
        ]}
        pointerEvents={isVisible ? 'auto' : 'none'}
      >
        <SafeAreaView style={styles.safeArea}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.container}
            keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}
          >
            {/* Drag Handle */}
            <View {...panResponder.panHandlers} style={styles.dragHandleContainer}>
              <View style={styles.dragHandle} />
            </View>

            {/* Header */}
            <View style={styles.header} {...panResponder.panHandlers}>
              <View style={styles.headerContent}>
                <View style={styles.headerTitle}>
                  <MaterialIcons
                    name="auto-awesome"
                    size={24}
                    color="#7C4DFF"
                  />
                  <Text style={styles.headerTitleText}>Trợ Lý AI</Text>
                </View>
                {isExpanded && (
                  <Text style={styles.headerSubtitle}>
                    Tự động ghi chép chi tiêu của bạn
                  </Text>
                )}
              </View>

              <Pressable
                style={styles.closeButton}
                onPress={handleClose}
                hitSlop={8}
              >
                <MaterialIcons name="close" size={24} color="#1D1D1F" />
              </Pressable>
            </View>

            {/* Messages Area */}
            <ScrollView
              ref={scrollViewRef}
              style={styles.messagesContainer}
              contentContainerStyle={styles.messagesContent}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              {messages.length === 0 ? (
                <View style={styles.emptyState}>
                  <MaterialIcons
                    name="auto-awesome"
                    size={48}
                    color="#7C4DFF"
                  />
                  <Text style={styles.emptyStateText}>
                    Kể cho tôi về chi tiêu của bạn
                  </Text>
                  <Text style={styles.emptyStateSubtext}>
                    Ví dụ: "Sáng nay ăn phở 45k" hoặc "Lương tháng 10 triệu"
                  </Text>
                </View>
              ) : (
                messages.map((msg, idx) => (
                  <View
                    key={idx}
                    style={[
                      styles.messageRow,
                      msg.role === 'user'
                        ? styles.messageRowUser
                        : styles.messageRowAssistant,
                    ]}
                  >
                    {msg.role === 'assistant' && (
                      <View style={styles.avatarAssistant}>
                        <MaterialIcons
                          name="auto-awesome"
                          size={16}
                          color="#FFF"
                        />
                      </View>
                    )}

                    <View
                      style={
                        msg.role === 'user'
                          ? styles.messageBubbleUser
                          : styles.messageBubbleAssistant
                      }
                    >
                      <Text
                        style={
                          msg.role === 'user'
                            ? styles.messageBubbleTextUser
                            : styles.messageBubbleTextAssistant
                        }
                      >
                        {msg.content}
                      </Text>

                      {msg.data && (
                        <View style={styles.dataPreview}>
                          <View style={styles.dataRow}>
                            <Text style={styles.dataTextMain}>
                              {msg.data.type === 0 ? '💸 Chi' : '💰 Thu'} {msg.data.amount.toLocaleString('vi-VN')}₫
                            </Text>
                            {msg.data.category && (
                              <View style={styles.categoryTag}>
                                <Text style={styles.categoryTagText}>{msg.data.category}</Text>
                              </View>
                            )}
                          </View>
                          {msg.data.note && (
                            <Text style={styles.dataNote} numberOfLines={1}>
                              📝 {msg.data.note}
                            </Text>
                          )}
                        </View>
                      )}
                    </View>
                  </View>
                ))
              )}

              {isProcessing && (
                <View style={styles.loadingContainer}>
                  <ActivityIndicator color="#7C4DFF" />
                  <Text style={styles.loadingText}>✨ Chờ tớ chút nha ✨</Text>
                </View>
              )}
            </ScrollView>

            {/* Suggestion Chips */}
            {messages.length === 0 && (
              <ScrollView
                style={styles.chipsContainer}
                horizontal
                keyboardShouldPersistTaps="handled"
                showsHorizontalScrollIndicator={false}
              >
                {suggestionChips.map((chip, idx) => (
                  <Pressable
                    key={idx}
                    style={styles.chip}
                    onPress={() => handleChipPress(chip)}
                    android_ripple={{ color: 'rgba(124, 77, 255, 0.1)' }}
                  >
                    <Text style={styles.chipText}>{chip}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            )}

            {/* Input Area */}
            <View style={styles.inputArea}>
              <View style={styles.inputContainer}>
                <TextInput
                  ref={inputRef}
                  style={styles.textInput}
                  placeholder="Nhập nội dung chi tiêu..."
                  placeholderTextColor="#A1A1A6"
                  value={input}
                  onChangeText={setInput}
                  multiline
                  maxLength={500}
                  editable={!isProcessing}
                />
                
                <Pressable
                  style={[
                    styles.voiceButton,
                    isListening && styles.voiceButtonActive,
                  ]}
                  onPress={handleVoicePress}
                  disabled={isProcessing}
                  hitSlop={8}
                >
                  <MaterialIcons
                    name={isListening ? 'mic' : 'mic-none'}
                    size={22}
                    color={isListening ? '#FF3B30' : '#7C4DFF'}
                  />
                </Pressable>
              </View>

              <Pressable
                style={[
                  styles.sendButton,
                  (!input.trim() || isProcessing) && styles.sendButtonDisabled,
                ]}
                onPress={handleSubmit}
                disabled={!input.trim() || isProcessing}
                hitSlop={8}
              >
                {isProcessing ? (
                  <ActivityIndicator color="#FFF" size="small" />
                ) : (
                  <MaterialIcons name="send" size={22} color="#FFF" />
                )}
              </Pressable>
            </View>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Animated.View>
    </Modal>
  );
};

export default AIChatModal;

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },

  overlayTouchable: {
    flex: 1,
  },

  modalContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#F5F7FA',
    borderTopLeftRadius: 32,
    borderTopRightRadius: 32,
    elevation: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -6 },
    shadowOpacity: 0.3,
    shadowRadius: 15,
    overflow: 'hidden',
  },

  safeArea: {
    flex: 1,
  },

  dragHandleContainer: {
    width: '100%',
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },

  dragHandle: {
    width: 40,
    height: 5,
    borderRadius: 3,
    backgroundColor: '#E1E1E1',
  },

  container: {
    flex: 1,
    justifyContent: 'space-between',
  },

  header: {
    paddingHorizontal: 20,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#E8E8ED',
  },

  headerContent: {
    flex: 1,
  },

  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 4,
  },

  headerTitleText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1D1D1F',
    marginLeft: 8,
  },

  headerSubtitle: {
    fontSize: 13,
    color: '#86868B',
  },

  closeButton: {
    padding: 8,
    marginLeft: 16,
  },

  messagesContainer: {
    flex: 1,
  },

  messagesContent: {
    paddingHorizontal: 16,
    paddingVertical: 12,
  },

  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 20,
  },

  emptyStateText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1D1D1F',
    marginTop: 16,
  },

  emptyStateSubtext: {
    fontSize: 13,
    color: '#86868B',
    marginTop: 8,
    textAlign: 'center',
  },

  messageRow: {
    flexDirection: 'row',
    marginVertical: 8,
    alignItems: 'flex-end',
  },

  messageRowUser: {
    justifyContent: 'flex-end',
  },

  messageRowAssistant: {
    justifyContent: 'flex-start',
  },

  avatarAssistant: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#7C4DFF',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },

  messageBubbleUser: {
    maxWidth: '85%',
    backgroundColor: '#7C4DFF',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderBottomRightRadius: 4,
    // Fix text cut off
    alignSelf: 'flex-end',
  },

  messageBubbleAssistant: {
    maxWidth: '85%',
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: '#E8E8ED',
  },

  messageBubbleTextUser: {
    fontSize: 14,
    color: '#FFFFFF',
  },

  messageBubbleTextAssistant: {
    fontSize: 14,
    color: '#1D1D1F',
  },

  dataPreview: {
    marginTop: 6,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(124, 77, 255, 0.1)',
  },
  dataRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 6,
  },
  dataTextMain: {
    fontSize: 13,
    color: '#7C4DFF',
    fontWeight: 'bold',
  },
  categoryTag: {
    backgroundColor: 'rgba(124, 77, 255, 0.1)',
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
  },
  categoryTagText: {
    fontSize: 10,
    color: '#7C4DFF',
    fontWeight: '600',
  },
  dataNote: {
    fontSize: 11,
    color: '#86868B',
    marginTop: 2,
    fontStyle: 'italic',
  },

  chipsContainer: {
    paddingHorizontal: 16,
    paddingVertical: 2,
    maxHeight: 32,
  },
 
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 2,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#E8E8ED',
    height: 24,
    justifyContent: 'center',
  },

  chipText: {
    fontSize: 11,
    lineHeight: 13,
    color: '#1D1D1F',
    fontWeight: '500',
    includeFontPadding: false,
    textAlignVertical: 'center',
  },

  loadingContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 20,
  },

  loadingText: {
    marginTop: 8,
    fontSize: 13,
    color: '#86868B',
    fontWeight: '500',
  },

  inputArea: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: Platform.OS === 'ios' ? 24 : 16,
    alignItems: 'flex-end',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderTopWidth: 1,
    borderTopColor: '#F0F0F5',
  },

  inputContainer: {
    flex: 1,
    flexDirection: 'row',
    backgroundColor: '#F5F7FA',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#E8E8ED',
    alignItems: 'flex-end',
    paddingRight: 4,
  },

  textInput: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 15,
    color: '#1D1D1F',
  },

  voiceButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 4,
  },

  voiceButtonActive: {
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
  },

  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#7C4DFF',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 3,
    shadowColor: '#7C4DFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
  },

  sendButtonDisabled: {
    backgroundColor: '#E1E1E6',
    shadowOpacity: 0,
    elevation: 0,
  },
});
