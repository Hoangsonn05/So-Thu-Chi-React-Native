/**
 * AI Assistant Service
 * Tương đương với showAiBottomSheet() logic từ HamchinhActivity.java
 * 
 * Quản lý: 
 * - Voice input processing
 * - Prompt generation
 * - Response handling
 * - Transaction auto-submit
 */

import { callGeminiAPI, GeminiAIResponse } from '../utils/gemini-client';
import { Platform } from 'react-native';
import { firebaseAuth } from '../config/firebase';

export interface AIPromptContext {
  userInput: string;
  currentDate: string;
  currentTime: string;
  currentBalance?: number;
  firebaseUid?: string;
  recentTransactions?: Array<{
    amount: number;
    note: string;
    category: string;
    date: string;
    type: 'CHI' | 'THU';
  }>;
}

export interface AIAssistantState {
  isProcessing: boolean;
  lastResponse: GeminiAIResponse | null;
  error: string | null;
  conversationHistory: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
  }>;
}

/**
 * Sinh ra prompt cho Gemini API (tương tự getAiPrompt() từ Java)
 * Prompt này yêu cầu Gemini trả về JSON với cấu trúc cố định
 */
export function generateAIPrompt(context: AIPromptContext): string {
  const recentTransLog =
    context.recentTransactions && context.recentTransactions.length > 0
      ? `\n\nCác giao dịch gần đây:\n${context.recentTransactions
          .slice(0, 5)
          .map(
            (t) =>
              `- ${t.date}: ${t.type === 'THU' ? '+' : '-'}${t.amount} (${t.category}): ${t.note}`
          )
          .join('\n')}`
      : '';

  const basePrompt = `Bạn là trợ lý AI thông minh, thân thiện. 
Hôm nay là ${context.currentDate}.
${context.currentBalance !== undefined ? `Số dư hiện tại: ${context.currentBalance}` : ''}
${recentTransLog}

NHIỆM VỤ:
1. Phân biệt rõ "Trò chuyện" và "Giao dịch".
2. Nếu là Giao dịch: Trả về thông tin chính xác.
3. Nếu là Trò chuyện: Trả về phản hồi tự nhiên, KHÔNG ghi nhận giao dịch.

QUY TẮC PHẢN HỒI (Trường "thong_bao"):
- GIAO DỊCH (BẮT BUỘC dùng mẫu cũ): "✅ Đã ghi nhận [chi/thu] [số tiền] cho [hạng mục] vào lúc ${context.currentTime} ngày ${context.currentDate}."
- TRÒ CHUYỆN: Phản hồi tự nhiên, linh hoạt và thân thiện (Ví dụ: "Chào bạn! Chúc bạn ngày mới tốt lành.").

QUY TẮC DỮ LIỆU (KHÔNG ĐƯỢC THAY ĐỔI):
Phân tích: "${context.userInput}" và trả về JSON:
{
  "so_tien": <số tiền (số) hoặc 0 nếu là chat>,
  "ghi_chu": "<ghi chú hoặc nội dung trò chuyện>",
  "danh_muc": "<danh mục hoặc 'Trò chuyện'>",
  "ngay": "<dd/MM/yyyy>",
  "auto_submit": <true nếu là giao dịch rõ ràng, false nếu là chat>,
  "thong_bao": "<theo quy tắc phản hồi ở trên>",
  "action_type": "<'CHI', 'THU' hoặc 'CHAT'>"
}

LƯU Ý: Nếu là CHAT, tuyệt đối đặt so_tien = 0 và auto_submit = false.`;

  return basePrompt;
}

/**
 * Xử lý AI response và chuẩn bị data cho transaction
 */
export function parseAIResponse(response: GeminiAIResponse) {
  return {
    amount: response.so_tien,
    note: response.ghi_chu,
    category: response.danh_muc,
    date: response.ngay,
    shouldAutoSubmit: response.auto_submit,
    message: response.thong_bao,
    type: response.action_type === 'THU' ? 1 : 0, // 0: Expense, 1: Income
    transactionId: response.transaction_id || null,
    backendSaved: Boolean(response.transaction_id),
  };
}

/**
 * Main service class
 */
export class AIAssistantService {
  private state: AIAssistantState = {
    isProcessing: false,
    lastResponse: null,
    error: null,
    conversationHistory: [],
  };

  /**
   * Gọi AI với user input
   */
  async processUserInput(
    userInput: string,
    context: Omit<AIPromptContext, 'userInput' | 'currentTime'>
  ): Promise<GeminiAIResponse> {
    this.state.isProcessing = true;
    this.state.error = null;

    const currentTime = new Date().toLocaleTimeString('vi-VN', {
      hour: '2-digit',
      minute: '2-digit',
    });

    try {
      const firebaseUid = context.firebaseUid || firebaseAuth().currentUser?.uid;
      const response = await callGeminiAPI(userInput, {
        firebaseUid,
        mode: 'auto',
      });

      this.state.lastResponse = response;
      this.state.isProcessing = false;

      // Lưu vào conversation history
      this.state.conversationHistory.push({
        role: 'user',
        content: userInput,
        timestamp: Date.now(),
      });

      this.state.conversationHistory.push({
        role: 'assistant',
        content: response.thong_bao,
        timestamp: Date.now(),
      });

      return response;
    } catch (error) {
      this.state.isProcessing = false;
      const errorMessage =
        error instanceof Error ? error.message : 'Lỗi không xác định';
      this.state.error = errorMessage;
      throw error;
    }
  }

  /**
   * Lấy state hiện tại
   */
  getState(): AIAssistantState {
    return this.state;
  }

  /**
   * Reset state
   */
  reset(): void {
    this.state = {
      isProcessing: false,
      lastResponse: null,
      error: null,
      conversationHistory: [],
    };
  }

  /**
   * Lấy conversation history
   */
  getConversationHistory() {
    return this.state.conversationHistory;
  }

  /**
   * Clear conversation history
   */
  clearHistory(): void {
    this.state.conversationHistory = [];
  }
}

// Singleton instance
export const aiAssistantService = new AIAssistantService();
