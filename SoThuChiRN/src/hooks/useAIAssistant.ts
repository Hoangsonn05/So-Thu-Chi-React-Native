/**
 * useAIAssistant Hook
 * 
 * Tập hợp logic quản lý AI features
 * - State management
 * - Message handling
 * - Voice input placeholder
 * - Transaction detection
 */

import { useState, useCallback } from 'react';
import {
  aiAssistantService,
  AIPromptContext,
  parseAIResponse,
} from '../services/AIAssistantService';
import { GeminiAIResponse } from '../utils/gemini-client';

export interface TransactionFromAI {
  amount: number;
  note: string;
  category: string;
  date: string;
  type: 0 | 1; // 0: Expense, 1: Income
  shouldAutoSubmit: boolean;
  message: string;
  transactionId?: string | null;
  backendSaved?: boolean;
}

interface UseAIAssistantReturn {
  isProcessing: boolean;
  error: string | null;
  lastResponse: GeminiAIResponse | null;
  messages: Array<any>;
  processInput: (
    input: string,
    context: Omit<AIPromptContext, 'userInput'>
  ) => Promise<TransactionFromAI | null>;
  resetState: () => void;
  clearHistory: () => void;
  getHistory: () => Array<any>;
}

export function useAIAssistant(): UseAIAssistantReturn {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<GeminiAIResponse | null>(null);

  const processInput = useCallback(
    async (
      input: string,
      context: Omit<AIPromptContext, 'userInput'>
    ): Promise<TransactionFromAI | null> => {
      setIsProcessing(true);
      setError(null);

      try {
        const response = await aiAssistantService.processUserInput(input, context);

        setLastResponse(response);

        const parsed = parseAIResponse(response);

        return {
          amount: parsed.amount,
          note: parsed.note,
          category: parsed.category,
          date: parsed.date,
          type: parsed.type as 0 | 1,
          shouldAutoSubmit: parsed.shouldAutoSubmit,
          message: parsed.message,
          transactionId: parsed.transactionId,
          backendSaved: parsed.backendSaved,
        };
      } catch (err) {
        const errorMsg =
          err instanceof Error ? err.message : 'Unknown error';
        setError(errorMsg);
        throw err;
      } finally {
        setIsProcessing(false);
      }
    },
    []
  );

  const resetState = useCallback(() => {
    aiAssistantService.reset();
    setIsProcessing(false);
    setError(null);
    setLastResponse(null);
  }, []);

  const clearHistory = useCallback(() => {
    aiAssistantService.clearHistory();
  }, []);

  const getHistory = useCallback(() => {
    return aiAssistantService.getConversationHistory();
  }, []);

  return {
    isProcessing,
    error,
    lastResponse,
    messages: aiAssistantService.getConversationHistory(),
    processInput,
    resetState,
    clearHistory,
    getHistory,
  };
}
